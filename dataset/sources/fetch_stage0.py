#!/usr/bin/env python3
"""Stage 0 fetch helper - built for pasting into a single Kaggle
notebook cell on a phone, no separate file management needed.

How to use on a phone/Kaggle notebook:
1. Browse the categories in dataset/sources/stage0_sources.md (Wikimedia
   Commons / NASA) in your phone's browser.
2. For each clip you decide meets its category's acceptance criteria,
   copy the page URL (the Commons "File:..." page, or the NASA item
   page/details URL - NOT a right-click "copy video address", the
   normal page URL you're already looking at is enough).
3. Paste each URL into the matching list in CATEGORY_URLS below - just
   editing this file/cell, no new files to create.
4. Run this script (as a notebook cell, or `python fetch_stage0.py`).
   It resolves each page URL to the real video file, downloads it into
   dataset/raw/<category>/, and prints an ffprobe summary so you can
   sanity-check duration/resolution before ingest.
5. Open a couple of the downloaded files (Kaggle's file browser can
   preview video) and confirm they actually match the category's
   acceptance criteria in stage0_sources.md - this script cannot judge
   composition (3+ people interacting, subject occupying ~20-25% of
   frame, a real building in motion) for you, only fetch+report.

Stdlib-only (urllib, json, subprocess) - no extra `pip install` beyond
what `uv sync --all-packages` already provides.

NOTE: written from a sandboxed session with no live network access to
Wikimedia/NASA, so the API calls below are correct per their documented
API shape but not live-tested end-to-end from here. Run it on ONE url
first and check the output before pasting in all 50.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------
# EDIT THIS: paste 10 page URLs per category (Wikimedia Commons "File:"
# page, or NASA item/details page). Category keys must match the 5
# folder names in dataset/sources/stage0_sources.md exactly.
# ---------------------------------------------------------------------
CATEGORY_URLS: dict[str, list[str]] = {
    "multi_entity_interaction": [],
    "distant_small_subject": [],
    "dense_architecture": [],
    "wide_anchor_camera": [],
    "animals_regression_guard": [],
}
# ---------------------------------------------------------------------

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NASA_ASSET_API = "https://images-api.nasa.gov/asset/{nasa_id}"
_USER_AGENT = "sallehly-ai-engine-stage0-fetch/1.0 (dataset sourcing for Wan2.2 LoRA training)"


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.load(resp)


def resolve_commons_url(page_url: str) -> str:
    """Wikimedia Commons File: page URL -> real direct media file URL."""
    match = re.search(r"File:([^?#]+)", page_url)
    if not match:
        raise ValueError(f"not a Commons File: page URL: {page_url}")
    title = "File:" + urllib.parse.unquote(match.group(1))
    params = urllib.parse.urlencode(
        {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url", "format": "json"}
    )
    data = _get_json(f"{COMMONS_API}?{params}")
    for page in data.get("query", {}).get("pages", {}).values():
        imageinfo = page.get("imageinfo")
        if imageinfo:
            return imageinfo[0]["url"]
    raise ValueError(f"Commons API returned no imageinfo for {title} - check the URL is a real File: page")


def resolve_nasa_url(item_url: str) -> str:
    """NASA Image and Video Library item/details URL -> real .mp4 asset URL."""
    match = re.search(r"/details/([^/?#]+)", item_url) or re.search(r"[?&]nasa_id=([^&]+)", item_url)
    if not match:
        raise ValueError(f"could not find a NASA asset id in {item_url}")
    nasa_id = match.group(1)
    data = _get_json(NASA_ASSET_API.format(nasa_id=nasa_id))
    mp4_urls = [item["href"] for item in data.get("collection", {}).get("items", []) if item.get("href", "").endswith(".mp4")]
    if not mp4_urls:
        raise ValueError(f"no .mp4 asset found for NASA id {nasa_id}")
    mp4_urls.sort(key=lambda u: ("orig" not in u, u))  # prefer the ~orig (highest quality) file if present
    return mp4_urls[0]


def resolve(url: str) -> str:
    if "wikimedia.org" in url and "File:" in url:
        return resolve_commons_url(url)
    if "nasa.gov" in url:
        return resolve_nasa_url(url)
    return url  # assume it's already a direct file URL


def download(url: str, dest_without_ext: Path) -> Path:
    ext = Path(urllib.parse.urlparse(url).path).suffix or ".mp4"
    dest = dest_without_ext.with_suffix(ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    return dest


def ffprobe_summary(path: Path) -> str:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration",
                "-of", "default=noprint_wrappers=1", str(path),
            ],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return result.stdout.strip().replace("\n", " ")
    except Exception as exc:  # noqa: BLE001 - best-effort diagnostic, must not crash the batch
        return f"ffprobe failed: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--urls", type=Path, default=None,
        help="Optional JSON file ({category: [url, ...]}) instead of editing CATEGORY_URLS above",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("dataset/raw"))
    args = parser.parse_args(argv)

    categories = json.loads(args.urls.read_text()) if args.urls else CATEGORY_URLS
    if not any(categories.values()):
        print("CATEGORY_URLS is empty - edit the lists at the top of this file (or pass --urls) and re-run.")
        return 1

    failures: list[tuple[str, str, str]] = []
    print(f"{'category':<28} {'#':<3} status")
    for category, urls in categories.items():
        for i, url in enumerate(urls):
            dest_stub = args.out_dir / category / f"{category}_{i:02d}"
            try:
                direct_url = resolve(url)
                dest = download(direct_url, dest_stub)
                info = ffprobe_summary(dest)
                print(f"{category:<28} {i:<3} OK    {dest.name}  {info}")
            except Exception as exc:  # noqa: BLE001 - one bad URL must not kill the whole batch
                failures.append((category, url, str(exc)))
                print(f"{category:<28} {i:<3} FAIL  {url} -> {exc}")

    if failures:
        print(f"\n{len(failures)} download(s) failed - re-check the URL or source that one manually:")
        for category, url, err in failures:
            print(f"  [{category}] {url}: {err}")

    print(
        "\nNext: open a few downloaded files and confirm each one actually meets its "
        "category's acceptance criteria in dataset/sources/stage0_sources.md (delete and "
        "re-source any that don't), then run ingest_dataset.py per stage0_sources.md."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
