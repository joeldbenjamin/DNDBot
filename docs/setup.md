## Setup & Configuration

### Prerequisites

- Python **3.11+**
- A Discord application with a **bot token**
- (Recommended) A DiceCloud account for players using DiceCloud sheets

### Local installation

1. **Clone the repository** and open the project.
2. Create and activate a virtual environment (recommended).
3. From the `src/` directory, install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file **next to `bot.py`** (`src/.env`) with at least:

   ```bash
   DISCORD_TOKEN=your_discord_bot_token
   DC_USER=your_dicecloud_username
   DC_PASS=your_dicecloud_password
   # Optional:
   # DC_CACHE_TTL=900          # seconds, default 900
   # DISCORD_PREFIX=!         # default "!"
   ```

5. Run the bot from `src/`:

   ```bash
   python bot.py
   ```

### Running with Docker

From the `src/` directory:

```bash
docker build -t dndbot .
docker run --env-file .env dndbot
```

### Environment variables

- **`DISCORD_TOKEN`**: Required. Bot token from the Discord Developer Portal.
- **`DC_USER`, `DC_PASS`**: Required for DiceCloud sync. Credentials for the DiceCloud service user the bot uses to fetch character data.
- **`DC_CACHE_TTL`** (optional): How long (in seconds) DiceCloud snapshots are cached before refresh. Default is `900`.
- **`DISCORD_PREFIX`** (optional): Command prefix. Defaults to `"!"`.

