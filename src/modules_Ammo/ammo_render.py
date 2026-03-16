# modules_Ammo/ammo_render.py
from __future__ import annotations
from typing import Dict
from utils import make_embed

def ammo_status_embed(quiver_by_name: Dict[str,int],
                      stash_by_name: Dict[str,int],
                      fired_by_name: Dict[str,int],
                      active_name: str,
                      cap: int):
    e = make_embed("Quiver & Ammo", None, None)
    e.add_field(name="Quiver capacity", value=str(cap), inline=False)

    # Quiver (only >0)
    if quiver_by_name:
        lines = []
        # active on top
        if active_name in quiver_by_name:
            lines.append(f"★ {active_name}: {quiver_by_name[active_name]}")
        for nm, cnt in sorted(quiver_by_name.items(), key=lambda x: x[0].lower()):
            if nm == active_name or cnt <= 0:
                continue
            lines.append(f"{nm}: {cnt}")
        if lines:
            e.add_field(name="Quiver", value="\n".join(lines), inline=False)

    # Stashed (only >0)
    stash_lines = [f"• {nm}: {cnt}" for nm, cnt in sorted(stash_by_name.items(), key=lambda x: x[0].lower()) if cnt > 0]
    if stash_lines:
        e.add_field(name="Stashed (not in quiver)", value="\n".join(stash_lines), inline=False)

    # Fired (only >0)
    fired_lines = [f"• {nm}: {cnt}" for nm, cnt in sorted(fired_by_name.items(), key=lambda x: x[0].lower()) if cnt > 0]
    if fired_lines:
        e.add_field(name="Fired (to collect)", value="\n".join(fired_lines), inline=False)

    return e

def ammo_help_embed():
    e = make_embed("Ammo help", None, None)
    e.add_field(name="Show", value="`!ammo`", inline=False)
    e.add_field(name="Add/Remove", value="`!ammo +N [Name]`   /   `!ammo -N [Name]`", inline=False)
    e.add_field(name="Set", value="`!ammo set N` (active type)", inline=False)
    e.add_field(name="Reload", value="`!ammoreload [Name] [N]` (loads from stash into quiver)", inline=False)
    e.add_field(name="Collect", value="`!ammocollect [Name] [N]` (fired → quiver, overflow → stash)", inline=False)
    e.add_field(name="Unload", value="`!ammounload [Name] [N]` (quiver → stash)", inline=False)
    return e
