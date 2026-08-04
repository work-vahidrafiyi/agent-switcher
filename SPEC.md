# Project spec — CLI agent account switcher

## What we're building

A desktop tool that lets one person keep several accounts for CLI coding agents
(starting with OpenAI Codex) side by side and switch between them in one click,
without signing out and back in each time.

GUI is the primary experience. The CLI is the official interface that everything
else — the GUI, a future VS Code extension, scripts — is built on top of.

Target platforms: **Linux and Windows** are supported and tested. macOS is
best-effort; leave the door open in the design but do not claim support.

## The problem this solves, and the one constraint that matters

Codex stores its ChatGPT session in `$CODEX_HOME/auth.json` (default
`~/.codex/auth.json`). The obvious approach — copy that file, log in as someone
else, copy it back — fails for two reasons:

1. **`codex logout` revokes the refresh token server-side.** It POSTs the token
   to the OAuth revoke endpoint before deleting the local file. Any copy you
   saved earlier is dead. **The tool must never invoke `codex logout`.** To
   switch away, delete or move `auth.json` instead.

2. **Refresh tokens rotate.** Every refresh writes a new token into `auth.json`
   and invalidates the previous one. A snapshot taken an hour ago is stale. So
   before switching away from a profile, the tool must copy the *live*
   `auth.json` back into that profile's file. This "sync live first, then swap"
   step is the core of the whole design — get it wrong and everything else is
   pointless.

Document both of these prominently in the README. They are the real value of
this project; the GUI is just packaging.

## On-disk layout

```
$CODEX_HOME/
  auth.json              # live credentials, owned by the codex CLI
  auth.<name>.json       # one saved profile per account
  .active                # plain text, name of the currently live profile
```

Profile names match `^[A-Za-z0-9._-]+$`. `auth.json` itself is never treated as
a profile.

## Architecture

```
<pkg>/
  core/
    store.py       # profiles(), active(), sync_live(), switch(), rename(), delete()
    identity.py    # decode the id_token JWT -> email, plan, last refresh
    login.py       # run the provider's device-auth flow, surface URL + code
    providers/
      base.py      # Provider protocol
      codex.py     # the only implementation for now
  cli.py           # every command supports --json
  gui/             # thin layer over core, no business logic
```

Rules:

- `core/` imports nothing from `gui/` and nothing from `cli.py`. It must be
  importable and testable with no display attached.
- Business logic lives only in `core/`. If the GUI and the CLI would each need
  a rule, that rule belongs in `core/`.
- Build `providers/` from day one even with a single provider. Adding Claude
  Code or Gemini CLI later should mean writing one new file, not reshaping the
  package.

### Provider protocol

Each provider describes where its credentials live and how to log in:

```python
class Provider(Protocol):
    name: str
    def home(self) -> Path: ...
    def auth_file(self) -> Path: ...
    def login_command(self) -> list[str]: ...
    def parse_identity(self, path: Path) -> Identity: ...
```

For Codex: home is `$CODEX_HOME` or `~/.codex`, auth file is `auth.json`, login
command is `codex login --device-auth`, identity comes from the `tokens.id_token`
JWT payload (`email`, and a plan type nested under an `https://api.openai.com/...`
claim).

Do not hardcode paths for providers you have not verified. When you add Claude
Code or Gemini CLI, check their actual credential locations first — at least one
of them uses the OS keyring on macOS, which breaks the copy-a-file model and
needs a different strategy.

## Device login flow

Run the provider's login command as a subprocess and stream its output live,
extracting two things: the verification URL and the one-time code. Show them to
the user with copy buttons and an "open in browser" action.

- **Unix:** run it on a pty (`pty.openpty()`), otherwise the CLI buffers or
  changes behaviour when it detects it isn't attached to a terminal.
- **Windows:** no pty. Use pipes, set `NO_COLOR=1` and `TERM=dumb` in the child
  environment, and pass `CREATE_NO_WINDOW`. If `codex` resolves to a `.cmd` or
  `.bat` shim (npm install), invoke it through `cmd /c`.
- Strip ANSI escapes before matching.
- The output format is undocumented and will change. Always expose the raw
  output in the UI so a user can read the code manually when the parser misses.

Before starting a login, sync the live profile and remove `auth.json`. If the
login is cancelled or fails, restore the previous profile and its `.active`
entry. Never leave the user logged out of an account they had.

## Safety behaviours

- Warn before switching if a `codex` process is running — it may write
  `auth.json` from under us. (`pgrep` on Unix, `tasklist` on Windows.)
- Deleting a profile removes the saved file only. Say so in the confirmation
  dialog: the upstream account is untouched.
- Never call any provider's `logout`.
- Writes to `auth.json` should be atomic (write to a temp file in the same
  directory, then replace) so an interrupted switch can't leave a truncated file.

## Testing

`core/` must be covered by tests that run in CI with no display and no network:

- Fixture `auth.json` files with synthetic JWTs — never commit a real token.
- The switch cycle: sync-live-then-swap preserves a token that changed after the
  profile was first saved. This is the regression test that matters most.
- Login failure restores the previous active profile.
- Profile discovery ignores `auth.json` and malformed names.
- Feed recorded sample output through the URL/code parser, including a sample
  with ANSI escapes and one where the code is on a separate line from the URL.

## GUI

One codebase for both platforms — prefer PySide6 over per-platform toolkits so
Linux and Windows share the same code, and use `QSystemTrayIcon` for quick
switching from the tray. Closing the window hides to tray; quitting is explicit.

Per account show: name, email, plan, when the token was last refreshed, and
which one is active. Actions: use, rename, remove, add.

After a switch, tell the user plainly that VS Code has to be closed and reopened
— a window reload alone does not always clear the cached token in the Codex
app-server.

## CLI

```
<cmd> list [--json]
<cmd> switch <name> [--json]
<cmd> add <name>          # runs device auth, prints URL and code
<cmd> current [--json]
<cmd> rename <old> <new>
<cmd> remove <name>
```

Exit codes: 0 success, 1 user error, 2 provider/login failure. `--json` prints a
single object to stdout and keeps all human text on stderr, so the future VS Code
extension can parse it.

## Roadmap

1. `core` + `cli` + tests. No GUI yet.
2. GUI on Linux and Windows.
3. VS Code extension — a thin wrapper that shells out to the CLI with `--json`
   and then triggers a window reload. It should not reimplement any logic.
4. Additional providers (Claude Code, Gemini CLI).
5. Per-account usage/quota display. **Last, and off by default.** It requires
   calling undocumented endpoints, it is the most fragile part of the project,
   and it is the part most likely to draw complaints. Ship everything else first.

## Positioning

Frame this in the README as managing separate accounts — work and personal, or
several clients — not as a way to stretch a rate limit. Add a short note that
users are responsible for complying with each provider's terms. Keep the tone
factual.

Pick a provider-neutral name, since this is meant to grow past Codex, and check
that it does not collide with an existing VS Code extension.

## Starting point

Two working prototypes are attached: a GTK version for Linux and a Tkinter
version for Windows. They implement the sync-live-then-swap logic, the JWT
identity parsing, and the device-login output parsing correctly — read them for
the behaviour, then restructure into the package layout above rather than
extending them in place.

Begin with step 1. Set up `pyproject.toml` for a `pipx`-installable package,
write `core/` with its tests, and get the CLI working end to end before touching
any UI code.