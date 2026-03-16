from __future__ import annotations
from typing import Optional, Dict, Tuple
import re
from discord.ext import commands

from config import OUT_OF_AMMO_IMG
from utils import make_embed, _norm
from dc import dc_links

# render + local store only (no DC math here)
from modules_Ammo.ammo_render import ammo_status_embed, ammo_help_embed
from modules_Ammo.ammo_store import (
    load_ammo_store, save_ammo_store,
    total_quiver_count, count_for_name_in_quiver,
    fired_get, fired_set, fired_add, fired_all,
    stash_all, stash_get, stash_set, stash_add,
)

# ---------------- local helpers ----------------

def _active_id(store: dict) -> Optional[str]:
    aid = store.get("_active")
    return aid if aid and aid in store else None

def _ensure_target_for_name(store: dict, maybe_name: Optional[str]) -> Tuple[str, str]:
    """
    Ensure we have a store entry (id -> {"name","count"}) for a target name.
    If no name given, uses active. If name not found, creates manual::<norm>.
    """
    if not maybe_name:
        aid = _active_id(store)
        if not aid:
            raise RuntimeError("No active ammo set. Try `!ammoreload <name>` first or `!ammoset <name>` if it’s already in the quiver.")
        return aid, store[aid].get("name") or "Ammo"

    name_n = _norm(maybe_name)
    # prefer existing entry by display name
    for iid, info in store.items():
        if isinstance(iid, str) and not iid.startswith("_"):
            if _norm((info or {}).get("name", "")) == name_n:
                return iid, info.get("name") or maybe_name

    pseudo_id = f"manual::{name_n}"
    store.setdefault(pseudo_id, {"name": maybe_name, "count": 0})
    return pseudo_id, maybe_name

def _totals_for_render_from_store(store: dict) -> Dict[str, int]:
    """
    The renderer expects 'totals' and then computes:
        stash = totals - quiver - fired
    We want to show stash = store["_stash"] exactly, so we feed:
        totals := stash + quiver + fired
    """
    quiver: Dict[str, int] = {}
    for k, v in (store or {}).items():
        if isinstance(k, str) and not k.startswith("_"):
            nm = (v.get("name") or "Ammo").strip()
            ct = int(v.get("count", 0) or 0)
            if ct > 0:
                quiver[nm] = quiver.get(nm, 0) + ct

    st = stash_all(store)           # display_name -> count
    fired = fired_all(store)        # display_name -> count

    names = set(quiver) | set(st) | set(fired)
    totals: Dict[str, int] = {}
    for nm in names:
        totals[nm] = int(st.get(nm, 0)) + int(quiver.get(nm, 0)) + int(fired.get(nm, 0))
    return totals

def _active_name(store: dict) -> str:
    aid = _active_id(store)
    if not aid:
        return "Ammo"
    return store[aid].get("name") or "Ammo"

# --- weapon ↔ ammo compatibility guard -----------------
_AMMO_MATCHERS = [
    # (weapon_substring, ammo_substring)
    ("crossbow", "bolt"),
    ("longbow",  "arrow"),
    ("shortbow", "arrow"),
    ("bow",      "arrow"),
    ("sling",    "bullet"),
    ("blowgun",  "dart"),
    ("pistol",   "bullet"),
    ("rifle",    "bullet"),
    ("musket",   "bullet"),
    ("gun",      "bullet"),
]

def weapon_uses_active_ammo(weapon_name: str, ammo_name: str) -> bool:
    """
    Heuristic map so melee weapons (e.g., shortsword) don't burn arrows.
    Both names matched case-insensitively by substring.
    """
    w = _norm(weapon_name or "")
    a = _norm(ammo_name or "")
    for w_sub, a_sub in _AMMO_MATCHERS:
        if w_sub in w and a_sub in a:
            return True
    return False

# ---------------- Cog ----------------

class AmmoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---- list / tweak ----
    @commands.command(name="ammo")
    async def ammo_cmd(self, ctx, *args):
        """
        Show or adjust quiver/stash/fired. !ammo -help for full help.
          !ammo              → show quiver, fired & stash
          !ammo +N [Name]    → add N ammo (fill quiver, overflow → stash)
          !ammo -N [Name]    → remove N from quiver (does not affect stash)
          !ammo set N        → set quiver count (respects capacity)
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")

        if args and _norm(args[0]) == "-help":
            return await ctx.send(embed=ammo_help_embed())

        store = load_ammo_store(cid)
        store.setdefault("_container", store.get("_container") or {"capacity": 20})

        # Show status
        if not args:
            cap = int((store.get("_container") or {}).get("capacity") or 20)

            # build quiver_by_name with only >0
            quiver_by_name: Dict[str, int] = {}
            for iid, info in store.items():
                if not isinstance(iid, str) or iid.startswith("_"):
                    continue
                nm = (info.get("name") or "Ammo").strip()
                ct = int(info.get("count", 0) or 0)
                if ct > 0:
                    quiver_by_name[nm] = quiver_by_name.get(nm, 0) + ct

            stash_by_name = stash_all(store)
            fired_by_name = fired_all(store)
            e = ammo_status_embed(
                quiver_by_name, stash_by_name, fired_by_name, _active_name(store), cap
            )
            return await ctx.send(embed=e)

        # Parse ops
        op = None
        val: Optional[int] = None
        name_tail: Optional[str] = None

        if len(args) >= 1 and isinstance(args[0], str):
            t0 = args[0].strip()
            if t0.lower().startswith("set"):
                pass
            elif t0 and (t0[0] in "+-") and t0[1:].isdigit():
                op = "delta"
                val = int(t0)
                if len(args) > 1:
                    name_tail = " ".join(args[1:]).strip() or None

        if (op is None) and len(args) == 2 and args[0].lower() == "set" and args[1].isdigit():
            op, val = "set", int(args[1])

        if not op:
            return await ctx.send("Usage: `!ammo`, `!ammo -help`, `!ammo +N [Name]`, `!ammo -N [Name]`, or `!ammo set N`")

        # Choose target id/name (active or named)
        try:
            target_id, target_name = _ensure_target_for_name(store, name_tail)
        except RuntimeError as ex:
            return await ctx.send(str(ex))

        cap = int((store.get("_container") or {}).get("capacity") or 20)
        total_now = total_quiver_count(store)
        cur = int(store[target_id].get("count", 0))

        if op == "delta":
            if val is None:
                return await ctx.send("Usage: `!ammo +N [Name]` or `!ammo -N [Name]`")

            if val > 0:
                # Add NEW ammo: fill quiver first; overflow → stash
                space = max(0, cap - total_now)
                to_quiver = min(space, int(val))
                overflow = int(val) - to_quiver
                if to_quiver > 0:
                    store[target_id]["count"] = cur + to_quiver
                if overflow > 0:
                    stash_add(store, target_name, overflow)
            else:
                # Remove from quiver (lost/used). We do NOT bump stash here.
                remove = min(cur, abs(int(val)))
                store[target_id]["count"] = cur - remove

        else:
            # set N: if lower, we do NOT add to stash; if higher, respect capacity
            new_val = max(0, int(val))
            if new_val < cur:
                store[target_id]["count"] = new_val
            else:
                inc = new_val - cur
                space = max(0, cap - total_now)
                add = min(space, inc)
                store[target_id]["count"] = cur + add
                overflow = inc - add
                if overflow > 0:
                    # any extra beyond capacity becomes stash (still "new ammo" semantics)
                    stash_add(store, target_name, overflow)

        save_ammo_store(cid, store)

        # Show refreshed
        cap2 = int((store.get("_container") or {}).get("capacity") or 20)
        quiver2: Dict[str, int] = {}
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                continue
            nm = (info.get("name") or "Ammo").strip()
            ct = int(info.get("count", 0) or 0)
            if ct > 0:
                quiver2[nm] = quiver2.get(nm, 0) + ct
        stash2 = stash_all(store)
        fired2 = fired_all(store)
        e = ammo_status_embed(quiver2, stash2, fired2, _active_name(store), cap2)
        await ctx.send(embed=e)

    # ---- choose active ammo (must already be in quiver) ----
    @commands.command(name="ammoset", aliases=["ammotype","setammo","ammoSet"])
    async def ammo_set_cmd(self, ctx, *, name: str = None):
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")
        if not name:
            return await ctx.send("Usage: `!ammoset <name>` (must already be in the quiver).")

        store = load_ammo_store(cid)
        name_n = _norm(name)

        target_id = None
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                if _norm(info.get("name","")) == name_n and int(info.get("count",0)) > 0:
                    target_id = iid
                    break
        if not target_id:
            return await ctx.send(f"{name} isn’t in your quiver. Load it first with `!ammoreload {name}`.")

        store["_active"] = target_id
        save_ammo_store(cid, store)
        return await ctx.send(f"Active ammo set to **{store[target_id]['name']}**.")

    # ---- reload from stash into quiver ----
    @commands.command(name="ammoreload", aliases=["ammoReload","reloadammo","reload"])
    async def ammo_reload_cmd(self, ctx, *, tail: str = ""):
        """
        Load ammo from stash into quiver (up to capacity).
          !ammoreload           → fill quiver with active type from stash
          !ammoreload <N>       → load exactly N of active type
          !ammoreload <name>     → fill with that type (also sets active)
          !ammoreload <name> <N> → load exactly N of that type
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")

        store = load_ammo_store(cid)
        store.setdefault("_container", store.get("_container") or {"capacity": 20})

        # Parse args: optional name, optional number
        name_part = None
        qty_part: Optional[int] = None
        toks = [t for t in (tail or "").strip().split() if t]
        if toks:
            if toks[-1].isdigit():
                qty_part = int(toks[-1])
                name_part = " ".join(toks[:-1]) or None
            else:
                name_part = " ".join(toks)

        # Target id/name (active or named)
        try:
            target_id, target_name = _ensure_target_for_name(store, name_part)
        except RuntimeError as ex:
            return await ctx.send(str(ex))

        cap_int = int((store.get("_container") or {}).get("capacity") or 20)
        total_quiver = total_quiver_count(store)
        space = max(0, cap_int - total_quiver)

        in_quiver_name = count_for_name_in_quiver(store, target_name)
        stash_avail = stash_get(store, target_name)

        if space <= 0:
            save_ammo_store(cid, store)
            return await ctx.send(f"Your quiver is already full ({cap_int}).")
        if stash_avail <= 0:
            save_ammo_store(cid, store)
            return await ctx.send(f"No stashed **{target_name}** to load.")

        amount = min(space, stash_avail) if qty_part is None else qty_part
        if amount > space:
            return await ctx.send(f"Not enough space. Quiver space: **{space}**.")
        if amount > stash_avail:
            return await ctx.send(f"Not enough stash. Available: **{stash_avail}**.")

        # Move from stash → quiver
        store[target_id]["count"] = int(store[target_id].get("count", 0)) + amount
        stash_set(store, target_name, stash_avail - amount)
        save_ammo_store(cid, store)

        cap2 = int((store.get("_container") or {}).get("capacity") or 20)
        quiver2: Dict[str, int] = {}
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                continue
            nm = (info.get("name") or "Ammo").strip()
            ct = int(info.get("count", 0) or 0)
            if ct > 0:
                quiver2[nm] = quiver2.get(nm, 0) + ct
        stash2 = stash_all(store)
        fired2 = fired_all(store)
        return await ctx.send(
            f"Loaded **{amount}** × **{target_name}** → quiver now **{total_quiver_count(store)}/{cap2}**.",
            embed=ammo_status_embed(quiver2, stash2, fired2, _active_name(store), cap2)
        )

    # ---- collect fired back to quiver (overflow implicitly stays stash) ----
    @commands.command(name="ammocollect", aliases=["collectammo","collect"])
    async def ammo_collect_cmd(self, ctx, *, tail: str = ""):
        """
        Collect fired ammo back to quiver/stash.
          !ammocollect           → collect 50% (round up) of fired, discard the rest
          !ammocollect -all      → collect all fired (then clear fired)
          !ammocollect <N>       → collect exactly N of active type
          !ammocollect -empty    → empty all fired (all types)
          Optional: <name> or -all <name> to target a type.
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")

        store = load_ammo_store(cid)
        cap = int((store.get("_container") or {}).get("capacity") or 20)

        toks = [t for t in (tail or "").strip().split() if t]

        # Empty everything
        if len(toks) == 1 and _norm(toks[0]) == "-empty":
            store["_fired"] = {}
            save_ammo_store(cid, store)
            quiver2: Dict[str, int] = {}
            for iid, info in store.items():
                if isinstance(iid, str) and not iid.startswith("_"):
                    nm = (info.get("name") or "Ammo").strip()
                    ct = int(info.get("count", 0) or 0)
                    if ct > 0:
                        quiver2[nm] = quiver2.get(nm, 0) + ct
            stash2 = stash_all(store)
            fired2 = fired_all(store)
            e = ammo_status_embed(quiver2, stash2, fired2, _active_name(store), cap)
            return await ctx.send(embed=e)

        # -all [name]: collect all fired
        collect_all = False
        if toks and _norm(toks[0]) == "-all":
            collect_all = True
            toks = toks[1:]
        # Optional name + optional number
        amount: Optional[int] = None
        target_name: Optional[str] = None
        if toks:
            if toks[-1].isdigit():
                amount = int(toks[-1])
                target_name = " ".join(toks[:-1]) or None
            else:
                target_name = " ".join(toks)
        if not target_name:
            target_name = _active_name(store)

        # Ensure active id for that name
        tid, tdisp = _ensure_target_for_name(store, target_name)

        fired_have = fired_get(store, tdisp)
        if fired_have <= 0:
            return await ctx.send(f"No fired **{tdisp}** to collect.")

        total_quiver = total_quiver_count(store)
        space = max(0, cap - total_quiver)

        if collect_all:
            collect_total = fired_have
        elif amount is not None:
            collect_total = amount
        else:
            # Default: 50% round up, then clear the rest (discard)
            collect_total = (fired_have + 1) // 2

        if collect_total > fired_have:
            return await ctx.send(f"Not enough to collect. Fired available: **{fired_have}**.")

        to_quiver = min(space, collect_total)
        to_stash  = collect_total - to_quiver

        if to_quiver > 0:
            store[tid]["count"] = int(store[tid].get("count", 0)) + to_quiver
        if to_stash > 0:
            stash_add(store, tdisp, to_stash)

        if collect_all or amount is not None:
            fired_set(store, tdisp, fired_have - collect_total)
        else:
            # Half mode: we collected 50%; discard the rest (clear fired for this type)
            fired_set(store, tdisp, 0)
        save_ammo_store(cid, store)

        parts = []
        if to_quiver > 0: parts.append(f"**{to_quiver}** → quiver")
        if to_stash  > 0: parts.append(f"**{to_stash}** → stash")
        if not parts:
            msg = f"Nothing collected for **{tdisp}**."
        elif not collect_all and amount is None:
            discarded = fired_have - collect_total
            msg = f"Collected {', '.join(parts)} for **{tdisp}** (50% round up). Discarded **{discarded}**."
        else:
            msg = f"Collected {', '.join(parts)} for **{tdisp}**."

        quiver2: Dict[str, int] = {}
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                nm = (info.get("name") or "Ammo").strip()
                ct = int(info.get("count", 0) or 0)
                if ct > 0:
                    quiver2[nm] = quiver2.get(nm, 0) + ct
        stash2 = stash_all(store)
        fired2 = fired_all(store)
        e = ammo_status_embed(quiver2, stash2, fired2, _active_name(store), cap)
        await ctx.send(msg, embed=e)

    # ---- unload from quiver into stash ----
    @commands.command(name="ammounload", aliases=["unloadammo","unload"])
    async def ammo_unload_cmd(self, ctx, *, tail: str = ""):
        """
            !ammounload                → unload **all** of the active type from quiver → stash
            !ammounload <N>            → unload **exactly** N of the active type → stash
            !ammounload <name> <N>     → unload **exactly** N of that type → stash
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")

        store = load_ammo_store(cid)
        toks = [t for t in (tail or "").strip().split() if t]
        amount: Optional[int] = None
        target_name: Optional[str] = None
        if toks:
            if toks[-1].isdigit():
                amount = int(toks[-1])
                target_name = " ".join(toks[:-1]) or None
            else:
                target_name = " ".join(toks)
        if not target_name:
            aid = _active_id(store)
            if not aid:
                return await ctx.send("No active ammo set.")
            target_name = store[aid]["name"]

        # Find an entry in quiver for that name
        target_id = None
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                if _norm(info.get("name","")) == _norm(target_name) and int(info.get("count",0)) > 0:
                    target_id = iid
                    break

        if not target_id:
            return await ctx.send(f"{target_name} isn’t currently in your quiver.")

        cur = int(store[target_id].get("count", 0))
        if cur <= 0:
            return await ctx.send(f"No **{store[target_id]['name']}** in the quiver to unload.")

        unload = cur if amount is None else amount
        if unload > cur:
            return await ctx.send(f"Not enough in quiver. You have **{cur}** {store[target_id]['name']}.")

        store[target_id]["count"] = cur - unload
        stash_add(store, store[target_id]["name"], unload)

        save_ammo_store(cid, store)
        cap2 = int((store.get("_container") or {}).get("capacity") or 20)
        quiver2: Dict[str, int] = {}
        for iid, info in store.items():
            if isinstance(iid, str) and not iid.startswith("_"):
                continue
            nm = (info.get("name") or "Ammo").strip()  # <-- fixed (no extra ')')
            ct = int(info.get("count", 0) or 0)
            if ct > 0:
                quiver2[nm] = quiver2.get(nm, 0) + ct
        stash2 = stash_all(store)
        fired2 = fired_all(store)
        e = ammo_status_embed(quiver2, stash2, fired2, _active_name(store), cap2)
        await ctx.send(embed=e)

    # ---- attack auto-decrement (+ add to fired) ----
    @commands.command(name="attack")
    async def attack_cmd(self, ctx, *, weapon: str):
        """
        Use like Avrae: !attack longbow
        - per-use quantity defaults to 1 unless your weapon resource says otherwise.
        - Only decrements ammo if the weapon plausibly uses the **active** ammo.
        - Spent ammo goes into the 'fired' bucket.
        """
        cid = dc_links.get(str(ctx.author.id))
        if not cid:
            return await ctx.send("🙈 You’re not linked. Use !dclink <dicecloud url> first.")

        per_use = 1  # You can extend this later to read per-attack costs

        store = load_ammo_store(cid)
        aid = _active_id(store)
        if not aid:
            return  # nothing to do

        ammo_name = store[aid].get("name") or "Ammo"

        # Only consume ammo if the weapon matches the active ammo.
        # If not, silently do nothing (no message).
        if not weapon_uses_active_ammo(weapon, ammo_name):
            return

        before = int(store[aid].get("count", 0))
        if before < per_use:
            e = make_embed("Out of ammo!", "You have no ammo to fire.", None)
            e.set_image(url=OUT_OF_AMMO_IMG)
            await ctx.send(embed=e)
            return

        store[aid]["count"] = before - per_use
        fired_add(store, ammo_name, per_use)
        save_ammo_store(cid, store)

        import asyncio
        await asyncio.sleep(0.5)
        await ctx.send(embed=make_embed(
            f"{weapon}: ammo updated",
            f"• {ammo_name}: {before} → {store[aid]['count']} (−{per_use})",
            None
        ))

__all__ = ["AmmoCog"]

async def setup(bot):
    if bot.get_cog("AmmoCog"):
        bot.remove_cog("AmmoCog")
    await bot.add_cog(AmmoCog(bot))
