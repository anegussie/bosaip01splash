#!/usr/bin/env bash
# Run one single-variable option-20 serving experiment end to end.
#
# The script stops the running option-20 server, relaunches it with the given
# launcher overrides, runs the pinned serving matrix against the new instance,
# records /status before and after, and appends one row to the experiment index
# so runs compare side by side.
#
# The running server answers this Mac's Splash agent, so stopping it interrupts
# any agent session that talks to it. That is why the script requires --yes.
#
#   ./option20_quota_experiment.sh --label quota-24g \
#       --set SPLASH_FLASH_NEXT_MAX_CACHE_DISK=24G --trials 2 --yes
#   ./option20_quota_experiment.sh --label ple-192m \
#       --set SPLASH_FLASH_NEXT_PLE_MEMORY=192M --trials 2 --yes
#   ./option20_quota_experiment.sh --label speculation-nominal \
#       --group coding --gate nominal --trials 2 --yes
#   ./option20_quota_experiment.sh --label chunk-1024 \
#       --set SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=1024 --group prefill \
#       --matrix-args "--sizes 256,1024,4096,8192" --trials 1 --yes
#   ./option20_quota_experiment.sh --label ladder-stock --group ladder \
#       --matrix-args "--turns 5 --turn-step 900" --trials 1 --yes
#   ./option20_quota_experiment.sh --compare
#
# --note "..." stores one line of context in the index notes column.
#
# Run one variant at a time and wait for it to finish. Overlapping invocations
# race on the same server and port, and each one that loses leaves nothing behind.
#
# The stock 16 GiB profile derives its Metal cap (10.8G) and its 2,048-token
# prefill chunk from the whole stock profile, so any single-variable experiment
# has to pin the other two or it silently changes three variables at once:
#
#   ./option20_quota_experiment.sh --label quota-24g \
#       --set SPLASH_FLASH_NEXT_MAX_CACHE_DISK=24G \
#       --set SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G \
#       --set SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048 --trials 2 --yes
#
# A streamed store override (expert or PLE memory) holds the cap at 10G and the
# chunk at 1,024, and a 4G expert store with 2,048-token chunks needs 10,940 MiB
# against a 10,240 MiB cap, so the engine will not start. Pin both explicitly:
#
#   ./option20_quota_experiment.sh --label expert-4g \
#       --set SPLASH_FLASH_NEXT_EXPERT_MEMORY=4G \
#       --set SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G \
#       --set SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048 --trials 2 --yes
#
# Rollback is the launcher default: run again with no --set for the stock
# profile, or relaunch from the menu.

set -euo pipefail

REPO=/Users/mymac/splash/splash
PYTHON="$REPO/.venv/bin/python"
MATRIX="$REPO/dev/benchmarks/option20_serving_matrix.py"
LAUNCHER="${LAUNCHER:-/Users/mymac/startllamacpp.sh}"
EXPERIMENTS="${EXPERIMENTS:-$REPO/dev/benchmarks/option20-experiments}"
BASE="${SPLASH_TEST_BASE:-http://127.0.0.1:1235}"

label=""
trials=2
group=full
gate=""
matrix_args_extra=""
note=""
confirmed=0
compare_only=0
declare -a sets=()

usage() {
  sed -n '2,47p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label) label="$2"; shift 2 ;;
    --note) note="$2"; shift 2 ;;
    --set) sets+=("$2"); shift 2 ;;
    --trials) trials="$2"; shift 2 ;;
    --group) group="$2"; shift 2 ;;
    --gate) gate="$2"; shift 2 ;;
    --matrix-args) matrix_args_extra="$2"; shift 2 ;;
    --launcher) LAUNCHER="$2"; shift 2 ;;
    --compare) compare_only=1; shift ;;
    --yes) confirmed=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$EXPERIMENTS"
if (( compare_only )); then
  "$PYTHON" "$MATRIX" --compare --out "$EXPERIMENTS"
  exit 0
fi

[[ -n "$label" ]] || { echo "An experiment needs --label." >&2; exit 2; }
(( confirmed )) || {
  echo "This stops the option-20 server, which also answers the Splash agent." >&2
  echo "Re-run with --yes once that is acceptable." >&2
  exit 2
}

status_url="${BASE}/status"

# Two experiments at once would stop and relaunch the same server on the same
# port, so the second one fails halfway through. Take a directory lock.
lock_dir="$EXPERIMENTS/.experiment.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another option-20 experiment is running (lock: $lock_dir)." >&2
  echo "Wait for it to finish, or remove the lock if it died: rmdir '$lock_dir'" >&2
  exit 1
