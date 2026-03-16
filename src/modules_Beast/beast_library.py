from __future__ import annotations
import json
from typing import Dict, Any
from modules_Beast.beast_store import library_path  # << use the package import

def load_beast_library() -> Dict[str, Any]:
    try:
        return json.loads(library_path().read_text(encoding="utf-8"))
    except Exception:
        return {"types": {}}

def load_type_block(beast_type: str) -> Dict[str, Any]:
    lib = load_beast_library()
    t = (lib.get("types") or {}).get((beast_type or "").lower())
    if t:
        return t
    return {
        "display_name": f"Primal Companion ({(beast_type or 'land').capitalize()})",
        "base_scores": {"STR": 14, "DEX": 14, "CON": 14, "INT": 8, "WIS": 12, "CHA": 8},
        "armor_class_formula": "12 + PB",
        "hp_formula": "5 + 5 * RANGER_LEVEL",
        "initiative_formula": "MOD.DEX",
        "saving_throw_proficiencies": [],
        "skill_proficiencies": [],
        "attack_profiles": []
    }
