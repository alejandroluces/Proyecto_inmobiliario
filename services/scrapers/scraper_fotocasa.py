"""
scraper_fotocasa.py — Fotocasa Altea scraper

Strategy: intercept the internal JSON API that Fotocasa's own frontend calls.
  - Opens Chrome once, navigates to the search page
  - Intercepts XHR/fetch calls to the internal API
  - Extracts all listing data from JSON responses (no individual page visits)
  - Fully automated after the first CAPTCHA solve — no repeated interruptions

Usage:
  python scraper_fotocasa.py --fetch --max-pages 5   # Fetch up to 5 pages of results
  python scraper_fotocasa.py --parse                 # Parse saved JSON data
  python scraper_fotocasa.py --fetch --parse         # Fetch + parse in one go
  python scraper_fotocasa.py --login                 # Open browser to solve CAPTCHA once
"""
import asyncio
import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright, Page, Route, Request
from playwright_stealth import stealth_async

from config import FOTOCASA_URL
from utils import parse_price, parse_m2, detect_zone

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).parent / "fotocasa_session"
HTML_DIR    = Path(__file__).parent / "html_cache" / "fotocasa"
JSON_DIR    = Path(__file__).parent / "html_cache" / "fotocasa_json"
MAX_PAGES   = 10


# ─── Browser setup ───────────────────────────────────────────

async def _launch_persistent() -> tuple:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(SESSION_DIR),
        channel="chrome",
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--start-maximized",
        ],
        ignore_default_args=["--enable-automation"],
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="es-ES",
        timezone_id="Europe/Madrid",
        accept_downloads=False,
        ignore_https_errors=True,
    )
    return pw, context


# ─── CAPTCHA helpers ─────────────────────────────────────────

async def _accept_cookies(page: Page) -> None:
    for selector in [
        "button[data-testid='TcfAccept']",
        "button:has-text('Aceptar todo')",
        "button:has-text('Aceptar')",
    ]:
        try:
            btn = page.locator(selector)
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
                return
        except Exception:
            pass


async def _is_blocked(page: Page) -> bool:
    """
    Detect if the page is showing a CAPTCHA or block page.
    Uses strict signals to avoid false positives.
    """
    title = await page.title()
    title_lower = title.lower()

    # Hard block signals in title
    if any(s in title_lower for s in ["captcha", "robot", "acceso denegado", "blocked", "403 forbidden"]):
        logger.debug(f"Blocked by title: '{title}'")
        return True

    # Check if the page has actual listing content (if yes, not blocked)
    try:
        has_listings = await page.locator("a[href*='/vivienda/']").count() > 0
        if has_listings:
            return False
    except Exception:
        pass

    # Check for DataDome iframe (the actual CAPTCHA widget)
    try:
        has_datadome = await page.locator("iframe[src*='datadome']").count() > 0
        if has_datadome:
            logger.debug("DataDome iframe detected")
            return True
    except Exception:
        pass

    # Check for CAPTCHA-specific elements
    try:
        has_captcha_el = await page.locator("[id*='captcha'], [class*='captcha'], [id*='datadome']").count() > 0
        if has_captcha_el:
            logger.debug("CAPTCHA element detected")
            return True
    except Exception:
        pass

    return False


async def _wait_captcha_auto(page: Page, timeout_s: int = 300) -> bool:
    """
    Wait for CAPTCHA to be solved automatically by polling the page.
    Shows a message but does NOT require user to press ENTER.
    Polls every 3 seconds for up to timeout_s seconds.
    """
    print("\n" + "━" * 60)
    print("  ⚠️  CAPTCHA detectado — esperando resolución automática…")
    print(f"  ⏳  Tiempo máximo de espera: {timeout_s // 60} minutos")
    print("  💡  Si no se resuelve solo, resuélvelo manualmente en Chrome.")
    print("━" * 60)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        await asyncio.sleep(3)
        if not await _is_blocked(page):
            logger.info("✅  CAPTCHA resuelto — continuando automáticamente")
            return True

    # If still blocked after timeout, ask user once
    print("\n  ⚠️  No se resolvió automáticamente.")
    print("  👉  Resuélvelo manualmente en Chrome y pulsa ENTER.")
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: input("  ▶  ENTER cuando esté resuelto… ")
    )
    return True


