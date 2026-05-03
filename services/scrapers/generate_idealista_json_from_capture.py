"""
generate_idealista_json_from_capture.py - Vision-assisted Idealista JSON maker.

Takes a GoFullPage PNG/JPG capture, sends readable vertical chunks to a vision
model, and writes a reviewable JSON file for scraper_idealista_manual.py.

Usage:
  python generate_idealista_json_from_capture.py --latest
  python generate_idealista_json_from_capture.py --image manual_imports/idealista/captures/page.png

Required env:
  OPENAI_API_KEY=<your OpenAI API key>
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "manual_imports" / "idealista"
CAPTURE_DIR = IMPORT_DIR / "captures"


def find_latest_capture() -> Path:
    captures = []
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        captures.extend(CAPTURE_DIR.glob(pattern))
    if not captures:
        raise SystemExit(f"No PNG/JPG captures found in {CAPTURE_DIR}")
    return max(captures, key=lambda p: p.stat().st_mtime)


def encode_image_chunks(
    image_path: Path,
    *,
    crop_listing_column: bool = True,
    chunk_height: int = 2200,
    overlap: int = 140,
    max_width: int = 1400,
    jpeg_quality: int = 86,
    max_chunks: int = 12,
) -> list[str]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: Pillow. Install scraper requirements first:\n"
            "  pip install -r requirements.txt"
        ) from exc

    image = Image.open(image_path)
    image = image.convert("RGB")
    width, height = image.size

    if crop_listing_column:
        # Idealista desktop result captures usually have filters at left and
        # listing cards centered. Cropping improves OCR and lowers API cost.
        left = int(width * 0.18)
        right = int(width * 0.70)
        image = image.crop((left, 0, right, height))

    chunks: list[str] = []
    y = 0
    while y < image.height and len(chunks) < max_chunks:
        bottom = min(y + chunk_height, image.height)
        chunk = image.crop((0, y, image.width, bottom))

        if chunk.width > max_width:
            ratio = max_width / chunk.width
            chunk = chunk.resize((max_width, int(chunk.height * ratio)))

        buffer = BytesIO()
        chunk.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        chunks.append(f"data:image/jpeg;base64,{encoded}")

        if bottom == image.height:
            break
        y = bottom - overlap

    return chunks


def response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                parts.append(value)
    return "\n".join(parts)


def parse_json_text(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def generate_json(image_path: Path, model: str, max_chunks: int) -> dict:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: openai. Install scraper requirements first:\n"
            "  pip install -r requirements.txt"
        ) from exc

    # Load .env if python-dotenv is installed. The script still works without it
    # when OPENAI_API_KEY is already in the shell environment.
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
        load_dotenv()
    except Exception:
        pass

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is missing. Add it to services/scrapers/.env or your shell before running this script."
        )

    chunks = encode_image_chunks(image_path, max_chunks=max_chunks)
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Extract real estate listings from these Idealista search-result screenshot chunks. "
                "Return JSON only. Ignore filters, banners, agency ads, footer links and duplicate cards. "
                "For each property, extract visible title, price, m2, zone, description, url if visible, "
                "and notes. Use null when a value is not visible. Preserve Spanish accents if present. "
                "Do not invent URLs or listing IDs. Prices like 3.990.000 must remain 3.990.000 EUR."
            ),
        }
    ]
    for chunk in chunks:
        content.append({"type": "input_image", "image_url": chunk, "detail": "high"})

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "properties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": ["string", "null"]},
                        "price": {"type": ["string", "number", "null"]},
                        "m2": {"type": ["string", "number", "null"]},
                        "zone": {"type": ["string", "null"]},
                        "url": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "images": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": ["string", "null"]},
                    },
                    "required": [
                        "title",
                        "price",
                        "m2",
                        "zone",
                        "url",
                        "description",
                        "images",
                        "notes",
                    ],
                },
            }
        },
        "required": ["properties"],
    }

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "idealista_capture_listings",
                "schema": schema,
            }
        },
    )

    data = parse_json_text(response_text(response))
    for item in data.get("properties", []):
        item.setdefault("capture_file", image_path.name)
        item.setdefault("images", [])
        if not item.get("notes"):
            item["notes"] = "Generated from Idealista GoFullPage capture; review before upload."
    return data


def output_path_for(image_path: Path) -> Path:
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", image_path.stem).strip("_")
    return IMPORT_DIR / f"idealista_auto_{safe_stem}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Idealista manual JSON from a PNG/JPG capture")
    parser.add_argument("--image", type=Path, help="Capture path to process")
    parser.add_argument("--latest", action="store_true", help="Use latest capture in manual_imports/idealista/captures")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--model", default="gpt-4.1", help="Vision model to use")
    parser.add_argument("--max-chunks", type=int, default=12, help="Maximum vertical screenshot chunks to send")
    args = parser.parse_args()

    image_path = find_latest_capture() if args.latest else args.image
    if not image_path:
        raise SystemExit("Pass --latest or --image <path>")
    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path
    if not image_path.exists():
        raise SystemExit(f"Capture not found: {image_path}")

    output = args.output or output_path_for(image_path)
    if not output.is_absolute():
        output = BASE_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)

    data = generate_json(image_path, args.model, args.max_chunks)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(data.get('properties', []))} properties -> {output}")
    print("Review the JSON, then run:")
    print("  python scraper_idealista_manual.py --parse")
    print("  python main.py --source idealista-manual")


if __name__ == "__main__":
    main()
