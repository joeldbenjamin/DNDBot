from __future__ import annotations
from typing import Dict, Optional
from utils import _norm

SKILL_TO_ABILITY: Dict[str, str] = {
    "acrobatics": "DEX",
    "animal handling": "WIS",
    "arcana": "INT",
    "athletics": "STR",
    "deception": "CHA",
    "history": "INT",
    "insight": "WIS",
    "intimidation": "CHA",
    "investigation": "INT",
    "medicine": "WIS",
    "nature": "INT",
    "perception": "WIS",
    "performance": "CHA",
    "persuasion": "CHA",
    "religion": "INT",
    "sleight of hand": "DEX",
    "stealth": "DEX",
    "survival": "WIS",
}

def ability_key(s: str) -> Optional[str]:
    s = _norm(s).replace(".", "")
    for ab in ["str","dex","con","int","wis","cha"]:
        if s == ab:
            return ab.upper()
    return None

def skill_key(s: str) -> Optional[str]:
    s = _norm(s)
    for k in SKILL_TO_ABILITY.keys():
        if s == k or s.replace(" ", "") == k.replace(" ", ""):
            return k
    return None
