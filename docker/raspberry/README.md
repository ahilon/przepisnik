# Raspberry Pi: Docker, verified OneDrive backups and scheduled updates

This deployment replaces the native `przepisnik.service`. It uses the existing
`data/` directory, not the unrelated `przepisnik-demo_demo-data` volume.
The public address stays `http://192.168.100.225:8000`. Caddy owns port 8000;
the application is accessible only inside the Compose network. Both run under
Docker. Do not expose this unauthenticated application to the internet.

## How the daily job works

The existing backup timer name is retained, scheduled at 03:00 Europe/Warsaw.
`Persistent=true` also runs a missed job after startup. There is no separate
update timer or fixed delay: a successful, remotely verified backup gates updates.

1. Acquire the original backup lock for the entire backup/update operation.
2. Display maintenance, stop the app, fingerprint `data/` and `przepisnik.toml`,
   and archive a consistent snapshot. Resume the same container, then upload
   and read back the archive on OneDrive. An unchanged snapshot still requires
   downloading and verifying the last archive. A missing/corrupt copy fails the job.
3. Require a clean working tree on `main`, fetch as the repository owner using
   that user's SSH key, and fast-forward only. Build the application while serving
   the old container. A build failure leaves the old application online.
4. Display maintenance and stop writes again. Recheck the snapshot; if edits were
   made during the build, create and remotely verify another backup. Keep the
   app stopped during this final verification so the backup matches deployment data.
5. Retain the old image as `przepisnik-local:previous`, start the new application,
   and wait up to 120 seconds for its healthcheck. Remove maintenance only on success.

Only the application container is replaced; Caddy keeps serving a Polish HTTP 503
page with `Retry-After`, no caching, and a 30-second refresh. Proxy errors also show
this page. An already open browser tab displays it on the next request/navigation.
The page also appears during the short consistent-backup pause, even with no update.
The final remote verification can extend downtime on slow connections.

Failures before starting the new image restart the previous container if needed.
Failures after attempting the new image keep maintenance enabled for manual recovery:
startup may have migrated SQLite, so blindly starting older code is unsafe.
There is no guarantee of cleanup after power loss or SIGKILL.

Keep 14 matching archives, including names from the previous backup script.
Other remote filenames are ignored. Only successful verification permits retention.
Archives contain `data/` and `przepisnik.toml`; deployment scripts, systemd units,
the root config, SSH credentials and rclone credentials are provisioned separately.
Archives are compressed but not additionally encrypted. Use an rclone crypt remote
if encryption is required. Keep recovery credentials outside the Pi.

## One-time migration from the native service

Run these commands on the Pi after the changes have been committed, pushed and
merged to `main`. Do not run them against a repository with unfinished local edits.
Replace the example username, path and IP in the config if necessary.
Prerequisites: Docker Engine/Compose v2 supporting `--wait`, rclone, Bash, Git,
util-linux (`flock` and `runuser`), GNU coreutils/tar/find, and an SSH key that
can read the repository without a password prompt.

### 1. Preserve and verify the existing backup

Stop future timer activations, then check that no backup is currently active:

```sh
sudo systemctl stop przepisnik-backup.timer
systemctl is-active przepisnik-backup.service
```

If active, wait for completion before continuing. Run the existing backup once
and check its log and OneDrive before changing the service:

```sh
sudo systemctl start przepisnik-backup.service
sudo journalctl -u przepisnik-backup.service -n 50 --no-pager
cd /home/ahilon/przepisnik
git status --short
git switch main
git pull --ff-only
```

An old "unchanged" message does not verify the remote archive. Confirm the latest
archive is readable on OneDrive; also create the local cold snapshot below.
Check that this checkout contains `docker/raspberry/compose.yaml`.

### 2. Install configuration and commands

```sh
sudo install -d -m 700 /var/lib/przepisnik-deploy
sudo install -d -m 755 /var/lib/przepisnik-deploy/maintenance
sudo install -m 600 docker/raspberry/deploy.conf.example /etc/przepisnik-deploy.conf
sudo nano /etc/przepisnik-deploy.conf
sudo install -m 755 scripts/przepisnik-compose.sh /usr/local/sbin/przepisnik-compose
sudo install -m 755 scripts/przepisnik-deploy.sh /usr/local/sbin/przepisnik-deploy
```

The example matches this instance (`ahilon`, `192.168.100.225:8000`). Keep
`przepisnik.toml` with `host = "0.0.0.0"`, `port = 8000`, and
`origins = ["http://192.168.100.225:8000"]`. Add any DNS names you actually use.
Do not commit personal config or credentials. The app uses the same numeric UID/GID
as `ahilon`, so no recursive ownership changes to recipe files are needed.

Verify unattended Git authentication as `ahilon`, not root, and prebuild images:

```sh
git ls-remote origin refs/heads/main
sudo przepisnik-compose config --quiet
sudo przepisnik-compose build app
sudo przepisnik-compose pull proxy
```

### 3. Transfer port 8000 to Docker

This step starts the planned short interruption. The existing demo is left alone;
its volume is never imported or deleted. Make a cold local snapshot first:

