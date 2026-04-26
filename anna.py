#!/usr/bin/env python3
"""anna — CLI to search and download books from Anna's Archive."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

_xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
_user_env = _xdg_config / "anna" / ".env"
if _user_env.exists():
    load_dotenv(_user_env)
else:
    load_dotenv()  # fallback: legacy behavior (search from caller / CWD)

MIRRORS = [
    "https://annas-archive.gl",
    "https://annas-archive.gd",
    "https://annas-archive.org",
    "https://annas-archive.li",
    "https://annas-archive.pm",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MD5_RE = re.compile(r"/md5/([a-f0-9]{32})", re.IGNORECASE)
UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_FILENAME_LEN = 200


def err(msg):
    print(msg, file=sys.stderr)


def sanitize_filename(name):
    """Make a string safe for use as a filename."""
    name = UNSAFE_CHARS.sub("_", name).strip(". ")
    if len(name) > MAX_FILENAME_LEN:
        name = name[:MAX_FILENAME_LEN].rsplit(" ", 1)[0]
    return name or "untitled"


def build_filename(md5, title="", author=""):
    """Build 'Title - Author' filename, or fall back to MD5."""
    if not title:
        return None
    parts = [sanitize_filename(title)]
    if author:
        parts.append(sanitize_filename(author))
    return " - ".join(parts)


def get_mirror():
    """Return configured mirror, or auto-detect a working one."""
    configured = os.getenv("ANNAS_MIRROR", "").rstrip("/")
    if configured:
        return configured

    for mirror in MIRRORS:
        try:
            requests.head(mirror, timeout=5, allow_redirects=True)
            return mirror
        except requests.RequestException:
            continue

    err("Error: No reachable mirror found. Set ANNAS_MIRROR in .env.")
    sys.exit(1)


def get_api_key():
    key = os.getenv("ANNAS_API_KEY")
    if not key or key == "your_key_here":
        err("Error: ANNAS_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    return key


# ── Search ──────────────────────────────────────────────────────────────────


def search(query, lang="", ext="", content="", limit=10):
    """Search Anna's Archive and return a list of results."""
    mirror = get_mirror()
    params = {"q": query}
    if lang:
        params["lang"] = lang
    if ext:
        params["ext"] = ext
    if content:
        params["content"] = content

    url = f"{mirror}/search?{urlencode(params)}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for link in soup.select("a.js-vim-focus"):
        href = link.get("href", "")
        md5_match = MD5_RE.search(href)
        if not md5_match:
            continue

        md5 = md5_match.group(1)
        title = link.get_text(strip=True)

        author = ""
        container = link.parent
        if container:
            author_el = container.select_one("a span.icon-\\[mdi--user-edit\\]")
            if author_el and author_el.parent:
                author = author_el.parent.get_text(strip=True)

        meta = ""
        grandparent = container.parent if container else None
        if grandparent:
            meta_el = grandparent.select_one("div.font-semibold.text-sm")
            if meta_el:
                meta = meta_el.get_text(strip=True)
                meta = meta.split("Save")[0].strip().rstrip("·").strip()

        results.append({
            "md5": md5, "title": title, "author": author,
            "meta": meta, "url": f"{mirror}/md5/{md5}",
        })

        if len(results) >= limit:
            break

    return results


# ── Book details ────────────────────────────────────────────────────────────


def get_book_details(md5):
    """Fetch book details as JSON from /md5/{hash}.json."""
    mirror = get_mirror()
    url = f"{mirror}/md5/{md5}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Download ────────────────────────────────────────────────────────────────


def fast_download(md5, output_dir=".", raw_name=False):
    """Download a book using the fast download API."""
    mirror = get_mirror()
    key = get_api_key()

    # Fetch metadata for human-readable filename
    pretty_name = None
    if not raw_name:
        try:
            details = get_book_details(md5)
            title = details.get("title", "")
            author = details.get("author", "")
            pretty_name = build_filename(md5, title, author)
        except Exception:
            pass  # fall through to default naming

    url = f"{mirror}/dyn/api/fast_download.json"
    params = {"md5": md5, "key": key}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    download_url = data.get("download_url")
    if not download_url:
        err(f"Error: No download URL returned. Response: {data}")
        return None

    err(f"Downloading {pretty_name or md5}...")
    file_resp = requests.get(download_url, headers=HEADERS, timeout=120, stream=True)
    file_resp.raise_for_status()

    # Determine extension from Content-Disposition or Content-Type
    ext = ""
    cd = file_resp.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        server_name = cd.split("filename=")[-1].strip('"').strip("'")
        ext = Path(server_name).suffix

    if not ext:
        ct = file_resp.headers.get("Content-Type", "")
        ext_map = {
            "application/pdf": ".pdf",
            "application/epub+zip": ".epub",
            "application/x-mobipocket-ebook": ".mobi",
        }
        ext = ext_map.get(ct, ".bin")

    filename = f"{pretty_name}{ext}" if pretty_name else f"{md5}{ext}"

    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = int(file_resp.headers.get("Content-Length", 0))
    downloaded = 0

    with open(output_path, "wb") as f:
        for chunk in file_resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
                err(f"\r  [{bar}] {pct}%  {downloaded // 1024}KB")

    err(f"Saved: {output_path}")
    print(json.dumps({"path": str(output_path), "md5": md5, "filename": filename}))


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="anna",
        description="Search and download books from Anna's Archive",
    )
    sub = parser.add_subparsers(dest="command")

    # search
    sp_search = sub.add_parser("search", aliases=["s"], help="Search for books")
    sp_search.add_argument("query", nargs="+", help="Search terms")
    sp_search.add_argument("-l", "--lang", default="", help="Language filter (e.g. en, fr)")
    sp_search.add_argument("-e", "--ext", default="", help="Format filter (pdf, epub, mobi)")
    sp_search.add_argument("-c", "--content", default="", help="Content type (book_fiction, book_nonfiction)")
    sp_search.add_argument("-n", "--limit", type=int, default=10, help="Max results (default: 10)")

    # download
    sp_dl = sub.add_parser("download", aliases=["dl", "d"], help="Download by MD5 hash(es)")
    sp_dl.add_argument("md5", nargs="+", help="One or more MD5 hashes")
    sp_dl.add_argument("-o", "--output", default=".", help="Download directory")
    sp_dl.add_argument("--raw", action="store_true", help="Use MD5 as filename instead of title")

    # info
    sp_info = sub.add_parser("info", aliases=["i"], help="Get book details by MD5")
    sp_info.add_argument("md5", help="MD5 hash of the book")

    args = parser.parse_args()

    if args.command in ("search", "s"):
        query = " ".join(args.query)
        results = search(query, lang=args.lang, ext=args.ext, content=args.content, limit=args.limit)
        print(json.dumps(results, ensure_ascii=False))

    elif args.command in ("download", "dl", "d"):
        for md5 in args.md5:
            fast_download(md5, output_dir=args.output, raw_name=args.raw)

    elif args.command in ("info", "i"):
        details = get_book_details(args.md5)
        print(json.dumps(details, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
