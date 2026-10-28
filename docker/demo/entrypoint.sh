#!/bin/sh
set -eu

# Seed a fresh volume only. Restarts preserve manual changes to the demo collection.
if [ ! -f /demo-data/recipes.sqlite3 ]; then
    seed_dir=$(mktemp -d)
    cp -R /app/docker/demo/recipes "$seed_dir/recipes"
    cp /app/docker/demo/placeholder.png "$seed_dir/empty_dish.png"
    /app/.venv/bin/przepisnik --data-dir "$seed_dir" migrate-json
    /app/.venv/bin/przepisnik --data-dir "$seed_dir" check-data
    cp -R "$seed_dir/." /demo-data/
fi

exec /app/.venv/bin/przepisnik --data-dir /demo-data serve --config /app/docker/demo/server.toml
