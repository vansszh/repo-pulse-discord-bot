# RepoPulse

A modern open-source Discord bot that connects GitHub collaboration directly into Discord servers.

RepoPulse transforms Discord into a lightweight developer collaboration hub by syncing GitHub repository activity in real time. Instead of constantly checking GitHub for updates, contributors and maintainers can receive clean, structured notifications for issues, pull requests, reviews, deployments, and repository events directly inside their Discord channels.

The bot is designed specifically for open-source communities, development teams, startup projects, and programming servers that want better visibility into repository activity without relying on bloated enterprise tools or noisy integrations.

---

## Core Purpose

Most GitHub-to-Discord integrations are either:

* too basic
* too noisy
* poorly formatted
* difficult to self-host
* overloaded with unnecessary features

RepoPulse focuses on one thing:

> Delivering clean, actionable GitHub collaboration workflows inside Discord.

The project prioritizes:

* simplicity
* developer experience
* extensibility
* modern UI embeds
* self-hosting support
* open-source friendliness

---

## Features

### Real-Time GitHub Event Tracking

RepoPulse listens to GitHub webhooks and instantly forwards important repository events to Discord.

Supported events include:

* issue opened / closed / reopened
* pull request opened / merged / closed
* draft PR marked ready for review
* pull request review submitted
* commits pushed
* releases published
* workflow / build status updates

### Beautiful Discord Embeds

Every GitHub event is rendered as a clean, readable Discord embed with:

* repository information
* author details
* labels
* PR status
* changed file counts
* direct GitHub links
* timestamps
* reviewer mentions

The goal is to make GitHub activity readable at a glance without overwhelming channels with clutter.

### Slash Command Management

Manage linked repositories directly from Discord using slash commands.

```
/link-repo           repo:owner/repository
/unlink-repo         repo:owner/repository
/list-repos
/set-channel         event:issues    channel:#issues
/set-channel         event:pulls     channel:#pull-requests
/review-reminder     mode:enable
/ping
/help-repopulse
```

### Pull Request Review Reminders

Automatically notify reviewers when pull requests remain inactive for too long.

* PR opened more than N hours ago
* no reviews submitted yet
* bot posts a reminder in the configured review channel

This helps maintainers reduce stale pull requests and improve contributor response times.

### Smart Repository Routing

Different repository event types can be routed into different Discord channels, per linked repository.

```
#issues           → bug reports and issue activity
#pull-requests    → code reviews
#ci-status        → GitHub Actions / workflow results
#releases         → new version announcements
```

This keeps developer communities organized and reduces notification noise.

### Self-Host Friendly

RepoPulse is designed for easy deployment and self-hosting.

Supported deployment methods:

* Docker
* Docker Compose
* plain Python 3.11+ runtime
* VPS hosting
* Railway, Render, Fly.io

Minimal setup should be possible in minutes.

### Permission System

Repository management commands are restricted to users with the Discord **Manage Server** permission. This prevents unauthorized repository linking or configuration changes.

---

## Technical Overview

RepoPulse uses GitHub webhooks to receive real-time repository events and forwards them through the Discord API using structured embeds.

```
GitHub Webhooks
        ↓
FastAPI webhook server   (HMAC-SHA256 signature verified)
        ↓
Event dispatcher         (routes by X-GitHub-Event + action)
        ↓
Embed builders           (render pretty Discord embeds)
        ↓
Discord bot client       (discord.py)
        ↓
Discord channels         (per-repo, per-event-type routing)
```

### Stack

| Layer              | Library                                    |
| ------------------ | ------------------------------------------ |
| Discord client     | [`discord.py`](https://discordpy.readthedocs.io) 2.x |
| Webhook server     | [`FastAPI`](https://fastapi.tiangolo.com) + `uvicorn` |
| Persistence        | SQLite via `aiosqlite`                     |
| Config             | `pydantic-settings` + `python-dotenv`      |
| HTTP               | `httpx`                                    |
| Tests              | `pytest` + `pytest-asyncio`                |

---

## Getting Started

### 1. Create a Discord application

1. Go to <https://discord.com/developers/applications> and create a new application.
2. Add a **Bot** to the application and copy the **Bot Token**.
3. Enable the `applications.commands` and `bot` scopes when generating an invite URL.
4. Invite the bot to your server.

### 2. Create a GitHub webhook

On your repository → **Settings → Webhooks → Add webhook**:

| Field         | Value                                                                |
| ------------- | -------------------------------------------------------------------- |
| Payload URL   | `https://your-host/github/webhook`                                   |
| Content type  | `application/json`                                                   |
| Secret        | a strong random string (also set as `GITHUB_WEBHOOK_SECRET`)         |
| Events        | *Send me everything*, or pick: Issues, Pull requests, Pull request reviews, Pushes, Releases, Workflow runs |

### 3. Configure environment

Copy `.env.example` to `.env` and fill in the values:

```env
DISCORD_BOT_TOKEN=...
GITHUB_WEBHOOK_SECRET=...
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
DATABASE_PATH=./data/repopulse.db
LOG_LEVEL=INFO
REVIEW_REMINDER_HOURS=24
```

### 4. Run locally

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Windows PowerShell
pip install -r requirements.txt
python -m repopulse
```

### 5. Run with Docker

```bash
docker compose up --build
```

---

## Usage

In any Discord channel where the bot is present:

```
/link-repo repo:octocat/hello-world
/set-channel event:issues channel:#issues
/set-channel event:pulls  channel:#pull-requests
/review-reminder mode:enable
/list-repos
```

All management commands require **Manage Server** permission.

---

## Built For

RepoPulse is ideal for:

* open-source projects
* developer communities
* hackathon teams
* startup engineering teams
* Discord coding servers
* student programming groups

---

## Design Philosophy

RepoPulse intentionally avoids becoming a "multi-purpose Discord bot." The project focuses entirely on developer collaboration and repository activity.

Key principles:

* clean architecture
* modular event handlers
* minimal setup friction
* low-noise notifications
* extensible plugin-style structure
* production-grade reliability

---

## Future Roadmap

Planned future features:

* AI pull request summaries
* contributor leaderboards
* advanced reviewer assignment
* GitHub Actions dashboards
* deployment notifications
* issue triaging tools
* analytics and activity metrics
* multi-repository workspaces

---

## Open Source

RepoPulse is fully open-source and community-driven. Contributions welcome for:

* new GitHub event integrations
* UI improvements
* slash commands
* deployment templates
* localization
* performance optimizations
* documentation improvements

The project aims to become a modern, developer-focused alternative to traditional GitHub notification systems for Discord communities.
