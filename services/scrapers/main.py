"""
main.py — Altea Intel Scraper Orchestrator
Runs all scrapers, scores properties, upserts to Supabase, and fires alerts.

Usage:
  python main.py                  # Run all scrapers
  python main.py --source idealista
  python main.py --source idealista-manual
  python main.py --source fotocasa
  python main.py --source facebook
  python main.py --no-facebook    # Skip Facebook (useful for quick runs)
"""
import asyncio
import argparse
import base64
import json
import logging
import sys
from datetime import date, datetime, timezone
from typing import Optional

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, ZONE_KEYWORDS
from scorer import score_property
from alerts import check_and_alert_facebook_exclusives

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ─── Supabase helpers ────────────────────────────────────────

def get_supabase() -> Client:
    validate_supabase_write_key()
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    except Exception:
        return {}


def validate_supabase_write_key() -> None:
    """
    Fail early when SUPABASE_SERVICE_KEY is actually the anon key.
    The scraper writes through RLS-protected tables, so it needs service_role.
    """
    payload = _decode_jwt_payload(SUPABASE_SERVICE_KEY)
    role = payload.get("role")

    if role and role != "service_role":
        raise SystemExit(
            "\nSupabase write key is not valid for scraper writes.\n"
            f"Detected JWT role: {role!r}.\n\n"
            "Fix services/scrapers/.env:\n"
            "  SUPABASE_SERVICE_KEY=<your Supabase service_role secret key>\n\n"
            "In Supabase: Project Settings -> API -> service_role key.\n"
            "Do not use VITE_SUPABASE_ANON_KEY or anon public key here.\n"
        )


def fetch_live_zone_averages(sb: Client) -> dict[str, float]:
    """Fetch current zone averages from Supabase for accurate scoring."""
    try:
        rows = sb.table("zone_averages").select("zone, avg_price_per_m2").execute()
        return {r["zone"]: float(r["avg_price_per_m2"]) for r in rows.data if r["avg_price_per_m2"]}
    except Exception as exc:
        logger.warning(f"Could not fetch zone averages from Supabase: {exc}")
        return {}


def fetch_market_context(sb: Client) -> dict:
    """
    Load existing DB state used by the scorer:
    price history, comparable sets, listing age and cross-source recurrence.
    """
    context = {
        "existing": {},
        "comparables": [],
        "fingerprints": {},
    }
    try:
        rows = (
            sb.table("v_opportunities")
            .select(
                "id,created_at,source,external_id,title,description,price,m2,price_per_m2,"
                "zone,price_history"
            )
            .limit(1000)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning(f"Could not fetch market context: {exc}")
        return context

    for row in rows:
        key = (row.get("source"), row.get("external_id"))
        context["existing"][key] = row
        if row.get("price_per_m2") and row.get("zone"):
            context["comparables"].append(row)
        fp = build_property_fingerprint(row)
        if fp:
            context["fingerprints"].setdefault(fp, set()).add(row.get("source"))

    return context


def build_property_fingerprint(prop: dict) -> str:
    """Coarse duplicate fingerprint across sources/agencies."""
    zone = (prop.get("zone") or "").strip().lower()
    price = prop.get("price")
    m2 = prop.get("m2")
    if not zone or not price or not m2:
        return ""
    try:
        price_bucket = round(float(price) / 25_000) * 25_000
        m2_bucket = round(float(m2) / 10) * 10
    except (TypeError, ValueError):
        return ""
    return f"{zone}|{price_bucket}|{m2_bucket}"


def infer_listing_age_days(existing_row: Optional[dict]) -> Optional[int]:
    if not existing_row or not existing_row.get("created_at"):
        return 0
    try:
        created = datetime.fromisoformat(existing_row["created_at"].replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - created).days)


