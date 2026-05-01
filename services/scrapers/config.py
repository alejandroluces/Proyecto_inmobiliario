"""
config.py — Centralised configuration loaded from .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Supabase ────────────────────────────────────────────────
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]

# ─── Telegram (optional) ─────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Facebook session ────────────────────────────────────────
FB_SESSION_DIR: str = os.getenv("FB_SESSION_DIR", "./fb_session")

# ─── Scraper behaviour ───────────────────────────────────────
PAUSE_MIN: float = float(os.getenv("PAUSE_MIN", "5"))
PAUSE_MAX: float = float(os.getenv("PAUSE_MAX", "15"))

# ─── Target URLs ─────────────────────────────────────────────
IDEALISTA_URL = "https://www.idealista.com/venta-viviendas/altea-alicante/"
FOTOCASA_URL  = "https://www.fotocasa.es/es/comprar/viviendas/altea/todas-las-zonas/l"

FB_GROUPS = [
    {
        "id": "806383410011342",
        "name": "Altea Real Estate",
        "url": "https://www.facebook.com/groups/806383410011342",
    },
    {
        "id": "358112831484535",
        "name": "Venta Altea",
        "url": "https://www.facebook.com/groups/358112831484535",
    },
]

# ─── Zone keyword mapping ────────────────────────────────────
# Used to detect zone from listing title / description
ZONE_KEYWORDS: dict[str, list[str]] = {
    "Altea Hills":         ["altea hills", "sierra de altea"],
    "Casco Antiguo":       ["casco antiguo", "casco histórico", "pueblo blanco", "centro histórico", "old town"],
    "Mascarat/Campomanes": ["mascarat", "campomanes"],
    "Altea la Vella":      ["altea la vella", "la vella"],
    "Playa/Centro":        ["playa", "paseo marítimo", "paseo maritimo", "centro", "puerto"],
}
