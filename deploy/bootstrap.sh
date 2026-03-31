#!/usr/bin/env bash
#
# Bootstrap script — rebuilds the server from scratch.
# Prerequisites: fresh Debian 12 machine with network access to NAS (192.168.1.150).
#
# Usage:
#   1. Install git + NFS: apt update && apt install -y git nfs-common
#   2. Mount NAS:         mount -t nfs4 192.168.1.150:/volume1/library /mnt/library
#   3. Clone repo:        git clone https://github.com/icyberdeveloper/false-mirror /app/false-mirror
#   4. Run:               bash /app/false-mirror/bootstrap.sh
#
set -euo pipefail

BACKUP_DIR="/mnt/library/.server-backup"

echo "============================================"
echo "  false-mirror server bootstrap"
echo "============================================"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup not found at $BACKUP_DIR"
    echo "Mount NAS first: mount -t nfs4 192.168.1.150:/volume1/library /mnt/library"
    exit 1
fi

# ============================================
# 1. System packages
# ============================================
echo "[1/8] Installing packages..."
apt update
apt install -y \
    docker.io docker-compose \
    autofs nfs-common \
    curl wget \
    software-properties-common

# ============================================
# 2. AmneziaWG VPN
# ============================================
echo "[2/8] Installing AmneziaWG..."
apt install -y amneziawg amneziawg-tools 2>/dev/null || {
    echo "Adding AmneziaWG repo..."
    add-apt-repository -y ppa:amnezia/ppa 2>/dev/null || {
        echo "deb https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu focal main" > /etc/apt/sources.list.d/amnezia.list
        apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 57290828 2>/dev/null || true
        apt update
    }
    apt install -y amneziawg amneziawg-tools
}

# Restore VPN config
mkdir -p /etc/amnezia/amneziawg
cp "$BACKUP_DIR/awg0.conf" /etc/amnezia/amneziawg/awg0.conf
chmod 600 /etc/amnezia/amneziawg/awg0.conf

# Restore systemd service for VPN
cp "$BACKUP_DIR/system/awg-quick@.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable awg-quick@awg0

# Start VPN
awg-quick up awg0 || echo "WARNING: VPN failed to start, check config"

# Add route for local network through physical interface (not VPN)
LOCAL_GW=$(ip route | grep "^default" | grep -v awg0 | awk '{print $3}' | head -1)
LOCAL_IF=$(ip route | grep "^default" | grep -v awg0 | awk '{print $5}' | head -1)
if [ -n "$LOCAL_GW" ] && [ -n "$LOCAL_IF" ]; then
    ip route add 192.168.1.0/24 via "$LOCAL_GW" dev "$LOCAL_IF" 2>/dev/null || true
    echo "Added local network route via $LOCAL_IF ($LOCAL_GW)"
fi

# ============================================
# 3. Nebula (mesh VPN)
# ============================================
echo "[3/8] Restoring Nebula..."
if [ -d "$BACKUP_DIR/nebula" ]; then
    mkdir -p /etc/nebula
    cp -a "$BACKUP_DIR/nebula/." /etc/nebula/
    # Install nebula if not present
    if ! command -v nebula &>/dev/null; then
        NEBULA_VER="1.9.5"
        wget -qO /tmp/nebula.tar.gz "https://github.com/slackhq/nebula/releases/download/v${NEBULA_VER}/nebula-linux-amd64.tar.gz"
        tar -xzf /tmp/nebula.tar.gz -C /usr/local/bin/ nebula nebula-cert
        rm /tmp/nebula.tar.gz
    fi
    systemctl enable nebula 2>/dev/null || true
    systemctl start nebula 2>/dev/null || true
fi

# ============================================
# 4. ZeroTier
# ============================================
echo "[4/8] Restoring ZeroTier..."
if [ -f "$BACKUP_DIR/zerotier-identity.secret" ]; then
    curl -s https://install.zerotier.com | bash || apt install -y zerotier-one
    systemctl stop zerotier-one 2>/dev/null || true
    cp "$BACKUP_DIR/zerotier-identity.public" /var/lib/zerotier-one/identity.public
    cp "$BACKUP_DIR/zerotier-identity.secret" /var/lib/zerotier-one/identity.secret
    systemctl enable --now zerotier-one
    # Rejoin networks from backup
    if [ -f "$BACKUP_DIR/zerotier-networks.json" ]; then
        python3 -c "
import json
with open('$BACKUP_DIR/zerotier-networks.json') as f:
    for net in json.load(f):
        print(net.get('nwid',''))
" | while read nwid; do
            [ -n "$nwid" ] && zerotier-cli join "$nwid" 2>/dev/null || true
        done
    fi
fi

# ============================================
# 5. NFS Autofs
# ============================================
echo "[5/8] Configuring autofs..."
mkdir -p /mnt /etc/auto.master.d
cp "$BACKUP_DIR/system/mnt.autofs" /etc/auto.master.d/
cp "$BACKUP_DIR/system/auto.mnt" /etc/auto.mnt 2>/dev/null || \
    cp "$BACKUP_DIR/system/auto.mnt" /etc/ 2>/dev/null || true

# If auto.mnt wasn't in backup, create it
[ -f /etc/auto.mnt ] || cat > /etc/auto.mnt << 'EOF'
library -fstype=nfs4,rw,noatime,nolock,intr,tcp,actimeo=1800 192.168.1.150:/volume1/library
tmp     -fstype=nfs4,rw,noatime,nolock,intr,tcp,actimeo=1800 192.168.1.150:/volume1/tmp
EOF

# Unmount static mounts if any, let autofs handle it
umount /mnt/library 2>/dev/null || true
umount /mnt/tmp 2>/dev/null || true

# Comment out static NFS mounts in fstab
sed -i 's|^192.168.1.150:/volume1|#192.168.1.150:/volume1|' /etc/fstab 2>/dev/null || true

systemctl enable --now autofs

# Verify
ls /mnt/library >/dev/null 2>&1 && echo "NAS mount OK" || echo "WARNING: NAS mount failed"

# ============================================
# 6. Restore storage data
# ============================================
echo "[6/8] Restoring storage..."
mkdir -p /storage
cp -a "$BACKUP_DIR/storage/." /storage/

# ============================================
# 7. Healthcheck
# ============================================
echo "[7/8] Setting up healthcheck..."
cp "$BACKUP_DIR/system/healthcheck.sh" /usr/local/bin/healthcheck.sh
chmod +x /usr/local/bin/healthcheck.sh
cp "$BACKUP_DIR/system/healthcheck.service" /etc/systemd/system/
cp "$BACKUP_DIR/system/healthcheck.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now healthcheck.timer

# ============================================
# 8. false-mirror (Docker)
# ============================================
echo "[8/8] Starting false-mirror..."

# Restore compose.yml with secrets
cp "$BACKUP_DIR/compose.yml" /app/false-mirror/deploy/compose.yml

cd /app/false-mirror/deploy
docker-compose build
docker-compose up -d

# ============================================
# 9. Backup cron
# ============================================
(crontab -l 2>/dev/null | grep -v backup-to-nas; echo "0 4 * * * /usr/local/bin/backup-to-nas.sh >> /var/log/backup-to-nas.log 2>&1") | crontab -
cp /usr/local/bin/backup-to-nas.sh /usr/local/bin/backup-to-nas.sh 2>/dev/null || true

echo ""
echo "============================================"
echo "  Bootstrap complete!"
echo "============================================"
echo ""
echo "Verify:"
echo "  cd /app/false-mirror/deploy && docker-compose ps  # Containers running"
echo "  awg show awg0              # VPN status"
echo "  ls /mnt/library/           # NAS mount"
echo "  systemctl status healthcheck.timer  # Healthcheck"
echo ""
