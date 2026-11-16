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
