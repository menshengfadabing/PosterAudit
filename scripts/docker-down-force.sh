#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.docker}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-check_2}"
NETWORK_NAME="${PROJECT_NAME}_default"

echo "[down] docker compose --env-file ${ENV_FILE} down --remove-orphans"
docker compose --env-file "${ENV_FILE}" down --remove-orphans || true

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[cleanup] network ${NETWORK_NAME} still exists, checking attached containers..."
  ids="$(docker network inspect "${NETWORK_NAME}" -f '{{range $id, $c := .Containers}}{{$id}} {{end}}' 2>/dev/null || true)"

  if [[ -n "${ids// }" ]]; then
    echo "[cleanup] removing attached containers: ${ids}"
    # shellcheck disable=SC2086
    docker rm -f ${ids} || true
  else
    echo "[cleanup] no attached containers found"
  fi

  echo "[cleanup] removing network ${NETWORK_NAME}"
  docker network rm "${NETWORK_NAME}" || true
fi

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "[result] network ${NETWORK_NAME} still exists (inspect manually)"
  exit 1
fi

echo "[result] compose stack and network cleaned"
