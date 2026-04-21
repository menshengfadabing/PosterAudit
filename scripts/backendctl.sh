#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
RUN_DIR="${ROOT_DIR}/run"
API_PID_FILE="${RUN_DIR}/api.pid"

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-18080}"
CELERY_WORKERS="${CELERY_WORKERS:-3}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-8}"
API_RELOAD="${API_RELOAD:-false}"

cd "${ROOT_DIR}"

mkdir -p "${LOG_DIR}" "${RUN_DIR}"

is_pid_alive() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  kill -0 "${pid}" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    cat "${pid_file}" 2>/dev/null || true
  fi
}

start_api() {
  local pid
  local api_args
  pid="$(read_pid "${API_PID_FILE}")"
  if is_pid_alive "${pid}"; then
    echo "[api] already running (pid=${pid})"
    return
  fi

  echo "[api] starting on ${API_HOST}:${API_PORT} ..."
  api_args=(--host "${API_HOST}" --port "${API_PORT}")
  if [[ "${API_RELOAD}" == "true" ]]; then
    api_args+=(--reload)
  fi
  nohup env USE_CELERY=true PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" uv run uvicorn web.main:app \
    "${api_args[@]}" \
    > "${LOG_DIR}/api.log" 2>&1 &
  echo $! > "${API_PID_FILE}"
  sleep 1

  pid="$(read_pid "${API_PID_FILE}")"
  if is_pid_alive "${pid}"; then
    echo "[api] started (pid=${pid}, log=${LOG_DIR}/api.log)"
  else
    echo "[api] failed to start, check ${LOG_DIR}/api.log"
    return 1
  fi
}

start_workers() {
  local i name pid_file pid
  for ((i=1; i<=CELERY_WORKERS; i++)); do
    name="audit${i}@%h"
    pid_file="${RUN_DIR}/celery_${i}.pid"
    pid="$(read_pid "${pid_file}")"

    if is_pid_alive "${pid}"; then
      echo "[celery-${i}] already running (pid=${pid})"
      continue
    fi

    echo "[celery-${i}] starting (queue=audit, concurrency=${CELERY_CONCURRENCY}) ..."
    nohup env USE_CELERY=true PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" uv run celery --workdir "${ROOT_DIR}" -A celery_app.celery worker \
      -Q audit -l info --concurrency="${CELERY_CONCURRENCY}" -n "${name}" \
      > "${LOG_DIR}/celery_${i}.log" 2>&1 &

    echo $! > "${pid_file}"
    sleep 1

    pid="$(read_pid "${pid_file}")"
    if is_pid_alive "${pid}"; then
      echo "[celery-${i}] started (pid=${pid}, log=${LOG_DIR}/celery_${i}.log)"
    else
      echo "[celery-${i}] failed to start, check ${LOG_DIR}/celery_${i}.log"
      return 1
    fi
  done
}

stop_one() {
  local pid_file="$1"
  local name="$2"
  local pid

  pid="$(read_pid "${pid_file}")"
  if ! is_pid_alive "${pid}"; then
    echo "[${name}] not running"
    rm -f "${pid_file}"
    return
  fi

  echo "[${name}] stopping pid=${pid} ..."
  kill "${pid}" >/dev/null 2>&1 || true

  for _ in {1..15}; do
    if ! is_pid_alive "${pid}"; then
      break
    fi
    sleep 0.2
  done

  if is_pid_alive "${pid}"; then
    echo "[${name}] force kill pid=${pid}"
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi

  rm -f "${pid_file}"
  echo "[${name}] stopped"
}

status_all() {
  local pid i pid_file

  pid="$(read_pid "${API_PID_FILE}")"
  if is_pid_alive "${pid}"; then
    echo "[api] running (pid=${pid})"
  else
    echo "[api] stopped"
  fi

  for ((i=1; i<=CELERY_WORKERS; i++)); do
    pid_file="${RUN_DIR}/celery_${i}.pid"
    pid="$(read_pid "${pid_file}")"
    if is_pid_alive "${pid}"; then
      echo "[celery-${i}] running (pid=${pid})"
    else
      echo "[celery-${i}] stopped"
    fi
  done
}

logs_hint() {
  echo "logs:"
  echo "  tail -f ${LOG_DIR}/api.log"
  echo "  tail -f ${LOG_DIR}/celery_1.log"
}

cmd="${1:-}" 
case "${cmd}" in
  up)
    start_api
    start_workers
    status_all
    logs_hint
    ;;
  down)
    for ((i=1; i<=CELERY_WORKERS; i++)); do
      stop_one "${RUN_DIR}/celery_${i}.pid" "celery-${i}"
    done
    stop_one "${API_PID_FILE}" "api"
    ;;
  restart)
    "${BASH_SOURCE[0]}" down
    "${BASH_SOURCE[0]}" up
    ;;
  status)
    status_all
    ;;
  logs)
    target="${2:-api}"
    case "${target}" in
      api)
        tail -f "${LOG_DIR}/api.log"
        ;;
      celery*|worker*)
        idx="${3:-1}"
        tail -f "${LOG_DIR}/celery_${idx}.log"
        ;;
      *)
        echo "usage: $0 logs [api|celery] [index]"
        exit 1
        ;;
    esac
    ;;
  *)
    cat <<USAGE
usage: $0 {up|down|restart|status|logs}

env override:
  API_HOST=0.0.0.0
  API_PORT=18080
  API_RELOAD=false
  CELERY_WORKERS=3
  CELERY_CONCURRENCY=8

examples:
  $0 up
  API_RELOAD=true $0 up
  CELERY_WORKERS=2 CELERY_CONCURRENCY=4 $0 up
  $0 status
  $0 logs api
  $0 logs celery 2
  $0 down
USAGE
    exit 1
    ;;
esac
