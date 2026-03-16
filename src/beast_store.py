from __future__ import annotations
from pathlib import Path
from typing import Dict, Any

from utils import json_safe_read, json_safe_write, _norm
from dc import ammo_path, meta_path

# ---------- paths ----------
def cache_dir_for_cid(cid: str) -> Path:
    return ammo_path(cid).parent  # same pattern as other per-character caches

def beast_path(cid: str) -> Path:
    return cache_dir_for_cid(cid) / "beast.json"

def charsheet_path(cid: str) -> Path:
    return meta_path(cid).with_name("characterSheet.json")

def library_path() -> Path:
    # modules_Beast/  ->  (repo root)/libraries/beast_library.json
    here = Path(__file__).resolve()
    return here.parent.parent / "libraries" / "beast_library.json"

# ---------- tiny storage (keep your schema) ----------
def load_beast(cid: str) -> Dict[str, Any]:
    # Load the user's beast.json with your original defaults preserved.
    b = json_safe_read(beast_path(cid), {})
    b.setdefault("name", "Your Companion")
    b.setdefault("type", "land")       # land | air | sea
    b.setdefault("photo", None)        # URL
    b.setdefault("hp_current", None)   # set to hp_max if missing
    b.setdefault("hp_auto", True)
    # optional field you asked to add:
    if "damage_type" in b and b["damage_type"] is not None:
        b["damage_type"] = _norm(str(b["damage_type"]))
    return b

def save_beast(cid: str, data: Dict[str, Any]) -> None:
    if "damage_type" in data and data["damage_type"] is not None:
        data["damage_type"] = _norm(str(data["damage_type"]))
    json_safe_write(beast_path(cid), data)

def load_charsheet(cid: str) -> Dict[str, Any]:
    return json_safe_read(charsheet_path(cid), {})

# ---------- read small bits from sheet ----------
def prof_bonus_from_sheet(sheet: Dict[str, Any]) -> int:
    try:
        return int((sheet.get("profile") or {}).get("prof_bonus") or 0)
    except Exception:
        return 0

def ranger_level_from_sheet(sheet: Dict[str, Any]) -> int:
    import re
    prof = (sheet.get("profile") or {})
    classes_text = (prof.get("classes_text") or "")
    lvl_total = int(prof.get("level_total") or 0)
    m = re.search(r"ranger\s+(\d+)", classes_text, flags=re.I)
    if m:
        return int(m.group(1))
    return max(1, int(lvl_total or 1))

def char_name_from_sheet(sheet: Dict[str, Any]) -> str:
    return (sheet.get("profile") or {}).get("name") or "Your Character"

def char_ability_mods_from_sheet(sheet: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for ab, obj in (sheet.get("abilities") or {}).items():
        try:
            out[ab.upper()] = int(obj.get("mod", 0))
        except Exception:
            out[ab.upper()] = 0
    return out
