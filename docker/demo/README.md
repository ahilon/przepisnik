# Docker demo environment

Install Docker Engine with Compose v2 (Docker Desktop with Linux containers on Windows).
Run these commands from the repository root:

```sh
docker compose -f docker/docker-compose.yaml up --build -d --wait
```

Open http://localhost:8001. This environment contains six sample recipes, seven
variants and one favorite. Each recipe has its own JSON and food image:

```text
docker/demo/recipes/<recipe-id>/
  recipe.json
  image.png
```

Recipe instructions and quantities were newly authored with AI assistance for this
demo. The six food images were generated from text prompts without using the old
photos as references. These are illustrative samples, not a validated meal plan;
nutrition is deliberately unset rather than copied from the previous fixtures.
The female/male labels demonstrate application variants, not dietary recommendations.
See [asset provenance and image prompts](ASSETS.md) for the generation record.

Recipe IDs remain stable because existing tests refer to them; the displayed titles,
ingredients and instructions describe the new samples. No personal collection or
source PDF is needed to generate or run this demo.

Startup copies the folders into a fresh demo volume and runs the existing
`migrate-json` command to populate SQLite. SQLite remains the application's active
store; fixture JSON files are not rewritten when editing in the UI.

The application runs as a non-root user. Only the local computer can access the
published port. A dedicated named volume stores SQLite and images; the host `data/`
directory and personal sources are excluded from the build context and never mounted.
Restarting or rebuilding preserves manual edits and any previously seeded recipes.
Rebuilding alone does not replace old sample text or photos in an existing volume.
Fixture changes apply to fresh volumes.
If upgrading from the previous single-JSON fixtures, use the reset commands below to
load the recipe folders and photos. This deletes manual edits in the demo volume.

```sh
# Inspect status and server output.
docker compose -f docker/docker-compose.yaml ps
docker compose -f docker/docker-compose.yaml logs app

# Stop containers while preserving demo data.
docker compose -f docker/docker-compose.yaml down

# Delete this environment's demo data, then load the six current sample recipes.
docker compose -f docker/docker-compose.yaml down --volumes
docker compose -f docker/docker-compose.yaml up --build -d --wait
```

The image's `HEALTHCHECK` reads the recipe API; Compose waits for readiness instead of sleeping
for a fixed interval. An occupied host port 8001 fails startup. Stop the conflicting
process; if changing the port, also update the browser origins in `server.toml`.

Compose explicitly builds the `demo` target. The default image contains no sample
recipes; see [the instance container guide](../README.md) for configuration and
persistent data. GitHub Actions checks demo readiness separately from instance
lifecycle checks and browser E2E against the instance image. Browser tests use their
own Python server by default unless `--container-image` is supplied.
