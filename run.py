#!/usr/bin/env python3
"""
LEIA — Lebanon Emergency Intelligence Agent
Single entry point.

Usage:
    python run.py            → launches the web dashboard (http://127.0.0.1:7860)
    python run.py api        → launches the FastAPI backend (http://127.0.0.1:8000)
    python run.py test       → runs the offline test suite (no API key required)
    python run.py test-live  → runs the test suite using the real Claude API

Before running, set your API key:
    export ANTHROPIC_API_KEY=sk-ant-...
(or copy .env.example to .env and fill it in, then `export $(cat .env | xargs)`)
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def check_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠️  ANTHROPIC_API_KEY is not set.")
        print("   export ANTHROPIC_API_KEY=sk-ant-your-key-here\n")
        sys.exit(1)


def run_ui():
    check_api_key()
    from ui.app import demo
    print("\n🇱🇧 LEIA dashboard starting at http://127.0.0.1:7860\n")
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


def run_api():
    check_api_key()
    import uvicorn
    print("\n🇱🇧 LEIA API starting at http://127.0.0.1:8000  (docs at /docs)\n")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)


def run_tests(live=False):
    if live:
        check_api_key()
    import subprocess
    args = [sys.executable, os.path.join(ROOT, "test_system.py")]
    if live:
        args.append("--live")
    sys.exit(subprocess.call(args))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ui"

    if mode == "ui":
        run_ui()
    elif mode == "api":
        run_api()
    elif mode == "test":
        run_tests(live=False)
    elif mode == "test-live":
        run_tests(live=True)
    else:
        print(__doc__)
        sys.exit(1)
