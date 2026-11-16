# Tested images and Raspberry Pi deployment

The `Release images` Actions workflow validates pull requests and, after merge,
publishes the production `app` image from `main` to **ghcr.io/ahilon/przepisnik**.
It never embeds personal data or demo recipes. PR jobs cannot publish images.

## Release contract

1. Classify changed code, dependencies and release inputs. Documentation, skills,
   tool wrappers/docs and version-only changes in pyproject/uv.lock do not publish
   a new image. Missing Git evidence fails the run instead of silently skipping.
2. Require lint/formatting, strict types, Checkov, Gitleaks and unit tests with
   at least 80% coverage. Every selected test must pass: zero tests, skips,
   expected failures, unexpected passes and collection/setup/teardown failures
   cannot establish a successful release.
3. Build `linux/amd64` and `linux/arm64` separately. ARM64 uses QEMU on the hosted
   AMD64 runner. Both images must pass startup/data-persistence checks and the full
   container-backed browser suite.
4. Save those exact image IDs as short-lived compressed Actions artifacts.
   The publication job loads them and checks architecture, version, source revision
   and image labels. It never rebuilds an image after testing.
5. Publish architecture tags, a multi-platform `sha-<commit>` and `v<version>`,
   then move `stable` last. Existing commit/version tags cannot change to different
   platform images. Retrying the same tested images is safe; a different rebuild
   needs a new package version. Run-specific `candidate-<run>-<attempt>` tags retain
   the checked index and may be cleaned up later through package settings.

Publication is serialized. A candidate whose runtime code was superseded on main
is skipped; later documentation-only changes do not make a valid candidate stale.
A failed or skipped publication leaves the previous stable image available.
Manual dispatch on main intentionally validates and publishes its current version;
dispatch on a feature branch can validate but cannot publish.

## GitHub configuration

The workflow uses automatic `GITHUB_TOKEN` authentication. Only its publication
job requests `packages: write`; the other jobs have read-only repository access.
No extra GHCR password secret is needed. Actions must be allowed to run the Docker
and artifact actions referenced by the workflow. If account/organization policies
restrict package writes, an administrator must permit this workflow's publication.

The image has an OCI source label linking it to this repository. New packages
published by its workflow are linked automatically. For a pre-existing GHCR
package, check Package settings → Manage Actions access and grant this repository
write access. Repository visibility does not by itself make the package public.

After first publication, choose package visibility deliberately:

- **Private:** log in on Raspberry with a PAT **classic** carrying `read:packages`
  and an account allowed to read the package. Store the credential only on that
  machine, not in the repository or Compose file.
- **Public:** anonymous pulls work; the repository can remain private. Publishing
  an image exposes the packaged application code even when its source repo is private.

See [GitHub's GHCR documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Run on Raspberry Pi OS 64-bit

Install Docker Engine and its Compose plugin. Python/uv are not needed to run the
published image. Copy this deployment Compose file and the server configuration,
or use a checkout of the repository. The first successful main release must exist
before the pull commands below can work.

From the checkout root, create configuration without overwriting an existing file:

```sh
test -e przepisnik.toml || cp docker/server.toml przepisnik.toml
```

For private images, log in interactively before pulling:

```sh
read -rsp 'GHCR read token: ' PRZEPISNIK_REGISTRY_TOKEN; echo
printf '%s' "$PRZEPISNIK_REGISTRY_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_LOGIN --password-stdin
unset PRZEPISNIK_REGISTRY_TOKEN
```

Set the exact browser URL in `przepisnik.toml` origins. The internal listener must
remain `0.0.0.0:8000`. For LAN access, set `PRZEPISNIK_BIND_ADDRESS` to the Pi's
intended host interface; loopback is the default. Follow [instance setup](../SETUP.md):
there is no built-in login/TLS, so keep access within a trusted network.

```sh
docker compose -f docker/docker-compose.release.yaml pull
docker compose -f docker/docker-compose.release.yaml up --detach --wait --wait-timeout 180
```

Compose chooses the ARM64 image from the tested multi-platform index. Its
`przepisnik-instance` project and `instance-data` volume names match the local-build
instance Compose file, preserving the same data when switching deployment method.
Do not run both Compose files as separate instances against that volume at once.

The default named volume starts empty. For a generated Respo collection, follow
the [instance bind-mount instructions](README.md#data-lifecycle), mount the whole
collection at `/data` and prepare write access for UID/GID 10001. Keep the read-only
configuration mount. Never replace an existing instance's data without a backup.

## Updates and rollback

Back up the entire stopped instance data directory/volume before an upgrade, then
repeat `pull` and `up --detach --wait`. The named volume is preserved. Never use
`down --volumes` to update a real instance.

Set `PRZEPISNIK_IMAGE=ghcr.io/ahilon/przepisnik:v<version>` to pin a tested release,
or use a registry digest. Old images may reject a newer database schema; rollback
can require the matching data backup, not just an older image tag.

An automatic Pi updater/systemd timer is a separate deployment step. This workflow
publishes images and supplies manual pull/update commands; it does not SSH into a Pi.