fi
run_dir=""
cleanup() {
  local status=$?
  if [[ -n "$run_dir" && ! -f "$run_dir/matrix.stdout" ]]; then
    # Nothing was measured. Keep the logs that explain why and mark the run
    # failed; drop a directory that only ever held the status probe.
    if [[ -s "$run_dir/launch.log" || -s "$run_dir/stop.log" ]]; then
      mv "$run_dir" "${run_dir}-FAILED"
      echo "   run produced no measurement; logs kept in ${run_dir}-FAILED" >&2
    else
      rm -rf "$run_dir"
    fi
  fi
  rmdir "$lock_dir" 2>/dev/null || true
  return $status
}
trap cleanup EXIT

# Read the instance being replaced before any directory is created, so a failed
# run leaves no empty experiment directories behind.
probe="$(mktemp)"
if ! curl -fsS --max-time 10 "$status_url" > "$probe" ||
   ! "$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("ready") and "Flash-Next" in d.get("instance",{}).get("model","") else 1)' "$probe"; then
  echo "Could not read a live option-20 server at $status_url." >&2
  echo "Start it with: bash $LAUNCHER --direct 20, then re-run this experiment." >&2
  rm -f "$probe"
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="$EXPERIMENTS/${stamp}-${label}"
mkdir -p "$run_dir"
mv "$probe" "$run_dir/status-before.json"
log="$run_dir/launch.log"

echo "== Experiment '$label' -> $run_dir"
if (( ${#sets[@]} )); then
  for pair in "${sets[@]}"; do echo "   override $pair"; done
else
  echo "   no overrides: the stock profile"
fi

# 1. Record the instance being replaced (already probed above).
echo "   stopping the running option-20 server"
printf '9\n' | bash "$LAUNCHER" > "$run_dir/stop.log" 2>&1 || true
for _ in {1..30}; do
  if ! curl -fsS --max-time 2 "$status_url" > /dev/null 2>&1; then break; fi
  sleep 2
done

# 2. Relaunch with the overrides and wait for the model to answer.
echo "   relaunching (log: $log)"
if (( ${#sets[@]} )); then
  env "${sets[@]}" bash "$LAUNCHER" --direct 20 > "$log" 2>&1 &
else
  bash "$LAUNCHER" --direct 20 > "$log" 2>&1 &
fi
launch_pid=$!
echo "$launch_pid" > "$run_dir/launch.pid"
ready=0
for _ in {1..90}; do
  # /status has no top-level model_name; the served identity lives in instance.model.
  if curl -fsS --max-time 5 "$status_url" 2>/dev/null |
     "$PYTHON" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(1)
sys.exit(0 if d.get("ready") and "Flash-Next" in d.get("instance",{}).get("model","") else 1)' 2>/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$launch_pid" 2>/dev/null; then break; fi
  sleep 5
done
if (( ! ready )); then
  echo "The relaunched server never answered; see $log" >&2
  exit 1
fi
curl -fsS --max-time 10 "$status_url" > "$run_dir/launch-status.json"

# 3. Run the pinned matrix, then record the counters it moved.
matrix_args=(--base "$BASE" --trials "$trials" --group "$group"
             --state-label fresh --out "$run_dir")
[[ -n "$gate" ]] && matrix_args+=(--thermal-gate "$gate")
if [[ -n "$matrix_args_extra" ]]; then
  # shellcheck disable=SC2206
  matrix_args+=($matrix_args_extra)
fi
"$PYTHON" "$MATRIX" "${matrix_args[@]}" > "$run_dir/matrix.stdout"
curl -fsS --max-time 10 "$status_url" > "$run_dir/status-after.json" || true
# bash 3.2 refuses to expand an empty array under set -u, which is the stock run.
if (( ${#sets[@]} )); then
  printf '%s\n' "${sets[@]}" > "$run_dir/overrides.txt"
  override_note="$(printf '%s;' "${sets[@]}")"
else
  : > "$run_dir/overrides.txt"
  override_note=""
fi
echo "   $(cat "$run_dir/summary.txt")"

# 4. One index row per run so experiments compare against each other.
"$PYTHON" "$MATRIX" --record "$EXPERIMENTS" --run "$run_dir" --label "$label" \
  --overrides "$override_note" --note "$note" > "$run_dir/compare.txt"
cat "$run_dir/compare.txt"
