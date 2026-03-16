## DiceCloud Sync

DNDBot integrates with DiceCloud to keep your character’s key stats and ammo in sync.

### Linking a character

Before any sync can happen, you must link your Discord user to a DiceCloud character:

- Use your existing link command (typically something like):

  ```text
  !dclink https://dicecloud.com/character/<id>
  ```

- This stores a mapping from your Discord user ID to the DiceCloud character ID.
- If you are not linked, sync and ammo commands will respond with a message like:
  - “You’re not linked. Use `!dclink <dicecloud url>` first.”

### How caching works

- DiceCloud snapshots are cached on disk per character.
- The cache lives under a `cache_dc/` directory and includes JSON files for:
  - Character sheet
  - Ammo
  - Spells
  - Metadata, etc.
- The `DC_CACHE_TTL` environment variable controls how long (in seconds) the cache is considered fresh:
  - Default: `900` seconds (15 minutes).
  - After TTL expires, the next `!sync` will refresh from DiceCloud again (unless forced).

### `!sync` workflow

The main entry point for sync is the `!sync` command:

```text
!sync
!sync force
!sync -purge
```

Under the hood, `!sync` does the following:

1. **Locate your DiceCloud ID**
   - Looks up your Discord user ID in the DiceCloud link map.
2. **Refresh snapshot**
   - Calls `dc_get_creature_cached(...)` to load your character snapshot:
     - Uses the cache if fresh.
     - If expired or forced, fetches from DiceCloud and rewrites the cache.
3. **Sync profile**
   - Passes the snapshot to `sync_profile.sync_profile_from_snapshot(...)`.
   - Mirrors key profile fields into a local representation (e.g. AC, HP, classes, photo).
4. **Mirror ammo**
   - Calls the ammo sync helper to mirror DiceCloud quiver + stash into DNDBot’s ammo store.
   - If `-purge` is used, local fired & stash are cleared before mirroring.
5. **Show a summary embed**
   - Sends a nicely formatted embed to the channel summarizing:
     - Character name.
     - Classes and level.
     - Proficiency bonus, AC, HP.
     - Companion HP, if present.
     - Which ammo sync behavior was used (plain vs purge).

### Force and purge options

- **`!sync`**
  - Uses cache if still fresh.
  - Leaves local fired/stash counts intact, only updates ammo from DiceCloud.

- **`!sync force`**
  - Bypasses TTL: always calls DiceCloud, then rewrites cache.

- **`!sync -purge`**
  - Same as `!sync`, but before mirroring ammo:
    - Clears local fired & stash.
    - Then mirrors DiceCloud ammo into the now‑clean local store.

You can combine these for heavy refresh scenarios, for example:

```text
!sync force -purge
```

(Exact argument parsing order may vary; see the implementation of `sync_cog` if you need precise details.)

