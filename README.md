# RepoPulse

A small Discord bot that posts GitHub repository activity (issues, PRs, reviews, pushes, releases, CI runs) into Discord channels as clean embeds.

Built because most GitHub→Discord integrations I've tried are either too noisy, too ugly, or too painful to self-host.

## What it does

- Listens to GitHub webhooks and forwards events to Discord.
- One bot process serves many servers — each server links its own repos.
- Different event types can go to different channels (issues → `#issues`, PRs → `#pull-requests`, etc.).
- Posts a reminder when a PR sits unreviewed for too long.

Supported events: `issues`, `pull_request`, `pull_request_review`, `push`, `release`, `workflow_run`.

## Slash commands

```
/link-repo        repo:owner/name [channel:#chan]
/unlink-repo      repo:owner/name
/list-repos
/set-channel      repo:owner/name event:<issues|pulls|reviews|pushes|releases|ci> channel:#chan
/review-reminder  mode:<enable|disable>
/ping
/help-repopulse
```

Management commands require the **Manage Server** permission.

## Stack

- `discord.py` 2.x
- `FastAPI` + `uvicorn` for webhooks
- `aiosqlite` for storage
- `pydantic-settings` for config
- `pytest` / `ruff`

Python 3.11+.

## Setup

1. **Discord** — create an app at <https://discord.com/developers/applications>, add a bot, copy the token. Invite URL needs `bot` and `applications.commands` scopes.
2. **GitHub webhook** — on the repo: Settings → Webhooks → Add webhook.
   - Payload URL: `https://your-host/github/webhook`
   - Content type: `application/json`
   - Secret: any random string (use the same value for `GITHUB_WEBHOOK_SECRET`)
   - Events: pick what you want, or "Send me everything".
3. **Env** — copy `.env.example` to `.env` and fill in at least `DISCORD_BOT_TOKEN` and `GITHUB_WEBHOOK_SECRET`.

## Run

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # or: source .venv/bin/activate
pip install -r requirements.txt
python -m repopulse
```

Or with Docker:

```bash
docker compose up --build
```

## How routing picks a channel

For a given event, RepoPulse picks the channel in this order:

1. Per-repo per-event route (set via `/set-channel`).
2. Per-repo default channel (set when linking).
3. Per-guild default (first channel used when linking any repo).
4. Skip.

## Dev

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

SQLite database lives at `./data/repopulse.db` by default. Delete it to wipe all links/routes.

## Roadmap

Stuff I'd like to add:

- AI PR summaries
- contributor leaderboards
- GitHub Actions dashboards
- analytics / activity metrics
- multi-repo workspaces

PRs welcome.
