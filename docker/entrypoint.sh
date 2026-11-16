#!/bin/sh
set -eu

data_dir=${PRZEPISNIK_DATA:-/data}
config_file=${PRZEPISNIK_CONFIG:-/app/docker/server.toml}

# Explicit CLI commands, including legacy migration, remain user-controlled.
if [ "$#" -gt 0 ]; then
    exec /app/.venv/bin/przepisnik --data-dir "$data_dir" "$@"
fi

if [ ! -d "$data_dir" ] || [ ! -w "$data_dir" ]; then
    echo "Data directory must exist and be writable by the container user: $data_dir" >&2
    exit 1
fi
if [ ! -f "$config_file" ] || [ ! -r "$config_file" ]; then
    echo "Server configuration must be a readable file: $config_file" >&2
    exit 1
fi

if [ ! -f "$data_dir/recipes.sqlite3" ]; then
    # Never silently import a legacy collection when starting an instance.
    legacy_recipe=
    if [ -d "$data_dir/recipes" ]; then
        legacy_recipe=$(find "$data_dir/recipes" -name recipe.json -type f -print -quit)
    fi
    if [ -n "$legacy_recipe" ] || [ -f "$data_dir/sources.json" ]; then
        echo "Legacy data found. Back it up and run migrate-json explicitly before serving." >&2
        exit 1
    fi
    # With no legacy sources, migration creates an empty, initialized SQLite store.
    /app/.venv/bin/przepisnik --data-dir "$data_dir" migrate-json
fi

if [ ! -e "$data_dir/empty_dish.png" ]; then
    cp /app/docker/placeholder.png "$data_dir/empty_dish.png"
fi

exec /app/.venv/bin/przepisnik --data-dir "$data_dir" serve --config "$config_file"
