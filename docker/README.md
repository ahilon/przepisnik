# Instance container and GitHub Actions

The default `docker/Dockerfile` target is `app`: an instance image without sample
recipes. The explicit `demo` target adds the versioned sample collection. Both use
the same installed application/runtime layer and non-root user (UID/GID 10001).

The Docker workflow checks demo and instance images on matching pull requests.
The separate [release workflow](RELEASE.md) validates both AMD64/ARM64 and publishes
tested production images to GHCR after merge to main. Full Playwright regression
runs against each release image; PRs run a short server-backed sanity suite.
Personal data remains outside every distributable image.

## Configure an instance

Create the ignored `przepisnik.toml` in the repository root once, preserving any
existing instance configuration instead of overwriting it:

```powershell
if (-not (Test-Path przepisnik.toml)) {
    Copy-Item docker/server.toml przepisnik.toml
}
```

```sh
test -e przepisnik.toml || cp docker/server.toml przepisnik.toml
```

For container use, set `host` to `0.0.0.0` and keep the internal port at 8000.
`origins` lists exact browser-facing URLs, including the published port. The
provided configuration accepts localhost on port 8000. The healthcheck reads the
same configuration and supplies an allowed Host header while connecting directly
to the internal listener; the browser hostname need not resolve in the container.

```sh
docker compose -f docker/docker-compose.instance.yaml up --build --detach --wait
```

Open `http://localhost:8000`. The host port is bound to loopback by default. For
LAN access, configure the browser origin in `przepisnik.toml` and set
`PRZEPISNIK_BIND_ADDRESS` to the intended host interface. `PRZEPISNIK_PORT` changes
the host port only; update origins to match. Host/origin checks are not user
authentication; keep access within the intended network.

`PRZEPISNIK_CONFIG_FILE` optionally supplies another host TOML path. Compose mounts
it read-only at `/config/server.toml` and refuses to create a directory when the
source file is missing. Relative source paths resolve from the Compose file's
directory; an absolute path avoids ambiguity.

## Data lifecycle

- The `instance-data` named volume stores SQLite, images, shopping state and
  migration backups at `/data`. A fresh volume starts empty with a placeholder
  image and receives no demo recipes.
- Existing SQLite data is reused. Application schema upgrades retain their
  transactional behavior and `.before-vN.bak` backups. Maintain a separate backup
  of the entire instance before upgrades.
- Legacy JSON without a database is not imported automatically. Back it up,
  review a dry run and explicitly migrate:

```sh
docker compose -f docker/docker-compose.instance.yaml run --rm app migrate-json --dry-run
docker compose -f docker/docker-compose.instance.yaml run --rm app migrate-json
```

Other explicit CLI commands work in the same form, such as `run --rm app check-data`.
The no-argument entrypoint starts the server.

Fresh named volumes inherit the image data directory's ownership. To use existing
host data, provide a Compose override mounting that directory at `/data`, prepare
access for UID/GID 10001 and retain the configuration mount. Startup does not run
as root or recursively change ownership of existing host data.

```sh
# Preserve instance data when stopping.
docker compose -f docker/docker-compose.instance.yaml down

# Replace the container using the same image and data.
docker compose -f docker/docker-compose.instance.yaml up --force-recreate --no-build --detach --wait
```

Do not use `down --volumes` for an instance whose data you want to retain. That
flag is reserved for the isolated CI project and disposable demo reset. Never
point Actions jobs at a real instance or its backups.

## GitHub Actions

`Docker build` retains the demo smoke check. The new `Instance container` job:

1. Builds the instance target and waits for health with a custom host configuration.
2. Checks non-root execution, absence of bundled demo recipes and an empty API.
   It also rejects missing configuration, read-only data and implicit legacy imports.
3. Saves a recipe through the API and copies a PNG into the disposable volume.
4. Recreates without rebuilding, confirms the container ID changed, checks the
   persisted recipe/PNG and runs `check-data` against the retained database.
5. Removes only the runner's explicitly named CI project and volume after the job.

This job does not repeat browser E2E. The post-merge release jobs run the full
browser suite against the exact AMD64 and ARM64 images before publication.

Without `--container-image`, `tests/e2e` starts its own Python server; see
[tests/README.md](../tests/README.md) for backend selection. The separate
[release pipeline](RELEASE.md) handles architecture coverage and GHCR promotion.
The PR Docker workflow is
path-filtered (including tests), so its jobs
remain optional PR checks; unfiltered quality/security checks remain merge gates.

See [demo/README.md](demo/README.md) for the separate demo commands and sample data.
