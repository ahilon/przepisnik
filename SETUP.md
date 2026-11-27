# Set up your own instance

## Install

Install Git, Python 3.12 or newer, and uv. Clone this repository, enter its folder,
and run `uv sync --locked`. On subsequent updates, use `git pull --ff-only`
and `uv sync --locked` while the server is stopped. Automatic Docker deployments
are planned separately and are not installed by these instructions. For a manually
managed container with persistent data, see [the container guide](docker/README.md).

## Prepare instance data

Each instance owns its data directory. To transfer an existing collection, stop its
server before copying the entire `data` directory, including SQLite and images.
Keep a separate backup. Do not copy a database while another process is writing it.
For a new, empty instance run `uv run przepisnik migrate-json`; this creates the
SQLite database and imports any legacy recipe JSON already present.
Run `uv run przepisnik check-data` to check the collection.

Use the global option `--data-dir /path/to/data` before the command, or set
`PRZEPISNIK_DATA`, to choose another directory. The CLI option wins over the
environment variable. Relative data paths are relative to the working directory.
Personal recipe data is ignored by Git.

## Configure and start

Copy `przepisnik.example.toml` to `przepisnik.toml`:

```powershell
# Windows PowerShell
Copy-Item przepisnik.example.toml przepisnik.toml
```

```sh
# Linux / macOS
cp przepisnik.example.toml przepisnik.toml
```

Edit the local copy and run:

```sh
uv run przepisnik serve
```

With the example settings, open http://localhost:8000. Stop with Ctrl+C.
`przepisnik.toml` is ignored by Git; the example is versioned. No personal
hostname or domain is required in application code.

The default configuration file is read from the working directory. A missing
default file uses localhost defaults. Use `serve --config /path/to/instance.toml`
for an explicit file; a missing explicit file fails. Unknown keys and invalid
ports/origins fail startup. CLI `--host`, `--port` and repeated `--origin` options
override file values; `--origin` replaces the entire origin list. Network settings
do not currently use environment variables. Changing the listener port does not
rewrite explicitly configured origins: set them to the actual browser URLs.

## AI nutrition estimates

To enable **Oszacuj wartości odżywcze z AI** while editing a recipe, set
`openai_api_key` to an OpenAI project key in the **server process environment**.
Existing `api_key` configurations continue to work for nutrition estimates.
Without a configured OpenAI key, the button stays visible and disabled.
The estimate covers all servings
of the selected variant. Save the recipe to keep the values and their AI label.

