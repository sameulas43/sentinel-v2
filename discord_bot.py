"""
SENTINEL V2.0 — Bot Discord
Seule instance Discord active.

Corrections appliquées :
1. handle_approval() appelé via asyncio.to_thread() dans approve/reject
   → évite de bloquer la boucle Discord (DB + HTTP + flow peuvent être lents)
2. call_from_thread() vérifie bot.is_ready() avec retry (max 30s)
   → les threads strategy/manager démarrent avant que Discord soit connecté
3. Strategy démarre APRÈS l'événement on_ready via asyncio.to_thread
   → garantit que bot.loop est prêt avant le premier appel Discord
"""
import os
import asyncio
import threading
import discord
from discord.ext import commands
from datetime import datetime, timezone

from core.logger import get_logger
from core.database import fetch_one
from agents.memory import save_event

log = get_logger("discord_bot")

TOKEN      = os.getenv("DISCORD_TOKEN",      "")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flag pour signaler que le bot est prêt
_bot_ready = threading.Event()


# ─── Thread safety ────────────────────────────────────────────────────────────

def call_from_thread(coro, timeout: int = 10):
    """
    Soumet une coroutine depuis un thread non-async.
    Attend que le bot soit prêt (max 30s) avant d'envoyer.
    Utilise run_coroutine_threadsafe sur bot.loop (thread principal).
    """
    # Retry : attend que le bot soit ready (max 30 secondes)
    ready = _bot_ready.wait(timeout=30)
    if not ready:
        raise RuntimeError(
            "Bot Discord pas prêt après 30s — "
            "vérifier DISCORD_TOKEN et connexion réseau."
        )
    future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return future.result(timeout=timeout)


def send_approval_request_sync(decision: dict):
    """Chemin unique pour les validations humaines."""
    call_from_thread(_send_approval_async(decision), timeout=15)


def send_message_sync(content: str):
    """Notifications informatives depuis un thread non-async."""
    try:
        call_from_thread(_send_message_async(content), timeout=10)
    except Exception as e:
        log("discord_bot.send_error", {"error": str(e)}, level="warning")
        _webhook_fallback(content)


def _webhook_fallback(content: str):
    """Fallback webhook — notifications non-critiques uniquement."""
    if not WEBHOOK:
        return
    try:
        import requests
        requests.post(WEBHOOK, json={"content": content}, timeout=5)
    except Exception as e:
        log("discord_bot.webhook_error", {"error": str(e)}, level="error")


# ─── Coroutines internes ──────────────────────────────────────────────────────

async def _send_approval_async(decision: dict):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        log("discord_bot.channel_not_found", {"channel_id": CHANNEL_ID}, level="error")
        return

    did8 = str(decision["decision_id"])[:8]
    mode = "PAPER" if decision.get("paper_mode") else "LIVE"

    embed = discord.Embed(title=f"ORDRE A VALIDER — #{did8}", color=0xC9A84C)
    embed.add_field(name="Ticker",  value=decision["ticker"],               inline=True)
    embed.add_field(name="Action",  value=decision["action"],               inline=True)
    embed.add_field(name="Montant", value=f"{decision['montant_eur']}EUR",  inline=True)
    embed.add_field(name="Broker",  value=decision.get("broker", "IBKR"),   inline=True)
    embed.add_field(name="Mode",    value=mode,                             inline=True)
    embed.add_field(name="Score",   value=f"{decision.get('score',0)}/100", inline=True)
    embed.add_field(name="Raison",  value=decision.get("raison", ""),       inline=False)
    embed.set_footer(text=f"decision_id: {decision['decision_id']} | Expire dans 2h")

    view = ApprovalView(str(decision["decision_id"]))
    await channel.send(embed=embed, view=view)
    log("discord_bot.approval_sent", {"decision_id": decision["decision_id"]})


async def _send_message_async(content: str):
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(content)


# ─── ApprovalView ─────────────────────────────────────────────────────────────

