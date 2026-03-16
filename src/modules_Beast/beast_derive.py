from __future__ import annotations
import ast, re
from typing import Dict, Any, List, Optional, Tuple
from modules_Beast.beast_library import load_type_block
from modules_Beast.beast_store import (
    prof_bonus_from_sheet, ranger_level_from_sheet, char_ability_mods_from_sheet
)


# ---------- math helpers ----------
def ability_mod(score: int) -> int:
    return (int(score) - 10) // 2

def base_mods_from_scores(scores: Dict[str, int]) -> Dict[str, int]:
    return {k.upper(): ability_mod(int(v)) for k, v in scores.items()}

# ---------- safe expression evaluator ----------
_ALLOWED_AST_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Name, ast.Attribute, ast.Call, ast.BoolOp,
    ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.IfExp, ast.Subscript, ast.Index, ast.Tuple, ast.List, ast.Dict
}

def _assert_safe_ast(node: ast.AST):
    for n in ast.walk(node):
        if type(n) not in _ALLOWED_AST_NODES:
            raise ValueError(f"Unsupported expression element: {type(n).__name__}")

def eval_formula(expr: Optional[str], env: Dict[str, Any]) -> int:
    if not expr:
        return 0
    def dot_to_index(match):
        a, b = match.group(1), match.group(2)
        if a in env:
            return f"{a}['{b}']"
        return match.group(0)
    transformed = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.(STR|DEX|CON|INT|WIS|CHA)\b", dot_to_index, expr)
    node = ast.parse(transformed, mode="eval")
    _assert_safe_ast(node)
    return int(eval(compile(node, "<expr>", "eval"), {"__builtins__": {}}, env))

# ---------- derived block ----------
def compute_beast_from_library(cid: str, beast_type: str, sheet: Dict[str, Any]) -> Dict[str, Any]:
    t = load_type_block(beast_type)
    base_scores = {k.upper(): int(v) for k, v in (t.get("base_scores") or {}).items()}
    beast_mods = base_mods_from_scores(base_scores)
    char_mods  = char_ability_mods_from_sheet(sheet)
    ranger_lvl = ranger_level_from_sheet(sheet)
    pb         = prof_bonus_from_sheet(sheet)

    env = {
        "RANGER_LEVEL": int(ranger_lvl),
        "PB": int(pb),
        "MOD": beast_mods,
        "CHARMOD": char_mods,
    }

    ac         = eval_formula(t.get("armor_class_formula", "10"), env)
    hp_max     = eval_formula(t.get("hp_formula", "5 + 5 * RANGER_LEVEL"), env)
    init_bonus = eval_formula(t.get("initiative_formula", "MOD.DEX"), env)

    return {
        "display_name": t.get("display_name") or f"Primal Companion ({(beast_type or 'land').capitalize()})",
        "scores": base_scores,
        "mods": beast_mods,
        "pb": pb,
        "ranger_level": ranger_lvl,
        "ac": ac,
        "hp_max": hp_max,
        "init": init_bonus,
        "saving_throw_proficiencies": [s.lower() for s in (t.get("saving_throw_proficiencies") or [])],
        "skill_proficiencies": [s.lower() for s in (t.get("skill_proficiencies") or [])],
        "attack_profiles": t.get("attack_profiles") or [],
        "features": t.get("features") or [],
        "movement": t.get("movement") or {},
        "senses": t.get("senses") or {},
        "size": t.get("size") or "Medium",
        "photo_default": t.get("photo_default"),
        "ac_formula": t.get("armor_class_formula") or "10",
        "init_formula": t.get("initiative_formula") or "MOD.DEX",
        "on_hit_extra": (t.get("on_hit_extra") or {}),
    }

# ---------- linear “explain” helpers ----------
_TOKEN_RX = re.compile(r"([+\-]?)\s*(PB|MOD\.(STR|DEX|CON|INT|WIS|CHA)|CHARMOD\.(STR|DEX|CON|INT|WIS|CHA)|\d+)\s*")

def explain_linear_formula(expr: str, beast_mods: Dict[str,int], char_mods: Dict[str,int], pb: int, char_name: str) -> Optional[str]:
    if not expr or any(x in expr for x in ("*", "/", "(", ")", "%")):
        return None
    parts_display: List[str] = []
    idx = 0
    while idx < len(expr):
        m = _TOKEN_RX.match(expr, idx)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        tok = m.group(2)
        if tok == "PB":
            parts_display.append(f"{sign*int(pb):+d} PB")
        elif tok.startswith("MOD."):
            ab = tok.split(".")[1]
            parts_display.append(f"{sign*int(beast_mods.get(ab, 0)):+d} {ab}")
        elif tok.startswith("CHARMOD."):
            ab = tok.split(".")[1]
            parts_display.append(f"{sign*int(char_mods.get(ab, 0)):+d} {ab} ({char_name})")
        else:
            parts_display.append(f"{sign*int(tok):+d}")
        idx = m.end()
        while idx < len(expr) and expr[idx].isspace():
            idx += 1
    if parts_display and parts_display[0].startswith("+"):
        parts_display[0] = parts_display[0][1:]
    return " ".join(parts_display)

def parts_from_formula(expr: str, beast_mods: Dict[str,int], char_mods: Dict[str,int], pb: int, char_name: str) -> Optional[List[Tuple[str,int]]]:
    if not expr:
        return []
    if any(x in expr for x in ("*", "/", "(", ")", "%")):
        return None
    parts: List[Tuple[str,int]] = []
    idx = 0
    while idx < len(expr):
        m = _TOKEN_RX.match(expr, idx)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        tok = m.group(2)
        if tok == "PB":
            parts.append(("", sign*int(pb)))
        elif tok.startswith("MOD."):
            ab = tok.split(".")[1]
            parts.append((ab, sign*int(beast_mods.get(ab, 0))))
        elif tok.startswith("CHARMOD."):
            ab = tok.split(".")[1]
            parts.append((f"{ab} {char_name}", sign*int(char_mods.get(ab, 0))))
        else:
            parts.append(("", sign*int(tok)))
        idx = m.end()
        while idx < len(expr) and expr[idx].isspace():
            idx += 1
    return parts