# ─── Phase 1: FETCH via JSON API interception ────────────────

async def fetch_html(max_pages: int = MAX_PAGES) -> list[Path]:
    """
    Navigate Fotocasa search results pages and save HTML + intercept JSON API responses.
    Fully automated — only stops if CAPTCHA appears (polls automatically).
    """
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    pw, context = await _launch_persistent()
    saved_files: list[Path] = []
    intercepted_json: list[dict] = []

    logger.info(f"[FETCH] Starting Fotocasa fetch — up to {max_pages} pages")

    try:
        page = await context.new_page()
        await stealth_async(page)

        # ── Intercept API responses ────────────────────────────
        async def handle_response(response):
            url = response.url
            # Fotocasa internal API patterns
            if any(p in url for p in [
                "api.fotocasa.es",
                "/api/v2/real-estate",
                "fotocasa.es/api",
                "/real-estate/search",
            ]):
                try:
                    if "json" in response.headers.get("content-type", ""):
                        data = await response.json()
                        intercepted_json.append({"url": url, "data": data})
                        logger.info(f"  📡 Intercepted API: {url[:80]}")
                except Exception:
                    pass

        page.on("response", handle_response)

        base = FOTOCASA_URL.rstrip("/")
        for page_num in range(1, max_pages + 1):
            url = base if page_num == 1 else f"{base}/{page_num}"
            logger.info(f"[FETCH] Page {page_num}/{max_pages}: {url}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)

            await stealth_async(page)
            await _accept_cookies(page)

            # Scroll to trigger lazy loading
            for _ in range(4):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                await asyncio.sleep(0.8)
            await asyncio.sleep(1)

            if await _is_blocked(page):
                await _wait_captcha_auto(page)
                # Reload the page after CAPTCHA
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30_000)
                except Exception:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                await _accept_cookies(page)
                for _ in range(4):
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    await asyncio.sleep(0.8)

            # Save results page HTML
            results_html = await page.content()
            results_file = HTML_DIR / f"results_page_{page_num}.html"
            results_file.write_text(results_html, encoding="utf-8")
            saved_files.append(results_file)

            # Check if there are listings on this page
            soup = BeautifulSoup(results_html, "html.parser")
            has_listings = bool(
                soup.find("a", href=re.compile(r"/vivienda/")) or
                soup.find("article")
            )
            if not has_listings:
                logger.info(f"  No listings on page {page_num} — stopping")
                break

            logger.info(f"  ✓ Page {page_num} saved")

            # Short pause between pages (no individual listing visits!)
            if page_num < max_pages:
                await asyncio.sleep(2)

    finally:
        # Save all intercepted JSON
        if intercepted_json:
            json_file = JSON_DIR / f"api_responses_{int(time.time())}.json"
            json_file.write_text(
                json.dumps(intercepted_json, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            logger.info(f"  📡 Saved {len(intercepted_json)} API responses → {json_file.name}")

        await context.close()
        await pw.stop()

    logger.info(f"[FETCH] Done — {len(saved_files)} HTML pages saved")
    return saved_files


# ─── Phase 2: PARSE ──────────────────────────────────────────

def _parse_from_json(data: dict) -> list[dict]:
    """Try to extract properties from intercepted API JSON."""
    results = []
    # Common Fotocasa API response structures
    items = (
        data.get("realEstates") or
        data.get("items") or
        data.get("results") or
        data.get("data", {}).get("items") or
        []
    )
    if isinstance(items, list):
        for item in items:
            try:
                ext_id = str(item.get("id") or item.get("realEstateId") or "")
                if not ext_id:
                    continue
                price_raw = item.get("price") or item.get("priceInfo", {}).get("price") or 0
                price = float(price_raw) if price_raw else None
                m2_raw = item.get("surface") or item.get("area") or 0
                m2 = float(m2_raw) if m2_raw else None
                title = item.get("title") or item.get("name") or f"Propiedad Fotocasa {ext_id}"
                url = item.get("url") or f"https://www.fotocasa.es/es/comprar/viviendas/altea/{ext_id}"
                if url.startswith("/"):
                    url = f"https://www.fotocasa.es{url}"
                location = item.get("location") or item.get("address") or {}
                zone_text = (
                    location.get("neighborhood") or
                    location.get("district") or
                    location.get("city") or ""
                ) if isinstance(location, dict) else str(location)
                zone = detect_zone(zone_text) or detect_zone(title)
                images = []
                for img in (item.get("images") or item.get("multimedia") or [])[:5]:
                    src = img.get("url") or img.get("src") or (img if isinstance(img, str) else "")
                    if src:
                        images.append(src)
                results.append({
                    "source": "Fotocasa",
                    "external_id": ext_id,
                    "url": url,
                    "title": title,
                    "description": item.get("description") or "",
                    "price": price,
                    "m2": m2,
                    "zone": zone,
                    "images": images,
                })
            except Exception:
                continue
    return results


def _parse_card_html(card, soup: BeautifulSoup) -> Optional[dict]:
    """Extract property from an HTML card element."""
    try:
        link = card.find("a", href=re.compile(r"/vivienda/"))
        if not link:
            return None
        href = link.get("href", "")
        url = f"https://www.fotocasa.es{href}" if href.startswith("/") else href
        id_match = re.search(r"/(\d{6,12})(?:/|\?|$)", url)
        if not id_match:
            return None
        ext_id = id_match.group(1)

        all_text = card.get_text(" ", strip=True)

        # Price: search for patterns like "350.000 €" or "1.200.000€" in the card text
        price = None
        price_match = re.search(r"([\d]{2,4}(?:[.,]\d{3})*)\s*€", all_text)
        if price_match:
            price_str = price_match.group(1).replace(".", "").replace(",", "")
            try:
                price = float(price_str)
                if price < 10000 or price > 50_000_000:  # sanity check
                    price = None
            except ValueError:
                price = None
        if price is None:
            price = parse_price(all_text)

        # m²: search for patterns like "120 m²" or "120m2"
        m2 = None
        m2_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", all_text, re.IGNORECASE)
        if m2_match:
            try:
                m2 = float(m2_match.group(1).replace(",", "."))
                if m2 < 10 or m2 > 10000:  # sanity check
                    m2 = None
            except ValueError:
                m2 = None
        if m2 is None:
            m2 = parse_m2(all_text)

        # Title
        title_el = card.find(["h2", "h3", "h4", "span"], class_=re.compile(r"[Tt]itle|[Nn]ame"))
        title = title_el.get_text(strip=True) if title_el else f"Propiedad Fotocasa {ext_id}"

        # Zone
        zone_el = card.find(class_=re.compile(r"[Ll]ocation|[Zz]ona|[Aa]ddress|[Uu]bica"))
        zone_text = zone_el.get_text(strip=True) if zone_el else ""
        zone = detect_zone(zone_text) or detect_zone(title) or detect_zone(all_text)

        # Image
        images = []
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src and not src.startswith("data:"):
                images.append(src)

        return {
            "source": "Fotocasa",
            "external_id": ext_id,
            "url": url,
            "title": title,
            "description": "",
            "price": price,
            "m2": m2,
            "zone": zone,
            "images": images,
        }
    except Exception:
        return None


def parse_all_html() -> list[dict]:
    """
    Parse saved data: first tries intercepted JSON API responses,
    then falls back to HTML card parsing.
    """
    results: list[dict] = []
    seen_ids: set[str] = set()

    # ── Try JSON API responses first (most complete data) ─────
    json_files = sorted(JSON_DIR.glob("api_responses_*.json")) if JSON_DIR.exists() else []
    if json_files:
        logger.info(f"[PARSE] Found {len(json_files)} intercepted API response files")
        for jf in json_files:
            try:
                entries = json.loads(jf.read_text(encoding="utf-8"))
                for entry in entries:
                    props = _parse_from_json(entry.get("data", {}))
                    for p in props:
                        if p["external_id"] not in seen_ids:
                            seen_ids.add(p["external_id"])
                            results.append(p)
            except Exception as exc:
                logger.warning(f"  Failed to parse {jf.name}: {exc}")
        if results:
            logger.info(f"[PARSE] Got {len(results)} properties from API JSON")

    # ── Fallback: parse HTML cards ─────────────────────────────
    results_files = sorted(HTML_DIR.glob("results_page_*.html")) if HTML_DIR.exists() else []
    if results_files:
        logger.info(f"[PARSE] Parsing {len(results_files)} HTML results pages…")
        for f in results_files:
            html = f.read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "html.parser")

            cards = (
                soup.select("article.re-CardPackMinimal") or
                soup.select("article.re-Card") or
                soup.select("article[class*='Card']") or
                soup.select("article")
            )

            page_count = 0
            for card in cards:
                prop = _parse_card_html(card, soup)
                if prop and prop["external_id"] not in seen_ids:
                    seen_ids.add(prop["external_id"])
                    results.append(prop)
                    page_count += 1

            if page_count:
                logger.info(f"  {f.name}: +{page_count} properties")

    # Filter out "precio a consultar" (no price, no m²)
    valid = [p for p in results if p.get("price") or p.get("m2")]
    no_price = [p for p in results if not p.get("price")]
    if no_price:
        logger.info(f"  Skipped {len(no_price)} listings with no price (precio a consultar)")

    logger.info(f"[PARSE] Final: {len(valid)} properties with price/m² data")
    return valid


# ─── Public API ──────────────────────────────────────────────

async def scrape_fotocasa(max_pages: int = MAX_PAGES) -> list[dict]:
    existing = list(HTML_DIR.glob("results_page_*.html")) if HTML_DIR.exists() else []
    if not existing:
        await fetch_html(max_pages=max_pages)
    else:
        logger.info(f"Using {len(existing)} cached results pages")
    return parse_all_html()


# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Fotocasa scraper — fully automated, no repeated CAPTCHA interruptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper_fotocasa.py --fetch --parse --max-pages 5   # ~150 listings, ~5 min
  python scraper_fotocasa.py --parse                         # Re-parse saved data
  python scraper_fotocasa.py --login                         # Solve CAPTCHA once
        """,
    )
    parser.add_argument("--fetch", action="store_true", help="Fetch HTML + intercept API")
    parser.add_argument("--parse", action="store_true", help="Parse saved data")
    parser.add_argument("--login", action="store_true", help="Open browser to solve CAPTCHA once")
    parser.add_argument(
        "--max-pages", type=int, default=MAX_PAGES, metavar="N",
        help=f"Max result pages (default: {MAX_PAGES})",
    )
    args = parser.parse_args()

    if args.login:
        import shutil
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR)
        print("\n  🔐  Abriendo Chrome en Fotocasa…")
        print("  👉  Resuelve el CAPTCHA UNA VEZ, navega por 2-3 anuncios.")
        print("  ✅  Pulsa ENTER cuando termines — la sesión se guarda para siempre.\n")

        async def _login():
            pw, ctx = await _launch_persistent()
            pg = await ctx.new_page()
            await stealth_async(pg)
            await asyncio.sleep(2)
            await pg.goto(FOTOCASA_URL, wait_until="domcontentloaded", timeout=60_000)
            await _accept_cookies(pg)
            input("  ✅  Pulsa ENTER para guardar la sesión… ")
            await ctx.close()
            await pw.stop()
            print(f"  ✅  Sesión guardada. Ya no necesitarás resolver el CAPTCHA.\n")

        asyncio.run(_login())

    elif args.fetch and args.parse:
        asyncio.run(fetch_html(max_pages=args.max_pages))
        props = parse_all_html()
        print(f"\nTotal: {len(props)} properties")
        for p in props[:5]:
            price_str = f"€{p['price']:,.0f}" if p.get("price") else "sin precio"
            print(f"  {p['title'][:55]} | {price_str} | {p.get('m2', '?')}m²")

    elif args.fetch:
        asyncio.run(fetch_html(max_pages=args.max_pages))

    elif args.parse:
        props = parse_all_html()
        print(f"\nTotal: {len(props)} properties")
        for p in props[:5]:
            price_str = f"€{p['price']:,.0f}" if p.get("price") else "sin precio"
            print(f"  {p['title'][:55]} | {price_str} | {p.get('m2', '?')}m²")

    else:
        props = asyncio.run(scrape_fotocasa(max_pages=args.max_pages))
        print(f"\nTotal: {len(props)} properties")
