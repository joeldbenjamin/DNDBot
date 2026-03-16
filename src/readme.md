## DNDBot

A Discord bot to assist with D&D play, including DiceCloud sync, ammo tracking, calendar utilities, and more.

### Prerequisites

- Python 3.11+
- A Discord bot token

### Setup (local)

1. Create and activate a virtual environment.
2. From the `src/` directory, install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file next to `bot.py` with at least:

   ```bash
   DISCORD_TOKEN=your_discord_bot_token
   DC_USER=your_dicecloud_username
   DC_PASS=your_dicecloud_password
   # Optional:
   # DC_CACHE_TTL=900
   # DISCORD_PREFIX=!
   ```

4. Run the bot from `src/`:

   ```bash
   python bot.py
   ```

### Running with Docker

From the `src/` directory:

```bash
docker build -t dndbot .
docker run --env-file .env dndbot
```

### Documentation

For full documentation, see the `docs/` folder:

- `docs/index.md` – overview.
- `docs/setup.md` – installation and configuration.
- `docs/commands.md` – full command reference.
- `docs/ammo.md` – ammo system details.
- `docs/sync.md` – DiceCloud sync flow.
- `docs/calendar.md` – calendar and campaign helpers.
