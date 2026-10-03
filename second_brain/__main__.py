"""Command line: python3 -m second_brain <command>."""
import argparse
import json
import os
import sys

from . import __version__, board, config, librarian, lookup, maps

VAULT_DIRS = ("maps", "sessions", "stubs")


def cmd_init(cfg, args):
    for sub in VAULT_DIRS:
        os.makedirs(os.path.join(cfg["vault"], sub), exist_ok=True)
    print(f"vault ready at {cfg['vault']}")
    print(f"config: {cfg['_source'] or 'none found, using defaults'}")
    return 0


def cmd_board(cfg, args):
    if not os.path.isdir(cfg["vault"]):
        print(f"no vault at {cfg['vault']}; run `python3 -m second_brain init` first")
        return 1
    path = board.write(cfg)
    if not path:
        print(f"{os.path.join(cfg['vault'], 'maps', board.BOARD)} was not written by second-brain; left as is")
        return 1
    print(path)
    return 0


def cmd_maps(cfg, args):
    return 0 if maps.generate(cfg) or os.path.isdir(cfg["vault"]) else 1


def cmd_index(cfg, args):
    if args.file:
        paths = args.file
    else:
        folders = args.folders or cfg["librarian"]["sources"]
        if not folders:
            print("nothing to index: pass folders, or set librarian.sources in the config")
            return 1
        paths = librarian.walk(folders, cfg)
    if args.dry_run:
        for path in (args.file or []):
            print(librarian.render(os.path.abspath(path), cfg)[1])
        return 0
    if not os.path.isdir(cfg["vault"]):
        print(f"no vault at {cfg['vault']}; run `python3 -m second_brain init` first")
        return 1
    written = librarian.process(paths, cfg)
    print(f"{written} stub(s) written")
    return 0


def cmd_lookup(cfg, args):
    context = lookup.context_for(" ".join(args.prompt), cfg)
    print(context or "(silent: no note clears the bar)")
    return 0


def cmd_config(cfg, args):
    print(json.dumps(cfg, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m second_brain",
                                     description="A plain-Markdown memory for Claude Code.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="path to a config file (default: the usual lookup order)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the vault folders").set_defaults(func=cmd_init)
    sub.add_parser("board", help="rebuild maps/_BOARD.md from every status file").set_defaults(func=cmd_board)
    sub.add_parser("maps", help="rebuild the domain maps and the index").set_defaults(func=cmd_maps)
    p = sub.add_parser("index", help="write stubs for documents (default: librarian.sources)")
    p.add_argument("folders", nargs="*")
    p.add_argument("--file", nargs="+", help="index these files only")
    p.add_argument("--dry-run", action="store_true", help="with --file: print the stub, write nothing")
    p.set_defaults(func=cmd_index)
    p = sub.add_parser("lookup", help="show what the prompt hook would inject for a prompt")
    p.add_argument("prompt", nargs="+")
    p.set_defaults(func=cmd_lookup)
    sub.add_parser("config", help="print the merged config").set_defaults(func=cmd_config)
    args = parser.parse_args(argv)
    if args.command == "index" and args.dry_run and not args.file:
        parser.error("--dry-run needs --file")
    return args.func(config.load(path=args.config), args)


if __name__ == "__main__":
    sys.exit(main())
