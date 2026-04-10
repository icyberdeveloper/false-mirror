#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/mnt/backups/server"

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

# Docker daemon config
cp /etc/docker/daemon.json "$BACKUP_DIR/system/" 2>/dev/null || true

# Claude Code memory
if [ -d /root/.claude ]; then
    mkdir -p "$BACKUP_DIR/claude"
    cp -a /root/.claude/. "$BACKUP_DIR/claude/"
fi

# Compose (contains secrets)
cp /app/false-mirror/deploy/compose.yml "$BACKUP_DIR/compose.yml"

# Timestamp
date > "$BACKUP_DIR/last-backup.txt"
echo "[backup] Done: $BACKUP_DIR"
