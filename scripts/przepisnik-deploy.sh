#!/bin/bash
# Root-owned installed copy; repository updates never replace this executable.
set -Eeuo pipefail
umask 077
[[ $EUID == 0 ]] || { echo "Run as root." >&2; exit 1; }
source /etc/przepisnik-deploy.conf
MODE=${1:---update}
[[ $MODE == --update || $MODE == --backup-only ]] || exit 2
export APP_DIR DEPLOY_STATE PUBLIC_AUTHORITY PUBLIC_BIND
export APP_UID="$(id -u "$DEPLOY_USER")" APP_GID="$(id -g "$DEPLOY_USER")"
COMPOSE=(docker compose --project-name przepisnik -f "$APP_DIR/docker/raspberry/compose.yaml")
RC=(/usr/bin/rclone --config "$RCLONE_CONFIG")
mkdir -p "$DEPLOY_STATE"
chmod 700 "$DEPLOY_STATE"
mkdir -p "$DEPLOY_STATE/maintenance"
chmod 755 "$DEPLOY_STATE/maintenance"
# Share the original backup lock, including during migration from the old timer.
mkdir -p /var/lib/przepisnik-backup
exec 9>/var/lib/przepisnik-backup/lock
flock -n 9 || { echo "Another backup/update is running."; exit 0; }
WORK=$(mktemp -d "$DEPLOY_STATE/work.XXXXXX")
PAUSED=0
NEW_START=0
cleanup() {
    local result=$?
    trap - EXIT
    if (( PAUSED && ! NEW_START )); then
        if "${COMPOSE[@]}" start --wait --wait-timeout 120 app; then
            rm -f -- "$DEPLOY_STATE/maintenance/enabled"
        else
            echo "Could not restart application; maintenance remains enabled." >&2
            result=1
        fi
    fi
    if (( NEW_START && result != 0 )); then
        echo "Deployment failed. Maintenance remains enabled; inspect logs before recovery." >&2
    fi
    rm -rf -- "$WORK"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$APP_DIR"
[[ -d data && -f data/recipes.sqlite3 && -f przepisnik.toml ]]
if systemctl is-active --quiet przepisnik.service; then
    echo "Stop and disable the old native service before using Docker deployment." >&2
    exit 1
fi
[[ ! -e "$DEPLOY_STATE/maintenance/enabled" ]] || {
    echo "Maintenance is already enabled; finish manual recovery first." >&2; exit 1;
}
CONTAINER=$("${COMPOSE[@]}" ps -q app)
[[ -n $CONTAINER && $(docker inspect -f '{{.State.Running}}' "$CONTAINER") == true ]]

git_as_user() {
    runuser -u "$DEPLOY_USER" -- env GIT_TERMINAL_PROMPT=0 \
        GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=15' git -C "$APP_DIR" "$@"
}
pause_app() {
    : > "$DEPLOY_STATE/maintenance/enabled"
    chmod 644 "$DEPLOY_STATE/maintenance/enabled"
    PAUSED=1
    "${COMPOSE[@]}" stop -t 30 app
}
resume_app() {
    "${COMPOSE[@]}" start --wait --wait-timeout 120 app
    PAUSED=0
    rm -f -- "$DEPLOY_STATE/maintenance/enabled"
}
fingerprint() {
    {
        find data -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum
        sha256sum przepisnik.toml
    } | sha256sum | cut -d ' ' -f1
}
prune_backups() {
    "${RC[@]}" lsf "$BACKUP_REMOTE" --files-only > "$WORK/remote-list"
    { grep -E '^przepisnik-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z(-[a-zA-Z0-9]+)?\.tar\.gz$' "$WORK/remote-list" || true; } |
        LC_ALL=C sort -r > "$WORK/retention"
    mapfile -t COPIES < "$WORK/retention"
    for ((i=14; i<${#COPIES[@]}; i++)); do
        "${RC[@]}" deletefile "$BACKUP_REMOTE/${COPIES[i]}"
    done
}
backup() {
    local keep_stopped=$1 current name digest previous_hash='' previous_name='' previous_digest=''
    pause_app
    current=$(fingerprint)
    if [[ -f "$DEPLOY_STATE/receipt" ]]; then
        { read -r previous_hash; read -r previous_name; read -r previous_digest; } < "$DEPLOY_STATE/receipt"
    fi
    if [[ $current == "$previous_hash" && -n $previous_name && -n $previous_digest ]]; then
        (( keep_stopped )) || resume_app
        # Even an unchanged collection needs a remotely readable recovery copy.
        digest=$("${RC[@]}" cat "$BACKUP_REMOTE/$previous_name" | sha256sum | cut -d ' ' -f1)
        [[ $digest == "$previous_digest" ]]
        echo "Unchanged collection; existing OneDrive archive verified: $previous_name"
        return
    fi
    name="przepisnik-$(date -u +%Y-%m-%dT%H-%M-%SZ)-$(date +%s%N)$RANDOM.tar.gz"
    # Never overwrite an earlier archive, even if two snapshots share a second.
    mkdir -p "$WORK/upload"
    tar -czf "$WORK/upload/$name" -C "$APP_DIR" data przepisnik.toml
    [[ $current == "$(fingerprint)" ]]
    digest=$(sha256sum "$WORK/upload/$name" | cut -d ' ' -f1)
    (( keep_stopped )) || resume_app
    "${RC[@]}" copyto "$WORK/upload/$name" "$BACKUP_REMOTE/$name" --immutable
    "${RC[@]}" check "$WORK/upload" "$BACKUP_REMOTE" --one-way --download
    printf '%s\n%s\n%s\n' "$current" "$name" "$digest" > "$DEPLOY_STATE/receipt.new"
    mv "$DEPLOY_STATE/receipt.new" "$DEPLOY_STATE/receipt"
    rm -f -- "$WORK/upload/$name"
    prune_backups
    echo "Backup verified: $name"
}

# A failed backup (including missing remote copies) prevents all updates.
backup 0
[[ $MODE == --update ]] || exit 0
[[ -z $(git_as_user status --porcelain --untracked-files=normal) ]] || {
    echo "Working tree is not clean; backup succeeded, update refused." >&2; exit 1;
}
[[ $(git_as_user branch --show-current) == "$DEPLOY_BRANCH" ]]
git_as_user fetch origin "$DEPLOY_BRANCH"
git_as_user merge --ff-only FETCH_HEAD
REVISION=$(git_as_user rev-parse HEAD)
[[ $REVISION == "$(git_as_user rev-parse FETCH_HEAD)" ]] || {
    echo "Local branch has commits outside the fetched remote branch; update refused." >&2
    exit 1
}
if [[ -f "$DEPLOY_STATE/deployed-revision" && $(cat "$DEPLOY_STATE/deployed-revision") == "$REVISION" ]]; then
    echo "Already deployed: $REVISION"
    exit 0
fi
"${COMPOSE[@]}" build app
OLD_IMAGE=$(docker inspect -f '{{.Image}}' "$CONTAINER")
docker tag "$OLD_IMAGE" przepisnik-local:previous
printf '%s\n' "$OLD_IMAGE" > "$DEPLOY_STATE/previous-image"
# Capture edits made during fetch/build. Keep writes stopped through remote verification.
backup 1
NEW_START=1
"${COMPOSE[@]}" up -d --no-deps --no-build --pull never --wait --wait-timeout 120 app
printf '%s\n' "$REVISION" > "$DEPLOY_STATE/deployed-revision.new"
mv "$DEPLOY_STATE/deployed-revision.new" "$DEPLOY_STATE/deployed-revision"
PAUSED=0
rm -f -- "$DEPLOY_STATE/maintenance/enabled"
echo "Deployed: $REVISION"
