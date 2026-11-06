#!/bin/bash
# Install a root-owned copy as /usr/local/sbin/przepisnik-compose.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo "Run as root." >&2; exit 1; }
source /etc/przepisnik-deploy.conf
export APP_DIR DEPLOY_STATE PUBLIC_AUTHORITY PUBLIC_BIND
export APP_UID="$(id -u "$DEPLOY_USER")" APP_GID="$(id -g "$DEPLOY_USER")"
exec docker compose --project-name przepisnik -f "$APP_DIR/docker/raspberry/compose.yaml" "$@"
