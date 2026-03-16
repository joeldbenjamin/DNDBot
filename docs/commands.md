## Command Reference

This page summarizes the main commands exposed by DNDBot. The actual prefix defaults to `!` but is configurable via `DISCORD_PREFIX`.

> In the examples below, `!` is used as the prefix.

### Sync commands

- **`!sync`**
  - **Description**: Refreshes your DiceCloud snapshot and mirrors ammo from DiceCloud into the local ammo store.
  - **Usage**:
    - `!sync` – refresh from DiceCloud cache (respects TTL) and mirror ammo.
    - `!sync force` – force-refresh DiceCloud now, bypassing cache TTL.
    - `!sync -purge` – same as `!sync`, but also clears local fired & stash before mirroring.

### Ammo commands

See more detail in [`ammo.md`](./ammo.md).

- **`!ammo`**
  - **Description**: Show or adjust quiver / stash / fired ammo.
  - **Usage**:
    - `!ammo` – show quiver, fired, and stash.
    - `!ammo -help` – show an embed with full ammo help.
    - `!ammo +N [Name]` – add `N` ammo of `Name` (fill quiver, overflow → stash).
    - `!ammo -N [Name]` – remove `N` ammo from quiver (does not affect stash).
    - `!ammo set N` – set quiver count for the active ammo, respecting capacity.

- **`!ammoset <name>`**
  - **Description**: Choose the **active** ammo type (must already be in quiver with count > 0).

- **`!ammoreload`**
  - **Description**: Move ammo from **stash** into **quiver**, up to container capacity.
  - **Usage**:
    - `!ammoreload` – fill quiver with **active** ammo from stash.
    - `!ammoreload N` – load exactly `N` of the active type from stash.
    - `!ammoreload <name>` – fill quiver with that type (also sets it as active).
    - `!ammoreload <name> N` – load exactly `N` of that type from stash.

- **`!ammocollect`**
  - **Description**: Move spent ammo from **fired** back into **quiver** and **stash**.
  - **Usage**:
    - `!ammocollect` – collect 50% (round up) of fired ammo, discard the rest.
    - `!ammocollect -all` – collect all fired ammo (then clear fired).
    - `!ammocollect N` – collect exactly `N` of the active type.
    - `!ammocollect -empty` – empty all fired ammo (for all types), no collection.

- **`!ammounload`**
  - **Description**: Move ammo from **quiver** back into **stash**.
  - **Usage**:
    - `!ammounload` – unload **all** of the active type.
    - `!ammounload N` – unload exactly `N` of the active type.
    - `!ammounload <name> N` – unload exactly `N` of the named type.

- **`!attack <weapon>`**
  - **Description**: Avrae-style helper that decrements the active ammo when you attack with a weapon that plausibly uses that ammo (e.g. longbow ↔ arrows).
  - **Behavior**:
    - If the weapon name and active ammo name “match” heuristically, the bot decrements 1 ammo and records it as fired.
    - If you have no ammo left, it shows an “out of ammo” embed.
    - If the weapon doesn’t match the active ammo, **no ammo is consumed**.

### Calendar / campaign commands

These are inferred from the code structure and `config.py`; customize this section to match your actual calendar cog implementation.

- **`!calendar ...`** (example)
  - Likely lives in `calendar_cog.py` and uses the month and weekday constants from `config.py`.
  - Typical patterns include:
    - Showing the current in‑world date.
    - Advancing days / months.
    - Setting an active campaign.
  - Once you finalize command names/usage, document them here.

### Utility commands

Exact names may vary by cog, but common patterns are:

- **Help**:
  - A dedicated help cog (`help_cog.py`) provides `!helpDND` / `!helpdnd` for DNDBot‑specific help, separate from Avrae.
- **Who‑am‑I**:
  - `whoami_cog.py` usually exposes a command that echoes your DiceCloud link status and character identity.
- **Dev commands**:
  - `dev_cog.py` contains developer‑only helpers such as impersonation (`!testAs`) for testing.

