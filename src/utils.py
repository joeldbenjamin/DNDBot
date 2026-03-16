# utils.py
import json
import re
from typing import Optional

import discord
from config import EMBED_COLOR, FOOTER_TEXT, WEEKDAYS, MONTH_NAMES


# -----------------------
# Text / formatting utils
# -----------------------
def _norm(s: str) -> str:
    """Collapse whitespace and lowercase (for fuzzy matches)."""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def make_embed(
    main_text: str,
    subtitle: str = None,
    thumbnail_url: str = None,
    *,
    brand: bool = False,                 # NEW: hide branding by default
    author_name: Optional[str] = None,   # optional custom author
    footer_text: Optional[str] = None,   # optional custom footer
) -> discord.Embed:
    """
    Standard embed style for the bot.

    - By default, no author/footer is set (no "D-D Bot" at top/bottom).
    - Pass brand=True to use default branding (author="D-D Bot", footer=FOOTER_TEXT).
    - Or pass author_name / footer_text to set custom values.
    """
    embed = discord.Embed(title=main_text, description=subtitle, color=EMBED_COLOR)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    # Branding / author / footer handling
    if brand:
        embed.set_author(name="D-D Bot")
        embed.set_footer(text=FOOTER_TEXT)
    else:
        if author_name:
            embed.set_author(name=author_name)
        if footer_text:
            embed.set_footer(text=footer_text)

    return embed


def ordinal(n: int) -> str:
    """Return 1 -> 1st, 2 -> 2nd, etc."""
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_date_us(year: int, month: int, day: int, weekday: Optional[str] = None) -> str:
    """Pretty US style: Friday, April 27th, 618 (weekday shown if provided)."""
    wd = f"{weekday}, " if weekday else ""
    month_name = MONTH_NAMES[month - 1]
    return f"{wd}{month_name} {ordinal(day)}, {year}"


# -----------------------
# JSON file helpers
# -----------------------
def json_safe_write(path, obj):
    """Atomic-ish write: write to .tmp then replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


def json_safe_read(path, default):
    """Read JSON or return default on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# -----------------------
# Parsing helpers
# -----------------------
def parse_bool(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def int_like(x):
    """Return int(x) if x looks integer-ish, else None."""
    try:
        if isinstance(x, (int, float)):
            return int(x)
        if isinstance(x, str) and x.strip().lstrip("-").isdigit():
            return int(x)
    except Exception:
        pass
    return None


def _first_int_from(*vals, default=0):
    """Return the first value among vals that parses as an int; else default."""
    for v in vals:
        out = int_like(v)
        if out is not None:
            return out
    return default


def first_int_from(*vals, default=0):
    """Public alias that forwards default= correctly (avoid recursion bug)."""
    return _first_int_from(*vals, default=default)


# -----------------------
# Date helpers
# -----------------------
def weekday_rollover(current: str, delta_days: int) -> str:
    """Rotate weekday name by delta_days (can be negative)."""
    idx = WEEKDAYS.index(current)
    return WEEKDAYS[(idx + delta_days) % 7]
