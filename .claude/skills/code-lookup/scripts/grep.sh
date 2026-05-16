#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
exec uv run --directory "$PROJECT_ROOT" python -m seer grep "$@"