def find_comparable_average(prop: dict, comparables: list[dict]) -> Optional[float]:
    zone = prop.get("zone")
    price = prop.get("price")
    m2 = prop.get("m2")
    if not zone or not price or not m2:
        return None
    try:
        m2 = float(m2)
    except (TypeError, ValueError):
        return None

    matches: list[float] = []
    for comp in comparables:
        if comp.get("zone") != zone:
            continue
        if comp.get("source") == prop.get("source") and comp.get("external_id") == prop.get("external_id"):
            continue
        comp_m2 = comp.get("m2")
        comp_ppm = comp.get("price_per_m2")
        if not comp_m2 or not comp_ppm:
            continue
        try:
            comp_m2 = float(comp_m2)
            comp_ppm = float(comp_ppm)
        except (TypeError, ValueError):
            continue
        if abs(comp_m2 - m2) / max(m2, 1) <= 0.30:
            matches.append(comp_ppm)

    if len(matches) < 3:
        return None
    matches.sort()
    trimmed = matches[1:-1] if len(matches) >= 5 else matches
    return round(sum(trimmed) / len(trimmed), 2)


def enrich_property_context(prop: dict, market_context: dict) -> dict:
    existing = market_context["existing"].get((prop.get("source"), prop.get("external_id")))
    history = list((existing or {}).get("price_history") or [])
    current_price = prop.get("price")
    if current_price and (not history or float(history[-1]) != float(current_price)):
        history.append(float(current_price))

    prop["price_history"] = history
    prop["listing_age_days"] = infer_listing_age_days(existing)
    prop["comparable_avg_price_per_m2"] = find_comparable_average(
        prop,
        market_context.get("comparables", []),
    )

    fp = build_property_fingerprint(prop)
    sources = set(market_context.get("fingerprints", {}).get(fp, set()))
    if prop.get("source"):
        sources.add(prop["source"])
    prop["recurrence_count"] = len(sources) if sources else 1

    if existing and existing.get("price") and current_price:
        old_price = float(existing["price"])
        new_price = float(current_price)
        if old_price > 0 and new_price < old_price:
            prop["new_price_drop_pct"] = round(((old_price - new_price) / old_price) * 100, 2)
        else:
            prop["new_price_drop_pct"] = 0.0
    else:
        prop["new_price_drop_pct"] = 0.0

    return prop


def upsert_property(sb: Client, prop: dict) -> Optional[str]:
    """
    Upsert a property into Supabase.
    Returns the property UUID on success, None on failure.
    The price_history trigger in the DB handles history automatically.
    """
    # Fields that map directly to the DB schema
    db_row = {
        "source":               prop["source"],
        "external_id":          prop["external_id"],
        "url":                  prop.get("url"),
        "title":                prop["title"],
        "description":          prop.get("description"),
        "price":                prop.get("price"),
        "m2":                   prop.get("m2"),
        "zone":                 prop.get("zone"),
        "images":               prop.get("images", []),
        "opportunity_score":    prop.get("opportunity_score", 0),
        "deviation_vs_avg":     prop.get("deviation_vs_avg"),
        "investment_tags":      prop.get("investment_tags", []),
        "opportunity_reason":   prop.get("opportunity_reason"),
        "comparable_avg_price_per_m2": prop.get("comparable_avg_price_per_m2"),
        "deviation_vs_comparables": prop.get("deviation_vs_comparables"),
        "price_drop_pct":       prop.get("price_drop_pct"),
        "new_price_drop_pct":   prop.get("new_price_drop_pct"),
        "listing_age_days":     prop.get("listing_age_days"),
        "recurrence_count":     prop.get("recurrence_count", 1),
        "keyword_hits":         prop.get("keyword_hits", []),
        "keyword_score":        prop.get("keyword_score", 0),
        "liquidity_score":      prop.get("liquidity_score"),
        "property_type":        prop.get("property_type"),
        "is_facebook_exclusive": prop.get("is_facebook_exclusive", False),
    }

    try:
        result = (
            sb.table("properties")
            .upsert(db_row, on_conflict="source,external_id")
            .execute()
        )
        if result.data:
            prop_id = result.data[0]["id"]
            logger.info(f"  ✓ Upserted: {db_row['title'][:50]} → {prop_id}")
            return prop_id
        else:
            logger.warning(f"  ⚠ Upsert returned no data for: {db_row['title'][:50]}")
            logger.debug(f"  Row sent: {db_row}")
            return None
    except Exception as exc:
        logger.error(f"  ✗ Upsert failed for '{prop.get('title', '?')[:50]}': {exc}")
        logger.error(f"  Row that failed: source={db_row.get('source')}, external_id={db_row.get('external_id')}, price={db_row.get('price')}, m2={db_row.get('m2')}")
        return None


