# termrec

A terminal recorder that exports clean Markdown/TXT reports. On Linux and macOS it
records an interactive Bash or zsh shell through Python's built-in pseudo-terminal.

termrec uses shell adapters to mark command boundaries, so shell themes such as Powerlevel10k,
prompts, colors and cursor redraws never need to be parsed from the report. Exported
terminal interaction has a stable format:

```text
$ command
> output line 1
> output line 2
```

`rec ...` control commands themselves are never included in exported console blocks.

## Install system packages

From this source directory on Arch Linux:

```bash
sh packaging/arch/build.sh
sudo pacman -U packaging/arch/termrec-0.4.0-1-any.pkg.tar.*
```

On Debian or Ubuntu, build a `.deb` from this directory and install the resulting file:

```bash
python3 packaging/debian/build_deb.py
sudo apt install ./packaging/debian/dist/termrec_0.4.0-1_all.deb
```

The package declares Python and Bash as dependencies; zsh is optional. No `script(1)`
dependency is needed.
Both system packages install `rec` and `termrec` under `/usr/bin`; `rec` works in a
new command prompt without `install-shell` or changes to `~/.zshrc`.

For a user-only installation instead, use pipx:

```bash
pipx install .
```

If you already have an older pipx installation, update or remove it to avoid that
`~/.local/bin/rec` taking precedence over `/usr/bin/rec` in `PATH`.

These are local packages. `pacman -S termrec` and `apt install termrec` by name require
publishing the artifacts in a configured package repository.

## Usage

```bash
# Uses your login shell when it is Bash or zsh.
rec start lab1 -path -terms

# Or choose the shell explicitly.
rec start lab1 --shell bash

rec task "Задание 1. Пользователи"
whoami
id

rec sep

rec code ~/.zshrc zsh ".zshrc"

rec task "Задание 2. Сеть"
ip addr
ip route

rec stop
```

### Continue a finished recording

Use the original session name or its directory path. A continuation appends to the
same report rather than creating `lab1-2`.

```bash
rec start lab1 --continue
# or
rec start ~/Documents/LinuxWorks/2026-10-06/lab1 --continue
```

### Record a child terminal

Start the second terminal from the first one so it inherits `TERMREC_SESSION_DIR`.
In the new terminal run `rec attach`; this opens an attached recording shell in that
window. `rec stop` there stops only the attached terminal. The original terminal and
the session remain active.

```bash
# first terminal, inside rec start ...
gnome-terminal &

# second terminal
rec attach
rec stop
```

Use `-terms` when starting the session to add a terminal heading with its detected
application name and TTY to each part of the report. Use `-path` to prepend the
working directory to commands outside the home directory.

## Platforms and shells

The terminal emulator does not matter: Terminal.app, iTerm2, Windows Terminal,
GNOME Terminal, Kitty and similar applications are only the window around a shell.

- **Linux and macOS:** `rec start` records Bash or zsh without modifying `.bashrc` or
  `.zshrc`. It uses Python's standard-library PTY backend rather than `script(1)`.
- **Other POSIX shells:** use `rec run <name> -- command arguments` for a portable
  non-interactive recording. Automatic clean command/output boundaries need an adapter
  for each shell; Bash and zsh adapters are currently included.
- **Windows:** use `rec run <name> -- command arguments`, for example
  `rec run system -- powershell -NoProfile -Command Get-ComputerInfo`. It exports a
  clean report but does not yet provide an interactive PowerShell/cmd session. That
  requires a Windows ConPTY backend, which will be added as an optional Windows extra.

```bash
rec run hostname -- hostname
rec run disk -- powershell -NoProfile -Command Get-Volume
```

## More controls

```bash
rec note "Check the network configuration next"
rec pause                 # exclude subsequent commands from Markdown/TXT
rec resume
rec redact                # privately enter a literal to hide in exports
rec redact --regex        # privately enter a regular expression
rec redact --list
rec redact --remove 1
rec list
rec show /path/to/session
rec export md --task 2
rec export txt --commands 1,3,5
rec replay /path/to/session
rec attach [--shell bash|zsh]
```

`rec show` lists commands with their global numbers; `--task` uses task numbers starting
at 1. `rec replay` prints the original recording without timing information.

**Sensitive data:** termrec records bytes emitted by the child pseudo-terminal and does
not log stdin. Input hidden by terminal echo settings (such as password prompts) is not
recorded as input. Programs that print secrets can still put them in `session.raw`.
Shell commands and their arguments are recorded by the shell adapter, so avoid putting
secrets directly in commands. `rec pause` and `rec redact` affect exported reports only; `session.raw`
still contains anything the child program printed while paused, and redaction rules
are stored locally in `redactions.json`. Review or remove these files before sharing a
session directory. The `rec redact` prompt hides its input to keep it out of command
history and the recording.

The default output directory is:

```text
~/Documents/LinuxWorks/YYYY-MM-DD/<session>/
```

Example:

```text
~/Documents/LinuxWorks/2026-09-21/lab1/
├── session.raw
├── session.json
├── lab1.md
├── lab1.txt
└── code/
    └── 001-zshrc
```

When `rec attach` is used, additional raw streams are kept in `terminals/` inside the
same session directory; the exports include them automatically.

## Export format

Markdown terminal blocks look like this:

```console
$ whoami
> user
$ hostname
> workstation
```

Task and separator commands are structural only:

```bash
rec task "Задание 1"
rec sep
```

They produce headings / `---` in Markdown, but the `rec ...` command lines and termrec UI
output do not appear in the report.

## Commands

```text
rec start <name>
rec start <name> --continue
rec start <name> -path -terms
rec attach
rec stop
rec task "Title"
rec sep
rec code <file> [language] [title]
rec status
rec export md|txt|all
```

## Custom output root

```zsh
export TERMREC_ROOT="$HOME/Documents/LinuxLabs"
```

## Notes

- `session.raw` is preserved as the original PTY recording and therefore still contains
  the original terminal presentation. It is the recovery/source file.
- `.md` and `.txt` are semantic exports: prompt/theme decoration is omitted, commands are
  prefixed with `$`, and command output is prefixed with `>`.
- `rec code` copies the file at the time the command is run, so later edits do not modify
  an already recorded report.
