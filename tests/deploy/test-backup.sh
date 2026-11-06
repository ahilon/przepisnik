#!/bin/bash
set -Eeuo pipefail
SOURCE=$(pwd)/scripts/przepisnik-deploy.sh
ROOT=$(mktemp -d)
trap 'rm -rf -- "$ROOT"' EXIT
export DEPLOY_STATE="$ROOT/state"
export WORK="$ROOT/work"
export BACKUP_REMOTE="$ROOT/remote"
export APP_DIR="$ROOT/app"
mkdir -p "$DEPLOY_STATE/maintenance" "$WORK" "$BACKUP_REMOTE" "$APP_DIR/data"
printf 'rice\n' > "$APP_DIR/data/recipes.sqlite3"
printf 'port = 8000\n' > "$APP_DIR/przepisnik.toml"
LOG="$ROOT/log"
PAUSED=0
compose() { printf '%s\n' "$*" >> "$LOG"; }
fake_rclone() {
    case $1 in
        cat) cat "$2" ;;
        copyto)
            [[ ${FAIL_UPLOAD:-0} == 0 ]] || return 1
            cp "$2" "$3" ;;
        check)
            for file in "$2"/*; do cmp "$file" "$3/$(basename "$file")" || return 1; done ;;
        lsf) find "$2" -maxdepth 1 -type f -printf '%f\n' ;;
        deletefile) rm -- "$2" ;;
        *) return 2 ;;
    esac
}
COMPOSE=(compose)
RC=(fake_rclone)
eval "$(sed -n '/^git_as_user()/,/^# A failed backup/p' "$SOURCE" | sed '$d')"
cd "$APP_DIR"
backup 0
[[ $PAUSED == 0 && ! -e "$DEPLOY_STATE/maintenance/enabled" ]]
[[ $(wc -l < "$DEPLOY_STATE/receipt") == 3 ]]
archive=$(sed -n '2p' "$DEPLOY_STATE/receipt")
tar -tzf "$BACKUP_REMOTE/$archive" | grep -qx data/recipes.sqlite3
[[ $(find "$BACKUP_REMOTE" -type f | wc -l) == 1 ]]
backup 0
[[ $(find "$BACKUP_REMOTE" -type f | wc -l) == 1 ]]
echo 'PASS: new verified snapshot and unchanged remote verification'
mv "$BACKUP_REMOTE/$archive" "$ROOT/saved.tar.gz"
set +e
( set -e; backup 0 )
status=$?
set -e
[[ $status != 0 && ! -e "$DEPLOY_STATE/maintenance/enabled" ]]
mv "$ROOT/saved.tar.gz" "$BACKUP_REMOTE/$archive"
echo 'PASS: missing remote copy fails after resuming application'
printf 'rice and beans\n' >> data/recipes.sqlite3
backup 1
[[ $PAUSED == 1 && -e "$DEPLOY_STATE/maintenance/enabled" ]]
[[ $(find "$BACKUP_REMOTE" -type f | wc -l) == 2 ]]
resume_app
echo 'PASS: final snapshot captures edits and keeps maintenance until resume'
receipt=$(cat "$DEPLOY_STATE/receipt")
printf 'new edit\n' >> data/recipes.sqlite3
set +e
( set -e; FAIL_UPLOAD=1; backup 0 )
status=$?
set -e
[[ $status != 0 && $(cat "$DEPLOY_STATE/receipt") == "$receipt" ]]
[[ ! -e "$DEPLOY_STATE/maintenance/enabled" ]]
echo 'PASS: upload failure preserves previous receipt and application availability'
for n in $(seq -w 1 16); do
    touch "$BACKUP_REMOTE/przepisnik-2025-01-${n}T03-00-00Z.tar.gz"
done
touch "$BACKUP_REMOTE/keep-me.txt"
prune_backups
[[ $(find "$BACKUP_REMOTE" -name '*.tar.gz' | wc -l) == 14 ]]
[[ -f "$BACKUP_REMOTE/keep-me.txt" ]]
echo 'PASS: retention keeps 14 matching archives and unrelated files'
