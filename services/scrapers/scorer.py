"""
scorer.py - The Altea Scorer

Turns raw listing data into an investment-oriented opportunity score.
The score still starts from price/m2 vs the zone average, but it also
adds practical signals: direct-owner leads, recent price drops and data
quality. The public API remains compatible with the existing scraper.
"""
import logging
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


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


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
