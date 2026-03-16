# dc.py
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

from config import DC_BASE, DC_CACHE_DIR, DC_CACHE_TTL, DCLINKS_FILE
from utils import json_safe_write, json_safe_read


# ---------- paths ----------
def _cid_dir(cid: str) -> Path:
    d = DC_CACHE_DIR / cid
    d.mkdir(parents=True, exist_ok=True)
    return d

def cache_path(cid: str) -> Path:   return _cid_dir(cid) / "creature.json"
def meta_path(cid: str) -> Path:    return _cid_dir(cid) / "metadata.json"
def ammo_path(cid: str) -> Path:    return _cid_dir(cid) / "ammo.json"
def slots_path(cid: str) -> Path:   return _cid_dir(cid) / "slots.json"
def spells_path(cid: str) -> Path:  return _cid_dir(cid) / "spells.json"
def beast_path(cid: str) -> Path:  return _cid_dir(cid) / "beast.json"

# ---------- link storage ----------
dc_links = json_safe_read(DCLINKS_FILE, {})

def save_dc_links() -> None:
    json_safe_write(DCLINKS_FILE, dc_links)


# ---------- utils ----------
def dc_extract_id(url_or_id: str) -> str:
    """Accepts a full DiceCloud URL or a bare ID and returns the ID."""
    s = (url_or_id or "").strip().rstrip("/")
    # https://dicecloud.com/character/<ID>/Optional-Name
    if "/character/" in s:
        s = s.split("/character/", 1)[1]
        s = s.split("/", 1)[0]
    return s


# ---------- HTTP client ----------
class DiceCloudClient:
    """
    Very small DiceCloud API client.
    NOTE: Environment variables (DC_USER/DC_PASS) are read when this module is imported.
    bot.py loads .env FIRST, then imports this module, so the creds are available.
    """
    def __init__(self, base: str = DC_BASE, user_env: str = "DC_USER", pass_env: str = "DC_PASS"):
        self.base = base
        self._user = os.getenv(user_env)
        self._pass = os.getenv(pass_env)
        self._token: Optional[str] = None

    async def login(self, session: aiohttp.ClientSession) -> None:
        if not self._user or not self._pass:
            raise RuntimeError("DC_USER / DC_PASS not set")
        r = await session.post(f"{self.base}/api/login", json={
            "username": self._user,
            "password": self._pass
        })
        r.raise_for_status()
        data = await r.json()
        self._token = data["token"]

    async def get_creature(self, creature_id: str) -> dict:
        async with aiohttp.ClientSession() as s:
            if not self._token:
                await self.login(s)
            headers = {"Authorization": f"Bearer {self._token}"}
            r = await s.get(f"{self.base}/api/creature/{creature_id}", headers=headers)
            if r.status == 401:
                # token expired → re-login and retry once
                self._token = None
                await self.login(s)
                headers = {"Authorization": f"Bearer {self._token}"}
                r = await s.get(f"{self.base}/api/creature/{creature_id}", headers=headers)
            r.raise_for_status()
            return await r.json()


dc = DiceCloudClient()


# ---------- cache helpers ----------
def _load_cache(cid: str):
    p = cache_path(cid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _cache_is_fresh(payload: dict, ttl: int = DC_CACHE_TTL) -> bool:
    ts = (payload or {}).get("fetched_at")
    if not ts:
        return False
    try:
        fetched = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - fetched).total_seconds()
    return age < ttl

def _save_cache(cid: str, data: dict) -> None:
    p = cache_path(cid)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }
    json_safe_write(p, payload)
    # also write metadata with creature name for readability
    try:
        creature = (data.get("creatures") or [{}])[0]
        name = creature.get("name") or "Unknown Creature"
        json_safe_write(meta_path(cid), {"name": name})
    except Exception:
        pass


# ---------- public API ----------
async def dc_get_creature_cached(cid: str, *, ttl: int = DC_CACHE_TTL, force: bool = False) -> dict:
    """
    Return the creature dict, using on-disk cache unless `force` or stale.
    The on-disk file at cache_path(cid) stores:
      { "fetched_at": "...Z", "data": {... full DiceCloud payload ...} }
    """
    cached = _load_cache(cid)
    if not force and _cache_is_fresh(cached, ttl):
        return cached["data"]
    data = await dc.get_creature(cid)
    _save_cache(cid, data)
    return data
