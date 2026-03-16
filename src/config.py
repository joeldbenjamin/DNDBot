from pathlib import Path
import os

# Bot
DISCORD_PREFIX = os.getenv("DISCORD_PREFIX", "!")

# Paths
ROOT = Path(__file__).resolve().parent
DATA_FILE    = ROOT / "game_state.json"
QUOTES_FILE  = ROOT / "quotes.json"
EVENTS_FILE  = ROOT / "events.json"
DCLINKS_FILE = ROOT / "dicecloud_links.json"

# Calendar campaigns (one active campaign globally; legacy = no campaign, use DATA_FILE/EVENTS_FILE)
CALENDARS_DIR = ROOT / "data" / "calendars"
ACTIVE_CAMPAIGN_FILE = CALENDARS_DIR / "active.json"

# DiceCloud / Cache
DC_BASE = "https://dicecloud.com"
DC_CACHE_DIR = ROOT / "cache_dc"
DC_CACHE_DIR.mkdir(exist_ok=True)
DC_CACHE_TTL = int(os.getenv("DC_CACHE_TTL", "900"))  # seconds

# Embed/style
EMBED_COLOR = 0x5865F2
FOOTER_TEXT = "D-D Bot"
COMMAND_IMAGE_URL = "https://s.mj.run/12ghvmj07l4"
OUT_OF_AMMO_IMG   = "https://s.mj.run/NpqOAqJ-Agk"

# Calendar (US-style input; display Weekday, MM/DD/YYYY)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]
MONTH_LENGTHS = [31,28,31,30,31,30,31,31,30,31,30,31]  # no leap years

# Avrae
AVRAE_ID = 261302296103747584
NAT1_IMG = "https://cdn.discordapp.com/attachments/1162858211217526914/1398319125381779517/joeldbenjamin_a_painting_of_an_old_dd_angry_demonic_god_76d15644-936c-4577-a531-37c7327a6660.png?ex=6884edab&is=68839c2b&hm=0614e0f804d584ec029fd8c42c3ecb5736deb7d70f7dfcdb17cee974b6517276&"
NAT20_IMG = "https://cdn.discordapp.com/attachments/1162858211217526914/1398320063253319762/joeldbenjamin_a_painting_of_an_old_dd_pleased_smiling_mysteriou_4607e154-06d6-45a4-9816-84050e3acecd.png?ex=6884ee8a&is=68839d0a&hm=30ca081282fd9ea640764232c3aa32f5f1665750c75334d2213a58801afd73df&"
