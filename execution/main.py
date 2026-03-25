"""
SENTINEL V2.0 — Execution Agent
Tourne sur VPS Linux uniquement. Seul agent autorisé à parler à IB Gateway.

Note /portfolio :
  Les valeurs de positions en EUR sont des approximations (avg_cost / taux FX IB).
  Pas une vérité comptable stricte — usage : décisions DCA et risk checks.

Note _active_trades :
  Mémoire RAM volatile. Perdue au redémarrage VPS.
  /order_status retourne "lost_on_restart" dans ce cas.
  fill_tracker.py côté Railway détecte et journalise.
"""
import os
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from ib_insync import IB, Stock, MarketOrder, Forex

from core.security       import verify_token
from core.logger         import get_logger
from core.ib_status      import normalize, is_filled, is_terminal
from core.ticker_map     import get_exchange, get_currency
from core.fractional_rules import supports_fractional
from core.config         import IB_HOST, IB_PORT, IB_ACCOUNT

log = get_logger("execution")
app = FastAPI(title="Sentinel Execution Agent V2.0")

# Mémoire volatile — perdue au redémarrage
_active_trades: dict = {}


class OrderRequest(BaseModel):
    ticker:      str
    action:      str
    quantity:    float
    montant_eur: float = 0.0
    event_id:    str   = ""
    paper_mode:  bool  = True


@app.get("/health")
def health():
    return {
        "status":    "online",
        "agent":     "execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/portfolio", dependencies=[Depends(verify_token)])
async def get_portfolio():
    """
    Retourne le portefeuille IB en temps réel.
    Valeurs positions en EUR = approximation (avg_cost / taux FX IB live).
    Non comptable — usage : décisions DCA et risk checks uniquement.
    """
    ib = IB()
    await ib.connectAsync(IB_HOST, IB_PORT, clientId=2, timeout=10)
    await asyncio.sleep(1)

    try:
        cash_eur  = 0.0
        total_eur = 0.0

        for av in ib.accountValues():
            if av.tag == "CashBalance"    and av.currency == "EUR":
                try: cash_eur  = max(cash_eur, float(av.value))
                except: pass
            if av.tag == "NetLiquidation" and av.currency == "EUR":
                try: total_eur = float(av.value)
                except: pass

        eur_usd = await _get_fx_rate(ib, "EUR", "USD") or 1.08
        eur_gbp = await _get_fx_rate(ib, "EUR", "GBP") or 0.85

        positions      = {}
        total_invested = 0.0

        for pos in ib.positions():
            ticker   = pos.contract.symbol
            qty      = pos.position
            avg_cost = pos.avgCost
            currency = pos.contract.currency or "USD"

            val_eur = (
                qty * avg_cost / eur_usd if currency == "USD"
                else qty * avg_cost / eur_gbp if currency == "GBP"
                else qty * avg_cost / eur_usd
            )

            positions[ticker]  = round(val_eur, 2)
            total_invested    += val_eur

        log("execution.portfolio_fetched", {
            "total_eur": total_eur, "cash_eur": cash_eur,
        })

        return {
            "total_eur":      round(total_eur, 2),
            "cash_eur":       round(cash_eur, 2),
            "total_invested": round(total_invested, 2),
            "positions":      positions,
            "eur_usd_rate":   round(eur_usd, 4),
            "eur_gbp_rate":   round(eur_gbp, 4),
            "source":         "ibkr_live",
            "note":           (
                "Approximation V2.0 — positions EUR = avg_cost / taux FX IB live. "
                "Non comptable. Migration V2.5 → prix market live."
            ),
        }
    finally:
        ib.disconnect()


