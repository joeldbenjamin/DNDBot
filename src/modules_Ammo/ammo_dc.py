# modules_Ammo/ammo_dc.py
from __future__ import annotations
from typing import Dict, List, Optional, Any
from utils import _norm
from dc import dc_get_creature_cached

AMMO_WORDS = ("arrow", "bolt", "bullet")


# ---------------- basic helpers ----------------
def _is_ammo_name(name: str) -> bool:
    n = _norm(name)
    return any(w in n for w in AMMO_WORDS)


def _read_quantity_field(q) -> int:
    """
    Be tolerant: child entries sometimes store counts in different keys or shapes.
    """
    if isinstance(q, dict):
        for k in ("value", "current", "available", "max", "maximum", "total", "count", "usesRemaining"):
            if k in q:
                try:
                    return int(q[k])
                except Exception:
                    pass
    try:
        return int(q)
    except Exception:
        return 0


def _first_str(*vals) -> Optional[str]:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# -------------- snapshot access ----------------
async def fetch_snapshot(cid: str) -> dict:
    return await dc_get_creature_cached(cid)


# ---------------- inventory flattening ----------------
def _yield_children(obj: dict):
    """
    Yield any item-like children collections that DiceCloud might use.
    """
    for key in ("contents", "containedItems", "children", "items", "contains", "childItems"):
        lst = obj.get(key)
        if isinstance(lst, list) and lst:
            for it in lst:
                if isinstance(it, dict):
                    yield it


def _as_item_row(d: dict) -> Optional[Dict[str, Any]]:
    """
    Convert a dict to a normalized item row if it looks like an item entry.
    Many child entries do not have type='item' but still act like items.
    """
    if not isinstance(d, dict):
        return None

    # A lot of actual inventory rows have type='item'
    is_item = (d.get("type") == "item")
    # but child rows might not — detect by the presence of a name and maybe quantity
    name = _first_str(d.get("name"), d.get("itemName"), d.get("tag"))
    has_name = isinstance(name, str) and name.strip()

    if not (is_item or has_name):
        return None

    # Normalize fields
    iid = d.get("_id") or d.get("id") or d.get("itemId")
    qty = 0

    # Preferred quantity field on full items
    if "quantity" in d:
        qty = _read_quantity_field(d.get("quantity"))
    else:
        # child entries often use these:
        for k in ("count", "available", "usesRemaining", "value", "current", "max", "total"):
            if k in d:
                qty = _read_quantity_field(d.get(k))
                break

    if not isinstance(qty, int):
        try:
            qty = int(qty)
        except Exception:
            qty = 0

    row = {
        "id": iid,
        "name": name or "Item",
        "qty": int(qty),
        "parent": (d.get("parent") or {}).get("id") or None,
        "ancestors": list(d.get("ancestors") or []),
        "type": d.get("type") or "item",
    }
    return row


def _walk_items_from_props(props: list, out: List[Dict[str, Any]]):
    for d in props:
        row = _as_item_row(d)
        if row:
            out.append(row)
        for ch in _yield_children(d or {}):
            row = _as_item_row(ch)
            if row:
                out.append(row)


def list_ammo_items(data: dict) -> List[Dict[str, Any]]:
    """
    Return a flat list of normalized item-like rows, including nested children.
    """
    rows: List[Dict[str, Any]] = []

    # main arrays DiceCloud tends to use
    for key in ("creatureProperties", "inventory", "items", "properties"):
        base = data.get(key)
        if isinstance(base, list):
            _walk_items_from_props(base, rows)

    # occasionally DC nests a "containers" or "childItems" at top level
    for key in ("containers", "childItems"):
        for d in (data.get(key) or []):
            row = _as_item_row(d)
            if row:
                rows.append(row)

    ammo_rows = [r for r in rows if _is_ammo_name(r.get("name", "")) and int(r.get("qty", 0)) > 0]

    # Deduplicate identical rows (same id) by summing quantities
    by_id: Dict[Optional[str], Dict[str, Any]] = {}
    for r in ammo_rows:
        k = r.get("id")
        if k in by_id:
            by_id[k]["qty"] += int(r["qty"])
        else:
            by_id[k] = dict(r)
    return list(by_id.values())


def totals_by_name(items: List[Dict[str, Any]]) -> Dict[str, int]:
    tot: Dict[str, int] = {}
    for it in items:
        nm = it.get("name") or "Ammo"
        tot[nm] = tot.get(nm, 0) + int(it.get("qty") or 0)
    return tot


