---
inclusion: always
---

# Output Behavior and Python Standards

Python rules are adjusted for MicroPython on the badge.

## Response tone

- Skip filler ("Good catch", "Great question", "You're absolutely right"). Answer the substance.
- State findings, not reactions.

## Evidence-based responses

- State only what the data shows. Cite the specific log line, error, value or measurement.
- Use precise language: "happened at the same time", not "caused", unless causation is shown.
- Absence of evidence is not evidence of absence: say "no evidence of X", not "X didn't happen".
- When investigating, name what you are looking at (file, function, serial log line, pin), not
  "examining the code".
- Verify exact names before reasoning about them. Trace from the entry point (`main.py`,
  `app_switcher`), not only from the line in the traceback.
- "Which file contains X" is a factual claim: search for the actual string first, then state it.

## Assumptions and speculation

- Label speculation ("This suggests...", "One possibility is...") and say why.
- If several explanations fit, present them as alternatives instead of picking one.
- Things only the user can see (the e-paper, the LEDs) are unverified until the user confirms
  them or sends a photo. Say so instead of claiming the screen looks right.

## Context discipline

- Return summaries, not raw dumps. Quote the relevant lines, not whole files or logs.
- Prefer specific queries (one file, one grep, a filtered serial log) over broad ones.

## File creation

- Don't create files the user didn't ask for, and no stray `.md` docs.
- Scratch and investigation files go in `/tmp/` or `.kiro/tmp/`. Clean them up when done.

## Acting without asking

- Go ahead without asking on read-only and local work: reading files, searching, running tests
  on the host, pushing code to the badge, reading the serial log, editing files on a feature branch.
- Ask first before:
  - destructive actions: deleting data, overwriting files you didn't write, `git reset --hard`,
    force pushes, erasing or reflashing the badge
  - pushing to a remote, opening or merging PRs, or anything else on GitHub
  - anything that writes to the upstream Hack-a-Day repo
- "Are you sure?" prompts on read-only work waste time. Default to action there.

## Commands the user runs

The user copies commands from the chat into a zsh terminal. Long lines wrap and get pasted as
separate lines, and two commands on one line get run as one. Write every command so it survives
a paste:

- One command per code block. Number the blocks in run order. Don't chain unrelated commands with
  `;` or `&&`.
- Keep each line under about 100 characters. Break longer ones with a trailing `\` at a word
  boundary, with nothing after the `\`.
- No multi-line shell constructs to paste (loops, `if`, heredocs). Put them in a script and give
  one short command that runs it, using an absolute path.
- No `#` comments in shell blocks: interactive zsh passes them to the command as arguments. Put
  the explanation in the prose above the block.
- Set variables in their own block, then use them in later blocks.
- No pagers: use `git --no-pager`, or `GIT_PAGER=cat` in scripts.
- When asking for output back, ask for one block's output at a time, and say what a pass looks like
  before the user runs it.

## Before you change code

- Restate the problem in a sentence or two. If you can't, you don't understand it yet.
- Name the data first: the buffers, files, pins or registers the change reads and writes.
- Fix the root cause. Trace the symptom back to the first place the system goes wrong. A
  try/except, retry or check that hides a bad state is not a fix.
- If two fixes resting on the same assumption have failed, stop. Write the assumption down and
  test it directly before trying a third.
- If you can find a fact out yourself (run it on the badge, read the code, check the log), do that
  instead of asking. Ask only about requirements or preferences.

## Writing code

- Make the smallest change that solves the problem. Deleting code beats adding it. Add no
  abstraction, layer, flag or option the task doesn't need.
- Remove code your change makes dead. Don't refactor, rename or reformat code you weren't asked to
  touch.
- Follow the repo's existing patterns, libraries and naming.
- Keep layers few: no single-caller wrappers, keep mutable state narrow.
- Validate input at the boundary (files in `/data`, I2C/SAO reads, network data) and trust
  internal values after that.
