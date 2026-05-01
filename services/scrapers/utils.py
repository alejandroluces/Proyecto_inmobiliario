"""
utils.py — Shared helpers: human-like delays, zone detection, price parsing
"""
import asyncio
import random
import re
import logging
from typing import Optional

from config import PAUSE_MIN, PAUSE_MAX, ZONE_KEYWORDS

logger = logging.getLogger(__name__)


# ─── Human-like delays ───────────────────────────────────────

async def random_pause(min_s: float = PAUSE_MIN, max_s: float = PAUSE_MAX) -> None:
    """Sleep for a random duration to mimic human browsing."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Pausing {delay:.1f}s …")
    await asyncio.sleep(delay)


async def human_scroll(page, steps: int = 5) -> None:
    """Scroll the page gradually, like a human reading content."""
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(300, 700))
        await asyncio.sleep(random.uniform(0.3, 0.9))


# ─── Price parsing ───────────────────────────────────────────

# Matches patterns like: 450.000 €  /  450,000€  /  €450000  /  450 000 €
_PRICE_RE = re.compile(
    r"(?:€\s*)?(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)\s*(?:€|EUR)?",
    re.IGNORECASE,
)

# Matches m² patterns: 120 m²  /  120m2  /  120 metros
_M2_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2|metros cuadrados|metros)",
    re.IGNORECASE,
)


def parse_price(text: str) -> Optional[float]:
    """
    Extract the first numeric price from a string.
    Returns None if the text contains 'precio a consultar' or no price found.
    """
    if not text:
        return None

    lower = text.lower()
    # Ignore "precio a consultar" listings — we can't score them
    if any(phrase in lower for phrase in [
        "precio a consultar", "a consultar", "price on request",
        "consultar precio", "precio bajo petición",
    ]):
        return None

    match = _PRICE_RE.search(text)
    if not match:
        return None

    raw = match.group(1)
    # Normalise: remove spaces and dots used as thousands separators
    # Handle both European (1.234,56) and US (1,234.56) formats
    raw = raw.replace(" ", "")
    if raw.count(",") == 1 and raw.count(".") == 0:
        # Could be decimal comma: 450,000 → 450000 or 450,50 → 450.50
        parts = raw.split(",")
        if len(parts[1]) <= 2:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(".") == 1 and raw.count(",") == 0:
        parts = raw.split(".")
        if len(parts[1]) > 2:
            raw = raw.replace(".", "")
        # else keep as decimal point
    else:
        # Multiple separators — strip all non-digit except last separator
        raw = re.sub(r"[.,](?=\d{3})", "", raw)
        raw = raw.replace(",", ".")

    try:
        value = float(raw)
        # Sanity check: realistic property prices in Altea (50k – 20M)
        if 50_000 <= value <= 20_000_000:
            return value
        return None
    except ValueError:
        return None


def parse_m2(text: str) -> Optional[float]:
    """Extract square metres from a string."""
    if not text:
        return None
    match = _M2_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    try:
        value = float(raw)
        if 10 <= value <= 10_000:
            return value
        return None
    except ValueError:
        return None


# ─── Zone detection ──────────────────────────────────────────

def detect_zone(text: str) -> Optional[str]:
    """
    Detect the Altea zone from a listing title or description.
    Returns the zone name or None if not detected.
    """
    if not text:
        return None
    lower = text.lower()
    for zone, keywords in ZONE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return zone
    return None


# ─── Sale post detection (Facebook) ──────────────────────────

_SALE_KEYWORDS = [
    "vendo", "venta", "se vende", "en venta", "for sale",
    "selling", "precio", "€", "eur", "oferta",
]

_NON_SALE_KEYWORDS = [
    "alquilo", "alquiler", "se alquila", "for rent", "renting",
    "busco", "looking for", "wanted", "buscamos",
]


def is_sale_post(text: str) -> bool:
    """
    Heuristic: decide if a Facebook post is a property-for-sale listing.
    Returns True if it looks like a sale post.
    """
    if not text:
        return False
    lower = text.lower()

    # Exclude rental / wanted posts
    if any(kw in lower for kw in _NON_SALE_KEYWORDS):
        return False

    # Must contain at least one sale keyword AND a price indicator
    has_sale_kw = any(kw in lower for kw in _SALE_KEYWORDS)
    has_price = bool(_PRICE_RE.search(text))

    return has_sale_kw and has_price