@app.get("/account_summary", dependencies=[Depends(verify_token)])
async def get_account_summary():
    """Résumé complet du compte IB."""
    ib = IB()
    await ib.connectAsync(IB_HOST, IB_PORT, clientId=3, timeout=10)
    await asyncio.sleep(1)

    try:
        TAGS = {
            "NetLiquidation", "CashBalance", "UnrealizedPnL",
            "RealizedPnL",    "TotalCashValue", "GrossPositionValue",
        }
        summary = {}
        for av in ib.accountValues():
            if av.tag in TAGS and av.currency in ("EUR", "USD", "BASE"):
                key = f"{av.tag}_{av.currency}"
                try: summary[key] = float(av.value)
                except: pass

        positions = []
        for pos in ib.positions():
            positions.append({
                "ticker":   pos.contract.symbol,
                "exchange": pos.contract.exchange,
                "currency": pos.contract.currency,
                "quantity": pos.position,
                "avg_cost": pos.avgCost,
            })

        return {
            "account":   IB_ACCOUNT,
            "summary":   summary,
            "positions": positions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        ib.disconnect()


@app.post("/order", dependencies=[Depends(verify_token)])
async def place_order(req: OrderRequest):
    """Passe un ordre sur IB Gateway."""
    log("order.received", req.dict())

    exchange = get_exchange(req.ticker)
    frac_ok  = supports_fractional(req.ticker)

    if req.quantity <= 0:
        return {"success": False, "status": "refused",
                "reason": "quantity <= 0", "event_id": req.event_id}

    if not frac_ok and req.quantity != int(req.quantity):
        return {"success": False, "status": "refused",
                "reason": f"Fractional non supporté pour {req.ticker} ({exchange})",
                "event_id": req.event_id}

    if req.paper_mode:
        log("order.paper", {"ticker": req.ticker, "qty": req.quantity})
        return {
            "success":   True,
            "status":    "filled",
            "mode":      "paper",
            "filled_qty": req.quantity,
            "avg_price":  0.0,
            "event_id":   req.event_id,
        }

    return await _place_live(req, exchange)


@app.get("/order_status/{event_id}", dependencies=[Depends(verify_token)])
async def get_order_status(event_id: str):
    """
    Retourne le statut d'un ordre.
    Si absent de _active_trades (redémarrage VPS) → "lost_on_restart".
    """
    trade = _active_trades.get(event_id)

    if not trade:
        log("order_status.lost", {
            "event_id": event_id,
            "reason":   "Trade absent — probable redémarrage VPS",
        }, level="warning")
        return {
            "event_id": event_id,
            "status":   "lost_on_restart",
            "reason":   (
                "Trade non trouvé en mémoire. "
                "VPS peut avoir redémarré. "
                "Vérifier manuellement sur IB Gateway."
            ),
        }

    raw  = trade.orderStatus.status
    norm = normalize(raw)
    return {
        "event_id":  event_id,
        "status":    norm,
        "raw":       raw,
        "filled":    trade.orderStatus.filled,
        "avg_price": trade.orderStatus.avgFillPrice,
    }


async def _place_live(req: OrderRequest, exchange: str) -> dict:
    ib = IB()
    await ib.connectAsync(IB_HOST, IB_PORT, clientId=1, timeout=15)
    await asyncio.sleep(1)

    try:
        contract = Stock(req.ticker, exchange, get_currency(req.ticker))
        await ib.qualifyContractsAsync(contract)
        order = MarketOrder(req.action, req.quantity)
        trade = ib.placeOrder(contract, order)

        _active_trades[req.event_id] = trade

        # Attente statut terminal (max 30s)
        for _ in range(30):
            await asyncio.sleep(1)
            if is_terminal(trade.orderStatus.status):
                break

        raw    = trade.orderStatus.status
        norm   = normalize(raw)
        filled = trade.orderStatus.filled
        price  = trade.orderStatus.avgFillPrice

        log("order.result", {
            "event_id":  req.event_id,
            "ticker":    req.ticker,
            "raw":       raw,
            "norm":      norm,
            "filled":    filled,
            "avg_price": price,
        }, level="info" if is_filled(raw) else "warning")

        if is_terminal(raw):
            _active_trades.pop(req.event_id, None)

        return {
            "success":    is_filled(raw),
            "status":     norm,
            "raw_status": raw,
            "filled_qty": filled,
            "avg_price":  price,
            "event_id":   req.event_id,
        }
    finally:
        ib.disconnect()


async def _get_fx_rate(ib: IB, base: str, quote: str) -> float | None:
    try:
        contract = Forex(f"{base}{quote}")
        bars = await ib.reqHistoricalDataAsync(
            contract, endDateTime="", durationStr="1 D",
            barSizeSetting="1 hour", whatToShow="MIDPOINT", useRTH=True,
        )
        if bars:
            return float(bars[-1].close)
    except Exception as e:
        log("execution.fx_error",
            {"pair": f"{base}{quote}", "error": str(e)}, level="warning")
    return None


if __name__ == "__main__":
    import uvicorn
    log("execution.starting", {"host": "0.0.0.0", "port": 8000})
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ─── Endpoint /price/{ticker} ─────────────────────────────────────────────────

@app.get("/price/{ticker}", dependencies=[Depends(verify_token)])
async def get_price(ticker: str):
    """
    Prix en temps réel depuis IB Gateway.
    Source unique pour le sizing et la détection de dips.
    """
    from core.ticker_map import get_exchange, get_currency
    ib = IB()
    await ib.connectAsync(IB_HOST, IB_PORT, clientId=4, timeout=10)
    await asyncio.sleep(1)

    try:
        exchange = get_exchange(ticker)
        currency = get_currency(ticker)
        contract = Stock(ticker, exchange, currency)
        await ib.qualifyContractsAsync(contract)

        bars = await ib.reqHistoricalDataAsync(
            contract, endDateTime="", durationStr="1 D",
            barSizeSetting="5 mins", whatToShow="MIDPOINT", useRTH=True,
        )

        if not bars:
            return {"ok": False, "error": f"Prix indisponible pour {ticker}"}

        price_local = float(bars[-1].close)

        # Taux FX depuis IB
        eur_usd = await _get_fx_rate(ib, "EUR", "USD") or 1.08
        eur_gbp = await _get_fx_rate(ib, "EUR", "GBP") or 0.85

        if currency == "USD":
            price_eur = price_local / eur_usd
            eur_rate  = eur_usd
        elif currency == "GBP":
            price_eur = price_local / eur_gbp
            eur_rate  = eur_gbp
        else:
            price_eur = price_local / eur_usd
            eur_rate  = eur_usd

        return {
            "ok":          True,
            "ticker":      ticker,
            "price_local": round(price_local, 4),
            "currency":    currency,
            "eur_rate":    round(eur_rate, 4),
            "price_eur":   round(price_eur, 4),
            "source":      "ibkr_live",
        }
    finally:
        ib.disconnect()
