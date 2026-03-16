# sync_profile.py
import re
from typing import Dict, Optional, Tuple, List, Any

from utils import json_safe_read, json_safe_write, first_int_from
from dc import meta_path

ABILITY_KEYS = [
    ("str", "strength"),
    ("dex", "dexterity"),
    ("con", "constitution"),
    ("int", "intelligence"),
    ("wis", "wisdom"),
    ("cha", "charisma"),
]

SKILL_LIST = [
    ("Acrobatics", "dex"), ("Animal Handling", "wis"), ("Arcana", "int"),
    ("Athletics", "str"), ("Deception", "cha"), ("History", "int"),
    ("Insight", "wis"), ("Intimidation", "cha"), ("Investigation", "int"),
    ("Medicine", "wis"), ("Nature", "int"), ("Perception", "wis"),
    ("Performance", "cha"), ("Persuasion", "cha"), ("Religion", "int"),
    ("Sleight of Hand", "dex"), ("Stealth", "dex"), ("Survival", "wis"),
]

def _sheet_path_for(cid: str):
    return meta_path(cid).with_name("characterSheet.json")

def _prof_bonus_from_level(level_total: Optional[int]) -> Optional[int]:
    if not level_total or level_total <= 0: return None
    if level_total <= 4:   return 2
    if level_total <= 8:   return 3
    if level_total <= 12:  return 4
    if level_total <= 16:  return 5
    return 6

def _classes_from_snapshot(data: dict) -> Tuple[str, int]:
    props = data.get("creatureProperties") or []
    cls: List[Tuple[str, int]] = []

    for p in props:
        if (p.get("type") or "").lower() == "class":
            cname = (p.get("name") or p.get("class") or p.get("variableName") or "").strip() or "Class"
            clev  = first_int_from(p.get("level"), default=0)
            if clev > 0:
                cls.append((cname, clev))

    if not cls:
        for p in props:
            if (p.get("type") or "").lower() == "classlevel":
                cname = (p.get("name") or p.get("variableName") or "").strip() or "Class"
                clev  = first_int_from(p.get("level"), default=0)
                if clev > 0:
                    cls.append((cname, clev))

    if not cls:
        creature = (data.get("creatures") or [{}])[0]
        if isinstance(creature.get("classes"), list):
            for cl in creature["classes"]:
                cname = (cl.get("name") or cl.get("class") or "").strip() or "Class"
                clev  = first_int_from(cl.get("level"), default=0)
                if clev > 0:
                    cls.append((cname, clev))

    total = sum(l for _, l in cls) if cls else 0
    classes_txt = " / ".join(f"{n} {l}" for n, l in cls) if cls else None
    return classes_txt or "", total

def _mod_from_score(score: Optional[int]) -> Optional[int]:
    if score is None: return None
    try: return (int(score) - 10) // 2
    except Exception: return None

def _read_number(*vals, default: Optional[int] = None) -> Optional[int]:
    for v in vals:
        if isinstance(v, (int, float)): return int(v)
        if isinstance(v, str) and v.strip().lstrip("+-").isdigit(): return int(v)
        if isinstance(v, dict):
            for k in ("total","value","current","base","mod","modifier","max","maximum"):
                if k in v:
                    got = _read_number(v[k])
                    if got is not None: return got
    return default

def _extract_abilities(creature: dict, props: list) -> Dict[str, Dict[str, Optional[int]]]:
    out = {}
    buckets = [creature.get("abilities"), creature.get("abilityScores"), creature.get("stats")]
    found = {}
    for b in buckets:
        if isinstance(b, dict):
            for short, long in ABILITY_KEYS:
                if short in b and _read_number(b[short]) is not None:
                    found[short] = _read_number(b[short])
                elif long in b and _read_number(b[long]) is not None:
                    found[short] = _read_number(b[long])

    if len(found) < 6:
        for p in props:
            n = (p.get("name") or p.get("variableName") or "").strip().lower()
            val = _read_number(p.get("value"), p.get("score"), p.get("total"), p.get("current"))
            for short, long in ABILITY_KEYS:
                if n in (short, long) and val is not None:
                    found[short] = val

    for short, _ in ABILITY_KEYS:
        sc = found.get(short)
        out[short.upper()] = {"score": sc, "mod": _mod_from_score(sc)}
    return out

def _extract_saves(creature: dict, props: list) -> Dict[str, Dict[str, Optional[int]]]:
    out: Dict[str, Dict[str, Optional[int]]] = {}
    candidate = creature.get("saves") or creature.get("savingThrows") or {}
    if isinstance(candidate, dict):
        for short, long in ABILITY_KEYS:
            v = candidate.get(short) or candidate.get(long)
            bonus = _read_number(v)
            if bonus is not None:
                out[short.upper()] = {"bonus": bonus}
    for p in props:
        t = (p.get("type") or "").lower()
        n = (p.get("name") or p.get("variableName") or "").lower()
        if "save" in n or "saving throw" in n or t in {"save", "savingthrow"}:
            bonus = _read_number(p.get("bonus"), p.get("value"), p.get("modifier"), p.get("total"))
            for short, long in ABILITY_KEYS:
                if short in n or long in n:
                    out.setdefault(short.upper(), {})
                    if bonus is not None:
                        out[short.upper()]["bonus"] = bonus
    return out

