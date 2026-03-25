import os

AGENT_NAME       = os.getenv("AGENT_NAME",        "sentinel")
DATABASE_URL     = os.getenv("DATABASE_URL",       "")
AGENT_SECRET     = os.getenv("AGENT_SECRET",       "")
VPS_URL          = os.getenv("VPS_URL",            "")
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK_URL","")
DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN",      "")
DISCORD_CHANNEL  = os.getenv("DISCORD_CHANNEL_ID", "")
IB_HOST          = os.getenv("IB_HOST",            "127.0.0.1")
IB_PORT          = int(os.getenv("IB_PORT",        "4001"))
IB_ACCOUNT       = os.getenv("IB_ACCOUNT",        "")
