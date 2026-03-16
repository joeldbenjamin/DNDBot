# bot.py
import os
import asyncio
import traceback
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands

from config import DISCORD_PREFIX

# ── Env setup ────────────────────────────────────────────────────────────────
# Load .env that sits next to this file, and override any existing env vars
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set")

# Heads-up for DiceCloud creds used by !sync
if not os.getenv("DC_USER") or not os.getenv("DC_PASS"):
    print("⚠️  Warning: DC_USER/DC_PASS not set in environment. !sync will fail until set.")

# ── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # required to read command text
bot = commands.Bot(command_prefix=DISCORD_PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    print(f"🌐 Connected to {len(bot.guilds)} guild(s).")

@bot.event
async def on_command_error(ctx, error):
    # Quietly ignore unknown commands so Avrae can coexist
    if isinstance(error, commands.CommandNotFound):
        return
    # Log full traceback to console for debugging
    traceback.print_exception(type(error), error, error.__traceback__)
    # Give a short notice in Discord so it never looks like “nothing happened”
    try:
        await ctx.send(f"⚠️ {type(error).__name__}: {error}")
    except Exception:
        pass

# ── Extension loading ────────────────────────────────────────────────────────
async def setup_all_extensions():
    """
    Load all cogs as extensions.
    Each module must expose:  async def setup(bot): await bot.add_cog(MyCog(bot))
    """
    extensions = [
        "sync_cog",
        "ammo_cog",
        "magic_cog",
        "calendar_cog",
        "avrae_watch_cog",
        "beast_cog",
        "whoami_cog",
        "help_cog",          # <- provides !helpDND / !helpdnd
        "dev_cog",           # <- !testAs (dev only)
    ]
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"✅ Loaded extension: {ext}")
        except Exception as e:
            print(f"❌ Failed to load extension {ext}: {e}")
            traceback.print_exc()

    # Print loaded commands for a quick sanity check
    try:
        names = sorted({c.name for c in bot.commands})
        print("📜 Loaded commands:", names)
    except Exception:
        pass

# ── Entrypoint ───────────────────────────────────────────────────────────────
async def main():
    await setup_all_extensions()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