class ApprovalView(discord.ui.View):
    """
    Boutons / .
    Correction 1 : handle_approval() via asyncio.to_thread()
    → ne bloque pas la boucle Discord (DB + HTTP peuvent être lents).
    """

    def __init__(self, decision_id: str):
        super().__init__(timeout=7200)
        self.decision_id = decision_id
        self.handled     = False

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if self.handled:
            await interaction.response.send_message("Deja traite.", ephemeral=True)
            return True

        row = fetch_one(
            "SELECT status, samed_choice FROM decisions WHERE decision_id = %s",
            (self.decision_id,)
        )
        if not row:
            await interaction.response.send_message("Decision introuvable.", ephemeral=True)
            return True

        terminal = {
            "executed", "cancelled", "rejected_human",
            "execution_failed", "rejected_validation", "blocked_risk",
        }
        if (row["status"] in terminal
                or row.get("samed_choice") in ("approved", "rejected", "timeout")):
            await interaction.response.send_message(
                f"Deja traitee (`{row['status']}`).", ephemeral=True
            )
            return True

        return False

    @discord.ui.button(label="VALIDER", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        if await self._guard(interaction):
            return

        self.handled = True
        self.stop()
        _disable_all(self)

        log("discord_bot.approved", {
            "decision_id": self.decision_id,
            "user":        str(interaction.user),
        })
        save_event("discord.approved", "discord", self.decision_id,
                   {"user": str(interaction.user)})

        # Réponse immédiate à Discord
        await interaction.response.edit_message(
            content=(
                f"Valide par {interaction.user.display_name} "
                f"a {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                f"└ `{self.decision_id[:8]}` → Execution Agent..."
            ),
            view=self,
        )

        # handle_approval via asyncio.to_thread — ne bloque pas la boucle Discord
        from core.flow import handle_approval
        result = await asyncio.to_thread(handle_approval, self.decision_id, True)

        if result.get("status") == "filled":
            suffix = f"execute @ {result.get('avg_price', '?')}"
        elif result.get("status") == "submitted":
            suffix = "soumis a IB, en attente de fill"
        else:
            suffix = f"echec : {result.get('reason', result.get('status', '?'))}"

        await interaction.edit_original_response(
            content=(
                f"Valide par {interaction.user.display_name}\n"
                f"└ `{self.decision_id[:8]}` — {suffix}"
            )
        )

    @discord.ui.button(label="REFUSER", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        if await self._guard(interaction):
            return

        self.handled = True
        self.stop()
        _disable_all(self)

        log("discord_bot.rejected", {
            "decision_id": self.decision_id,
            "user":        str(interaction.user),
        })
        save_event("discord.rejected", "discord", self.decision_id,
                   {"user": str(interaction.user)})

        # handle_approval via asyncio.to_thread — ne bloque pas la boucle Discord
        from core.flow import handle_approval
        await asyncio.to_thread(handle_approval, self.decision_id, False)

        await interaction.response.edit_message(
            content=(
                f"Refuse par {interaction.user.display_name} "
                f"a {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                f"└ `{self.decision_id[:8]}` — archive"
            ),
            view=self,
        )

    async def on_timeout(self):
        self.stop()
        _disable_all(self)
        log("discord_bot.view_timeout", {"decision_id": self.decision_id})


def _disable_all(view: discord.ui.View):
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.disabled = True


# ─── Commandes ────────────────────────────────────────────────────────────────

@bot.command(name="status")
async def cmd_status(ctx):
    from agents.memory import get_pending
    pending = get_pending()
    if not pending:
        await ctx.send("Aucune decision en attente.")
        return
    lines = [f"{len(pending)} decision(s) en attente :"]
    for d in pending[:10]:
        lines.append(
            f"• `{str(d['decision_id'])[:8]}` — {d['ticker']} "
            f"{d['action']} {d['montant_eur']}EUR — `{d['status']}`"
        )
    await ctx.send("\n".join(lines))


@bot.command(name="killswitch")
async def cmd_killswitch(ctx, state: str):
    from core.kill_switch import activate, deactivate
    if state.lower() == "on":
        activate()
        await ctx.send("Kill switch active.")
    elif state.lower() == "off":
        deactivate()
        await ctx.send("Kill switch desactive.")
    else:
        await ctx.send("Usage : !killswitch on ou !killswitch off")


@bot.command(name="portfolio")
async def cmd_portfolio(ctx):
    from core.portfolio import get_portfolio
    try:
        p = get_portfolio()
        lines = [
            f"Portefeuille (source : {p['source']})",
            f"Total   : {p['total_eur']:.2f} EUR",
            f"Cash    : {p['cash_eur']:.2f} EUR",
            f"Investi : {p['total_invested']:.2f} EUR",
            f"Note : {p.get('note', 'Approximation V2.0')}",
        ]
        for ticker, val in p.get("positions", {}).items():
            if val > 0:
                lines.append(f"  • {ticker} : {val:.2f} EUR")
        await ctx.send("\n".join(lines))
    except RuntimeError as e:
        await ctx.send(f"Portefeuille indisponible : {e}")


# ─── on_ready : démarre strategy APRÈS connexion Discord ─────────────────────

@bot.event
async def on_ready():
    log("discord_bot.ready", {"user": str(bot.user), "channel_id": CHANNEL_ID})

    # Signale aux threads en attente que le bot est prêt
    _bot_ready.set()

    # Démarre strategy dans un thread séparé APRÈS on_ready
    # → garantit que bot.loop est disponible pour call_from_thread()
    def _start_strategy():
        from agents.strategy import run as run_strategy
        run_strategy()

    t = threading.Thread(target=_start_strategy, name="strategy", daemon=True)
    t.start()
    log("discord_bot.strategy_started", {
        "note": "Strategy démarrée après on_ready — bot.loop garanti disponible"
    })


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run_discord_bot():
    if not TOKEN:
        log("discord_bot.no_token", {}, level="error")
        raise RuntimeError("DISCORD_TOKEN non configuré.")
    log("discord_bot.starting", {})
    bot.run(TOKEN, log_handler=None)
