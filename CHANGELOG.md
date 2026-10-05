# Changelog

## 0.4.0 — 2026-10-06

- Continue a finished recording with `rec start <name-or-path> --continue`.
- Attach a child terminal launched from an active session with `rec attach`.
- Add `-terms` terminal headings and `-path` working-directory lines to exports.

## 0.3.0 — 2026-09-22

- Install `rec` directly from the Python, Arch, or Debian package. Shell integration
  loads automatically inside a recording; users do not need to edit `.zshrc`.
- Add notes, export pause/resume, redaction rules, session listing and inspection,
  raw replay, and task or command selection for exports.
- Record terminal output without logging hidden input. Redaction and pause affect
  reports; the original `session.raw` may still contain program output.
- Add local Arch and Debian package builders and MIT licensing.
