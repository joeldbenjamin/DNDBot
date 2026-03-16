# sync_ammo_snapshot.py
from __future__ import annotations

async def sync_ammo_snapshot(cid: str, creature_data) -> dict:
    """
    No-op: we deliberately keep ammo out of characterSheet.json to avoid confusion.
    Downstream callers expecting a dict will get {}.
    """
    return {}
