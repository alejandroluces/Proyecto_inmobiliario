"""Quick diagnostic: parse cached HTML and attempt one Supabase upsert."""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ── 1. Parse Fotocasa HTML cache ──────────────────────────────
print("\n=== FOTOCASA PARSE ===")
from scraper_fotocasa import parse_all_html as fc_parse
fc_props = fc_parse()
print(f"Fotocasa: {len(fc_props)} properties parsed")
for p in fc_props[:3]:
    print(f"  title={p['title'][:50]} | price={p.get('price')} | m2={p.get('m2')} | zone={p.get('zone')} | ext_id={p.get('external_id')}")

# ── 2. Parse Idealista HTML cache ─────────────────────────────
print("\n=== IDEALISTA PARSE ===")
from scraper_idealista import parse_all_html as id_parse
id_props = id_parse()
print(f"Idealista: {len(id_props)} properties parsed")
for p in id_props[:3]:
    print(f"  title={p['title'][:50]} | price={p.get('price')} | m2={p.get('m2')} | zone={p.get('zone')} | ext_id={p.get('external_id')}")

all_props = fc_props + id_props
if not all_props:
    print("\n❌ No properties parsed — check html_cache/ folder has results_page_*.html files")
    sys.exit(1)

# ── 3. Score first property ───────────────────────────────────
print("\n=== SCORING ===")
from scorer import score_property
test_prop = all_props[0]
zone_avgs = {"Altea Hills": 2750.0, "Casco Antiguo": 2820.0, "Playa/Centro": 2780.0}
score_property(test_prop, zone_avgs)
print(f"Score: {test_prop.get('opportunity_score')} | deviation: {test_prop.get('deviation_vs_avg')}")

# ── 4. Try Supabase upsert ────────────────────────────────────
print("\n=== SUPABASE UPSERT TEST ===")
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from supabase import create_client

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
print(f"Supabase URL: {SUPABASE_URL}")

db_row = {
    "source":            test_prop["source"],
    "external_id":       test_prop["external_id"],
    "url":               test_prop.get("url"),
    "title":             test_prop["title"],
    "description":       test_prop.get("description", ""),
    "price":             test_prop.get("price"),
    "m2":                test_prop.get("m2"),
    "zone":              test_prop.get("zone"),
    "images":            test_prop.get("images", []),
    "opportunity_score": test_prop.get("opportunity_score", 0),
    "deviation_vs_avg":  test_prop.get("deviation_vs_avg"),
    "is_facebook_exclusive": False,
}
print(f"Row to upsert: {db_row}")

try:
    result = sb.table("properties").upsert(db_row, on_conflict="source,external_id").execute()
    print(f"✅ Upsert OK — returned {len(result.data)} rows")
    if result.data:
        print(f"   ID: {result.data[0].get('id')}")
except Exception as e:
    print(f"❌ Upsert FAILED: {e}")
    # Try insert instead
    print("\nTrying plain INSERT...")
    try:
        result2 = sb.table("properties").insert(db_row).execute()
        print(f"✅ Insert OK — {result2.data}")
    except Exception as e2:
        print(f"❌ Insert also FAILED: {e2}")