```sh
sudo systemctl disable --now przepisnik.service
sudo install -d -m 700 /var/backups/przepisnik
sudo sh -c 'umask 077; tar -czf "/var/backups/przepisnik/before-docker-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C /home/ahilon/przepisnik data przepisnik.toml -C /etc/systemd/system przepisnik.service'
sudo przepisnik-compose up -d --no-build --wait --wait-timeout 120
sudo przepisnik-compose ps
sudo przepisnik-compose logs --tail=80 app proxy
```

If the snapshot command fails, do not start Docker. Restore the native service
with `sudo systemctl enable --now przepisnik.service` and resolve the failure.
If Docker startup fails, stop it before restoring native service (see recovery).
Open the existing address and confirm the real recipe count, details, photo,
creation and editing. Confirm edits persist after restarting `app`.

### 4. Replace the old backup job and test before scheduling

Preserve the original job files for recovery, then install the replacement:

```sh
sudo cp -an /usr/local/sbin/przepisnik-backup /var/backups/przepisnik/
sudo cp -an /etc/systemd/system/przepisnik-backup.service /var/backups/przepisnik/
sudo cp -an /etc/systemd/system/przepisnik-backup.timer /var/backups/przepisnik/
sudo install -m 644 docker/raspberry/przepisnik-backup.service /etc/systemd/system/przepisnik-backup.service
sudo install -m 644 docker/raspberry/przepisnik-backup.timer /etc/systemd/system/przepisnik-backup.timer
sudo systemctl daemon-reload
sudo /usr/local/sbin/przepisnik-deploy --backup-only
```

Check the new archive in OneDrive and perform a restore rehearsal into a separate
directory, never over live data. Then test the full update and enable scheduling:

```sh
sudo systemctl start przepisnik-backup.service
sudo journalctl -u przepisnik-backup.service -n 100 --no-pager
sudo systemctl enable --now przepisnik-backup.timer
systemctl list-timers przepisnik-backup.timer
```

The first deployment rebuilds even if `main` has not changed, establishing its
deployment receipt. Later unchanged revisions only run the verified backup.
Do not enable the schedule until the manual job and restore rehearsal succeed.
Never invoke the old backup script after migration: it stops the wrong service.

## Manual operations and recovery

```sh
# Verified backup without fetching/building code:
sudo /usr/local/sbin/przepisnik-deploy --backup-only
# Full backup and update:
sudo systemctl start przepisnik-backup.service
# Logs:
sudo journalctl -u przepisnik-backup.service -n 100 --no-pager
sudo przepisnik-compose logs --tail=100 app proxy
```

Do not run these in parallel with manual Compose operations. All invocations of
the deployment script share the original backup lock. Keep the checkout clean:
untracked scratch files also block updates. Do not bypass this with a hard reset.
Fix authentication as `ahilon` if Git fails; root does not need its own Git key.

After a failed new-image startup, stop the timer and inspect logs. Keep maintenance
enabled until ready. To retry the current image after resolving the cause:

```sh
sudo systemctl stop przepisnik-backup.timer
sudo przepisnik-compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 app
# Only after successful startup and checking logs:
sudo rm -f /var/lib/przepisnik-deploy/maintenance/enabled
```

For a rollback, stop `app` first. Preserve failed-deployment data in a separate
archive. Download and verify the latest pre-deployment OneDrive snapshot, inspect
its paths with `tar -tzf`, and restore `data/` plus `przepisnik.toml` with their
original ownership. Do not overlay old SQLite files onto a directory with newer
WAL/SHM files: move the stopped data directory aside and restore into an empty
location. Never restore while either the native service or Docker app is running.
Then select the saved image and start it:

```sh
sudo docker tag przepisnik-local:previous przepisnik-local:current
sudo przepisnik-compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 app
# After successful validation:
sudo rm -f /var/lib/przepisnik-deploy/maintenance/enabled
sudo rm -f /var/lib/przepisnik-deploy/deployed-revision
```

Removing the deployment revision allows a subsequent job to retry the repository
revision. Re-enable the timer only when the deployment issue is resolved.
For an initial migration failure, use `sudo przepisnik-compose down` (no `-v`),
restore the cold snapshot if needed for schema compatibility, and run
`sudo systemctl enable --now przepisnik.service`. Leave scheduling stopped until
the old backup service/timer files have also been restored and daemon-reloaded.

Runtime scripts and systemd units are deliberately installed root-owned outside
Git. After changing them in a future release, review and reinstall the files;
automatic application updates do not replace them or restart Caddy. Proxy/config
changes require a reviewed `przepisnik-compose up -d --no-deps proxy` separately.

## Local verification

`bash tests/deploy/test-backup.sh` exercises archive creation, remote verification,
missing remote archives, final snapshot pausing, upload failure, and retention in
a temporary directory using mocked Compose/rclone calls. It does not contact
OneDrive, operate real containers or prove that credentials work. Run
`bash -n scripts/przepisnik-deploy.sh scripts/przepisnik-compose.sh` for syntax.
Actual Docker healthchecks, Caddy configuration and OneDrive access must also be
verified during the manual Pi migration before enabling the timer.
