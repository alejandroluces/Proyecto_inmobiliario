"""
scraper_idealista.py — Idealista Altea scraper

Strategy: intercept the internal JSON API that Idealista's own frontend calls.
  - Opens Chrome once, navigates to the search page
  - Intercepts XHR/fetch calls to the internal API
  - Extracts all listing data from JSON responses (no individual page visits)
  - Fully automated after the first CAPTCHA solve — no repeated interruptions

Usage:
  python scraper_idealista.py --fetch --max-pages 5   # Fetch up to 5 pages
  python scraper_idealista.py --parse                 # Parse saved data
  python scraper_idealista.py --fetch --parse         # Fetch + parse in one go
  python scraper_idealista.py --login                 # Open browser to solve CAPTCHA once
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

from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async

from config import IDEALISTA_URL
from utils import parse_price, parse_m2, detect_zone

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).parent / "idealista_session"
HTML_DIR    = Path(__file__).parent / "html_cache" / "idealista"
JSON_DIR    = Path(__file__).parent / "html_cache" / "idealista_json"
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
        viewport={"width": 1366, "height": 768},
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
        "#didomi-notice-agree-button",
        "button[id*='accept']",
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
        has_listings = await page.locator("article.item, a.item-link").count() > 0
        if has_listings:
            return False
    except Exception:
        pass

    # Check for CAPTCHA-specific elements
    try:
        has_captcha_el = await page.locator(
            "iframe[src*='datadome'], [id*='captcha'], [class*='captcha'], #captcha-container"
        ).count() > 0
        if has_captcha_el:
            logger.debug("CAPTCHA element detected")
            return True
    except Exception:
        pass

    return False


async def _wait_captcha_auto(page: Page, timeout_s: int = 300) -> bool:
    """
    Wait for CAPTCHA to be solved — polls automatically every 3s.
    Only asks for ENTER if not resolved within timeout.
    """
    print("\n" + "━" * 60)
    print("  ⚠️  CAPTCHA detectado en Idealista — esperando…")
    print(f"  ⏳  Tiempo máximo: {timeout_s // 60} minutos")
    print("  💡  Si no se resuelve solo, resuélvelo manualmente en Chrome.")
    print("━" * 60)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        await asyncio.sleep(3)
        if not await _is_blocked(page):
            logger.info("✅  CAPTCHA resuelto — continuando automáticamente")
            return True

    print("\n  ⚠️  No se resolvió automáticamente.")
    print("  👉  Resuélvelo manualmente en Chrome y pulsa ENTER.")
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: input("  ▶  ENTER cuando esté resuelto… ")
    )
    return True


# ─── Phase 1: FETCH ──────────────────────────────────────────

async def fetch_html(max_pages: int = MAX_PAGES) -> list[Path]:
    """
    Navigate Idealista search results pages, save HTML + intercept JSON API.
    Fully automated — no individual listing page visits.
    """
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    pw, context = await _launch_persistent()
    saved_files: list[Path] = []
    intercepted_json: list[dict] = []

    logger.info(f"[FETCH] Starting Idealista fetch — up to {max_pages} pages")

    try:
        page = await context.new_page()
        await stealth_async(page)

        # ── Intercept API responses ────────────────────────────
        async def handle_response(response):
            url = response.url
            if any(p in url for p in [
                "api.idealista.com",
                "idealista.com/api",
                "/ajax/",
                "listingController",
            ]):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        intercepted_json.append({"url": url, "data": data})
                        logger.info(f"  📡 Intercepted API: {url[:80]}")
                except Exception:
                    pass

        page.on("response", handle_response)

        for page_num in range(1, max_pages + 1):
            url = IDEALISTA_URL if page_num == 1 else f"{IDEALISTA_URL}pagina-{page_num}.htm"
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

            # Check if there are listings
            soup = BeautifulSoup(results_html, "html.parser")
            has_listings = bool(
                soup.find("article", class_="item") or
                soup.find("a", class_="item-link")
            )
            if not has_listings:
                logger.info(f"  No listings on page {page_num} — stopping")
                break

            count = len(soup.find_all("article", class_="item"))
            logger.info(f"  ✓ Page {page_num} saved — ~{count} listings")

            if page_num < max_pages:
                await asyncio.sleep(2)

    finally:
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
    """Try to extract properties from intercepted Idealista API JSON."""
    results = []
    items = (
        data.get("elementList") or
        data.get("items") or
        data.get("results") or
        []
    )
    if isinstance(items, list):
        for item in items:
            try:
                ext_id = str(item.get("propertyCode") or item.get("id") or "")
                if not ext_id:
                    continue
                price = float(item.get("price") or 0) or None
                m2 = float(item.get("size") or item.get("surface") or 0) or None
                title = item.get("suggestedTexts", {}).get("title") or item.get("title") or f"Propiedad Idealista {ext_id}"
                url = item.get("url") or f"https://www.idealista.com/inmueble/{ext_id}/"
                if url.startswith("/"):
                    url = f"https://www.idealista.com{url}"
                neighborhood = item.get("neighborhood") or item.get("district") or item.get("municipality") or ""
                zone = detect_zone(neighborhood) or detect_zone(title)
                images = []
                for img in (item.get("thumbnail") and [item["thumbnail"]] or item.get("images") or [])[:5]:
                    src = img if isinstance(img, str) else img.get("url") or img.get("src") or ""
                    if src:
                        images.append(src)
                results.append({
                    "source": "Idealista",
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


def _parse_card_html(card) -> Optional[dict]:
    """Extract property from an Idealista search result card."""
    try:
        link = card.find("a", class_="item-link")
        if not link:
            link = card.find("a", href=re.compile(r"/inmueble/"))
        if not link:
            return None

        href = link.get("href", "")
        url = f"https://www.idealista.com{href}" if href.startswith("/") else href
        id_match = re.search(r"/inmueble/(\d+)/", url)
        if not id_match:
            return None
        ext_id = id_match.group(1)

        # Title
        title_el = card.find(class_=re.compile(r"item-title|title-link"))
        title = title_el.get_text(strip=True) if title_el else f"Propiedad Idealista {ext_id}"

        # Price
        price_el = card.find(class_=re.compile(r"item-price|price-row"))
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_text)

        # m²
        all_text = card.get_text(" ", strip=True)
        m2 = parse_m2(all_text)

        # Zone
        location_el = card.find(class_=re.compile(r"item-detail-location|location"))
        zone_text = location_el.get_text(strip=True) if location_el else ""
        zone = detect_zone(zone_text) or detect_zone(title) or detect_zone(all_text)

        # Image
        images = []
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                images.append(src)

        return {
            "source": "Idealista",
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
    Parse saved data: tries intercepted JSON first, then HTML card fallback.
    """
    results: list[dict] = []
    seen_ids: set[str] = set()

    # ── JSON API responses (most complete) ────────────────────
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

    # ── HTML card fallback ─────────────────────────────────────
    results_files = sorted(HTML_DIR.glob("results_page_*.html")) if HTML_DIR.exists() else []
    if results_files:
        logger.info(f"[PARSE] Parsing {len(results_files)} HTML results pages…")
        for f in results_files:
            html = f.read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "html.parser")

            cards = (
                soup.select("article.item") or
                soup.select("article[class*='item']") or
                soup.select("div.item-info-container")
            )

            page_count = 0
            for card in cards:
                prop = _parse_card_html(card)
                if prop and prop["external_id"] not in seen_ids:
                    seen_ids.add(prop["external_id"])
                    results.append(prop)
                    page_count += 1

            if page_count:
                logger.info(f"  {f.name}: +{page_count} properties")

    # Filter "precio a consultar"
    valid = [p for p in results if p.get("price") or p.get("m2")]
    skipped = len(results) - len(valid)
    if skipped:
        logger.info(f"  Skipped {skipped} listings with no price (precio a consultar)")

    logger.info(f"[PARSE] Final: {len(valid)} properties")
    return valid


