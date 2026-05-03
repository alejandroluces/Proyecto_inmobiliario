"""
scraper_idealista_manual.py - Manual/assisted Idealista importer.

This is the conservative Idealista path: you browse Idealista yourself,
capture or copy what is visible, then this importer normalizes the records
so they can use the same scorer and Supabase upsert as the automated scrapers.

Supported inputs:
  - JSON files in manual_imports/idealista/*.json
  - TXT files in manual_imports/idealista/*.txt with one listing block separated
    by a blank line

Usage:
  python scraper_idealista_manual.py --template
  python scraper_idealista_manual.py --parse
  python main.py --source idealista-manual
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from utils import detect_zone, parse_m2, parse_price

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "manual_imports" / "idealista"
CAPTURE_DIR = IMPORT_DIR / "captures"
PROCESSED_DIR = IMPORT_DIR / "processed"

SOURCE_NAME = "Idealista Manual"


def _safe_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _stable_id(record: dict) -> str:
    """
    Prefer a real Idealista URL id. Fall back to a deterministic hash so repeated
    manual imports update the same row instead of creating duplicates.
    """
    url = _safe_text(record.get("url"))
    match = re.search(r"/inmueble/(\d+)/?", url)
    if match:
        return match.group(1)

    explicit = _safe_text(record.get("external_id") or record.get("id"))
    if explicit:
        return explicit

    fingerprint = "|".join(
        [
            _safe_text(record.get("title")).lower(),
            _safe_text(record.get("price")),
            _safe_text(record.get("m2") or record.get("surface")),
            _safe_text(record.get("zone")),
            url.lower(),
        ]
    )
    return "manual-" + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]


def _read_float(value: Any, parser) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parser(str(value))


def normalize_record(record: dict, source_file: Optional[Path] = None) -> Optional[dict]:
    title = _safe_text(record.get("title") or record.get("titulo"))
    description = _safe_text(record.get("description") or record.get("descripcion"))
    url = _safe_text(record.get("url"))

    if "123456789" in url or "Texto visible o notas de la captura" in description:
        logger.info("Skipping Idealista manual template/example record")
        return None

    text_blob = " ".join(
        [
            title,
            description,
            _safe_text(record.get("zone") or record.get("zona")),
            _safe_text(record.get("raw_text")),
        ]
    )

    price = _read_float(record.get("price") or record.get("precio"), parse_price)
    m2 = _read_float(record.get("m2") or record.get("surface") or record.get("metros"), parse_m2)
    raw_zone = _safe_text(record.get("zone") or record.get("zona"))
    zone = detect_zone(" ".join([raw_zone, text_blob]))

    if not title:
        title = f"Idealista manual {_stable_id(record)}"

    if not price and not m2:
        logger.warning(
            "Skipping manual Idealista record without price or m2: %s",
            title[:80],
        )
        return None

    images = record.get("images") or record.get("imagenes") or []
    if isinstance(images, str):
        images = [images]

    capture_file = _safe_text(record.get("capture_file") or record.get("captura"))
    capture_path = ""
    if capture_file:
        candidate = Path(capture_file)
        if not candidate.is_absolute():
            candidate = CAPTURE_DIR / capture_file
        capture_path = str(candidate)

    notes = _safe_text(record.get("notes") or record.get("notas"))
    source_note = f"Imported manually from {source_file.name}" if source_file else "Manual Idealista import"
    description_parts = [p for p in [description, notes, source_note, capture_path] if p]

    return {
        "source": SOURCE_NAME,
        "external_id": _stable_id(record),
        "url": url or None,
        "title": title,
        "description": "\n".join(description_parts),
        "price": price,
        "m2": m2,
        "zone": zone or None,
        "images": images,
        "manual_capture_path": capture_path or None,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


def _records_from_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("properties"), list):
            return data["properties"]
        if isinstance(data.get("listings"), list):
            return data["listings"]
        return [data]
    if isinstance(data, list):
        return data
    return []


def _record_from_text_block(block: str) -> dict:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    joined = " ".join(lines)
    url_match = re.search(r"https?://\S+", joined)

    title = lines[0] if lines else "Idealista manual"
    price = parse_price(joined)
    m2 = parse_m2(joined)
    zone = detect_zone(joined)

    return {
        "title": title,
        "description": joined,
        "price": price,
        "m2": m2,
        "zone": zone,
        "url": url_match.group(0) if url_match else "",
        "raw_text": block,
    }


def _records_from_txt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return [_record_from_text_block(block) for block in blocks]


def parse_manual_imports(import_dir: Path = IMPORT_DIR) -> list[dict]:
    import_dir.mkdir(parents=True, exist_ok=True)
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    json_files = [
        path for path in sorted(import_dir.glob("*.json"))
        if not path.name.endswith(".example.json")
    ]
    txt_files = [
        path for path in sorted(import_dir.glob("*.txt"))
        if not path.name.endswith(".example.txt")
    ]
    candidates = json_files + txt_files
    results: list[dict] = []
    seen: set[str] = set()

    for path in candidates:
        try:
            raw_records = _records_from_json(path) if path.suffix.lower() == ".json" else _records_from_txt(path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", path.name, exc)
            continue

        for raw in raw_records:
            prop = normalize_record(raw, source_file=path)
            if not prop:
                continue
            key = prop["external_id"]
            if key in seen:
                continue
            seen.add(key)
            results.append(prop)

    logger.info("Idealista Manual: %s properties ready from %s", len(results), import_dir)
    return results


async def scrape_idealista_manual() -> list[dict]:
    return parse_manual_imports()


def write_template(path: Path = IMPORT_DIR / "idealista_manual_template.example.json") -> Path:
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

    if path.exists():
        return path

    sample = {
        "properties": [
            {
                "title": "Casa o chalet en venta en Calle Holanda, 91, Altea Hills",
                "price": "3.990.000 EUR",
                "m2": "1065 m2",
                "zone": "Altea Hills",
                "url": "https://www.idealista.com/inmueble/123456789/",
                "description": "Texto visible o notas de la captura.",
                "capture_file": "idealista_altea_hills_2026-05-02.png",
                "images": [],
                "notes": "Pegado manual desde captura GoFullPage."
            }
        ]
    }
    path.write_text(json.dumps(sample, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Idealista manual/assisted importer")
    parser.add_argument("--template", action="store_true", help="Create a JSON template")
    parser.add_argument("--parse", action="store_true", help="Parse manual import files")
    args = parser.parse_args()

    if args.template:
        template = write_template()
        print(f"Template ready: {template}")
    else:
        props = parse_manual_imports()
        print(f"\nTotal: {len(props)} manual Idealista properties")
        for prop in props[:10]:
            price = f"EUR {prop['price']:,.0f}" if prop.get("price") else "sin precio"
            print(f"  {prop['external_id']} | {price} | {prop.get('m2') or '?'} m2 | {prop['title'][:70]}")
