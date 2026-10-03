# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability** (<https://github.com/decano5107-boop/second-brain/security/advisories/new>). It creates a private thread visible only to the maintainer.

This is maintained by one person, so treat these as targets rather than guarantees: an
acknowledgement within 7 days, and a status update within 30.

Disclosure is coordinated: once a fix is released, the advisory is published with credit to the
reporter, unless they prefer to stay anonymous.

## Scope

This project runs locally as developer tooling. The most relevant risks are:

- Text from an indexed document, or from a note, reaching the agent's context in a way that
  reads as instructions (by default `lookup` never searches document stubs)
- Any write outside the vault, through a crafted project name, session id, domain name, file
  name or symlink
- Any overwrite or deletion of a file that does not carry `generated: second-brain`
- A hook that blocks a prompt or a session instead of failing open

## Supported versions

The latest released minor version receives fixes. Older versions do not.
