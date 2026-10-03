#!/usr/bin/env python3
"""SessionEnd hook: write the session note, then rebuild the board. Always exits 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from second_brain import board, capture, config
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    cfg = config.load()
    for step in (lambda: capture.run(event, cfg), lambda: board.write(cfg)):
        try:
            step()
        except Exception as exc:  # one failed step must not cost the other
            print(f"second-brain: {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