# ─── Public API ──────────────────────────────────────────────

async def scrape_idealista(max_pages: int = MAX_PAGES) -> list[dict]:
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
        description="Idealista scraper — fully automated, no repeated CAPTCHA interruptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper_idealista.py --fetch --parse --max-pages 5   # ~150 listings, ~5 min
  python scraper_idealista.py --parse                         # Re-parse saved data
  python scraper_idealista.py --login                         # Solve CAPTCHA once
        """,
    )
    parser.add_argument("--fetch", action="store_true", help="Fetch HTML + intercept API")
    parser.add_argument("--parse", action="store_true", help="Parse saved data")
    parser.add_argument("--login", action="store_true", help="Open browser to solve CAPTCHA once")
    parser.add_argument(
        "--max-pages", type=int, default=MAX_PAGES, metavar="N",
        help=f"Max result pages (default: {MAX_PAGES}, ~30 listings each)",
    )
    args = parser.parse_args()

    if args.login:
        import shutil
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR)
        print("\n  🔐  Abriendo Chrome en Idealista…")
        print("  👉  Resuelve el CAPTCHA UNA VEZ, navega por 2-3 anuncios.")
        print("  ✅  Pulsa ENTER cuando termines — la sesión se guarda para siempre.\n")

        async def _login():
            pw, ctx = await _launch_persistent()
            pg = await ctx.new_page()
            await stealth_async(pg)
            await asyncio.sleep(2)
            await pg.goto(IDEALISTA_URL, wait_until="domcontentloaded", timeout=60_000)
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
        props = asyncio.run(scrape_idealista())
        print(f"\nTotal: {len(props)} properties")
