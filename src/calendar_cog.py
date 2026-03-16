import re
import random
import shutil
from pathlib import Path

from discord.ext import commands

from config import (
    DATA_FILE, QUOTES_FILE, EVENTS_FILE,
    CALENDARS_DIR, ACTIVE_CAMPAIGN_FILE,
    WEEKDAYS, MONTH_NAMES, MONTH_LENGTHS, COMMAND_IMAGE_URL,
)
from utils import make_embed, json_safe_read, json_safe_write, format_date_us, weekday_rollover, _norm

# ---------------------------------------------------------------------------
# Campaign helpers (one active campaign globally; no campaign = legacy root files)
# ---------------------------------------------------------------------------

DEFAULT_STATE = {"year": 1, "month": 1, "day": 1, "weekday": None, "start_year": 1, "start_month": 1, "start_day": 1}


def campaign_slug(name: str) -> str:
    """Turn 'Campaign Name' into a folder-safe slug: lowercase, spaces to hyphens."""
    if not name or not str(name).strip():
        return "default"
    s = str(name).strip().lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return s or "default"


def get_active_slug() -> str | None:
    """Return the active campaign slug, or None for legacy (root game_state/events)."""
    try:
        data = json_safe_read(ACTIVE_CAMPAIGN_FILE, None)
        if isinstance(data, dict) and data.get("slug"):
            return str(data["slug"]).strip()
        if isinstance(data, str) and data.strip():
            return data.strip()
    except Exception:
        pass
    return None


def set_active_slug(slug: str | None) -> None:
    """Set the global active campaign. None = legacy (use root game_state/events)."""
    if slug:
        ACTIVE_CAMPAIGN_FILE.parent.mkdir(parents=True, exist_ok=True)
        json_safe_write(ACTIVE_CAMPAIGN_FILE, {"slug": slug})
    elif ACTIVE_CAMPAIGN_FILE.exists():
        ACTIVE_CAMPAIGN_FILE.unlink()


def get_data_paths() -> tuple[Path, Path]:
    """Return (state_path, events_path) for the current context (active campaign or legacy)."""
    slug = get_active_slug()
    if slug:
        d = CALENDARS_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        return (d / "game_state.json", d / "events.json")
    return (DATA_FILE, EVENTS_FILE)


def load_state() -> dict:
    state_path, _ = get_data_paths()
    state = json_safe_read(state_path, DEFAULT_STATE.copy())
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, v)
    state.setdefault("start_year", state["year"])
    state.setdefault("start_month", state["month"])
    state.setdefault("start_day", state["day"])
    return state


def load_events() -> dict:
    _, events_path = get_data_paths()
    return json_safe_read(events_path, {})


def save_state(state: dict) -> None:
    state_path, _ = get_data_paths()
    json_safe_write(state_path, state)


def save_events(events: dict) -> None:
    _, events_path = get_data_paths()
    json_safe_write(events_path, events)


def rollover_date(state: dict, days: int) -> None:
    state["day"] += days
    while True:
        idx = state["month"] - 1
        if state["day"] > MONTH_LENGTHS[idx]:
            state["day"] -= MONTH_LENGTHS[idx]
            state["month"] += 1
            if state["month"] > 12:
                state["month"] = 1
                state["year"] += 1
        else:
            break
    while state["day"] < 1:
        state["month"] -= 1
        if state["month"] < 1:
            state["month"] = 12
            state["year"] -= 1
        prev_idx = state["month"] - 1
        state["day"] += MONTH_LENGTHS[prev_idx]
    if state.get("weekday") is not None:
        state["weekday"] = weekday_rollover(state["weekday"], days)


# Quotes stay global (one file for the bot)
quotes = json_safe_read(QUOTES_FILE, [])


class CalendarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="date")
    async def show_date(self, ctx, *, tail: str = ""):
        """
        Show or adjust the in-game date. One global active campaign; no campaign = legacy calendar.
          !date / !date +N / !date -N   → show or move days
          !date -help                    → list all date & campaign commands
          !date -setCampaign "Name"      → set active campaign (create if needed)
          !date -listCampaigns           → list all campaigns (marks active)
          !date -transferToCampaign "Name" → copy current date/events into that campaign, set active
          !date -renameCampaign "Old" "New" → rename a campaign
        """
        tail = (tail or "").strip()

        # -------- -help --------
        if _norm(tail) == "-help":
            lines = [
                "**!date** — show current in-game date (or use campaign commands below).",
                "**!date +N** / **!date -N** — move the date by N days.",
                "",
                "**Campaigns** (one active campaign globally):",
                "• **!date -setCampaign \"Name\"** — set active campaign (create if needed).",
                "• **!date -listCampaigns** — list all campaigns; marks the active one.",
                "• **!date -transferToCampaign \"Name\"** — copy current date & events into that campaign, set active.",
                "• **!date -renameCampaign \"Old\" \"New\"** — rename a campaign folder (and active if applicable).",
                "",
                "**Other date commands:**",
                "• **!startdate** — show campaign start date.",
                "• **!setdate MM/DD/YYYY** — set date absolutely.",
                "• **!setweekday Monday** (or **none** to clear).",
                "• **!addevent** / **!listevents** / **!removeevent** — events on the calendar.",
            ]
            embed = make_embed("📅 Date & campaign commands", "\n".join(lines), thumbnail_url=COMMAND_IMAGE_URL)
            return await ctx.send(embed=embed)

        # -------- -listCampaigns --------
        if tail.lower().strip() == "-listcampaigns":
            CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
            active = get_active_slug()
            campaigns = sorted(
                p.name for p in CALENDARS_DIR.iterdir()
                if p.is_dir() and not p.name.startswith("_")
            )
            if not campaigns:
                return await ctx.send("No campaigns yet. Use `!date -setCampaign \"Name\"` to create one.")
            lines = [
                f"• **{s}** (active)" if s == active else f"• {s}"
                for s in campaigns
            ]
            if not active:
                lines.insert(0, "*(Currently using legacy calendar — no campaign set.)*")
            embed = make_embed("📋 Campaigns", "\n".join(lines), thumbnail_url=COMMAND_IMAGE_URL)
            return await ctx.send(embed=embed)

        # -------- -setCampaign "Campaign Name" --------
        if tail.lower().startswith("-setcampaign"):
            rest = tail[len("-setcampaign"):].strip().strip('"\'')
            if not rest:
                return await ctx.send("Usage: `!date -setCampaign \"Campaign Name\"`")
            slug = campaign_slug(rest)
            CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
            campaign_dir = CALENDARS_DIR / slug
            campaign_dir.mkdir(parents=True, exist_ok=True)
            state_path, events_path = campaign_dir / "game_state.json", campaign_dir / "events.json"
            if not state_path.exists():
                json_safe_write(state_path, DEFAULT_STATE.copy())
            if not events_path.exists():
                json_safe_write(events_path, {})
            set_active_slug(slug)
            return await ctx.send(f"✅ Active campaign set to **{rest}** (slug: `{slug}`). All date/events now use this campaign.")

        # -------- -transferToCampaign "Campaign Name" --------
        if tail.lower().startswith("-transfertocampaign"):
            rest = tail[len("-transfertocampaign"):].strip().strip('"\'')
            if not rest:
                return await ctx.send("Usage: `!date -transferToCampaign \"Campaign Name\"`")
            slug = campaign_slug(rest)
            CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
            campaign_dir = CALENDARS_DIR / slug
            campaign_dir.mkdir(parents=True, exist_ok=True)
            state_path = campaign_dir / "game_state.json"
            events_path = campaign_dir / "events.json"
            # Source: current (active campaign or legacy)
            src_state = load_state()
            src_events = load_events()
            json_safe_write(state_path, src_state)
            json_safe_write(events_path, src_events)
            set_active_slug(slug)
            return await ctx.send(f"✅ Current date and events copied into campaign **{rest}** (slug: `{slug}`). Active campaign is now **{rest}**.")

        # -------- -renameCampaign "Old Name" "New Name" --------
        if tail.lower().startswith("-renamecampaign"):
            rest = tail[len("-renamecampaign"):].strip()
            parts = re.findall(r'"([^"]*)"', rest)
            if len(parts) < 2:
                return await ctx.send('Usage: `!date -renameCampaign "Old Name" "New Name"` (both names in quotes).')
            old_name, new_name = parts[0].strip(), parts[1].strip()
            if not old_name or not new_name:
                return await ctx.send("Both old and new campaign names must be non-empty.")
            slug_old = campaign_slug(old_name)
            slug_new = campaign_slug(new_name)
            if slug_old == slug_new:
                return await ctx.send("Old and new names produce the same slug; no change.")
            old_dir = CALENDARS_DIR / slug_old
            new_dir = CALENDARS_DIR / slug_new
            if not old_dir.is_dir():
                return await ctx.send(f"No campaign found for **{old_name}** (slug: `{slug_old}`).")
            if new_dir.exists():
                return await ctx.send(f"A campaign already exists for **{new_name}** (slug: `{slug_new}`). Choose a different new name.")
            shutil.move(str(old_dir), str(new_dir))
            if get_active_slug() == slug_old:
                set_active_slug(slug_new)
            return await ctx.send(f"✅ Campaign renamed from **{old_name}** to **{new_name}** (slug: `{slug_new}`).")

        # -------- Normal: show date or adjust by offset --------
        state = load_state()
        if tail:
            try:
                days = int(tail)
            except ValueError:
                return await ctx.send("🚫 Invalid offset. Use `!date +N` or `!date -N`, or `!date -setCampaign \"Name\"`.")
            rollover_date(state, days)
            save_state(state)
            subtitle = f"🗓 Date Adjusted by {days:+d} Day(s)"
        else:
            subtitle = "📜 Current In-Game Date"

        date_line = format_date_us(state["year"], state["month"], state["day"], state.get("weekday"))
        active = get_active_slug()
        if active:
            campaign_title = active.replace("-", " ").title()
            embed = make_embed(campaign_title, f"{date_line}\n{subtitle}", thumbnail_url=COMMAND_IMAGE_URL)
        else:
            embed = make_embed(date_line, subtitle, thumbnail_url=COMMAND_IMAGE_URL)
        if quotes:
            embed.add_field(name="💬 Quote of the Day", value=random.choice(quotes), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="startdate")
    async def show_startdate(self, ctx):
        state = load_state()
        date_line = format_date_us(state["start_year"], state["start_month"], state["start_day"], state.get("weekday"))
        active = get_active_slug()
        if active:
            campaign_title = active.replace("-", " ").title()
            embed = make_embed(campaign_title, f"{date_line}\n🎬 Campaign Start Date", thumbnail_url=COMMAND_IMAGE_URL)
        else:
            embed = make_embed(date_line, "🎬 Campaign Start Date", thumbnail_url=COMMAND_IMAGE_URL)
        if quotes:
            embed.add_field(name="💬 Quote of the Day", value=random.choice(quotes), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="addevent")
    async def add_event(self, ctx, *, description: str):
        state = load_state()
        events = load_events()
        key = f"{state['year']:04}-{state['month']:02}-{state['day']:02}"
        events.setdefault(key, []).append(description)
        save_events(events)
        date_str = format_date_us(state["year"], state["month"], state["day"])
        embed = make_embed(f"On {date_str}, {description}.", None, thumbnail_url=COMMAND_IMAGE_URL)
        await ctx.send(embed=embed)

    @commands.command(name="listevents")
    async def list_events(self, ctx):
        events = load_events()
        if not events:
            return await ctx.send(embed=make_embed("No events recorded yet.", None, thumbnail_url=COMMAND_IMAGE_URL))
        embed = make_embed("📖 All Recorded Events", None, thumbnail_url=COMMAND_IMAGE_URL)
        for date_key, ev_list in events.items():
            y, m, d = map(int, date_key.split("-"))
            date_str = format_date_us(y, m, d)
            lines = [f"{i+1}. {ev}" for i, ev in enumerate(ev_list)]
            embed.add_field(name=date_str, value="\n".join(lines) or "—", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="removeevent")
    async def remove_event(self, ctx, index: int):
        state = load_state()
        events = load_events()
        key = f"{state['year']:04}-{state['month']:02}-{state['day']:02}"
        day_events = events.get(key, [])
        if index < 1 or index > len(day_events):
            return await ctx.send(embed=make_embed("Invalid event number for today.", None, thumbnail_url=COMMAND_IMAGE_URL))
        removed = day_events.pop(index - 1)
        if day_events:
            events[key] = day_events
        else:
            events.pop(key, None)
        save_events(events)
        date_str = format_date_us(state["year"], state["month"], state["day"])
        await ctx.send(embed=make_embed(f"Removed event: On {date_str}, {removed}.", None, thumbnail_url=COMMAND_IMAGE_URL))

    @commands.command(name="setdate")
    async def set_date_cmd(self, ctx, *parts):
        """
        Set the in-game date absolutely (US order).
          !setdate MM/DD/YYYY
          !setdate MM-DD-YYYY
          !setdate MM DD YYYY
        """
        if not parts:
            return await ctx.send("Usage: `!setdate MM/DD/YYYY`")
        joined = " ".join(parts).strip().replace(".", "/").replace("-", "/")
        if not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", joined):
            return await ctx.send("Usage: `!setdate MM/DD/YYYY`")
        m, d, y = map(int, joined.split("/"))
        if not (1 <= m <= 12):
            return await ctx.send("🚫 Month must be 1–12.")
        max_day = MONTH_LENGTHS[m - 1]
        if not (1 <= d <= max_day):
            return await ctx.send(f"🚫 Day must be 1–{max_day} for month {m}.")
        state = load_state()
        state["year"], state["month"], state["day"] = y, m, d
        save_state(state)
        display = format_date_us(state["year"], state["month"], state["day"], state.get("weekday"))
        await ctx.send(embed=make_embed(display, "✅ Date set", thumbnail_url=COMMAND_IMAGE_URL))

    @commands.command(name="setweekday")
    async def set_weekday_cmd(self, ctx, *, weekday: str = None):
        """
        Set or clear the in-game weekday.
          !setweekday Monday
          !setweekday mon
          !setweekday none   ← clears weekday (no rotation on !date +/-)
        """
        if not weekday:
            return await ctx.send("Usage: `!setweekday <Monday|Tuesday|...>` or `!setweekday none`")

        w = weekday.strip().lower()
        if w in {"none", "null", "reset", "unset"}:
            state = load_state()
            state["weekday"] = None
            save_state(state)
            return await ctx.send(embed=make_embed("Weekday cleared", "Future `!date +/-` will not show/rotate weekday.", COMMAND_IMAGE_URL))

        match = next((wd for wd in WEEKDAYS if wd.lower().startswith(w)), None)
        if not match:
            allowed = ", ".join(WEEKDAYS)
            return await ctx.send(f"🚫 Unknown weekday. Use one of: {allowed}, or `none` to clear.")

        state = load_state()
        state["weekday"] = match
        save_state(state)
        display = format_date_us(state["year"], state["month"], state["day"], state["weekday"])
        await ctx.send(embed=make_embed(display, f"✅ Weekday set to {match}", COMMAND_IMAGE_URL))


async def setup(bot):
    await bot.add_cog(CalendarCog(bot))
