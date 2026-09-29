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

Prints a JSON array (`[]` when nothing matches). Every record has `record_id`, `title`, `author`, `metadata` and `url`. `info` and `dl` need an MD5, and only legacy `/md5/` results carry an `md5` field (their `record_id` is the same MD5). Current catalog cards, which is what `annas-archive.is` returns, have a numeric `record_id`, a `/books/` URL and **no `md5`**. You cannot download them with this CLI.

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

Files are named `Title - Author.ext` when the metadata page is reachable, and `<md5>.ext` otherwise (or with `--raw`). One JSON line per downloaded file:

```json
{"path": "/home/user/Books/Title - Author.epub", "md5": "<md5>", "filename": "Title - Author.epub"}
```

Pick an MD5 from search and download it in one pipeline, when the search results include legacy MD5 records:

```bash
md5=$(anna search "meditations marcus aurelius" -n 20 | jq -r '[.[] | select(.md5)][0].md5')
[ "$md5" != null ] && anna dl "$md5" -o ~/Books
```

Each successful `dl` uses up one fast download from the account's daily quota.

## Filters

| Flag | Description | Examples |
|------|-------------|----------|
| `-l` | Language, sent as `lang` (ignored by `annas-archive.is`) | `en`, `fr`, `de` |
| `-e` | Format, sent as `ext` and `extension` | `pdf`, `epub`, `mobi` |
| `-c` | Content type, sent as `content` (ignored by `annas-archive.is`) | `book_fiction`, `book_nonfiction` |
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
| `No download URL returned for <md5>: …` | The API answered without a link (for example `Record not found`); its `error` text follows |

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT
