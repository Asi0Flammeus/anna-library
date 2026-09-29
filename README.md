# anna

CLI to search and download books from Anna's Archive. Non-interactive, JSON on stdout, errors on stderr: built for scripts and AI agents.

## Install

```bash
pipx install git+https://github.com/Asi0Flammeus/anna-library.git
```

Or from a local clone:

```bash
pipx install -e .
```

## Setup

`anna` reads its config from the process environment first, then `./.env`, then `~/.config/anna/.env`. A variable already set is never overridden.

| Variable | Required | Description |
|----------|----------|-------------|
| `ANNAS_API_KEY` | For `dl` | Secret key of an Anna's Archive account with an active membership |
| `ANNAS_MIRROR` | No | Mirror to try first (default: auto-detect, see below) |

```bash
cp .env.example .env
# edit .env → set ANNAS_API_KEY=your_secret_key
```

Never print, log or commit the key.

## Mirrors

Built-in list, tried in order (`ANNAS_MIRROR` is tried before it):
`annas-archive.gl`, `.gd`, `.is`, `.org`, `.li`, `.pm`. `.gl` and `.gd` serve the member API; `.is` serves search pages only and is used as a search fallback.

Two roles are detected separately, once per run:

- **Search** uses the first mirror that serves the HTML search page.
- **`info` and `dl`** use the first mirror that serves the genuine member API: a keyless call to `/dyn/api/fast_download.json` must return JSON with a `download_url` field. The key is only ever sent to a mirror that passed that probe, so a domain that only serves search pages never receives it.

## Usage

### Search

```bash
anna search "the design of everyday things"
anna search "dune" -l en -e epub -n 5
```

Prints a JSON array. Current catalog cards carry a numeric `record_id`; legacy `/md5/` results also carry `md5`, which `info` and `dl` need.

```json
[
  {
    "record_id": "674762",
    "title": "Dune",
    "author": "Herbert, Frank",
    "metadata": "Herbert, Frank · 1982 · EPUB · 1 B · Books catalog",
    "url": "https://annas-archive.is/books/674762-dune-674762"
  },
  {
    "record_id": "<md5>",
    "md5": "<md5>",
    "title": "…",
    "author": "…",
    "metadata": "…",
    "url": "https://<mirror>/md5/<md5>"
  }
]
```

### Info

```bash
anna info <md5>
```

Prints the archive's full metadata record for that file as JSON.

### Download

```bash
anna dl <md5> -o ~/Books
anna dl <md5_1> <md5_2> -o ~/Books   # batch
anna dl <md5> --raw                  # MD5 as filename
```

Files are named `Title - Author.ext` when metadata is reachable, `<md5>.ext` otherwise. One JSON line per downloaded file:

```json
{"path": "/home/user/Books/Dune - Frank Herbert.epub", "md5": "<md5>", "filename": "Dune - Frank Herbert.epub"}
```

## Filters

| Flag | Description | Examples |
|------|-------------|----------|
| `-l` | Language | `en`, `fr`, `de` |
| `-e` | Format | `pdf`, `epub`, `mobi` |
| `-c` | Content type | `book_fiction`, `book_nonfiction` |
| `-n` | Max results | `5`, `20` (default: 10) |

## Exit codes and errors

`0` on success, `1` on any error (for `dl`, if any requested file failed). Messages go to stderr and never contain the key.

| stderr | Meaning |
|--------|---------|
| `ANNAS_API_KEY not set` | No key in env, `./.env` or `~/.config/anna/.env` |
| `No search-capable mirror found` | Every mirror is down or shows a DDoS-Guard challenge to your IP; set `ANNAS_MIRROR` |
| `No mirror serves the member API` | No mirror passed the keyless API probe |
| `HTTP 401 … Invalid secret key` | The key is wrong |
| `HTTP 403 … Not a member` | The key is valid but its membership is inactive |
| `HTTP 403 DDoS-Guard challenge` (`info`, or a filename warning in `dl`) | HTML/metadata pages are blocked from your network; `dl` still works and names the file by MD5 |

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT
