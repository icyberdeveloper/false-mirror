#!/usr/bin/env bash
set -euo pipefail

# --- Config ---
TG_BOT_TOKEN="6934685680:AAF1uNpBNVya6ljNFrxahUsli4ZezRstZYo"
TG_CHAT_ID="${HEALTHCHECK_TG_CHAT_ID:?Set HEALTHCHECK_TG_CHAT_ID env var}"

NAS_PATHS=("/mnt/library" "/mnt/tmp")
VPN_IFACE="awg0"
VPN_TEST_HOST="1.1.1.1"
QB_URL="http://127.0.0.1:8080/api/v2/app/version"

STATE_DIR="/var/lib/healthcheck"
mkdir -p "$STATE_DIR"

# --- Helpers ---
send_alert() {
    local msg="⚠️ $(hostname): $1"
    curl -sf --max-time 10 \
        "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TG_CHAT_ID" \
        -d text="$msg" \
        -d parse_mode="HTML" >/dev/null 2>&1 || true
}

send_recovery() {
    local msg="✅ $(hostname): $1"
    curl -sf --max-time 10 \
        "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TG_CHAT_ID" \
        -d text="$msg" \
        -d parse_mode="HTML" >/dev/null 2>&1 || true
}

# Track alert state to avoid spam: alert once, then notify on recovery
is_failing() { [ -f "$STATE_DIR/$1.fail" ]; }
mark_failing() { touch "$STATE_DIR/$1.fail"; }
mark_ok() { rm -f "$STATE_DIR/$1.fail"; }

check_and_alert() {
    local name="$1" msg="$2"
    if ! is_failing "$name"; then
        send_alert "$msg"
        mark_failing "$name"
    fi
}

recover() {
    local name="$1" msg="$2"
    if is_failing "$name"; then
        send_recovery "$msg"
        mark_ok "$name"
    fi
}

# --- Checks ---
errors=0

# 1. NAS mounts
for path in "${NAS_PATHS[@]}"; do
    name="nas_$(echo "$path" | tr '/' '_')"
    if timeout 5 stat "$path" >/dev/null 2>&1 && timeout 5 test -d "$path"; then
        recover "$name" "NFS mount <b>${path}</b> is back"
    else
        check_and_alert "$name" "NFS mount <b>${path}</b> is stale or missing"
        # Try remount
        mount "$path" 2>/dev/null || true
        ((errors++))
    fi
done

# 2. VPN tunnel
name="vpn"
if ip link show "$VPN_IFACE" up >/dev/null 2>&1 && \
   ping -c1 -W3 -I "$VPN_IFACE" "$VPN_TEST_HOST" >/dev/null 2>&1; then
    recover "$name" "VPN tunnel <b>${VPN_IFACE}</b> is back"
else
    check_and_alert "$name" "VPN tunnel <b>${VPN_IFACE}</b> is down"
    # Try restart
    if [ -S "/var/run/amneziawg/${VPN_IFACE}.sock" ]; then
        ip link set "$VPN_IFACE" up 2>/dev/null || true
    fi
    ((errors++))
fi

# 3. qBittorrent API (403 Forbidden = alive, just unauthenticated)
name="qbittorrent"
qb_http_code=$(curl -so /dev/null -w '%{http_code}' --max-time 5 "$QB_URL" 2>/dev/null || echo "000")
if [ "$qb_http_code" != "000" ]; then
    recover "$name" "qBittorrent is back"
else
    check_and_alert "$name" "qBittorrent is not responding"
    # Try restart container
    docker-compose restart qbittorrent 2>/dev/null || true
    ((errors++))
fi

# 5. Disk space
name="disk_root"
disk_pct=$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "$disk_pct" -ge 90 ]; then
    check_and_alert "$name" "Disk usage <b>${disk_pct}%</b> on /"
    # Auto-prune old Docker images
    docker image prune -f >/dev/null 2>&1 || true
    ((errors++))
else
    recover "$name" "Disk usage back to <b>${disk_pct}%</b>"
fi

# 6. RAM usage
name="ram"
ram_pct=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ "$ram_pct" -ge 90 ]; then
    check_and_alert "$name" "RAM usage <b>${ram_pct}%</b>"
    ((errors++))
else
    recover "$name" "RAM usage back to <b>${ram_pct}%</b>"
fi

# 7. Docker containers
for svc in false-mirror nocron qbittorrent; do
    name="docker_${svc}"
    if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
        recover "$name" "Container <b>${svc}</b> is back"
    else
        check_and_alert "$name" "Container <b>${svc}</b> is not running"
        ((errors++))
    fi
done

# 8. System load
name="load"
load_1m=$(awk '{print $1}' /proc/loadavg)
load_int=${load_1m%.*}  # truncate to integer
cpus=$(nproc)
threshold=$((cpus * 2))
if [ "$load_int" -ge "$threshold" ]; then
    check_and_alert "$name" "High load: <b>${load_1m}</b> (${cpus} CPUs)"
    ((errors++))
else
    recover "$name" "Load back to normal: <b>${load_1m}</b>"
fi

exit $errors