To supply the key for a single run, use the environment setup in
[Kucharz AI](#kucharz-ai-optional-trusted-home-instance).
The app sends ingredient names, quantities and the serving count to OpenAI when
someone clicks the button. Anyone who can use the editor on a configured instance
can request a billed estimate.

## Access from your home network

Example local configuration (replace both names and IP with your own):

```toml
host = "0.0.0.0"
port = 8000
origins = ["http://my-recipes.local:8000", "http://192.168.1.50:8000"]
```

`host` is the listener address; `0.0.0.0` listens on all IPv4 interfaces.
`origins` lists exact browser-facing URLs, without paths or trailing slashes.
Each entry includes its scheme, lowercase hostname, and port if nonstandard.
Only listed Host headers are accepted. Browser writes must also originate from
the same listed authority; arbitrary external origins remain forbidden.
Requests without an Origin header are accepted for CLI clients with a permitted
Host header. These checks are not user authentication.

Reserve the server IP in your router and allow the configured TCP port through
the host firewall for your trusted home network. Open the configured URL on a
phone or computer on that network. All devices with access can read and edit;
keep this instance in a trusted LAN and do not forward its port to the internet.

## Names and domains

The TOML file authorizes a name; it does not create DNS records. Configure name
resolution separately:

- On Raspberry Pi OS, set a hostname such as `my-recipes`. With working mDNS on
  the client and network, use `http://my-recipes.local:8000`.
- For local DNS, configure a router record such as `my-recipes.home.arpa` pointing
  at the reserved IP. Clients must use that DNS server. If your router lacks this
  feature, a local DNS resolver can provide it.
- A short name such as `http://my-recipes:8000` depends on client DNS search settings.
  Add its exact URL to `origins` if you use it.

To omit `:8000`, serve HTTP on port 80, typically through a reverse proxy. In that
case list the external URL, e.g. `http://my-recipes.local`, in `origins`. The proxy
must preserve the browser Host header; HTTPS origins must be listed with `https`.
Forwarded headers are not used to bypass validation. Docker packaging and proxy
configuration are separate deployment steps.

## Verify and back up

Check browsing, searching, creating/editing a recipe and uploading an image from
another device. Restart the server and confirm edits persist. A request with an
unlisted Host or browser Origin should return HTTP 403.

Before updates, stop the application and back up the entire data directory to
another device. Server startup can migrate SQLite and create a schema backup;
that backup does not replace your full data and image backup. Rolling back code
after a schema migration may also require restoring compatible data.

## Kucharz AI (optional, trusted home instance)

For a local OpenAI trial, run this from the project root in PowerShell or Bash:

```text
uv run --locked python scripts/chef_demo.py
```

Open `http://127.0.0.1:8000`. The launcher copies the bundled demo recipes
and photos to a temporary directory and initializes SQLite there. It removes
that directory, including edits made during the trial, when the server exits
normally or is stopped with Ctrl+C. Every launch starts with fresh demo data.

The launcher reuses `openai_api_key` from the environment or prompts for a key
without echo when the variable is empty or unset. A prompted key is available
only inside the launcher process. Use the lowercase name on Linux and in Docker.

For an existing instance, supply the OpenAI project key as `openai_api_key`
in the server process environment. The repository's instance and release
Compose files pass that variable to the app container. Restart the native
service or recreate the container after changing the key.

Select the round **AI** button in the lower-right corner to open Kucharz AI.
Ask for a dish and include any serving or ingredient preferences in your message,
or paste a recipe for cleanup. Use the same message box to answer follow-up
questions and revise the draft. The preview combines repeated ingredients with
compatible units and labels any estimated calories per serving. Use **Nowa rozmowa**
to start over.

Everyone who can reach a configured instance can use its shared budget.
Use authenticated access before exposing a paid instance outside a trusted network.
The chat footer shows the budget left and identifies OpenAI as the recipient.

OpenAI text requests use up to 2,200 output tokens with
[GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol).
The same key enables nutrition estimates and the illustration button. The
illustration button requests one low-quality 1024×1024 JPEG with
[GPT Image 1 mini](https://developers.openai.com/api/docs/models/gpt-image-1-mini).
OpenAI [scheduled this model for retirement on December 1, 2026](https://developers.openai.com/api/docs/deprecations).
If the model is unavailable, the text recipe can still be saved.
Requests do not retry automatically.

An unattended Raspberry Pi service needs a credential source available at
startup. The manual commands above supply a key only for that launch.
If keeping a long-lived OpenAI key off the Pi is required for unattended startup,
OpenAI supports short-lived tokens through workload identity federation with a
supported identity provider. The current application uses a project API key.
[OpenAI workload identity federation](https://developers.openai.com/api/docs/guides/workload-identity-federation)

The lifetime allowance is **USD 1 for the instance**, shared by all requests.
The server reserves an upper estimate in `chef.sqlite3` in the data volume before
each call. Text reserves the UTF-8 request size plus framing overhead at the
highest short-context input rate and the full output allowance. Images reserve
USD 0.02. The panel reports conservative accounting. A timeout or missing usage
keeps the reservation. Declined or incomplete output can still cost tokens.
Keep the ledger across container replacements, backups and restores. Restoring
an older ledger rolls back its accounting. The cap covers this instance at the
documented rates, excluding taxes, nutrition estimates and other API clients.
Review model pricing before enabling the feature and whenever provider prices
change.

Preview cards expire after 24 hours. The chat's **Dodaj do przepisów** button
opens the editor for review. Confirm the save there to add the recipe to the
collection. Images are held in the current browser until saving. OpenAI receives
your recipe request, any recent details needed to complete it, and the prior
draft when you revise a recipe. An illustration request sends the draft title.
