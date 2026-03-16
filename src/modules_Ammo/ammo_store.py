# modules_Ammo/ammo_store.py
from __future__ import annotations
from typing import Dict
import os, json
from dc import ammo_path

# ---- tiny safe json helpers (no external dependency) ----
def _json_safe_read(path: str) -> dict:
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _json_safe_write(path: str, data: dict):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))

# ---------------- core load/save ----------------
def load_ammo_store(cid: str) -> dict:
    p = ammo_path(cid)
    data = _json_safe_read(p) or {}
    return ensure_ammo_schema(data)

def save_ammo_store(cid: str, store: dict):
    p = ammo_path(cid)
    _json_safe_write(p, ensure_ammo_schema(store))

# --------------- schema & sanity ----------------
def ensure_ammo_schema(store: dict) -> dict:
    store = dict(store or {})
    store.setdefault("_container", {"id": None, "name": "Quiver", "capacity": 20, "equipped": False})
    store.setdefault("_active", None)
    store.setdefault("_fired", {})   # lower-case name -> int
    store.setdefault("_stash", {})   # lower-case name -> {"name": display, "count": int}

    # Normalise quiver entries (top-level keys that are not underscored)
    for k, v in list(store.items()):
        if isinstance(k, str) and not k.startswith("_"):
            if not isinstance(v, dict):
                store[k] = {"name": str(v), "count": 0}
            store[k].setdefault("name", "Ammo")
            store[k]["count"] = int(store[k].get("count", 0) or 0)

    # Normalise fired
    f = {}
    for k, v in (store.get("_fired") or {}).items():
        f[str(k).strip().lower()] = int(v or 0)
    store["_fired"] = f

    # Normalise stash
    s = {}
    for k, meta in (store.get("_stash") or {}).items():
        if isinstance(meta, dict):
            disp = (meta.get("name") or str(k)).strip()
            cnt  = int(meta.get("count", 0) or 0)
        else:
            disp = str(k)
            cnt  = int(meta or 0)
        s[disp.strip().lower()] = {"name": disp, "count": max(0, cnt)}
    store["_stash"] = s
    return store

# ----------------- fired helpers ----------------
def fired_get(store: dict, name: str) -> int:
    return int(store.get("_fired", {}).get(name.strip().lower(), 0))

def fired_add(store: dict, name: str, delta: int):
    k = name.strip().lower()
    store.setdefault("_fired", {})
    store["_fired"][k] = max(0, int(store["_fired"].get(k, 0)) + int(delta))

def fired_set(store: dict, name: str, value: int):
    k = name.strip().lower()
    store.setdefault("_fired", {})
    store["_fired"][k] = max(0, int(value))

def fired_all(store: dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k, v in (store.get("_fired") or {}).items():
        # try to display with nice casing if we can find it in stash or quiver
        disp = None
        st = store.get("_stash") or {}
        if k in st:
            disp = (st[k] or {}).get("name")
        if not disp:
            for iid, info in (store or {}).items():
                if isinstance(iid, str) and not iid.startswith("_"):
                    if str(info.get("name","")).strip().lower() == k:
                        disp = info.get("name")
                        break
        out[disp or k] = int(v or 0)
    return out

# --------------- quiver math helpers ------------
def total_quiver_count(store: dict) -> int:
    total = 0
    for k, v in (store or {}).items():
        if isinstance(k, str) and not k.startswith("_"):
            total += int((v or {}).get("count", 0) or 0)
    return total

def count_for_name_in_quiver(store: dict, display_name: str) -> int:
    want = display_name.strip().lower()
    c = 0
    for k, v in (store or {}).items():
        if isinstance(k, str) and not k.startswith("_"):
            if str(v.get("name","")).strip().lower() == want:
                c += int(v.get("count", 0) or 0)
    return c

# ----------------- stash helpers ----------------
def stash_all(store: dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k, meta in (store.get("_stash") or {}).items():
        if not isinstance(meta, dict):
            out[str(k)] = int(meta or 0)
        else:
            out[meta.get("name") or k] = int(meta.get("count", 0) or 0)
    return out

def stash_get(store: dict, name: str) -> int:
    k = name.strip().lower()
    meta = (store.get("_stash") or {}).get(k) or {}
    return int(meta.get("count", 0) or 0)

def stash_set(store: dict, name: str, value: int):
    k = name.strip().lower()
    disp = name
    store.setdefault("_stash", {})
    if value <= 0:
        store["_stash"].pop(k, None)
    else:
        store["_stash"][k] = {"name": disp, "count": int(value)}

def stash_add(store: dict, name: str, delta: int):
    if int(delta) == 0:
        return
    cur = stash_get(store, name)
    stash_set(store, name, max(0, cur + int(delta)))
