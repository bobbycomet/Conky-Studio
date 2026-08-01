# Security Policy

Conky Studio is maintained by **Bobby Comet** as a solo project.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Report privately on Discord (fastest response):

- **Discord:** https://discord.gg/kJZCZWg5nw  
  Use the bug report forum there or message me and mark it as a security report.

Include when you can: affected version or commit, OS/session (X11/Wayland), steps to reproduce, and impact.

There is **no bug bounty**. Good-faith reports are appreciated; fixes land on a best-effort basis for the current main branch.

## Trust model (important)

Conky Studio builds and launches real Conky themes. By design, it will run:

- Shell scripts from themes (`scripts/`, `start.sh`)
- Custom Lua and plugin Lua inside Conky (with the same access Conky already has, including process spawning)

Treat themes, plugins, and scripts like any other software you install. Only use sources you trust.

**In scope:** issues in Conky Studio itself (e.g., unsafe archive extraction, unexpected behaviour beyond the documented trust model).

**Out of scope:** malicious themes/plugins a user chose to load; bugs in Conky, Qt, or the OS; anything that requires already-compromised local access.
