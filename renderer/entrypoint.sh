#!/bin/sh
set -eu
umask 077
mkdir -p "${HOME:-/scratch/home}" "${TMPDIR:-/scratch/tmp}" "${XDG_CACHE_HOME:-/scratch/cache}"
mkdir -p /scratch/cache/slidev /scratch/cache/vite /scratch/cache/vite-temp \
    /scratch/cache/slidev-cli-vite /scratch/cache/slidev-cli-vite-temp
exec uv run --no-project --python /usr/bin/python3.12 /usr/bin/python3.12 -m autopoc.cli_tools "$@"