def _extract_skills(creature: dict, props: list, abilities_mods: Dict[str, Dict[str, Optional[int]]]) -> Dict[str, Dict[str, Optional[int]]]:
    out: Dict[str, Dict[str, Optional[int]]] = {}
    cand = creature.get("skills") or {}
    if isinstance(cand, dict):
        for name, abil in SKILL_LIST:
            key = name.replace(" ", "").lower()
            v = cand.get(name) or cand.get(key) or cand.get(name.lower())
            bonus = _read_number(v)
            if bonus is not None:
                out[name] = {"bonus": bonus, "ability": abil.upper()}
    for p in props:
        t = (p.get("type") or "").lower()
        n = (p.get("name") or p.get("variableName") or "").strip()
        if t == "skill" or n.lower() in {s[0].lower() for s in SKILL_LIST}:
            bonus = _read_number(p.get("bonus"), p.get("value"), p.get("modifier"), p.get("total"))
            if bonus is None:
                continue
            for name, abil in SKILL_LIST:
                if n.lower() == name.lower():
                    out[name] = {"bonus": bonus, "ability": abil.upper()}
                    break
    return out

# ---- DC-specific extractors (HP/AC/Portrait/Companion HP) ----
def _extract_ac(data: dict) -> Optional[int]:
    props = data.get("creatureProperties") or []
    # Prefer resolved property with variableName "armor"
    for p in props:
        if (p.get("variableName") or "").lower() == "armor":
            return _read_number(p.get("total"), p.get("value"), (p.get("baseValue") or {}).get("value"))
    # Fallback: creatureVariables[0].armor
    cvs = data.get("creatureVariables") or []
    if cvs and isinstance(cvs[0], dict):
        arm = cvs[0].get("armor")
        if isinstance(arm, dict):
            return _read_number(arm.get("total"), arm.get("value"), (arm.get("baseValue") or {}).get("value"))
    return None

def _extract_character_hp(data: dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (current, max) for the CHARACTER.
    In your payload this lives at creatureVariables[0].hitPoints.{value,total}.
    """
    cvs = data.get("creatureVariables") or []
    if cvs and isinstance(cvs[0], dict):
        hp = cvs[0].get("hitPoints")
        if isinstance(hp, dict):
            cur = _read_number(hp.get("value"))
            mx  = _read_number(hp.get("total"))
            if cur is not None or mx is not None:
                return cur, mx

    # Fallbacks (older sheets)
    creature = (data.get("creatures") or [{}])[0]
    cur = _read_number((creature.get("hp") or {}).get("current"), creature.get("currentHP"), creature.get("hpCurrent"))
    mx  = _read_number((creature.get("hp") or {}).get("max"), creature.get("maxHP"), creature.get("hpMax"))
    return cur, mx

def _extract_companion_hp(data: dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Companion HP in your payload is at creatureVariables[0].companionHP.{value,total}.
    We read that first; fall back to any property named companionHP if needed.
    """
    cvs = data.get("creatureVariables") or []
    if cvs and isinstance(cvs[0], dict):
        chp = cvs[0].get("companionHP")
        if isinstance(chp, dict):
            return _read_number(chp.get("value")), _read_number(chp.get("total"))
    # Fallback to properties
    props = data.get("creatureProperties") or []
    for p in props:
        if (p.get("variableName") or "").lower() == "companionhp":
            return _read_number(p.get("value"), p.get("current")), _read_number(p.get("total"), (p.get("baseValue") or {}).get("value"))
    return None, None

def _extract_portrait(data: dict) -> Optional[str]:
    creature = (data.get("creatures") or [{}])[0]
    pic = creature.get("picture")
    return pic if isinstance(pic, str) and pic.startswith("http") else None

# ---- main entry ----
async def sync_profile_from_snapshot(cid: str, data: dict) -> dict:
    """Build/merge 'profile', 'abilities', 'saves', 'skills' (+ AC/HP/portrait/companion HP) into characterSheet.json."""
    sheet_path = _sheet_path_for(cid)
    sheet = json_safe_read(sheet_path, {})

    creature = (data.get("creatures") or [{}])[0]
    props = data.get("creatureProperties") or []

    # Identity
    name = creature.get("name") or "Unknown Creature"
    photo = _extract_portrait(data)

    # Classes / PB
    classes_text, level_total = _classes_from_snapshot(data)
    prof_bonus = _prof_bonus_from_level(level_total)

    # Abilities / Saves / Skills
    abilities = _extract_abilities(creature, props)
    saves     = _extract_saves(creature, props)
    skills    = _extract_skills(creature, props, abilities)

    # Numbers
    ac = _extract_ac(data)
    hp_c, hp_m = _extract_character_hp(data)
    comp_c, comp_m = _extract_companion_hp(data)

    # Write profile
    sheet.setdefault("profile", {})
    sheet["profile"].update({
        "name": name,
        "classes_text": classes_text or None,
        "level_total": level_total or None,
        "prof_bonus": prof_bonus,
        "hp_current": hp_c,
        "hp_max": hp_m,
        "ac": ac,
        "photo": photo or sheet["profile"].get("photo"),
    })
    sheet["abilities"] = abilities
    sheet["saves"]     = saves
    sheet["skills"]    = skills

    # Companion summary (for !sync card and other cogs)
    if comp_c is not None or comp_m is not None:
        comp = sheet.get("companion") or {}
        if comp_c is not None: comp["hp_current"] = comp_c
        if comp_m is not None: comp["hp_max"] = comp_m
        sheet["companion"] = comp

    json_safe_write(sheet_path, sheet)
    return sheet
