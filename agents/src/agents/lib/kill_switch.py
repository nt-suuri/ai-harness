"""Repo-wide kill-switch. Every agent workflow calls `exit_if_paused()` early."""

import os
import sys


def agents_paused() -> bool:
    return os.environ.get("PAUSE_AGENTS", "").strip().lower() == "true"


def exit_if_paused() -> None:
    if agents_paused():
        print("PAUSE_AGENTS=true — exiting", flush=True)
        sys.exit(0)
