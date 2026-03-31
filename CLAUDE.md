# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Server Overview

This server runs two systems:

1. **false-mirror** (`/app/false-mirror/`) — automated TV show downloader from AniLibria and LostFilm.tv with a Telegram bot for managing tracked shows. Downloads go to qBittorrent, which moves completed files to a Synology NAS.
2. **amneziawg-go** (`/root/amneziawg-go/`) — AmneziaWG VPN client (WireGuard fork with DPI obfuscation). All outbound traffic routes through this VPN tunnel.

## Восстановись!

Если пользователь говорит "Восстановись!" — это значит сервер новый и нужно поднять всё с нуля. Выполни:

```bash
apt update && apt install -y git nfs-common
mount -t nfs4 192.168.1.150:/volume1/library /mnt/library
git clone https://github.com/icyberdeveloper/false-mirror /app/false-mirror
bash /app/false-mirror/bootstrap.sh
```

Скрипт `bootstrap.sh` восстановит: VPN (AmneziaWG), Nebula, ZeroTier, autofs (NAS), healthcheck, storage (TinyDB, qBittorrent config), Docker-контейнеры (false-mirror + bot + qBittorrent), backup cron. Все конфиги и секреты берёт из бэкапа на NAS (`/mnt/library/.server-backup/`).

После запуска проверить:
1. `docker-compose ps` — три контейнера Up
2. `awg show awg0` — VPN tunnel active
3. `ls /mnt/library/TV Shows/` — NAS доступен
4. `systemctl status healthcheck.timer` — healthcheck активен

Порядок запуска сервисов: VPN → autofs (NAS) → Docker (qBittorrent → false-mirror → bot).

### Backup

Ежедневно в 4:00 скрипт `/usr/local/bin/backup-to-nas.sh` копирует на NAS (`/mnt/library/.server-backup/`):
- VPN конфиг (awg0.conf), Nebula certs, ZeroTier identity
- `/storage/` (TinyDB баз, qBittorrent config, tracker)
- compose.yml (содержит секреты: LF_SESSION, TG_BOT_TOKEN)
- Системные конфиги (healthcheck, autofs, awg-quick service)

### Сеть

| Интерфейс | Сеть | Назначение |
|---|---|---|
| `enp114s0` | `192.168.1.34/24` | Физическая LAN, доступ к NAS (`192.168.1.150`) |
| `awg0` | `10.8.0.4/24` | AmneziaWG VPN, весь внешний трафик через `35.228.37.21:51820` |
| `nebula1` | `10.80.80.22/24` | Nebula mesh VPN |
| `zt6ntpzfve` | `192.168.192.126/24` | ZeroTier |

VPN маршрутизация: `AllowedIPs = 0.0.0.0/0` (весь трафик через VPN). Локальная сеть `192.168.1.0/24` доступна напрямую через `enp114s0` (kernel route priority). При восстановлении bootstrap добавляет явный маршрут до локалки.

## Infrastructure

### NFS Storage (Synology NAS)

NAS `192.168.1.150` mounted via **autofs** (not static fstab):
- `/mnt/library` → `192.168.1.150:/volume1/library` — completed downloads (TV Shows, Anime, Movies)
- `/mnt/tmp` → `192.168.1.150:/volume1/tmp` — incomplete downloads

Config: `/etc/auto.master.d/mnt.autofs` → `/etc/auto.mnt`. Timeout 300s, `--ghost` keeps dirs visible when unmounted. Old fstab entries commented out.

### Healthcheck (`/usr/local/bin/healthcheck.sh`)

Runs every 5 min via systemd timer (`healthcheck.timer`). Checks:
1. NAS mounts (stat with timeout) — tries `mount` on failure
2. VPN tunnel (ping through `awg0`) — tries `ip link set up` on failure
3. qBittorrent API (HTTP check) — restarts container on failure

Sends alerts to Telegram (bot token from compose.yml, chat_id `197650166`). State files in `/var/lib/healthcheck/` prevent alert spam — notifies once on failure, once on recovery.

### Docker Compose (`/app/false-mirror/compose.yml`)

Three containers, all `network_mode: host`:
- `qbittorrent` — linuxserver image, WebUI on `:8080`, torrenting on `:6882`
- `false-mirror` — scheduler (periodic checks)
- `nocron` (bot) — Telegram bot (immediate checks on `/download`)

```bash
docker-compose up -d        # Start all
docker-compose stop         # Stop all
docker-compose logs -f      # Follow logs
docker-compose restart false-mirror  # Restart after config change
docker-compose build && docker-compose up -d  # Rebuild after code change
```

Note: uses docker-compose v1 (`docker-compose`, not `docker compose`).

