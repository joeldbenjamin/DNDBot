## Ammo System

The ammo system tracks ammunition per player in three buckets:

- **Quiver** – what you currently have “ready to fire” (subject to a capacity limit).
- **Stash** – total spare ammo you own but are not currently carrying in the quiver.
- **Fired** – shots you have taken that may later be recoverable.

Internally, ammo is stored per DiceCloud character ID using a JSON file with:

- Top‑level entries for each ammo type (ID → `{"name","count"}`).
- A `_container` entry with capacity and metadata.
- `_stash` and `_fired` entries for off‑quiver ammo.

You generally don’t need to know the details; you just interact via commands.

### Linking with DiceCloud

Before ammo commands work, you must be linked to a DiceCloud character:

- Use your existing `!dclink <dicecloud url>` style command (implemented in `dc.py`) to associate your Discord user ID with a DiceCloud character ID.
- Many ammo commands will refuse to run until you are linked and will respond with:
  - “You’re not linked. Use `!dclink <dicecloud url>` first.”

### Core flows

#### 1. Seeding ammo from DiceCloud

1. Link your character with `!dclink`.
2. Run `!sync` to pull your DiceCloud snapshot and mirror DiceCloud ammo into DNDBot’s ammo store.
3. After this, your quiver and stash are populated based on DiceCloud’s data.

#### 2. Viewing current ammo

- Run:

  ```text
  !ammo
  ```

- The bot shows an embed with:
  - Quiver contents.
  - Stash contents.
  - Fired counts.
  - Capacity and active ammo type.

#### 3. Adjusting ammo counts

- Add ammo:

  ```text
  !ammo +10 Arrows
  ```

  - Fills the quiver up to capacity.
  - Any extra beyond capacity goes to stash.

- Remove ammo:

  ```text
  !ammo -5 Arrows
  ```

  - Decrements ammo from quiver only (does not affect stash).

- Set a specific count:

  ```text
  !ammo set 20
  ```

  - Sets the active ammo’s quiver count to 20, respecting container capacity.

#### 4. Choosing active ammo

- Set which ammo type is “active”:

  ```text
  !ammoset Arrows
  ```

- The “active” ammo is:
  - The default target for `!ammo set`.
  - What `!attack` consumes when the weapon matches.

#### 5. Loading from stash to quiver

- Typical usage:

  ```text
  !ammoreload
  !ammoreload 10
  !ammoreload Arrows 20
  ```

- Behavior:
  - Moves ammo from stash → quiver.
  - Respects quiver capacity.
  - Can target either the active ammo or a named type (which becomes active).

#### 6. Collecting fired ammo

- Basic:

  ```text
  !ammocollect
  ```

  - Collects 50% (rounded up) of fired ammo of the active type.
  - Puts collected ammo back into quiver/stash based on capacity.
  - Discards the remaining 50%.

- Collect everything:

  ```text
  !ammocollect -all
  ```

  - Tries to collect all fired ammo (across types if you specify a name).

- Empty fired without collecting:

  ```text
  !ammocollect -empty
  ```

  - Clears all fired ammo, for all types.

#### 7. Unloading quiver back to stash

- Example:

  ```text
  !ammounload
  !ammounload 10
  !ammounload Arrows 15
  ```

- Behavior:
  - Moves ammo from quiver → stash.
  - Won’t unload more than is currently in the quiver.

### Attack integration

- Use:

  ```text
  !attack longbow
  ```

- Behavior:
  - If the weapon name (e.g. “longbow”) and your active ammo name (e.g. “arrows”) match according to a small heuristic map, the bot:
    - Decrements 1 from the active ammo in quiver.
    - Adds 1 to the fired bucket for that ammo.
  - If you don’t have enough ammo:
    - Shows an “Out of ammo!” embed with a configured image.
  - If the weapon doesn’t plausibly use the active ammo (e.g. `!attack shortsword` while arrows are active):
    - The bot **does nothing** and consumes no ammo.

### Custom weapon names

If your weapon or ammo names don’t follow the built‑in patterns (like “crossbow” ↔ “bolt”, “longbow” ↔ “arrow”), you can teach the bot how to match them.

#### Add a custom mapping

```text
!ammomap <weapon text> -> <ammo text>
```

Examples:

- `!ammomap hand crossbow -> bolt`
- `!ammomap laser rifle -> charge`

The bot will then treat any weapon whose name contains `<weapon text>` as using ammo whose name contains `<ammo text>`, for **your** user.

#### List your mappings

```text
!ammomaps
```

- Shows all custom weapon↔ammo mappings you’ve defined for your user.

#### Remove mappings

```text
!ammounmap <weapon text>
!ammounmap <weapon text> -> <ammo text>
```

- The first form removes **all** mappings for the given weapon text.
- The second form removes only the specific weapon+ammo pair.