def name_by_id(items: List[Dict[str, Any]], iid: Optional[str]) -> Optional[str]:
    for it in items:
        if it.get("id") == iid:
            return it.get("name")
    return None


def pick_active_id(items: List[Dict[str, Any]]) -> Optional[str]:
    """
    Prefer 'Arrow' if present; else any first id.
    """
    if not items:
        return None
    arrow = next((it for it in items if _norm(it.get("name","")) == "arrow"), None)
    return (arrow or items[0]).get("id")


# ---------------- quiver helpers ----------------
def find_quiver(data: dict) -> Optional[Dict[str, Any]]:
    """
    Return a quiver-like container and capacity (fallback to 20 if missing).
    Prefer returning the *container* id for counting contents. If the quiver
    is represented only as an item without a separate container child, we fall
    back to the item id.
    """
    props = data.get("creatureProperties") or []
    quivers = []
    for p in props:
        if p.get("type") == "item" and "quiver" in _norm(p.get("name") or ""):
            equipped = bool(p.get("equipped") or p.get("isEquipped") or p.get("worn"))
            quivers.append((p, equipped))
    if not quivers:
        return None

    chosen = next((p for p, e in quivers if e), quivers[0][0])

    # Capacity (best-effort across a few common fields)
    capacity = 20
    for key in ("capacity", "maxCapacity", "limit", "max", "available"):
        v = chosen.get(key)
        try:
            if v is not None:
                capacity = int(v)
                break
        except Exception:
            pass

    # Prefer the *container* child of the chosen item for counting contents
    chosen_item_id = chosen.get("_id") or chosen.get("id")
    container_id = None
    for q in props:
        if q.get("type") == "container" and (q.get("parent") or {}).get("id") == chosen_item_id:
            if "quiver" in _norm(q.get("name") or chosen.get("name") or ""):
                container_id = q.get("_id") or q.get("id")
                break

    return {
        # id used for counting contents; fall back to the item id if no container found
        "id": container_id or chosen_item_id,
        "name": chosen.get("name") or "Quiver",
        "capacity": int(capacity or 20),
        "equipped": any(e for _, e in quivers),
    }


def read_quiver_contents(data: dict, quiver_id: Optional[str]) -> Dict[str, int]:
    """
    Return {name -> count} for ammo items actually inside the quiver container.
    Handles:
      1) explicit child lists on the quiver item
      2) flat items elsewhere whose parent/ancestors reference the quiver id
    """
    out: Dict[str, int] = {}

    def _add(nm: str, q):
        nm = (nm or "").strip()
        if not _is_ammo_name(nm):
            return
        cnt = _read_quantity_field(q)
        if cnt <= 0:
            return
        out[nm] = out.get(nm, 0) + int(cnt)

    props = data.get("creatureProperties") or []

    # If given the *item* id, switch to the container child id if present
    if quiver_id:
        for q in props:
            if q.get("type") == "container" and (q.get("parent") or {}).get("id") == quiver_id:
                quiver_id = q.get("_id") or q.get("id")
                break

    # Style 1: child lists directly on the quiver item
    target = None
    if quiver_id:
        for p in props:
            if p.get("type") != "item":
                continue
            pid = p.get("_id") or p.get("id")
            if pid and pid == quiver_id:
                target = p
                break
    if not target:
        for p in props:
            if p.get("type") == "item" and "quiver" in _norm(p.get("name") or ""):
                target = p
                break

    if target:
        for ch in _yield_children(target):
            nm = _first_str(ch.get("name"), ch.get("itemName"), ch.get("tag"))
            q = ch.get("quantity", None)
            if q is None:
                q = ch.get("count") or ch.get("available") or ch.get("usesRemaining")
            _add(nm, q)

    # Style 2: separate item rows whose parent/ancestors reference the quiver
    def _has_ancestor(p, qid: str) -> bool:
        for anc in (p.get("ancestors") or []):
            if anc.get("id") == qid:
                return True
        # also handle parent pointer directly
        if (p.get("parent") or {}).get("id") == qid:
            return True
        return False

    if quiver_id:
        for p in props:
            if p.get("type") != "item":
                continue
            parent_ok = (p.get("parent") or {}).get("id") == quiver_id
            anc_ok = _has_ancestor(p, quiver_id)
            if not (parent_ok or anc_ok):
                continue
            nm = _first_str(p.get("name"), p.get("itemName"), p.get("tag"))
            _add(nm, p.get("quantity"))

    return out