- Comments describe behavior: the non-obvious why of the code as it stands. A comment is not change
  history. Don't narrate what the code does, don't leave "changed X" or "added for Y" notes, and
  don't put PR numbers in comments. That belongs in git history. Leave comments you didn't touch
  alone.
- Use plain ASCII punctuation in code, comments, commit messages and PR text. No em dashes.

## Python

Two kinds of Python live in this repo, with different rules:
- **Badge code** (`firmware/badge/`, and the badge-side test scripts `firmware/scripts/fast_refresh_demo.py`,
  `ghost_compare.py`, `hold_test.py`, `check_filesystem.py`, run with `mpremote run`) runs on MicroPython 1.24.1.
- **Host tools** (`firmware/scripts/update.py`, `copy_assets.py`, `led_demo.py`, the Python inside
  `boot_test.sh`/`soft_reboot_test.sh`, `firmware/sim/sao_example.py`) run on CPython 3.10+ under `uv run`.

### Both
- Double quotes. Line length up to 120 characters.
- Imports sorted: stdlib, then third-party, then local (`apps.`, `lib.`). One `from` import per line
  where it helps readability.
- f-strings preferred over `.format()` or `%`.
- No bare `except:`. Catch specific exceptions. `except Exception` is acceptable only at a top-level
  guard (an app's `arun()`, a boot step) that must not crash the badge, and it must print the
  traceback (`sys.print_exception(ex)` on the badge).
- No mutable default arguments.
- Type hints on new function signatures (arguments and return). MicroPython accepts and ignores them.
- Docstrings on public functions and classes: one line for simple functions, plus an "Args"/"Returns"
  section only when the meaning isn't obvious. Follow the docstring style already in the file.

### Badge code (MicroPython)
- Only use what MicroPython provides: no `pathlib`, `logging`, `typing`, `dataclasses`, stepped
  slices (`a[::2]`) or positional-only `/` parameters. Use `print()` for logs; it goes to the serial
  console.
- Never block the asyncio loop for long. Await between chunks of slow work, and check display
  busy state (`display._framebuffer_ready.is_set() or not display.is_done_updating()`) before
  requesting a refresh.
- Use `@micropython.viper` with `ptr8` for per-pixel or per-byte loops over framebuffers.
- Keep flash writes rare: write `/data` files only when the value changed.
- A syntax error in any app file must not stop boot; test new apps on the badge before merging.

### Host tools (CPython)
- Run with `uv run`. Add dependencies to `pyproject.toml` with `uv add`, not with pip.
- Use `pathlib.Path` for new path handling.
- Format and lint with `uv run --with ruff ruff format` and `ruff check` if you add tooling; don't
  reformat files you didn't change.

## Tests

- Test what callers can observe, not internals. A good test fails when the behavior breaks and
  keeps passing through a refactor.
- For a bug, reproduce it first (on the badge or with a host-side stub), then fix it and show the
  same test passing.
- On the badge, a refresh test checks timing: a real full refresh is about 33 s after
  "display working", and one that finishes in 1 to 2 s means the panel never redrew.

## Done means verified

- Run it on the badge or the host. "It compiles" or "it should work" is not done.
- Check the real result: the serial log, the file on the badge, the measured time, and the
  user's confirmation or photo for anything on the screen or LEDs.
- If you couldn't verify something, say what and why.

## Reporting

- Label each claim as verified (name what you ran), inferred, or a guess.
- Point to files and lines. Quote the command and the relevant output lines, not the whole log.
- Say what you didn't do and what is still open.

## Reviewing

Flag each of these with file and line:
- Speculative abstraction, unused parameters, or options nobody asked for.
- A guard that masks a root cause instead of fixing it.
- Narrating comments, change history or PR numbers in comments, stale comments, and dead code.
- Tests that check implementation details or only exercise mocks.
- "Fixed" or "works" claims with no test or run behind them.
