#!/usr/bin/env python3
"""UserPromptSubmit hook: print pointers to matching notes, or nothing. Always exits 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from second_brain import config, lookup
    event = json.loads(sys.stdin.read() or "{}")
    if not isinstance(event, dict):
        return
    context = lookup.context_for(event.get("prompt"), config.load(warn=lambda _msg: None))
    if context:
        print(lookup.hook_output(context))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
