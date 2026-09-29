#!/usr/bin/env python3
"""anna — CLI to search and download books from Anna's Archive."""

import argparse
import functools
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Config precedence: process environment, then ./.env, then ~/.config/anna/.env.
# load_dotenv(override=False) never replaces a variable that is already set.
_xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
for _env_path in (Path.cwd() / ".env", _xdg_config / "anna" / ".env"):
    if _env_path.exists():
        load_dotenv(_env_path, override=False)

# .gl/.gd serve the genuine member API. .is serves search pages only (no API):
# it is kept for search, and get_api_mirror() never selects it for the key.
MIRRORS = [
    "https://annas-archive.gl",
    "https://annas-archive.gd",
    "https://annas-archive.is",
    "https://annas-archive.org",
    "https://annas-archive.li",
    "https://annas-archive.pm",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MD5_RE = re.compile(r"/md5/([a-f0-9]{32})(?:[/?#]|$)", re.IGNORECASE)
BOOK_RE = re.compile(r"/books/([0-9]+)(?:-[^/?#]+)?/?(?:[?#].*)?$")
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


def is_search_capable(response):
    """Return whether a response is Anna's HTML search page."""
    if response.status_code != 200 or "html" not in response.headers.get("Content-Type", "").lower():
        return False

    path = response.url.split("?", 1)[0].rstrip("/")
    if not path.endswith("/search"):
        return False

    soup = BeautifulSoup(response.text, "html.parser")
    return bool(soup.select_one('form[role="search"] input[name="q"]'))


def is_member_api(response):
    """Return whether a response is Anna's genuine fast_download JSON API.

    Probed without a key: the real API answers a keyless call with a JSON body
    carrying a `download_url` field (null) and an `error`.
    """
    if "json" not in response.headers.get("Content-Type", "").lower():
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    return isinstance(data, dict) and "download_url" in data


def candidate_mirrors():
    """ANNAS_MIRROR first when set, then the built-in list."""
    configured = os.getenv("ANNAS_MIRROR", "").rstrip("/")
    if not configured:
        return MIRRORS
    return [configured] + [m for m in MIRRORS if m != configured]


@functools.cache
def get_search_mirror():
    """Return the first mirror that serves Anna's HTML search page."""
    for mirror in candidate_mirrors():
        try:
            response = requests.get(
                f"{mirror}/search?q=anna", headers=HEADERS, timeout=10, allow_redirects=True,
            )
            if is_search_capable(response):
                return mirror
        except requests.RequestException:
            continue

    err("Error: No search-capable mirror found (unreachable, or HTML behind a DDoS-Guard challenge). Set ANNAS_MIRROR to a mirror that works from your network.")
    sys.exit(1)


@functools.cache
def get_api_mirror():
    """Return the first mirror that serves the genuine member API.

    The key is only ever sent to a mirror that passed this keyless probe, so a
    lookalike domain that only serves search pages never receives it.
    """
    for mirror in candidate_mirrors():
        try:
            response = requests.get(
                f"{mirror}/dyn/api/fast_download.json", headers=HEADERS, timeout=10, allow_redirects=False,
            )
            if is_member_api(response):
                return mirror
        except requests.RequestException:
            continue

    err("Error: No mirror serves the member API (/dyn/api/fast_download.json). Set ANNAS_MIRROR to a mirror that does.")
    sys.exit(1)


def get_api_key():
    key = os.getenv("ANNAS_API_KEY")
    if not key or key == "your_key_here":
        err("Error: ANNAS_API_KEY not set. Export it, or put it in ./.env or ~/.config/anna/.env (see .env.example).")
        sys.exit(1)
    return key


# ── Search ──────────────────────────────────────────────────────────────────


def parse_search_results(html, mirror, limit=10):
    """Parse current and legacy Anna search-result markup into JSON-ready records."""
    if limit <= 0:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for link in soup.select("h3 a[href]"):
        href = link["href"]
        match = BOOK_RE.search(href)
        if not match:
            continue

        metadata_el = link.find_parent("h3").find_next_sibling("div")
        metadata = " ".join(metadata_el.get_text(" ", strip=True).split()) if metadata_el else ""
        metadata_parts = [part.strip() for part in metadata.split("·")]
        author = metadata_parts[0] if metadata_parts else ""
        if author == "Unknown author":
            author = ""

        path = href[href.find("/books/"):]
        results.append({
            "record_id": match.group(1),
            "title": link.get_text(" ", strip=True),
            "author": author,
            "metadata": metadata,
            "url": f"{mirror}{path}",
        })
        if len(results) >= limit:
            return results

    for link in soup.select("a.js-vim-focus[href]"):
        href = link["href"]
        match = MD5_RE.search(href)
        if not match:
            continue

        md5 = match.group(1)
        container = link.parent
        author_el = container.select_one("a span.icon-\\[mdi--user-edit\\]") if container else None
        author = author_el.parent.get_text(strip=True) if author_el and author_el.parent else ""
        grandparent = container.parent if container else None
        meta_el = grandparent.select_one("div.font-semibold.text-sm") if grandparent else None
        metadata = meta_el.get_text(" ", strip=True).split("Save")[0].rstrip("· ").strip() if meta_el else ""
        results.append({
            "record_id": md5,
            "md5": md5,
            "title": link.get_text(" ", strip=True),
            "author": author,
            "metadata": metadata,
            "url": f"{mirror}/md5/{md5}",
        })
        if len(results) >= limit:
            break

    return results


def search(query, lang="", ext="", content="", limit=10):
    """Search Anna's Archive and return a list of results."""
    mirror = get_search_mirror()
    params = {"q": query}
    if lang:
        params["lang"] = lang
    if ext:
        params["ext"] = ext
        params["extension"] = ext  # .is names the format filter `extension`
    if content:
        params["content"] = content

    url = f"{mirror}/search?{urlencode(params)}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_search_results(resp.text, mirror, limit=limit)


# ── Book details ────────────────────────────────────────────────────────────


class DetailsError(Exception):
    pass


def get_book_details(md5):
    """Fetch book details as JSON from /md5/{hash}.json on the member-API mirror."""
    mirror = get_api_mirror()
    url = f"{mirror}/md5/{md5}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        raise DetailsError(f"{mirror} unreachable ({type(e).__name__})") from None
    if resp.status_code == 403 and "ddos-guard" in resp.text[:2000].lower():
        raise DetailsError(f"HTTP 403 DDoS-Guard challenge on {mirror}: its HTML/metadata pages are blocked from this network (the download API is not)")
    if resp.status_code != 200:
        raise DetailsError(f"HTTP {resp.status_code} from {url}")
    try:
        return resp.json()
    except ValueError:
        raise DetailsError(f"non-JSON response from {url}") from None


# ── Download ────────────────────────────────────────────────────────────────


def fast_download(md5, output_dir=".", raw_name=False):
    """Download a book using the fast download API."""
    mirror = get_api_mirror()
    key = get_api_key()

    # Fetch metadata for human-readable filename
    pretty_name = None
    if not raw_name:
        try:
            details = get_book_details(md5)
            title = details.get("title", "")
            author = details.get("author", "")
            pretty_name = build_filename(md5, title, author)
        except Exception as e:
            err(f"Warning: metadata fetch failed for {md5} ({type(e).__name__}: {e}); falling back to MD5 filename. Use --raw to silence.")

    url = f"{mirror}/dyn/api/fast_download.json"
    params = {"md5": md5, "key": key}
    # Never let the request URL reach stderr: it carries the key as a query parameter.
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        err(f"Error: fast_download request to {mirror} failed ({type(e).__name__}).")
        return None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code != 200:
        err(f"Error: fast_download for {md5} returned HTTP {resp.status_code} from {mirror}: {data.get('error', resp.reason)}")
        return None

    download_url = data.get("download_url")
    if not download_url:
        err(f"Error: No download URL returned for {md5}: {data.get('error', 'no error message')}")
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
    return output_path


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
        failed = [md5 for md5 in args.md5 if fast_download(md5, output_dir=args.output, raw_name=args.raw) is None]
        if failed:
            sys.exit(1)

    elif args.command in ("info", "i"):
        try:
            details = get_book_details(args.md5)
        except DetailsError as e:
            err(f"Error: info for {args.md5} failed: {e}")
            sys.exit(1)
        print(json.dumps(details, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
