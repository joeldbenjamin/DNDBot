# modules_Ammo/ammo_sync.py
from __future__ import annotations
from typing import Dict, List, Tuple

from utils import _norm
from modules_Ammo.ammo_store import (
    ensure_ammo_schema, load_ammo_store, save_ammo_store,
)
from modules_Ammo.ammo_dc import (
    fetch_snapshot, find_quiver, list_ammo_items, totals_by_name,
    pick_active_id, name_by_id, read_quiver_contents,
)

def _sum_by_name(entries: Dict[str, int]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for nm, ct in (entries or {}).items():
        out[nm] = int(ct or 0)
    return out

async def seed_ammo_from_cache(cid: str, *, overwrite_counts: bool = False, purge_local: bool = False) -> dict:
    """
    Pull DC → write ammo.json.
      - _container (capacity) from DC quiver if present
      - if overwrite_counts: mirror DC quiver content into local quiver counts
      - ALWAYS set _stash exactly to DC stash = (DC totals - DC quiver)
      - if purge_local: also clear _fired and remove any manual::* entries
      - refresh active id to a sensible choice
    """
    data = await fetch_snapshot(cid)
    store = ensure_ammo_schema(load_ammo_store(cid))

    quiver_meta = find_quiver(data)
    if quiver_meta:
        store["_container"] = {
            "id": quiver_meta.get("id"),
            "name": quiver_meta.get("name") or "Quiver",
            "capacity": int(quiver_meta.get("capacity") or 20),
            "equipped": bool(quiver_meta.get("equipped")),
        }
    else:
        store.setdefault("_container", {"id": None, "name": "Quiver", "capacity": 20, "equipped": False})

    if purge_local:
        # clear fired + manual ids
        store["_fired"] = {}
        for k in list(store.keys()):
            if isinstance(k, str) and k.startswith("manual::"):
                store.pop(k, None)

    items = list_ammo_items(data)            # DC items with ids + quantities
    dc_totals = totals_by_name(items)        # display_name -> total across all places
    dc_quiver  = _sum_by_name(read_quiver_contents(data, (quiver_meta or {}).get("id")) or {})

    # --- Mirror quiver counts if asked ---
    if overwrite_counts:
        # zero local quiver
        for k in list(store.keys()):
            if isinstance(k, str) and not k.startswith("_"):
                store[k]["count"] = 0

        # map each DC quiver name onto an existing or new entry
        # we prefer staying with existing entries by display name
        for nm, cnt in dc_quiver.items():
            # find an existing entry by display name
            target_id = None
            for iid, info in store.items():
                if isinstance(iid, str) and not iid.startswith("_"):
                    if _norm(info.get("name","")) == _norm(nm):
                        target_id = iid
                        break
            if not target_id:
                # create a manual entry if we don't already have one
                target_id = f"manual::{_norm(nm)}"
                store.setdefault(target_id, {"name": nm, "count": 0})
            store[target_id]["name"]  = nm
            store[target_id]["count"] = int(cnt)

    # --- Stash from DC exactly: totals - quiver ---
    stash_exact: Dict[str, int] = {}
    all_names = set(dc_totals) | set(dc_quiver)
    for nm in all_names:
        stash_exact[nm] = max(0, int(dc_totals.get(nm, 0)) - int(dc_quiver.get(nm, 0)))

    # Write canonical stash (_stash) with display casing
    new_stash = {}
    for nm, ct in stash_exact.items():
        if int(ct) > 0:
            new_stash[_norm(nm)] = {"name": nm, "count": int(ct)}
    store["_stash"] = new_stash

    # --- Pick active ---
    # prefer an id that has >0 in quiver; fallback to any entry; fallback None
    candidates = [(iid, info) for iid, info in store.items()
                  if isinstance(iid, str) and not iid.startswith("_") and int(info.get("count",0)) > 0]
    if candidates:
        prefer = next((iid for iid, info in candidates if _norm(info.get("name","")) == "arrow"), candidates[0][0])
        store["_active"] = prefer
    elif not store.get("_active") or store.get(store.get("_active"), None) is None:
        # no good candidates – keep or clear
        store["_active"] = None

    save_ammo_store(cid, store)
    return store
