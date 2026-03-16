# sync_cog.py
from __future__ import annotations
from discord.ext import commands
import re

from config import COMMAND_IMAGE_URL
from utils import make_embed, _norm
from dc import dc_links, dc_get_creature_cached
import sync_profile

from modules_Ammo.ammo_sync import seed_ammo_from_cache as _seed_ammo_from_cache

def _class_names_only(classes_text: str) -> str:
    if not classes_text:
        return "—"
    parts = []
    for chunk in str(classes_text).split("/"):
        name = re.sub(r"\s*\d+\s*$", "", chunk.strip())
        parts.append(name.strip() or "?")
    return " / ".join(parts)

class SyncCog(commands.Cog):
    """Sync profile (AC/HP/portrait) from DiceCloud, and mirror DC ammo into ammo.json."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sync", aliases=["SYNC"])
    async def sync_cmd(self, ctx, *args):
        """
        !sync             → refresh from DiceCloud cache (respects TTL) + mirror DC ammo into ammo.json
        !sync force       → force-refresh DiceCloud now (bypass TTL)
        !sync -purge      → also clear local fired & stash before mirroring DC
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use `!dclink <dicecloud url>` first.")

        force = True
        purge = any(_norm(a) in {"purge", "-purge", "--purge", "clear", "-clear"} for a in args)

        try:
            # 1) Freshen creature snapshot (cached or forced)
            data = await dc_get_creature_cached(cid, force=force)

            # 2) Sync profile (no ammo injection here)
            sheet = await sync_profile.sync_profile_from_snapshot(cid, data)

            # 3) Mirror DC ammo into ammo.json (quiver & stash). Purge clears local fired+stash first.
            if _seed_ammo_from_cache:
                try:
                    await _seed_ammo_from_cache(cid, overwrite_counts=True, purge_local=purge)
                except Exception:
                    pass

            # 4) Build summary embed
            prof = sheet.get("profile") or {}
            comp = sheet.get("companion") or {}

            name    = prof.get("name") or "Your Character"
            classes = _class_names_only(prof.get("classes_text") or "")
            level   = prof.get("level_total") or "—"
            pb      = prof.get("prof_bonus")
            ac      = prof.get("ac")
            hp_c    = prof.get("hp_current")
            hp_m    = prof.get("hp_max")
            photo   = prof.get("photo")

            e = make_embed(f"{name}", "Sync complete.", COMMAND_IMAGE_URL)
            if photo:
                e.set_thumbnail(url=photo)

            e.add_field(name="Classes", value=str(classes), inline=True)
            e.add_field(name="Level", value=str(level), inline=True)
            e.add_field(name="PB", value=f"+{pb}" if pb is not None else "—", inline=True)
            e.add_field(name="AC", value=f"{ac if ac is not None else '—'}", inline=True)
            e.add_field(name="HP", value=f"{hp_c if hp_c is not None else '—'} / {hp_m if hp_m is not None else '—'}", inline=True)

            if comp:
                c_cur = comp.get("hp_current"); c_max = comp.get("hp_max")
                e.add_field(name="Companion HP", value=f"{c_cur if c_cur is not None else '—'} / {c_max if c_max is not None else '—'}", inline=True)

            if purge:
                e.add_field(name="Ammo purge", value="Cleared local fired & stash, then mirrored DC quiver + stash into ammo.json.", inline=False)
            else:
                e.add_field(name="Ammo", value="Mirrored DC quiver + stash into ammo.json.", inline=False)

            await ctx.send(embed=e)

        except Exception as e:
            import traceback
            traceback.print_exception(type(e), e, e.__traceback__)
            await ctx.send(f"⚠️ Sync crashed: {e}")

async def setup(bot):
    if bot.get_cog("SyncCog"):
        bot.remove_cog("SyncCog")
    await bot.add_cog(SyncCog(bot))
