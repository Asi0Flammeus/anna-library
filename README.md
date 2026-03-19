# anna

CLI to search and download books from [Anna's Archive](https://annas-archive.org). Non-interactive, JSON-output, designed for scripting and AI agent pipelines.

## Install

```bash
pipx install git+https://github.com/asi0/anna-library.git
```

Or from a local clone:

```bash
pipx install -e .
```

## Setup

1. Create an account on Anna's Archive and get your secret key from the [account page](https://annas-archive.org/account)
2. Copy `.env.example` to `.env` and add your key:

```bash
cp .env.example .env
# edit .env → set ANNAS_API_KEY=your_secret_key
```

## Usage

### Search

```bash
anna search "the design of everyday things"
anna search "dune" -l en -e epub -n 5
```

Returns a JSON array to stdout:

```json
[
  {
    "md5": "abc123...",
    "title": "The Design of Everyday Things",
    "author": "Don Norman",
    "meta": "pdf, 12MB, English",
    "url": "https://annas-archive.org/md5/abc123..."
  }
]
```

### Download

```bash
anna dl <md5> -o ~/Books
anna dl <md5_1> <md5_2> <md5_3> -o ~/Books   # batch
anna dl <md5> --raw                            # use MD5 as filename
```

Files are saved with human-readable names by default (`Title - Author.pdf`). Use `--raw` for MD5-based filenames.

Returns one JSON object per file to stdout:

```json
{"path": "/home/user/Books/The Design of Everyday Things - Don Norman.pdf", "md5": "abc123...", "filename": "The Design of Everyday Things - Don Norman.pdf"}
```

### Info

```bash
anna info <md5>
```

Returns full book metadata as JSON.

## Agent-friendly design

- **No interactive prompts** — no `input()`, no menus, no confirmation dialogs
- **JSON to stdout** — all commands output structured JSON, parseable by `jq` or any agent
- **Progress/errors to stderr** — stdout stays clean for data piping
- **Proper exit codes** — `0` on success, `1` on error
- **Composable** — search, pick, download as separate steps:

```bash
# Find an epub and download the first result
anna search "meditations marcus aurelius" -e epub | jq -r '.[0].md5' | xargs anna dl -o ~/Books
```

## Filters

| Flag | Description | Examples |
|------|-------------|----------|
| `-l` | Language | `en`, `fr`, `de` |
| `-e` | Format | `pdf`, `epub`, `mobi` |
| `-c` | Content type | `book_fiction`, `book_nonfiction` |
| `-n` | Max results | `5`, `20` (default: 10) |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANNAS_API_KEY` | For downloads | Your Anna's Archive secret key |
| `ANNAS_MIRROR` | No | Override mirror URL (auto-detected otherwise) |

## License

MIT
