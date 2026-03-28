import os

# Lecture simple — aucun fail-fast ici
# Railway injecte les variables au runtime uniquement, pas au build
# La vérification se fait dans main.py via check_vars()

DATABASE_URL     = os.getenv("DATABASE_URL",        "")
DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN",       "")
AGENT_SECRET     = os.getenv("AGENT_SECRET",        "")
VPS_URL          = os.getenv("VPS_URL",             "")
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK_URL", "")
AGENT_NAME       = os.getenv("AGENT_NAME",          "sentinel")

DISCORD_CHANNEL_STR = os.getenv("DISCORD_CHANNEL_ID", "0")
DISCORD_CHANNEL     = int(DISCORD_CHANNEL_STR) if DISCORD_CHANNEL_STR.isdigit() else 0

IB_HOST          = os.getenv("IB_HOST",    "127.0.0.1")
IB_PORT          = int(os.getenv("IB_PORT", "4001"))
IB_ACCOUNT       = os.getenv("IB_ACCOUNT", "")
