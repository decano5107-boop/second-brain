#!/usr/bin/env python3
"""Build a complete demo vault for a fictional freelance designer, then show what it does.

    python3 examples/demo/run.py              # into a new temporary folder
    python3 examples/demo/run.py ~/sb-demo    # into a folder that does not exist yet

Nothing outside the target folder is read or written: the demo has its own projects, documents,
transcripts and config, and runs the real hooks against them.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True       # the demo leaves nothing behind in the repo, not even .pyc
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from second_brain import board, config, librarian, lookup, maps  # noqa: E402

TODAY = datetime.date.today()

# project folder -> (status, days since update, Now, Next step, domain declared in the file)
PROJECTS = {
    "trailhead-app": ("active", 0,
                      "onboarding flow shipped to the beta group; location prompt moved to 'start hike'",
                      "read the first week of beta feedback and decide on offline maps", ""),
    "harbor-bakery-rebrand": ("active", 3,
                              "direction B (hand-drawn wordmark) approved; packaging proofs at the printer",
                              "check the proofs against the colour swatches on Thursday", ""),
    "component-library": ("active", 64,
                          "button, input and card migrated to semantic tokens",
                          "migrate the remaining components and publish the docs site", ""),
    "interview-kit": ("parked", 20, "discussion guide and consent form templates done",
                      "resume when the next research project starts", ""),
    "tokens": ("done", 40, "token naming spec adopted by both client projects", "", "Design-System"),
}

DOMAINS = {
    "Client-Work": {
        "summary": "Paid projects: briefs, proposals, deliverables and invoices.",
        "projects": ["trailhead-app", "harbor-bakery-rebrand"],
        "folders": {"archive": ["Clients"]},
        "keywords": ["brief", "proposal", "invoice"],
        "neighbors": ["Design-System", "Research"],
    },
    "Design-System": {
        "summary": "Tokens, components and the documentation site.",
        "projects": ["component-library"],
        "folders": {"archive": ["Design System"]},
        "keywords": ["design token", "component"],
        "neighbors": ["Client-Work"],
    },
    "Research": {
        "summary": "User interviews, surveys and synthesis.",
        "projects": ["interview-kit"],
        "folders": {"archive": ["Research"]},
        "keywords": ["interview", "usability"],
        "neighbors": ["Client-Work"],
    },
    "Studio": {"summary": "Running the business: pricing, taxes, contracts. Maintained by hand.",
               "curated": True},
}

# (project folder, session id, user prompts, files edited)
SESSIONS = [
    ("trailhead-app", "a1b2c3d4",
     ["The beta testers say the location prompt feels pushy. Can we move it?",
      "Yes, ask when they tap start hike instead.", "Ship it to the beta group.", "wrap up"],
     ["src/onboarding/LocationPrompt.tsx", "src/onboarding/flow.ts", "STATUS.md"]),
    ("component-library", "e5f6a7b8",
     ["Migrate the card component to the semantic tokens.", "Check contrast on the dark theme too."],
     ["src/card/Card.tsx", "src/card/card.css"]),
]

PROMPTS = [
    "What did we decide about the Trailhead onboarding beta?",
    "Where is the work on the component library and its tokens?",
    "ok thanks",
]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def status_file(name, status, age, now, nxt, domain):
    front = [f"project: {name}", f"status: {status}",
             f"updated: {(TODAY - datetime.timedelta(days=age)).isoformat()}"]
    if domain:
        front.append(f"domain: {domain}")
    return "---\n" + "\n".join(front) + f"\n---\n\n# {name}\n\n**Now:** {now}\n**Next step:** {nxt}\n"


def transcript(prompts, files):
    lines = []
    for i, prompt in enumerate(prompts):
        lines.append({"type": "user", "message": {"role": "user", "content": prompt}})
        if i < len(files):
            lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": files[i]}}]}})
    return "\n".join(json.dumps(line) for line in lines) + "\n"


def build(target):
    code, docs, vault = (os.path.join(target, d) for d in ("code", "documents", "vault"))
    shutil.copytree(os.path.join(HERE, "documents"), docs)
    shutil.copytree(os.path.join(HERE, "inbox"), os.path.join(target, "inbox"))
    for name, (status, age, now, nxt, domain) in PROJECTS.items():
        write(os.path.join(code, name, "STATUS.md"), status_file(name, status, age, now, nxt, domain))

    raw = {"vault": vault, "projects_root": code,
           "roots": {"archive": docs, "inbox": os.path.join(target, "inbox")},
           "librarian": {"sources": [docs, os.path.join(target, "inbox")]},
           "domains": DOMAINS}
    config_path = os.path.join(target, "brain.config.json")
    write(config_path, json.dumps(raw, indent=2) + "\n")
    cfg = config.load(path=config_path)
    for sub in ("maps", "sessions", "stubs"):
        os.makedirs(os.path.join(vault, sub), exist_ok=True)

    print("1. librarian — one stub per document")
    librarian.process(librarian.walk(cfg["librarian"]["sources"], cfg), cfg)

    print("\n2. two sessions end — the real SessionEnd hook runs for each")
    hook = os.path.join(REPO, "hooks", "session_end.py")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": target, "SECOND_BRAIN_CONFIG": config_path}
    for project, sid, prompts, files in SESSIONS:
        cwd = os.path.join(code, project)
        tpath = os.path.join(target, "transcripts", f"{sid}.jsonl")
        write(tpath, transcript(prompts, [os.path.join(cwd, f) for f in files]))
        event = {"session_id": sid, "cwd": cwd, "transcript_path": tpath, "hook_event_name": "SessionEnd"}
        subprocess.run([sys.executable, "-B", hook], input=json.dumps(event), text=True, env=env, check=True)
        print(f"  + session note for {project}")

    print("\n3. maps — one per domain, plus the index")
    maps.generate(cfg)
    board.write(cfg)
    return cfg


def show(cfg):
    print("\n4. the board (maps/_BOARD.md)\n")
    with open(os.path.join(cfg["vault"], "maps", board.BOARD), encoding="utf-8") as f:
        for line in f:
            if line.startswith("|"):
                print("  " + line.rstrip())
    print("\n  component-library had a session today, but nobody updated its STATUS.md, so the")
    print("  board still calls it stale and its session note stays 'summary pending'. trailhead-app")
    print("  was wrapped up today, so its session note carries the Now / Next step lines.")
    print("\n5. what the prompt hook would inject (silent unless a note clears the bar)")
    for prompt in PROMPTS:
        print(f"\n  > {prompt}")
        context = lookup.context_for(prompt, cfg)
        for line in (context or "(silent)").splitlines():
            print("    " + line)


def main(argv):
    if len(argv) > 1:
        target = os.path.abspath(os.path.expanduser(argv[1]))
        if os.path.exists(target):
            sys.exit(f"{target} already exists; pass a folder that does not exist yet")
        os.makedirs(target)
    else:
        target = tempfile.mkdtemp(prefix="second-brain-demo-")
    cfg = build(target)
    show(cfg)
    print(f"\nDemo vault: {cfg['vault']}")
    print("Open it in Obsidian or a text editor; delete the folder when you are done.")
    return cfg


if __name__ == "__main__":
    main(sys.argv)
