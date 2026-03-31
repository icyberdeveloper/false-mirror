#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/mnt/library/.server-backup"
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"

echo "[backup] Starting backup to NAS..."

# VPN config (contains private keys)
cp /etc/amnezia/amneziawg/awg0.conf "$BACKUP_DIR/awg0.conf"

# false-mirror storage (TinyDB, qBittorrent config, tracker)
cp -a /storage/. "$BACKUP_DIR/storage/"

# System configs
mkdir -p "$BACKUP_DIR/system"
cp /usr/local/bin/healthcheck.sh "$BACKUP_DIR/system/"
cp /etc/systemd/system/healthcheck.service "$BACKUP_DIR/system/"
cp /etc/systemd/system/healthcheck.timer "$BACKUP_DIR/system/"
cp /etc/auto.master.d/mnt.autofs "$BACKUP_DIR/system/"
cp /etc/auto.mnt "$BACKUP_DIR/system/"
cp /etc/systemd/system/awg-quick@.service "$BACKUP_DIR/system/"

# Compose (contains secrets)
cp /app/false-mirror/deploy/compose.yml "$BACKUP_DIR/compose.yml"

# Timestamp
date > "$BACKUP_DIR/last-backup.txt"
echo "[backup] Done: $BACKUP_DIR"
