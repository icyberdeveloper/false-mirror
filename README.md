# false-mirror

Automated TV show downloader for [AniLibria](https://anilibria.tv) and [LostFilm](https://lostfilm.tv). Monitors tracked shows for new episodes, downloads them via qBittorrent, and moves completed files to a Synology NAS. Includes a Telegram bot for managing the watch list.

## How it works

1. You send a link to the Telegram bot (`/download <url>`)
2. Bot saves the show and **immediately** checks for available episodes
3. Episodes are downloaded via qBittorrent to the NAS
4. A scheduler rechecks all shows hourly (each show at a random time to spread load)
5. Post-download tracker verifies files landed on NAS and alerts via Telegram

## Quick Start

```bash
git clone https://github.com/icyberdeveloper/false-mirror.git
cd false-mirror/deploy
```

Edit `compose.yml` and set environment variables:

| Variable | Required | Description |
|---|---|---|
| `LF_SESSION` | Yes | LostFilm session cookie |
| `TG_BOT_TOKEN` | Yes | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `HEALTHCHECK_TG_CHAT_ID` | Yes | Your Telegram chat ID for alerts |
| `QB_USERNAME` | No | qBittorrent username (default: `admin`) |
| `QB_PASSWORD` | No | qBittorrent password (default: `adminadmin`) |

```bash
docker-compose build
docker-compose up -d
```

## Telegram Bot Commands

- `/download <url>` - Add a show or movie. Accepts:
  - `lostfilm.*/series/...` — TV series (tracked, periodic checks)
  - `lostfilm.*/movies/...` — movies (fire-and-forget, downloads immediately)
  - `anilibria.*/release/...` — anime series (tracked, periodic checks)
- `/list` - Show all tracked series
- `/start` - Help

## Project Structure

```
false-mirror/
├── app/                    # Python application
│   ├── scheduler.py        # Periodic checks (entry point)
│   ├── bot.py              # Telegram bot (entry point)
│   ├── worker.py           # Isolated per-series check functions
│   ├── config.py           # Config parsing
│   ├── clients/            # Data providers
│   │   ├── anilibria.py    # AniLibria REST API client
│   │   └── lostfilm.py     # LostFilm HTML scraper
│   └── services/           # Shared services
│       ├── database.py     # TinyDB storage
│       ├── library.py      # Filesystem scanner (duplicate prevention)
│       ├── qbittorrent.py  # qBittorrent API wrapper
│       ├── tracker.py      # Post-download verification + alerts
│       ├── renamer.py      # File renaming (Show - s01e01.mkv)
│       └── network.py      # HTTP client with retry
├── deploy/                 # Infrastructure
│   ├── compose.yml         # Docker Compose
│   ├── Dockerfile          # Scheduler container
│   ├── Dockerfile.bot      # Bot container
│   ├── bootstrap.sh        # Full server recovery script
│   └── backup-to-nas.sh    # Daily backup to NAS
├── config.yaml             # Application config
└── requirements.txt
```

## Architecture

**Two triggers:**
- **Immediate** - Bot adds a show and instantly checks for episodes in a background thread
- **Periodic** - Scheduler assigns each show a random time slot within a 1-hour cycle, spreading load evenly

**Error isolation:** Each show is processed independently. If one show's source is down, others continue working normally.

**Duplicate prevention** (three layers):
1. Database check - is this episode tracked?
2. Filesystem scan - is it already on NAS?
3. qBittorrent queue check - is it already downloading?

**Post-download verification:** Tracker monitors qBittorrent state per torrent. On completion, verifies the file exists on NAS. Alerts via Telegram on problems (stalled downloads, missing files, errors).

## Docker Images

All images are hosted on Docker Hub and built by CI on every push to main:

| Image | Description |
|---|---|
| `icyberdeveloper/false-mirror` | Scheduler (periodic episode checks) |
| `icyberdeveloper/nocron` | Telegram bot |
| `icyberdeveloper/qbittorrent` | Mirror of linuxserver/qbittorrent (pinned version) |

Images are tagged with `latest` and git SHA for version tracking.

```bash
cd deploy
docker-compose pull && docker-compose up -d   # Update from registry
docker-compose up -d --build                   # Build locally (development)
```

## Configuration

Application config is in `config.yaml`. Secrets are set via environment variables in `deploy/compose.yml`.

### Providers

**AniLibria** - REST API. Selects best quality torrent (prefers non-HEVC). Downloads full seasons.

**LostFilm** - HTML scraper. Follows multi-step redirects to get torrent URLs. Requires `LF_SESSION` cookie (get it from browser after logging in to lostfilm.tv). Prefers 1080p, falls back to 720p/HDTVRip. Downloads individual episodes.

## Disaster Recovery

All configs and data are backed up daily to NAS. To rebuild the server from scratch:

```bash
apt update && apt install -y git nfs-common
mkdir -p /mnt/backups && mount -t nfs4 192.168.1.150:/volume1/backups /mnt/backups
git clone https://github.com/icyberdeveloper/false-mirror /app/false-mirror
bash /app/false-mirror/deploy/bootstrap.sh
```

See [CLAUDE.md](CLAUDE.md) for full infrastructure documentation.
