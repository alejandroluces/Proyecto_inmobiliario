"""
alerts.py — Alert system for Facebook-exclusive listings
Detects when a Facebook post describes a property NOT found in Idealista/Fotocasa
(potential direct owner deal) and sends a notification via console + Telegram.
"""
import asyncio
import logging
from typing import Optional

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


# ─── Telegram sender ─────────────────────────────────────────

async def _send_telegram(message: str) -> bool:
    """
    Send a message to the configured Telegram chat.
    Returns True on success, False if Telegram is not configured or fails.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False  # Telegram not configured — silent skip

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.warning(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
    except Exception as exc:
        logger.warning(f"Failed to send Telegram message: {exc}")
        return False


# ─── Duplicate detection ─────────────────────────────────────

def _normalise_price(price: Optional[float], tolerance: float = 0.05) -> tuple[float, float]:
    """Return a price range for fuzzy matching (±5% by default)."""
    if not price:
        return (0.0, 0.0)
    return (price * (1 - tolerance), price * (1 + tolerance))


def is_duplicate_in_portals(
    fb_prop: dict,
    portal_props: list[dict],
    price_tolerance: float = 0.05,
) -> bool:
    """
    Check if a Facebook property likely already exists in Idealista/Fotocasa.

    Matching strategy (any of these is enough to consider it a duplicate):
      1. Same price (within ±5%) AND same m² (within ±5%) AND same zone
      2. Same price (within ±5%) AND very similar title keywords
    """
    fb_price = fb_prop.get("price")
    fb_m2 = fb_prop.get("m2")
    fb_zone = fb_prop.get("zone")
    fb_title_words = set(
        w.lower() for w in (fb_prop.get("title") or "").split() if len(w) > 3
    )

    for portal in portal_props:
        p_price = portal.get("price")
        p_m2 = portal.get("m2")
        p_zone = portal.get("zone")

        # ── Price match ────────────────────────────────────────
        price_match = False
        if fb_price and p_price:
            lo, hi = _normalise_price(fb_price, price_tolerance)
            price_match = lo <= p_price <= hi

        if not price_match:
            continue  # No price match → can't be a duplicate

        # ── m² match ──────────────────────────────────────────
        m2_match = False
        if fb_m2 and p_m2:
            lo, hi = _normalise_price(fb_m2, price_tolerance)
            m2_match = lo <= p_m2 <= hi

        # ── Zone match ────────────────────────────────────────
        zone_match = (fb_zone and p_zone and fb_zone == p_zone)

        if price_match and m2_match and zone_match:
            return True

        # ── Title keyword overlap ─────────────────────────────
        p_title_words = set(
            w.lower() for w in (portal.get("title") or "").split() if len(w) > 3
        )
        overlap = fb_title_words & p_title_words
        if price_match and len(overlap) >= 3:
            return True

    return False


# ─── Main alert function ─────────────────────────────────────

async def check_and_alert_facebook_exclusives(
    fb_properties: list[dict],
    portal_properties: list[dict],
) -> list[dict]:
    """
    Compare Facebook listings against portal listings.
    For each Facebook property NOT found in portals, fire an alert.

    Returns the list of Facebook-exclusive properties (with is_facebook_exclusive=True).
    """
    exclusives: list[dict] = []

    for fb_prop in fb_properties:
        if is_duplicate_in_portals(fb_prop, portal_properties):
            logger.debug(f"FB prop already in portals: {fb_prop.get('title', '')[:60]}")
            continue

        # Mark as exclusive
        fb_prop["is_facebook_exclusive"] = True
        exclusives.append(fb_prop)

        # ── Console alert ──────────────────────────────────────
        price_str = f"€{fb_prop['price']:,.0f}" if fb_prop.get("price") else "Precio no indicado"
        zone_str = fb_prop.get("zone") or "Zona desconocida"
        score_str = str(fb_prop.get("opportunity_score", "N/A"))

        alert_lines = [
            "🚨 TRATO DIRECTO DETECTADO — Propiedad exclusiva de Facebook",
            f"📌 Título:  {fb_prop.get('title', 'Sin título')[:80]}",
            f"💶 Precio:  {price_str}",
            f"📍 Zona:    {zone_str}",
            f"⭐ Score:   {score_str}",
        ]
        if fb_prop.get("url"):
            alert_lines.append(f"🔗 URL:     {fb_prop['url']}")

        console_msg = "\n".join(alert_lines)
        print("\n" + "=" * 60)
        print(console_msg)
        print("=" * 60)
        logger.info(f"FB exclusive alert: {fb_prop.get('title', '')[:60]} | {price_str}")

        # ── Telegram alert ─────────────────────────────────────
        tg_lines = [
            "🚨 <b>TRATO DIRECTO — Exclusivo Facebook</b>",
            f"📌 <b>{fb_prop.get('title', 'Sin título')[:80]}</b>",
            f"💶 Precio: <b>{price_str}</b>",
            f"📍 Zona: {zone_str}",
            f"⭐ Opportunity Score: <b>{score_str}</b>",
        ]
        if fb_prop.get("url"):
            tg_lines.append(f'🔗 <a href="{fb_prop["url"]}">Ver post</a>')

        await _send_telegram("\n".join(tg_lines))

    logger.info(
        f"Alert check complete: {len(exclusives)} Facebook-exclusive properties "
        f"out of {len(fb_properties)} FB posts"
    )
    return exclusives
