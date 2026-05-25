"""
FitLog demo entry point — run as a Python module.

Usage:
    uv run python -m app.demo

Delegates to scripts/demo.py which contains the full walkthrough.
Requires the API running on http://127.0.0.1:8000.
"""
import os
import sys

# Add project root to path so `scripts.demo` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.demo import demo  # noqa: E402

if __name__ == "__main__":
    demo()