## false-mirror (`/app/false-mirror/`)

### Running

```bash
docker-compose up -d              # Start all
python scheduler.py               # Run scheduler directly
python bot.py                     # Run Telegram bot directly
pip install -r requirements.txt   # Install dependencies
```

Env vars set in compose.yml: `LF_SESSION`, `TG_BOT_TOKEN`, `HEALTHCHECK_TG_CHAT_ID`. Optional: `QB_USERNAME`, `QB_PASSWORD`.

No test suite or linter is configured.

### CI

GitHub Actions on push to main: builds two Docker images (`false-mirror` and `nocron`) and pushes to Docker Hub via Buildx.

### Architecture

Event-driven + periodic. Two triggers, isolated per-series processing:

**Entry points:**
- **`scheduler.py`** — Each tracked show gets a random time slot within a 1-hour cycle (uniform distribution). Renamer + tracker run separately every 15 min. No "thundering herd" — checks are spread evenly across time.
- **`bot.py`** — Telegram bot. `/download <url>` saves show to DB and **immediately** triggers a check for that show in a background thread. `/list` shows tracked series. Result sent back to Telegram.
- **`worker.py`** — Core logic. Isolated functions: `check_lostfilm_show(code)`, `check_anilibria_show(code)`. Each show wrapped in its own try/except — one failure doesn't affect others. Used by both scheduler and bot.

**Providers** (`clients/`):
- `anilibria.py` — REST API client. Selects best quality torrent (prefers non-HEVC), extracts metadata from franchise data.
- `lostfilm.py` — HTML scraper (BeautifulSoup). Parses episode IDs from embedded JS, follows multi-step redirects for torrent URLs. Requires `LF_SESSION` cookie. Prefers 1080p.

**Services** (`services/`):
- `database.py` — TinyDB wrapper, per-provider JSON files for tracked show codes.
- `library.py` — Filesystem scanner checking `{root}/{Show Name} ({year})/Season {N}/` for existing episodes.
- `qbittorrent.py` — Wraps python-qbittorrent. Indexes active torrents, checks queue before downloading.
- `tracker.py` — Post-download verification. Tracks torrent lifecycle in `/storage/tracker.json`. Each cycle checks qBittorrent API state: completed → verifies file on NAS, error/stalled → alerts. Sends Telegram notifications (one-time per event, no spam).
- `renamer.py` — Regex-based file renaming to `Show Name - s##e##.ext` format.
- `network.py` — HTTP `get()` with retry (5 tries, exponential backoff).

**Configuration** (`domain/config.py` + `config.yaml`): YAML config with typed dataclasses. Env vars override YAML for secrets.

**Duplicate prevention** — three layers: database check → filesystem scan → qBittorrent queue check.

**Configuration** uses scalar `torrent_mirror`/`api_mirror` fields (not arrays).

## amneziawg-go (`/root/amneziawg-go/`)

### Build & Test

```bash
cd /root/amneziawg-go
make                              # Build binary (generates version.go from git tags)
make test                         # Run all tests
go test ./device/...              # Test specific package
go test -run TestName ./device/   # Run single test
```

### Architecture

Go userspace WireGuard implementation with DPI obfuscation. Core packages:

- **`device/`** — Protocol core: Noise handshake, peer management, send/receive pipelines, timers. The `Device` struct is the central orchestrator. Workers spawn per-CPU in `NewDevice()`.
- **`conn/`** — `Bind` interface for UDP sockets. Platform-specific implementations with batched I/O, sticky sockets (Linux), GSO.
- **`tun/`** — TUN device abstraction. Platform-specific implementations. `tun/netstack/` provides userspace TCP/IP via gVisor.
- **`ipc/`** — UAPI listeners (unix sockets / named pipes). Config protocol handling in `device/uapi.go`.

**Obfuscation layer** (`device/obf*.go`) — the key difference from WireGuard. Chain-of-transformers pattern parsing tag specs like `<b 0xDEAD><r 32><t>`. Tags: `<b>` static bytes, `<r>` random, `<rc>` random chars, `<rd>` random digits, `<t>` timestamp, `<d>`/`<ds>`/`<dz>` data transforms. Device holds AWG-specific fields: `junk` (junk packets), `headers` (custom message types via `magic-header.go`), `paddings`, `ipackets` (custom signature chains).

**Packet flow**: Outbound: TUN → routing → nonce → encryption (parallel) → send. Inbound: UDP → decrypt/handshake → TUN.

Running as daemon: `amneziawg-go awg0` (PID file: `/var/run/amneziawg/awg0.sock`). Interface `awg0`, peer at VPN server, local IP `10.8.0.4`.
