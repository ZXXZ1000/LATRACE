#!/usr/bin/env bash

set -euo pipefail

uv run ruff check modules/memory
uv run pytest modules/memory/tests -q
