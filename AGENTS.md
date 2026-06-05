# AGENTS.md — chatgpt-exporter

CLI tool to back up ChatGPT conversations (including project chats and file attachments) to local JSON, then convert to Markdown. Written in TypeScript, built with tsup, runs on Node ≥20.

## Directory Layout

```
chatgpt-exporter/
├── src/
│   ├── index.ts              # CLI entry point (shebang)
│   ├── api/
│   │   ├── client.ts         # HTTP client — authenticated fetch with browser headers, retry, rate-limit backoff
│   │   ├── endpoints.ts      # API endpoint URL builders
│   │   ├── pagination.ts     # Paginated fetchers for conversations, projects, project-conversations
│   │   └── types.ts          # Zod schemas + TS types for API responses
│   ├── cli/
│   │   ├── index.ts          # Commander.js CLI setup (backup, list, projects commands)
│   │   └── commands/
│   │       ├── backup.ts     # Main backup flow: list → download → markdown conversion, with progress bars
│   │       ├── list.ts       # List conversations without downloading
│   │       └── projects.ts   # List GPTs/projects
│   ├── services/
│   │   ├── backup-service.ts # Orchestrates listing + downloading, handles incremental/caching logic
│   │   ├── storage-service.ts# JSON read/write, index, listing cache, backup log
│   │   ├── file-service.ts   # Scans conversations for file references, downloads files/images
│   │   └── markdown-service.ts# Converts JSON conversations to readable Markdown
│   └── utils/
│       ├── progress.ts       # cli-progress bar factory
│       └── retry.ts          # Exponential backoff with jitter, sleep utility
├── show-conversation.py      # Standalone Python viewer for a single exported JSON conversation
├── run.sh                    # Shell wrapper that builds + runs the backup (reads token from `pass`)
├── package.json
├── tsconfig.json
└── dist/                     # Built output (tsup → ESM)
```

## Applications & Scripts

### 1. `chatgpt-exporter` (CLI — `src/`)

The main tool. Single binary installed via `npm start` or `npx`. Three commands:

| Command | What it does |
|---|---|
| `backup` | Full backup: list all conversations → download JSON → optionally download file attachments → convert to Markdown. Supports `--incremental`, `--project`, `--download-files`, `--concurrency`, `--delay`. |
| `list` | List conversation IDs + titles without downloading. Supports `--json` output. |
| `projects` | List all GPTs/projects. Supports `--json` output. |

**Auth:** Reads `CHATGPT_TOKEN` env var (or `--token`). Token comes from browser DevTools → Network → Authorization header.

**Output structure:**
```
export/<account>/
├── conversations/
│   ├── <uuid>.json          # individual conversation exports
│   ├── index.json            # listing of all conversation metadata
│   └── listing-cache.json    # cached listing for --incremental runs
├── projects/<project_name>/
│   └── conversations/
│       └── <uuid>.json
├── files/<file-id>/<filename># downloaded attachments/images
├── metadata.json             # backup stats + failed file IDs
└── backup.log                # timestamped log
```

**Key behaviors:**
- `--incremental` checks `update_time` on each conversation; skips unchanged ones. Uses a listing cache to avoid re-scanning when total count hasn't changed.
- Retry: exponential backoff with jitter (8s base, 60s max, 10 retries). Auth errors and 403/404 network errors bail immediately.
- Rate limiting: configurable `--delay` between requests, defaults to 500ms.
- Progress bars: separate bars for listing, downloading conversations, and downloading files. Each conversation download shows the topic title being downloaded in the progress bar.
- File downloads: scans exported JSON for `image_asset_pointer`, `attachments[]`, and `citations[]`; downloads each file once via signed URL; tracks previously-failed file IDs in `metadata.json` to skip on re-runs.

### 2. `show-conversation.py`

Standalone Python script (requires Python ≥3.10, uses `uv` for self-contained dependency management). Pretty-prints a single exported conversation JSON in the terminal with Unicode box-drawing:

```
╭──────────────────────────────────────────────────────────────────────────────╮
│                                            2024-01-15 10:30:00    🧑 You  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Hello, what's the weather like?                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

**Usage:**
- `show-conversation.py` — shows most recent conversation from default dirs
- `show-conversation.py <file.json>` — shows a specific file
- `show-conversation.py -l` — lists all conversations with titles, dates, message counts
- `show-conversation.py -l <dir>` — lists conversations in a specific directory

Handles ChatGPT genui widget markup (job postings), strips hidden/weight:0 messages, word-wraps to terminal width.

### 3. `run.sh`

Wrapper script that:
1. Reads the ChatGPT access token from `pass show openai/manweitam/access_token`
2. Runs `npm run build` to compile TypeScript
3. Runs `npm start -- backup` with `export/mwt` output, `--incremental`, `--download-files`, `--verbose`, concurrency=1, delay=10s
4. Unsets the token when done

## Build / Run

```bash
npm run build          # tsup → dist/
npm start -- backup --output export/mwt --incremental --verbose --delay 10000
npm run dev -- backup  # tsx → runs directly without build
```

## Dependencies

- **commander** — CLI framework
- **cli-progress** — progress bars (supports custom format tokens like `{topic}`)
- **ora** — spinners
- **chalk** — terminal colors
- **zod** — API response validation
- **tsup** — TypeScript bundler (build only)
- **tsx** — TypeScript executor (dev only)
