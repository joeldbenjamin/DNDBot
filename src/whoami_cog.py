# whoami_cog.py
from __future__ import annotations
from typing import Dict, Any, Optional, List
import re

from discord.ext import commands

from config import COMMAND_IMAGE_URL
from utils import make_embed, json_safe_read
from dc import dc_links, meta_path, dc_extract_id, save_dc_links


def _sheet_path_for(cid: str):
    return meta_path(cid).with_name("characterSheet.json")


def _class_names_only(classes_text: Optional[str]) -> str:
    """
    Turn 'Ranger 3 / Rogue 2' into 'Ranger / Rogue'.
    """
    if not classes_text:
        return "—"
    parts: List[str] = []
    for chunk in str(classes_text).split("/"):
        name = chunk.strip()
        # strip trailing level numbers
        name = re.sub(r"\s*\d+\s*$", "", name)
        parts.append(name.strip() or "?")
    return " / ".join(parts)


def _plus(n: Optional[int]) -> str:
    if n is None:
        return "—"
    try:
        n = int(n)
    except Exception:
        return "—"
    return f"{n:+d}" if n >= 0 else f"{n}"


def _abilities_line(abilities: Dict[str, Dict[str, Any]]) -> str:
    order = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    chunks: List[str] = []
    for ab in order:
        node = abilities.get(ab) or {}
        sc = node.get("score")
        md = node.get("mod")
        sc_txt = str(sc) if sc is not None else "—"
        md_txt = _plus(md)
        chunks.append(f"{ab} {sc_txt} ({md_txt})")
    return " • ".join(chunks) if chunks else "—"


class WhoAmICog(commands.Cog):
    """Show your cached character sheet without contacting DiceCloud."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dclink")
    async def dclink_cmd(self, ctx, *, url_or_id: str = None):
        """
        Link your Discord user to a DiceCloud character. Use your character URL or paste the character ID.
        Example: !dclink https://dicecloud.com/character/abc123/My-Character
        """
        if not url_or_id or not url_or_id.strip():
            return await ctx.send("❌ Give a DiceCloud character URL or character ID. Example: `!dclink https://dicecloud.com/character/...`")
        cid = dc_extract_id(url_or_id.strip())
        if not cid:
            return await ctx.send("❌ Couldn’t get a character ID from that. Use a full DiceCloud character URL or the character ID.")
        dc_links[str(ctx.author.id)] = cid
        save_dc_links()
        await ctx.send(f"✅ Linked to DiceCloud character `{cid}`. Use `!sync` to pull your sheet.")

    @commands.command(name="whoami", aliases=["me"])
    async def whoami_cmd(self, ctx):
        """
        !whoami (or !me)
        Uses the cached characterSheet.json only (no DC calls).
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        sheet_path = _sheet_path_for(cid)
        sheet = json_safe_read(sheet_path, {})

        prof = sheet.get("profile") or {}
        comp = sheet.get("companion") or {}
        abilities = sheet.get("abilities") or {}

        name    = prof.get("name") or "Your Character"
        classes = _class_names_only(prof.get("classes_text"))
        level   = prof.get("level_total")
        pb      = prof.get("prof_bonus")
        ac      = prof.get("ac")
        hp_c    = prof.get("hp_current")
        hp_m    = prof.get("hp_max")
        photo   = prof.get("photo")

        # Build the embed (no 'Sync complete.' subtitle; big portrait instead)
        e = make_embed(f"{name}", "", COMMAND_IMAGE_URL)

        # Big portrait image if available
        if isinstance(photo, str) and photo.startswith("http"):
            e.set_image(url=photo)

        # Row 1
        e.add_field(name="Classes", value=str(classes), inline=True)
        e.add_field(name="Level", value=str(level) if level is not None else "—", inline=True)

        # Row 2
        e.add_field(name="PB", value=_plus(pb) if pb is not None else "—", inline=True)
        e.add_field(name="AC", value=str(ac) if ac is not None else "—", inline=True)

        # Row 3
        e.add_field(
            name="HP",
            value=f"{hp_c if hp_c is not None else '—'} / {hp_m if hp_m is not None else '—'}",
            inline=True
        )
        c_cur = comp.get("hp_current") if isinstance(comp, dict) else None
        c_max = comp.get("hp_max") if isinstance(comp, dict) else None
        if c_cur is not None or c_max is not None:
            e.add_field(
                name="Companion HP",
                value=f"{c_cur if c_cur is not None else '—'} / {c_max if c_max is not None else '—'}",
                inline=True
            )

        # Abilities
        e.add_field(name="Abilities", value=_abilities_line(abilities), inline=False)

        await ctx.send(embed=e)


async def setup(bot):
    # hot-reload safe
    if bot.get_cog("WhoAmICog"):
        bot.remove_cog("WhoAmICog")
    await bot.add_cog(WhoAmICog(bot))
