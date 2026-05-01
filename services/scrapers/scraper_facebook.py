"""
scraper_facebook.py — Scraper for Facebook Group property posts
Uses a PERSISTENT browser context so you can log in once and reuse the session.

FIRST-TIME SETUP:
  1. Run:  python scraper_facebook.py --login
  2. A visible browser window will open. Log in to Facebook manually.
  3. Close the browser — the session is saved to FB_SESSION_DIR.
  4. From now on, run without --login and the session is reused automatically.
"""
import asyncio
import hashlib
import logging
import random
import re
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import stealth_async

from config import FB_GROUPS, FB_SESSION_DIR
from utils import random_pause, human_scroll, parse_price, parse_m2, detect_zone, is_sale_post

logger = logging.getLogger(__name__)

# How many posts to scroll through per group
MAX_POSTS_PER_GROUP = 50


async def _get_persistent_context(headless: bool = True) -> tuple:
    """
    Create (or reuse) a persistent browser context stored at FB_SESSION_DIR.
    The persistent context preserves cookies, localStorage, etc. across runs.
    """
    session_path = Path(FB_SESSION_DIR).resolve()
    session_path.mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(session_path),
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="es-ES",
        timezone_id="Europe/Madrid",
    )
    return pw, context


async def login_flow() -> None:
    """
    Interactive login: opens a visible browser so the user can log in to Facebook.
    Call once with:  python scraper_facebook.py --login
    """
    print("\n🔐  Opening Facebook login page …")
    print("   Please log in manually in the browser window that opens.")
    print("   Once logged in, close the browser window to save the session.\n")

    pw, context = await _get_persistent_context(headless=False)
    page = await context.new_page()
    await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

    # Wait until the user closes the browser
    try:
        await page.wait_for_url("https://www.facebook.com/", timeout=300_000)
        print("✅  Login detected! Session saved.")
    except Exception:
        print("ℹ️  Browser closed. Session saved (if you completed login).")
    finally:
        await context.close()
        await pw.stop()


def _extract_post_id(post_element) -> str:
    """Generate a stable ID for a Facebook post element."""
    # Try to get the post permalink from a timestamp link
    return hashlib.md5(str(id(post_element)).encode()).hexdigest()[:12]


def _parse_fb_post_text(text: str) -> Optional[dict]:
    """
    Parse a Facebook post text and extract property data.
    Returns a dict or None if the post is not a sale listing.
    """
    if not is_sale_post(text):
        return None

    price = parse_price(text)
    m2 = parse_m2(text)
    zone = detect_zone(text)

    # Build a title from the first non-empty line (max 120 chars)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0][:120] if lines else "Propiedad Facebook"

    return {
        "source": "Facebook",
        "title": title,
        "description": text[:2000],  # Store first 2000 chars
        "price": price,
        "m2": m2,
        "zone": zone,
        "images": [],
    }


async def _scrape_group(context: BrowserContext, group: dict) -> list[dict]:
    """
    Scrape posts from a single Facebook group.
    Returns a list of property dicts.
    """
    page = await context.new_page()
    await stealth_async(page)
    results: list[dict] = []
    seen_ids: set[str] = set()

    try:
        logger.info(f"Opening FB group: {group['name']} ({group['url']})")
        await page.goto(group["url"], wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(3)

        # Check if we're logged in
        content = await page.content()
        if "login" in page.url.lower() or "Log in" in content:
            logger.error(
                "Not logged in to Facebook! Run:  python scraper_facebook.py --login"
            )
            return []

        # Scroll to load posts
        posts_collected = 0
        scroll_attempts = 0
        max_scrolls = 20

        while posts_collected < MAX_POSTS_PER_GROUP and scroll_attempts < max_scrolls:
            await human_scroll(page, steps=4)
            await asyncio.sleep(random.uniform(1.5, 3.0))
            scroll_attempts += 1

            # Facebook renders posts in role="article" elements
            post_els = page.locator("div[role='article']")
            count = await post_els.count()

            for i in range(count):
                post_el = post_els.nth(i)

                # Get post text
                try:
                    text_el = post_el.locator("div[data-ad-comet-preview='message'], div[data-testid='post_message']")
                    if not await text_el.count():
                        # Fallback: grab all visible text from the article
                        text_el = post_el.locator("div[dir='auto']")

                    if not await text_el.count():
                        continue

                    post_text = (await text_el.first.inner_text()).strip()
                except Exception:
                    continue

                if not post_text or len(post_text) < 20:
                    continue

                # Stable ID based on text content
                post_id = hashlib.md5(post_text[:200].encode()).hexdigest()[:16]
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                prop = _parse_fb_post_text(post_text)
                if not prop:
                    continue

                # Try to grab the first image from the post
                try:
                    img_el = post_el.locator("img[src*='scontent']").first
                    if await img_el.count():
                        src = await img_el.get_attribute("src")
                        if src:
                            prop["images"] = [src]
                except Exception:
                    pass

                # Try to get the post permalink
                try:
                    link_el = post_el.locator("a[href*='/groups/'][href*='/posts/']").first
                    if await link_el.count():
                        href = await link_el.get_attribute("href")
                        prop["url"] = href
                        # Extract post ID from URL
                        m = re.search(r"/posts/(\d+)", href or "")
                        post_id = m.group(1) if m else post_id
                except Exception:
                    pass

                prop["external_id"] = f"fb_{group['id']}_{post_id}"
                results.append(prop)
                posts_collected += 1
                logger.info(
                    f"  FB post: {prop['title'][:60]} | "
                    f"€{prop['price']:,.0f}" if prop.get("price") else f"  FB post: {prop['title'][:60]} | price=None"
                )

                if posts_collected >= MAX_POSTS_PER_GROUP:
                    break

        logger.info(f"Group '{group['name']}': {len(results)} sale posts found")

    except Exception as exc:
        logger.error(f"Error scraping FB group {group['name']}: {exc}")
    finally:
        await page.close()

    return results


async def scrape_facebook() -> list[dict]:
    """
    Main entry point. Scrapes all configured Facebook groups.
    Returns a list of property dicts ready for scoring and DB upsert.
    """
    pw, context = await _get_persistent_context(headless=True)
    all_results: list[dict] = []

    try:
        for group in FB_GROUPS:
            group_results = await _scrape_group(context, group)
            all_results.extend(group_results)
            await random_pause(min_s=10, max_s=25)  # Pause between groups
    finally:
        await context.close()
        await pw.stop()

    logger.info(f"Facebook scrape complete: {len(all_results)} posts found")
    return all_results


# ─── CLI entry point ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if "--login" in sys.argv:
        asyncio.run(login_flow())
    else:
        results = asyncio.run(scrape_facebook())
        print(f"\nTotal FB properties found: {len(results)}")
        for r in results:
            print(f"  • {r['title'][:70]} | price={r.get('price')} | zone={r.get('zone')}")
