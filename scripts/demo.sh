#!/usr/bin/env bash
# FitLog end-to-end demo
# Usage: bash scripts/demo.sh
set -e

echo "=== FitLog Demo ==="
echo ""
echo "Checking API is reachable..."
curl -sf http://127.0.0.1:8000/ | python -m json.tool
echo ""
echo "Running demo script..."
uv run python -m app.demo
