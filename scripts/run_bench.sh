#!/bin/bash
set -a
source "$(dirname "$0")/../.env"
set +a
exec "$(dirname "$0")/../.venv/bin/python" "$(dirname "$0")/bench_cache.py" "$@"
