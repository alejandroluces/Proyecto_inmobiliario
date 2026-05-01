"""
main.py — Altea Intel Scraper Orchestrator
Runs all scrapers, scores properties, upserts to Supabase, and fires alerts.

Usage:
  python main.py                  # Run all scrapers
  python main.py --source idealista
  python main.py --source fotocasa
  python main.py --source facebook
  python main.py --no-facebook    # Skip Facebook (useful for quick runs)
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
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
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def fetch_live_zone_averages(sb: Client) -> dict[str, float]:
    """Fetch current zone averages from Supabase for accurate scoring."""
    try:
        rows = sb.table("zone_averages").select("zone, avg_price_per_m2").execute()
        return {r["zone"]: float(r["avg_price_per_m2"]) for r in rows.data if r["avg_price_per_m2"]}
    except Exception as exc:
        logger.warning(f"Could not fetch zone averages from Supabase: {exc}")
        return {}


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

async def run_scraper(source: str, sb: Client, live_averages: dict) -> list[dict]:
    """Run a single scraper and return scored properties."""
    logger.info(f"\n{'='*60}")
    logger.info(f"  Starting {source} scraper …")
    logger.info(f"{'='*60}")

    props: list[dict] = []

    try:
        if source == "Idealista":
            from scraper_idealista import scrape_idealista
            props = await scrape_idealista()

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
        score_property(prop, live_averages)

    logger.info(f"{source}: {len(props)} properties scraped and scored")
    return props


async def main(sources: list[str]) -> None:
    sb = get_supabase()
    live_averages = fetch_live_zone_averages(sb)
    logger.info(f"Live zone averages loaded: {live_averages}")

    all_portal_props: list[dict] = []
    all_fb_props: list[dict] = []
    total_new = 0
    total_updated = 0

    for source in sources:
        props = await run_scraper(source, sb, live_averages)

        # Upsert to Supabase
        new_count = 0
        upd_count = 0
        for prop in props:
            prop_id = upsert_property(sb, prop)
            if prop_id:
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
        if source in ("Idealista", "Fotocasa"):
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
        choices=["idealista", "fotocasa", "facebook"],
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
        elif args.source == "fotocasa":
            sources_to_run = ["Fotocasa"]
        elif args.source == "facebook":
            sources_to_run = ["Facebook"]
    elif args.no_facebook:
        sources_to_run = ["Idealista", "Fotocasa"]
    else:
        sources_to_run = ["Idealista", "Fotocasa", "Facebook"]

    asyncio.run(main(sources_to_run))