def record_daily_snapshot(sb: Client, prop_id: str, prop: dict) -> None:
    try:
        sb.table("property_snapshots").upsert(
            {
                "property_id": prop_id,
                "snapshot_date": date.today().isoformat(),
                "price": prop.get("price"),
                "m2": prop.get("m2"),
                "opportunity_score": prop.get("opportunity_score", 0),
                "deviation_vs_avg": prop.get("deviation_vs_avg"),
                "deviation_vs_comparables": prop.get("deviation_vs_comparables"),
                "investment_tags": prop.get("investment_tags", []),
            },
            on_conflict="property_id,snapshot_date",
        ).execute()
    except Exception as exc:
        logger.warning(f"Could not record daily snapshot for {prop_id}: {exc}")


def record_opportunity_alert(sb: Client, prop_id: str, prop: dict) -> None:
    score = prop.get("opportunity_score", 0)
    drop = prop.get("new_price_drop_pct") or 0
    fresh = prop.get("listing_age_days") == 0
    if score < 85 and drop < 5 and not (fresh and score >= 75):
        return

    alert_type = "high_score"
    if drop >= 5:
        alert_type = "price_drop"
    elif fresh:
        alert_type = "fresh_opportunity"

    try:
        sb.table("opportunity_alerts").upsert(
            {
                "property_id": prop_id,
                "alert_type": alert_type,
                "score": score,
                "price": prop.get("price"),
                "price_drop_pct": drop,
                "message": prop.get("opportunity_reason"),
            },
            on_conflict="property_id,alert_type",
        ).execute()
    except Exception as exc:
        logger.warning(f"Could not record opportunity alert for {prop_id}: {exc}")


