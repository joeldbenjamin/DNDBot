from __future__ import annotations
import random, re
from typing import List, Tuple

_DICE_RX = re.compile(r"^\s*(\d+)[dD](\d+)\s*$")

def roll_dice(dice_expr: str) -> Tuple[int, List[int]]:
    if not dice_expr:
        return 0, []
    m = _DICE_RX.match(dice_expr.strip())
    if not m:
        try:
            v = int(dice_expr)
            return v, [v]
        except Exception:
            return 0, []
    n = int(m.group(1)); d = int(m.group(2))
    rolls = [random.randint(1, d) for _ in range(max(1, n))]
    return sum(rolls), rolls

def roll_d20(adv: bool=False, dis: bool=False) -> Tuple[int, List[int], str]:
    if adv and not dis:
        a = random.randint(1,20); b = random.randint(1,20)
        return max(a,b), [a,b], "adv"
    if dis and not adv:
        a = random.randint(1,20); b = random.randint(1,20)
        return min(a,b), [a,b], "dis"
    r = random.randint(1,20)
    return r, [r], ""

def format_d20_detail(rolls: List[int], tag: str, parts: List[Tuple[str,int]]) -> str:
    total_bonus = sum(b for _, b in parts)
    if tag == "adv":
        kept = max(rolls); other = min(rolls)
        roll_txt = f"2d20kh1 ({kept}, ~~{other}~~)"
    elif tag == "dis":
        kept = min(rolls); other = max(rolls)
        roll_txt = f"2d20kl1 ({kept}, ~~{other}~~)"
    else:
        kept = rolls[0]
        roll_txt = f"1d20 ({kept})"

    chunks = []
    for lbl, val in parts or []:
        chunks.append(f"{val:+d} ({lbl})" if lbl else f"{val:+d}")
    parts_txt = " ".join(chunks) if chunks else "+0"
    return f"{roll_txt} {parts_txt} = **`{kept + total_bonus}`**"

def format_damage_line(dice_expr: str, dice_total: int, mod_parts: List[Tuple[str,int]], dmg_type: str) -> str:
    mods_total = sum(v for _, v in (mod_parts or []))
    dice_txt = f"{dice_expr} ({dice_total})"
    chunks = []
    for lbl, v in (mod_parts or []):
        chunks.append(f"{v:+d} ({lbl})" if lbl else f"{v:+d}")
    plus = (" " + " ".join(chunks)) if chunks else ""
    total = dice_total + mods_total
    return f"{dice_txt}{plus} = **`{total}`** {dmg_type}"
