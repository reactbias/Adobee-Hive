#!/usr/bin/env bash
# Two Hives and the app, on this machine, reachable from everyone else at the hackathon.
#
#   ./lan.sh up      start both hubs and the app, seed the fake vaults, print the join URL
#   ./lan.sh down    stop everything
#   ./lan.sh check   is this machine actually reachable from another device?
#
# Everything is hosted here. Other people do not install anything: they open the URL this
# prints, on a laptop or a phone, and sign up in the browser.
set -uo pipefail
cd "$(dirname "$0")"

BACKEND=code/backend
RUN=.lan
mkdir -p "$RUN"

lan_ip() {
  # The address other devices on this network can actually reach, not 127.0.0.1.
  ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1 \
    || hostname -I 2>/dev/null | awk '{print $1}'
}

IP="$(lan_ip)"
[ -z "$IP" ] && { echo "Could not work out this machine's LAN address."; exit 1; }

free_port() {
  # Hackathon laptops already run things. Take the first free port from here upwards
  # rather than assuming 8000 is ours.
  local p="$1"
  while [ "$p" -lt 65000 ]; do
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then echo "$p"; return; fi
    exec 3<&- 2>/dev/null
    p=$((p + 1))
  done
  echo "no free port from $1" >&2; exit 1
}

PORT_A="${PORT_A:-$(free_port 8420)}"
PORT_B="${PORT_B:-$(free_port $((PORT_A + 1)))}"
PORT_APP="${PORT_APP:-$(free_port $((PORT_B + 1)))}"

start_hub() {
  local id="$1" port="$2" peer="$3"
  HIVE_HUB_ID="$id" \
  HIVE_NAME="Adobee Hive ($id)" \
  HIVE_PEER_URLS="$peer" \
  ADMISSION_POLICY="${ADMISSION_POLICY:-open}" \
  SEED_ON_EMPTY="$([ "$id" = basel ] && echo true || echo false)" \
  ADMIN_TOKEN="${ADMIN_TOKEN:-}" \
  DUCKDB_PATH="$PWD/$RUN/$id.duckdb" \
  CORS_ORIGINS='*' \
  nohup "$BACKEND/.venv/bin/python" -m uvicorn app.main:app \
      --app-dir "$BACKEND" --host 0.0.0.0 --port "$port" \
      > "$RUN/$id.log" 2>&1 &
  echo $! > "$RUN/$id.pid"
  printf "  %-8s http://%s:%s\n" "$id" "$IP" "$port"
}

wait_for() {
  for _ in $(seq 1 40); do
    curl -fsS "$1/api/health" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 1
}

case "${1:-up}" in
  up)
    echo "This machine: $IP"
    echo
    echo "Starting hubs..."
    start_hub basel  "$PORT_A" "http://$IP:$PORT_B"
    start_hub zurich "$PORT_B" "http://$IP:$PORT_A"

    for p in "$PORT_A" "$PORT_B"; do
      wait_for "http://127.0.0.1:$p" || { echo "  hub on $p did not come up; see $RUN/*.log"; exit 1; }
    done

    echo
    echo "Seeding the fake vaults through the real signup endpoint..."
    "$BACKEND/.venv/bin/python" "$BACKEND/tools/seed_vaults.py" \
        --hub "http://127.0.0.1:$PORT_A" --hub-id basel  --keys "$RUN/keys"
    "$BACKEND/.venv/bin/python" "$BACKEND/tools/seed_vaults.py" \
        --hub "http://127.0.0.1:$PORT_B" --hub-id zurich --keys "$RUN/keys"

    echo
    echo "Building the app against http://$IP:$PORT_A ..."
    APPLOG="$PWD/$RUN/app.log"
    APPPID="$PWD/$RUN/app.pid"
    ( cd code/frontend \
      && VITE_API_URL="http://$IP:$PORT_A" npm run build >/dev/null 2>&1 \
      && nohup npx --yes vite preview --host 0.0.0.0 --port "$PORT_APP" --strictPort \
           > "$APPLOG" 2>&1 &
      echo $! > "$APPPID" )
    sleep 3

    echo
    echo "────────────────────────────────────────────────────────────"
    echo "  Sign up here, from any browser on this network:"
    echo
    echo "      http://$IP:$PORT_APP"
    echo
    echo "  Laptop or phone, no install. Both hubs are on this machine."
    echo "────────────────────────────────────────────────────────────"
    echo
    echo "  hub directory   http://$IP:$PORT_A/api/hub/directory"
    echo "  what it asks    http://$IP:$PORT_A/api/hub/registration"
    echo "  API docs        http://$IP:$PORT_A/docs"
    echo "  second hub      http://$IP:$PORT_B"
    echo "  logs            $RUN/*.log"
    echo
    echo "  Tell someone on another device to run:  ./lan.sh check  (or just open the URL)"
    ;;

  check)
    echo "From ANOTHER device on this network, these should all answer:"
    echo "  curl http://$IP:$PORT_A/api/health"
    echo "  curl http://$IP:$PORT_B/api/health"
    echo "  open http://$IP:$PORT_APP"
    echo
    echo "From here:"
    for p in "$PORT_A" "$PORT_B"; do
      if curl -fsS "http://$IP:$p/api/health" >/dev/null 2>&1; then
        echo "  ✓ $IP:$p answers on the LAN address"
      else
        echo "  ✗ $IP:$p does not answer — hub down, or bound to localhost only"
      fi
    done
    echo
    echo "If another device cannot reach it but this one can, the wifi has client isolation."
    echo "Use a phone hotspot instead: every device joins the hotspot, including this laptop."
    ;;

  down)
    for f in "$RUN"/*.pid; do
      [ -e "$f" ] || continue
      kill "$(cat "$f")" 2>/dev/null && echo "stopped $(basename "$f" .pid)"
      rm -f "$f"
    done
    ;;

  *) echo "usage: ./lan.sh [up|down|check]"; exit 1 ;;
esac
