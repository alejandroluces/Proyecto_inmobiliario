"""
scorer.py - The Altea Scorer

Turns raw listing data into an investment-oriented opportunity score.
The score still starts from price/m2 vs the zone average, but it also
adds practical signals: direct-owner leads, recent price drops and data
quality. The public API remains compatible with the existing scraper.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback zone averages (EUR/m2) - kept in sync with zone_averages table.
ZONE_AVERAGES: dict[str, float] = {
    "Altea Hills": 2750.0,
    "Casco Antiguo": 2820.0,
    "Mascarat/Campomanes": 3100.0,
    "Altea la Vella": 1480.0,
    "Playa/Centro": 2780.0,
}

GLOBAL_AVERAGE: float = 2650.0

DIRECT_DEAL_BONUS = 8
UNKNOWN_ZONE_PENALTY = 8
INCOMPLETE_DATA_PENALTY = 10

MOTIVATED_SELLER_KEYWORDS = {
    "urgent": ("urgente", "urge", "oportunidad", "rebajado", "rebajada", "bajada", "negociable"),
    "distress": ("herencia", "divorcio", "embargo", "banco", "liquidacion", "liquidación"),
    "direct": ("particular", "directo propietario", "sin comisión", "sin comision"),
}

VIEW_KEYWORDS = ("vistas al mar", "vista mar", "frente el mar", "primera línea", "primera linea")
LUXURY_KEYWORDS = ("lujo", "villa", "chalet", "ático", "atico", "piscina", "altea hills")

LIQUIDITY_BY_ZONE = {
    "Playa/Centro": 9,
    "Altea Hills": 8,
    "Mascarat/Campomanes": 7,
    "Casco Antiguo": 7,
    "Altea la Vella": 6,
}


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def number_or(value, default=0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_zone_average(zone: Optional[str], live_averages: Optional[dict] = None) -> float:
    """
    Return the average price/m2 for a zone.
    Prefers live_averages fetched from Supabase over hardcoded fallbacks.
    """
    if live_averages and zone and zone in live_averages:
        return float(live_averages[zone])
    if zone and zone in ZONE_AVERAGES:
        return ZONE_AVERAGES[zone]
    return GLOBAL_AVERAGE


def calculate_score(
    price: Optional[float],
    m2: Optional[float],
    zone: Optional[str],
    live_averages: Optional[dict] = None,
) -> tuple[int, Optional[float]]:
    """
    Calculate the base score and deviation vs zone average.

    Returns:
        (opportunity_score, deviation_pct)

    deviation_pct is negative when the property is cheaper than average.
    """
    if not price or not m2 or m2 <= 0:
        return 0, None

    price_per_m2 = price / m2
    zone_avg = get_zone_average(zone, live_averages)
    deviation_pct = ((price_per_m2 - zone_avg) / zone_avg) * 100

    if deviation_pct >= 0:
        score = max(0, int(38 - deviation_pct * 1.25))
    elif deviation_pct >= -10:
        score = int(40 + abs(deviation_pct) * 2.4)
    elif deviation_pct >= -20:
        score = int(64 + (abs(deviation_pct) - 10) * 1.8)
    elif deviation_pct >= -30:
        score = int(82 + (abs(deviation_pct) - 20) * 1.1)
    else:
        score = int(93 + min(7, (abs(deviation_pct) - 30) * 0.5))

    score = clamp(score)

    logger.debug(
        "Score: %s | zone=%s | EUR/m2=%.0f vs avg=%.0f | dev=%.1f%%",
        score,
        zone,
        price_per_m2,
        zone_avg,
        deviation_pct,
    )
    return score, round(deviation_pct, 2)


def calculate_price_drop_bonus(price_history: Optional[list]) -> int:
    """Reward listings whose price has fallen since first observation."""
    if not price_history or len(price_history) < 2:
        return 0

    try:
        first = float(price_history[0])
        last = float(price_history[-1])
    except (TypeError, ValueError):
        return 0

    if first <= 0 or last >= first:
        return 0

    drop_pct = ((first - last) / first) * 100
    if drop_pct >= 15:
        return 10
    if drop_pct >= 10:
        return 7
    if drop_pct >= 5:
        return 4
    return 2


def calculate_price_drop_pct(price_history: Optional[list]) -> Optional[float]:
    if not price_history or len(price_history) < 2:
        return None
    try:
        first = float(price_history[0])
        last = float(price_history[-1])
    except (TypeError, ValueError):
        return None
    if first <= 0 or last >= first:
        return 0.0
    return round(((first - last) / first) * 100, 2)


def keyword_signals(prop: dict) -> dict[str, int | list[str]]:
    text = " ".join(
        str(prop.get(key) or "")
        for key in ("title", "description", "opportunity_reason")
    ).lower()
    hits: list[str] = []
    score = 0

    for family, words in MOTIVATED_SELLER_KEYWORDS.items():
        if any(word in text for word in words):
            hits.append(family)
            score += 5 if family != "distress" else 8

    if any(word in text for word in VIEW_KEYWORDS):
        hits.append("sea_view")
        score += 3
    if any(word in text for word in LUXURY_KEYWORDS):
        hits.append("premium_asset")

    return {"score": min(score, 15), "hits": hits}


def estimate_property_type(prop: dict) -> str:
    text = " ".join(str(prop.get(key) or "") for key in ("title", "description", "url")).lower()
    if re.search(r"\b(villa|chalet|casa)\b", text):
        return "villa"
    if re.search(r"\b(ático|atico|penthouse)\b", text):
        return "atico"
    if re.search(r"\b(parcela|terreno|plot)\b", text):
        return "terreno"
    if re.search(r"\b(apartamento|piso|flat)\b", text):
        return "apartamento"
    return "unknown"


def comparable_bonus(prop: dict) -> tuple[int, Optional[float]]:
    price = prop.get("price")
    m2 = prop.get("m2")
    comparable_avg = prop.get("comparable_avg_price_per_m2")
    if not price or not m2 or not comparable_avg:
        return 0, None

    price_per_m2 = price / m2
    deviation = ((price_per_m2 - float(comparable_avg)) / float(comparable_avg)) * 100
    if deviation <= -25:
        return 12, round(deviation, 2)
    if deviation <= -15:
        return 8, round(deviation, 2)
    if deviation <= -8:
        return 4, round(deviation, 2)
    if deviation >= 20:
        return -8, round(deviation, 2)
    return 0, round(deviation, 2)


def freshness_bonus(prop: dict) -> int:
    days = prop.get("listing_age_days")
    if days is None:
        return 0
    try:
        days = float(days)
    except (TypeError, ValueError):
        return 0
    if days <= 1:
        return 8
    if days <= 3:
        return 5
    if days <= 7:
        return 3
    if days >= 90:
        return -4
    return 0


def recurrence_bonus(prop: dict) -> int:
    count = prop.get("recurrence_count") or 1
    try:
        count = int(count)
    except (TypeError, ValueError):
        return 0
    if count >= 3:
        return -6
    if count == 2:
        return -3
    return 2


def liquidity_bonus(zone: Optional[str]) -> tuple[int, Optional[int]]:
    if not zone:
        return 0, None
    liquidity = LIQUIDITY_BY_ZONE.get(zone, 5)
    if liquidity >= 8:
        return 5, liquidity
    if liquidity >= 7:
        return 3, liquidity
    if liquidity <= 4:
        return -3, liquidity
    return 0, liquidity


def build_investment_tags(prop: dict, deviation: Optional[float]) -> list[str]:
    """Small explanation labels for humans reading alerts/logs."""
    tags: list[str] = []

    if deviation is not None:
        if deviation <= -25:
            tags.append("deep_discount")
        elif deviation <= -15:
            tags.append("below_market")

    if prop.get("is_facebook_exclusive") or prop.get("source") == "Facebook":
        tags.append("direct_lead")

    if calculate_price_drop_bonus(prop.get("price_history")) >= 4:
        tags.append("price_drop")
    new_drop = number_or(prop.get("new_price_drop_pct"))
    if new_drop >= 3:
        tags.append("new_price_drop")

    comparable_deviation = prop.get("deviation_vs_comparables")
    if comparable_deviation is not None and comparable_deviation <= -12:
        tags.append("below_comparables")

    for hit in prop.get("keyword_hits", []):
        tags.append(f"keyword_{hit}")

    listing_age = prop.get("listing_age_days")
    if listing_age is not None and number_or(listing_age, 999) <= 3:
        tags.append("fresh_listing")
    if number_or(prop.get("recurrence_count"), 1) > 1:
        tags.append("multi_source")
    if number_or(prop.get("liquidity_score")) >= 8:
        tags.append("liquid_zone")

    if not prop.get("zone"):
        tags.append("needs_zone_review")
    if not prop.get("images"):
        tags.append("needs_manual_review")

    return tags


def build_opportunity_reason(prop: dict, deviation: Optional[float], score: int) -> str:
    """Readable reason stored in-memory for logs/alerts and future UI use."""
    parts: list[str] = []
    if deviation is not None:
        if deviation < 0:
            parts.append(f"{abs(deviation):.1f}% below zone average")
        else:
            parts.append(f"{deviation:.1f}% above zone average")
    if prop.get("is_facebook_exclusive") or prop.get("source") == "Facebook":
        parts.append("possible direct-owner lead")
    if calculate_price_drop_bonus(prop.get("price_history")):
        parts.append("price has dropped")
    if prop.get("new_price_drop_pct"):
        parts.append(f"new drop {prop['new_price_drop_pct']:.1f}%")
    if prop.get("deviation_vs_comparables") is not None:
        comp = prop["deviation_vs_comparables"]
        parts.append(f"{abs(comp):.1f}% {'below' if comp < 0 else 'above'} comparable set")
    if prop.get("listing_age_days") is not None:
        parts.append(f"{int(prop['listing_age_days'])} days tracked")
    if number_or(prop.get("recurrence_count"), 1) > 1:
        parts.append(f"seen in {prop['recurrence_count']} sources")
    if prop.get("keyword_hits"):
        parts.append("keywords: " + ", ".join(prop["keyword_hits"][:3]))
    if prop.get("liquidity_score"):
        parts.append(f"liquidity {prop['liquidity_score']}/10")
    if not prop.get("zone"):
        parts.append("zone not confirmed")
    if score >= 85:
        parts.append("high-priority review")
    return "; ".join(parts) if parts else "insufficient data"


def score_property(prop: dict, live_averages: Optional[dict] = None) -> dict:
    """
    Enrich a property dict with scoring fields.
    Mutates and returns the dict.
    """
    base_score, deviation = calculate_score(
        price=prop.get("price"),
        m2=prop.get("m2"),
        zone=prop.get("zone"),
        live_averages=live_averages,
    )

    score = base_score
    score += calculate_price_drop_bonus(prop.get("price_history"))
    drop_pct = calculate_price_drop_pct(prop.get("price_history"))
    prop["price_drop_pct"] = drop_pct

    if prop.get("new_price_drop_pct"):
        score += 10 if prop["new_price_drop_pct"] >= 10 else 6

    comp_score, comp_deviation = comparable_bonus(prop)
    score += comp_score
    prop["deviation_vs_comparables"] = comp_deviation

    keywords = keyword_signals(prop)
    score += int(keywords["score"])
    prop["keyword_hits"] = keywords["hits"]
    prop["keyword_score"] = keywords["score"]

    score += freshness_bonus(prop)
    score += recurrence_bonus(prop)

    liq_bonus, liquidity = liquidity_bonus(prop.get("zone"))
    score += liq_bonus
    prop["liquidity_score"] = liquidity
    prop["property_type"] = prop.get("property_type") or estimate_property_type(prop)

    if prop.get("is_facebook_exclusive") or prop.get("source") == "Facebook":
        score += DIRECT_DEAL_BONUS

    if not prop.get("zone"):
        score -= UNKNOWN_ZONE_PENALTY

    if not prop.get("images") or not prop.get("url"):
        score -= INCOMPLETE_DATA_PENALTY

    score = clamp(score)
    prop["opportunity_score"] = score
    prop["deviation_vs_avg"] = deviation
    prop["investment_tags"] = build_investment_tags(prop, deviation)
    prop["opportunity_reason"] = build_opportunity_reason(prop, deviation, score)
    return prop