def update_zone_averages(sb: Client) -> None:
    """
    Recalculate and update zone averages from current properties in the DB.
    Called after each scraper run.
    """
    try:
        # Fetch all priced properties grouped by zone
        rows = (
            sb.table("properties")
            .select("zone, price_per_m2")
            .not_.is_("price_per_m2", "null")
            .not_.is_("zone", "null")
            .execute()
        )

        # Aggregate
        zone_data: dict[str, list[float]] = {}
        for r in rows.data:
            z = r["zone"]
            v = r["price_per_m2"]
            if z not in ZONE_KEYWORDS:
                continue
            if z and v:
                zone_data.setdefault(z, []).append(float(v))

        for zone, values in zone_data.items():
            avg = sum(values) / len(values)
            sb.table("zone_averages").upsert(
                {
                    "zone": zone,
                    "avg_price_per_m2": round(avg, 2),
                    "property_count": len(values),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="zone",
            ).execute()
            logger.info(f"Zone avg updated: {zone} → €{avg:,.0f}/m² ({len(values)} props)")

    except Exception as exc:
        logger.warning(f"Could not update zone averages: {exc}")


def log_scraper_run(
    sb: Client,
    source: str,
    found: int,
    new: int,
    updated: int,
    errors: list[str],
    status: str,
    run_id: Optional[str] = None,
) -> Optional[str]:
    """Insert or update a scraper_runs audit record."""
    try:
        row = {
            "source": source,
            "properties_found": found,
            "properties_new": new,
            "properties_updated": updated,
            "errors": errors,
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if run_id:
            sb.table("scraper_runs").update(row).eq("id", run_id).execute()
            return run_id
        else:
            result = sb.table("scraper_runs").insert(row).execute()
            return result.data[0]["id"] if result.data else None
    except Exception as exc:
        logger.warning(f"Could not log scraper run: {exc}")
        return None


# ─── Orchestration ───────────────────────────────────────────

async def run_scraper(source: str, sb: Client, live_averages: dict, market_context: dict) -> list[dict]:
    """Run a single scraper and return scored properties."""
    logger.info(f"\n{'='*60}")
    logger.info(f"  Starting {source} scraper …")
    logger.info(f"{'='*60}")

    props: list[dict] = []

    try:
        if source == "Idealista":
            from scraper_idealista import scrape_idealista
            props = await scrape_idealista()

        elif source == "Idealista Manual":
            from scraper_idealista_manual import scrape_idealista_manual
            props = await scrape_idealista_manual()

        elif source == "Fotocasa":
            from scraper_fotocasa import scrape_fotocasa
            props = await scrape_fotocasa()

        elif source == "Facebook":
            from scraper_facebook import scrape_facebook
            props = await scrape_facebook()

    except Exception as exc:
        logger.error(f"{source} scraper crashed: {exc}", exc_info=True)
        return []

    # Score each property
    for prop in props:
        enrich_property_context(prop, market_context)
        score_property(prop, live_averages)

    logger.info(f"{source}: {len(props)} properties scraped and scored")
    return props


async def main(sources: list[str]) -> None:
    sb = get_supabase()
    live_averages = fetch_live_zone_averages(sb)
    market_context = fetch_market_context(sb)
    logger.info(f"Live zone averages loaded: {live_averages}")

    all_portal_props: list[dict] = []
    all_fb_props: list[dict] = []
    total_new = 0
    total_updated = 0

    for source in sources:
        props = await run_scraper(source, sb, live_averages, market_context)

        # Upsert to Supabase
        new_count = 0
        upd_count = 0
        for prop in props:
            prop_id = upsert_property(sb, prop)
            if prop_id:
                record_daily_snapshot(sb, prop_id, prop)
                record_opportunity_alert(sb, prop_id, prop)
                # Determine if it was new or updated (simple heuristic)
                new_count += 1

        total_new += new_count
        total_updated += upd_count

        log_scraper_run(
            sb,
            source=source,
            found=len(props),
            new=new_count,
            updated=upd_count,
            errors=[],
            status="success",
        )

        # Separate portal vs Facebook for alert comparison
        if source in ("Idealista", "Idealista Manual", "Fotocasa"):
            all_portal_props.extend(props)
        elif source == "Facebook":
            all_fb_props.extend(props)

    # ── Update zone averages after all scrapes ─────────────────
    update_zone_averages(sb)

    # ── Facebook exclusive alert check ─────────────────────────
    if all_fb_props:
        logger.info("\nChecking for Facebook-exclusive listings …")
        exclusives = await check_and_alert_facebook_exclusives(
            fb_properties=all_fb_props,
            portal_properties=all_portal_props,
        )
        logger.info(f"Found {len(exclusives)} Facebook-exclusive properties")

        # Update is_facebook_exclusive flag in DB for confirmed exclusives
        for prop in exclusives:
            if prop.get("external_id"):
                try:
                    sb.table("properties").update(
                        {"is_facebook_exclusive": True}
                    ).eq("external_id", prop["external_id"]).execute()
                except Exception:
                    pass

    logger.info(
        f"\n✅  Run complete — "
        f"New: {total_new} | Updated: {total_updated} | "
        f"FB exclusives: {len(all_fb_props)}"
    )


# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Altea Intel Scraper")
    parser.add_argument(
        "--source",
        choices=["idealista", "idealista-manual", "fotocasa", "facebook"],
        help="Run only a specific scraper",
    )
    parser.add_argument(
        "--no-facebook",
        action="store_true",
        help="Skip the Facebook scraper",
    )
    args = parser.parse_args()

    if args.source:
        sources_to_run = [args.source.capitalize()]
        if args.source == "idealista":
            sources_to_run = ["Idealista"]
        elif args.source == "idealista-manual":
            sources_to_run = ["Idealista Manual"]
        elif args.source == "fotocasa":
            sources_to_run = ["Fotocasa"]
        elif args.source == "facebook":
            sources_to_run = ["Facebook"]
    elif args.no_facebook:
        sources_to_run = ["Idealista", "Fotocasa"]
    else:
        sources_to_run = ["Idealista", "Fotocasa", "Facebook"]

    asyncio.run(main(sources_to_run))
