#!/usr/bin/env bash
# Two Hives and the app, on this machine, reachable from everyone else at the hackathon.
#
#   ./lan.sh up      start both hubs and the app, seed the fake vaults, print the join URL
#   ./lan.sh down    stop everything this checkout started
#   ./lan.sh check   is this machine actually reachable from another device?
#
# What it starts is recorded in .lan/state - the address, the ports, this checkout - so that
# 'down' and 'check' act on the stack that is running rather than guessing it again, and so a
# change of network can be noticed rather than silently breaking every link.
#
# Everything is hosted here. Other people do not install anything: they open the URL this
# prints, on a laptop or a phone, and sign up in the browser.
set -uo pipefail
cd "$(dirname "$0")"

BACKEND=code/backend
RUN=.lan
STATE="$RUN/state"
HERE=$(pwd -P)          # this checkout, used to tell our servers from another worktree's
mkdir -p "$RUN"
CMD="${1:-up}"

pid_on() {
  # The pid listening on a TCP port, or "" when nothing is.
  ss -ltnp 2>/dev/null | grep ":$1 " | grep -oP 'pid=\K[0-9]+' | head -1
}

ours() {
  # True when this pid is one of ours: a uvicorn or vite started from inside THIS checkout.
  #
  # Both halves earn their place. The cmdline test keeps out an unrelated process that merely
  # inherited a recycled pid number, and the cwd test keeps out another worktree's demo. #113 gave
  # the port sweep in 'down' this test and left the pid-file loop and the app-port reclaim without
  # it, so a stale pid file could still kill whatever now holds that number and 'up' would still
  # kill whatever held the app port - including a live demo this checkout never started.
  local pid="$1" cwd
  [ -n "$pid" ] || return 1
  case "$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" in
    *uvicorn*|*vite*) ;;
    *) return 1 ;;
  esac
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null) || return 1
  case "$cwd/" in "$HERE"/*) return 0 ;; *) return 1 ;; esac
}

whose() {
  # Where a pid is running from, for a message that says why we left it alone.
  readlink -f "/proc/$1/cwd" 2>/dev/null || echo "a process we cannot read"
}

# The address the running stack was started on, read without pulling in its ports: 'up' wants
# fresh ones, and only 'check' and 'down' want the recorded ones.
RECORDED_IP=$(sed -n 's/^LAN_IP=//p' "$STATE" 2>/dev/null | head -1)

save_state() {
  # What is running, so the next 'check' or 'down' does not have to guess.
  {
    echo "LAN_IP=$IP"
    echo "PORT_APP=$PORT_APP"
    echo "PORT_A=$PORT_A"
    echo "PORT_B=$PORT_B"
    echo "PORT_C=$PORT_C"
    echo "CHECKOUT=$HERE"
    echo "STARTED=$(date -Is)"
  } > "$STATE"
}

lan_ip() {
  # The address other devices on this network can actually reach, not 127.0.0.1.
  ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1 \
    || hostname -I 2>/dev/null | awk '{print $1}'
}

# Load code/.env if there is one, so an API key reaches the hubs. Without this the header says
# "Offline mode" for ever: the backend is up and reachable, it just has no model to call, which
# looks identical to being disconnected if you only read the badge.
if [ -f code/.env ]; then
  set -a; . ./code/.env; set +a
  echo "Loaded code/.env"
fi

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

# The app's port is FIXED. It is the address people are given and put in a chat, so it must
# survive a restart. The hubs may move — the frontend is rebuilt against them each time — but
# the entry point never does.
#
# 'check' and 'down' read the ports off .lan/state instead of looking for free ones. Guessing was
# wrong in a way that looked right: free_port skips past the hubs that are already listening and
# reports the next free number, so 'check' probed ports nothing was on and printed three crosses
# for a perfectly healthy stack, and 'down' swept a range the stack was not even in. An explicit
# PORT_* in the environment still wins over both.
if [ "$CMD" != up ] && [ -f "$STATE" ]; then
  # shellcheck source=/dev/null
  . "$STATE"
fi
PORT_APP="${PORT_APP:-8440}"
PORT_A="${PORT_A:-$(free_port 8420)}"
PORT_B="${PORT_B:-$(free_port $((PORT_A + 1)))}"
PORT_C="${PORT_C:-$(free_port $((PORT_B + 1)))}"

hub_blurb() {
  case "$1" in
    basel)  echo "Stays and places to eat in Basel." ;;
    zurich) echo "Developers, designers and freelance work around Zürich." ;;
    bern)   echo "Local services in Bern: hands, tools and a room above the river." ;;
    *)      echo "Signed cards for this hub's members." ;;
  esac
}

start_hub() {
  local id="$1" port="$2" peer="$3"
  HIVE_HUB_ID="$id" \
  HIVE_NAME="Adobee Hive ($id)" \
  HIVE_PEER_URLS="$peer" \
  ADMISSION_POLICY="${ADMISSION_POLICY:-open}" \
  SEED_ON_EMPTY="$([ "$id" = basel ] && echo true || echo false)" \
  HIVE_DESCRIPTION="$(hub_blurb "$id")" \
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

case "$CMD" in
  up)
    echo "This machine: $IP"
    # Reclaim the fixed entry point. A stale preview from a previous run holds it open, and
    # quietly starting somewhere else would invalidate the URL everyone was given.
    if (exec 3<>"/dev/tcp/127.0.0.1/$PORT_APP") 2>/dev/null; then
      exec 3<&- 2>/dev/null
      STALE=$(pid_on "$PORT_APP")
      if [ -n "$STALE" ] && ours "$STALE"; then
        kill "$STALE" 2>/dev/null && echo "  reclaimed port $PORT_APP from our own pid $STALE"
        sleep 2
      elif [ -n "$STALE" ]; then
        # This used to kill whatever held the port, with no check at all. On a machine with
        # several worktrees of this repo - one of them serving the demo - that is how 'up' in a
        # branch checkout takes down the live stack. Refuse, and say what to do instead.
        echo "  Port $PORT_APP is held by pid $STALE, running in $(whose "$STALE")."
        echo "  That is not this checkout, so I will not kill it. Pin a free port instead:"
        echo "      PORT_APP=8460 PORT_A=8461 PORT_B=8462 PORT_C=8463 ./lan.sh up"
        exit 1
      fi
    fi
    if (exec 3<>"/dev/tcp/127.0.0.1/$PORT_APP") 2>/dev/null; then
      exec 3<&- 2>/dev/null
      echo "  Port $PORT_APP is held by something I cannot stop. The entry point is fixed there"
      echo "  on purpose, so free it and run again rather than letting the URL move."
      exit 1
    fi
    # The hub ports have to be free before anything else happens. 'up' never checked them: with
    # the ports pinned, the new hubs failed to bind and the *old* ones kept answering, still
    # holding the peer URLs they were started with. Nothing in the output said so, which is the
    # same class of failure as the address move below - it looks fine and is broken.
    for p in "$PORT_A" "$PORT_B" "$PORT_C"; do
      held=$(pid_on "$p")
      [ -z "$held" ] && continue
      if ours "$held"; then
        echo "  Port $p is already held by our own pid $held, so this checkout has a stack up."
        echo "  Stop it first, or the new hubs cannot bind and the old ones keep answering with"
        echo "  the peer URLs they were started with:"
        echo "      ./lan.sh down"
      else
        echo "  Port $p is held by pid $held, running in $(whose "$held")."
        echo "  That is not this checkout, so I will not touch it. Pin a free range instead:"
        echo "      PORT_APP=8460 PORT_A=8461 PORT_B=8462 PORT_C=8463 ./lan.sh up"
      fi
      exit 1
    done

    # A change of network is the one failure that breaks everything while looking like nothing.
    # The hubs bind 0.0.0.0, so they keep answering on the new address and every health check
    # still passes - but the peer URLs were baked with the old one, and peers are seeded from the
    # environment only while the table is empty (app/peers.py:69), and the stores under .lan
    # survive a stop. So 'down' and 'up' alone would leave all six peer rows pointing at an
    # address nothing is on, and federated search quietly local-only.
    if [ -n "$RECORDED_IP" ] && [ "$RECORDED_IP" != "$IP" ]; then
      echo
      echo "  This machine's address moved: $RECORDED_IP -> $IP"
      echo "  Every link anyone was given names the old one and is dead. Clearing the hub stores"
      echo "  so the peers are seeded against $IP; the vaults are seeded again below."
      rm -f "$RUN"/*.duckdb "$RUN"/*.duckdb.wal
    fi
    echo
    echo "Starting hubs..."
    start_hub basel  "$PORT_A" "http://$IP:$PORT_B,http://$IP:$PORT_C"
    start_hub zurich "$PORT_B" "http://$IP:$PORT_A,http://$IP:$PORT_C"
    start_hub bern   "$PORT_C" "http://$IP:$PORT_A,http://$IP:$PORT_B"

    for p in "$PORT_A" "$PORT_B" "$PORT_C"; do
      wait_for "http://127.0.0.1:$p" || { echo "  hub on $p did not come up; see $RUN/*.log"; exit 1; }
    done

    echo
    echo "Seeding the fake vaults through the real signup endpoint..."
    "$BACKEND/.venv/bin/python" "$BACKEND/tools/seed_vaults.py" \
        --hub "http://127.0.0.1:$PORT_A" --hub-id basel  --keys "$RUN/keys"
    "$BACKEND/.venv/bin/python" "$BACKEND/tools/seed_vaults.py" \
        --hub "http://127.0.0.1:$PORT_B" --hub-id zurich --keys "$RUN/keys"
    "$BACKEND/.venv/bin/python" "$BACKEND/tools/seed_vaults.py" \
        --hub "http://127.0.0.1:$PORT_C" --hub-id bern   --keys "$RUN/keys"

    echo
    echo "Building the app same-origin, proxying /api to 127.0.0.1:$PORT_A ..."
    APPLOG="$PWD/$RUN/app.log"
    APPPID="$PWD/$RUN/app.pid"
    ( cd code/frontend \
      && VITE_API_URL="" VITE_PREVIEW_BACKEND="http://127.0.0.1:$PORT_A" npm run build >/dev/null 2>&1 \
      && VITE_PREVIEW_BACKEND="http://127.0.0.1:$PORT_A" nohup npx --yes vite preview --host 0.0.0.0 --port "$PORT_APP" --strictPort \
           > "$APPLOG" 2>&1 &
      echo $! > "$APPPID" )
    sleep 3
    save_state

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
    echo "  zurich hub      http://$IP:$PORT_B   developers and freelance work"
    echo "  bern hub        http://$IP:$PORT_C   local services"
    echo "  logs            $RUN/*.log"
    echo
    echo "  Tell someone on another device to run:  ./lan.sh check  (or just open the URL)"
    ;;

  check)
    if [ ! -f "$STATE" ]; then
      echo "Nothing recorded in $STATE, so these are guesses, not the running stack."
      echo "Run ./lan.sh up here first, or pass the ports: PORT_A=... PORT_APP=... ./lan.sh check"
      echo
    elif [ -n "$RECORDED_IP" ] && [ "$RECORDED_IP" != "$IP" ]; then
      echo "!! The address moved since this stack started: $RECORDED_IP -> $IP"
      echo
      echo "   Every check below will still pass, and that is exactly the trap: the hubs bind"
      echo "   0.0.0.0, so they answer on $IP too. What is broken is invisible from here - the"
      echo "   links people were given name $RECORDED_IP, and so do the peer URLs the hubs hold,"
      echo "   so federated search has quietly gone local-only."
      echo
      echo "   Restart, which re-points the peers and prints the new URLs:"
      echo "       ./lan.sh down && ADMIN_TOKEN=... ./lan.sh up"
      echo
    fi
    echo "From ANOTHER device on this network, these should all answer:"
    echo "  curl http://$IP:$PORT_A/api/health"
    echo "  curl http://$IP:$PORT_B/api/health"
    echo "  open http://$IP:$PORT_APP"
    echo
    echo "From here:"
    for p in "$PORT_A" "$PORT_B" "$PORT_C"; do
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
      pid=$(cat "$f" 2>/dev/null)
      name=$(basename "$f" .pid)
      if [ -n "$pid" ] && ours "$pid"; then
        kill "$pid" 2>/dev/null && echo "stopped $name"
      elif [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
        # A pid file outlives its process, and the kernel reuses pid numbers. Killing a number
        # read off a stale file is how 'down' reaches something that was never ours.
        echo "left pid $pid alone ($name is stale; that pid now runs in $(whose "$pid"))"
      fi
      rm -f "$f"
    done
    # Earlier runs of THIS checkout leave listeners behind whose pid files are long gone. Reap
    # those, so a restart is not a slow leak of dead servers.
    #
    # Scoped to this checkout deliberately. Several worktrees of this repo run at once - one
    # serving a demo, others held by people or agents working on branches - and they share the
    # 8420-8445 range. A sweep that killed every uvicorn in the range would stop a demo this
    # checkout never started, which is what used to happen: 'down' in one worktree took down the
    # hubs another had running. A process is ours only if its working directory is inside HERE.
    # The default range is where an unpinned stack lands. The recorded ports are swept too, so a
    # stack pinned outside it - the 85xx the docs suggest when another one is already up - is
    # reaped as well, which the hardcoded range alone did not do.
    for port in $(seq "${SWEEP_FROM:-8420}" "${SWEEP_TO:-8445}") "$PORT_APP" "$PORT_A" "$PORT_B" "$PORT_C"; do
      pid=$(pid_on "$port")
      [ -z "$pid" ] && continue
      if ours "$pid"; then
        kill "$pid" 2>/dev/null && echo "released port $port (stale, pid $pid)"
      else
        echo "left port $port alone (pid $pid belongs to $(whose "$pid"))"
      fi
    done
    rm -f "$STATE"
    ;;

  *) echo "usage: ./lan.sh [up|down|check]"; exit 1 ;;
esac
