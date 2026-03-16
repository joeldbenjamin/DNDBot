# sync_spells.py
from typing import Optional, List, Dict

from utils import json_safe_read, json_safe_write, first_int_from
from dc import meta_path, slots_path

import re

def _sheet_path_for(cid: str):
    return meta_path(cid).with_name("characterSheet.json")

_SLOT_NAME_PATTERNS = [
    re.compile(r"(?:^|\s)([1-9])(?:st|nd|rd|th)?\s*(?:level)?\s*spell\s*slots?", re.I),
    re.compile(r"spell\s*slots?\s*(?:\(|\-|\s)*([1-9])(?:st|nd|rd|th)?", re.I),
    re.compile(r"pact\s*magic.*slot\s*level\s*([1-9])", re.I),
]
_SLOT_LEVEL_RX = re.compile(r"(?:slot\s*level|slotlevel|spellSlotLevel)\s*([1-9])", re.I)
_LEVEL_IN_NAME_RX = re.compile(r"\b([1-9])(?:st|nd|rd|th)?\s*level\b", re.I)

def _guess_level_from_name(name: str) -> Optional[int]:
    n = name or ""
    for rx in _SLot_NAME_PATTERNS if False else _SLOT_NAME_PATTERNS:
        m = rx.search(n)
        if m:
            try: return int(m.group(1))
            except: pass
    return None

def _slot_level_from_node(p: dict) -> Optional[int]:
    ssl = p.get("spellSlotLevel")
    if isinstance(ssl, dict):
        for key in ("value", "baseValue", "calculatedValue"):
            try:
                v = ssl.get(key)
                if v is not None:
                    v = int(v)
                    if 1 <= v <= 9:
                        return v
            except: pass
    vn = (p.get("variableName") or p.get("name") or "")
    m = _SLOT_LEVEL_RX.search(str(vn))
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 9: return v
        except: pass
    nm = p.get("name") or ""
    m = _LEVEL_IN_NAME_RX.search(nm)
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 9: return v
        except: pass
    return None

def _slot_max_from_node(p: dict) -> int:
    return int(first_int_from(
        p.get("total"),
        p.get("value"),
        p.get("usesMax"),
        p.get("max"),
        p.get("available"),
        (p.get("quantity") or {}).get("max"),
        (p.get("quantity") or {}).get("value"),
        (p.get("quantity") or {}).get("current"),
        (p.get("uses") or {}).get("max"),
        (p.get("uses") or {}).get("value"),
        (p.get("uses") or {}).get("current"),
        default=0,
    ))

def _iter_all_nodes(data: dict):
    for p in (data.get("creatureProperties") or []):
        yield p
    for p in (data.get("creatureAttributes") or []):
        yield p

def _collect_spells_all(data: dict) -> List[str]:
    props = data.get("creatureProperties") or []
    tuples = []
    for p in props:
        if (p.get("type") == "spell") and p.get("name"):
            lvl = p.get("level")
            try: lvl = int(lvl)
            except: lvl = 99
            tuples.append((lvl, p["name"].strip()))
    seen = {}
    for lvl, name in tuples:
        seen[name.lower()] = (lvl, name)
    return [name for lvl, name in sorted(seen.values(), key=lambda t: (t[0], t[1].lower()))]

def _collect_spells_prepared(data: dict) -> List[str]:
    props = data.get("creatureProperties") or []
    prepared = []
    for p in props:
        if p.get("type") != "spell":
            continue
        flag = p.get("prepared") or p.get("isPrepared") or p.get("equipped")
        if (str(flag).strip().lower() in {"1", "true", "yes", "y", "on"}) or (flag is True):
            nm = (p.get("name") or "").strip()
            if nm:
                prepared.append(nm)
    uniq = {}
    for s in prepared:
        uniq[s.lower()] = s
    return sorted(uniq.values(), key=str.lower)

async def sync_spells_from_snapshot(cid: str, data: dict) -> dict:
    """
    Compute slot maxima and collect spells; write to:
      - slots_path(cid) (preserving used where possible)
      - characterSheet.json under 'slots' and 'spells'
    """
    # Build slots (max)
    store = json_safe_read(slots_path(cid), {str(i): {"max": 0, "used": 0} for i in range(1, 10)})
    for p in _iter_all_nodes(data):
        tags = [t.lower() for t in (p.get("libraryTags") or []) if isinstance(t, str)]
        a_type = (p.get("attributeType") or "").lower()
        lvl = _slot_level_from_node(p)
        looks_like_slot = ("spellslot" in tags) or (a_type == "spellslot")
        if not looks_like_slot and lvl is None:
            continue
        if lvl is None or not (1 <= lvl <= 9):
            lvl = _guess_level_from_name(p.get("name") or "")
            if lvl is None or not (1 <= lvl <= 9):
                continue
        max_v = _slot_max_from_node(p)
        if max_v <= 0:
            continue
        k = str(lvl)
        used_prev = int(store.get(k, {}).get("used", 0))
        store[k] = {"max": int(max_v), "used": min(used_prev, int(max_v))}

    json_safe_write(slots_path(cid), store)

    # Spells lists
    spells_all = _collect_spells_all(data)
    spells_prep = _collect_spells_prepared(data)
    json_safe_write(_sheet_path_for(cid), {
        **json_safe_read(_sheet_path_for(cid), {}),
        "slots": store,
        "spells": {"known": spells_all, "prepared": spells_prep},
    })
    # also persist a plain spells list (if you still want it)
    json_safe_write(_sheet_path_for(cid).with_name("spells.json"), {"list": spells_all})
    return {"slots": store, "spells": {"known": spells_all, "prepared": spells_prep}}
