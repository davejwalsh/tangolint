# TangoLint — VS Code Extension

Surfaces **tangolint** diagnostics (squiggles and the Problems panel) for
PyTango device-server code directly in VS Code.

## What it checks

| Prefix | Source | Example |
|--------|--------|---------|
| `T0xx` | Tango-specific | Missing `description` on `@attribute`, wrong naming conventions |
| `G0xx` | General Python | Bare `except:`, `== None`, mutable defaults, star imports, … |

Patterns that other linters (ruff, pylint, mypy, pylance) flag *incorrectly*
for Tango code — such as PascalCase `device_property` names, class-level
`attribute(…)` descriptors, or `self.debug_stream()` calls — are **not
reported**.

Run `python3 tangolint.py --list-rules` to see every rule.

---

## Installation

### Option A — copy into the VS Code extensions folder (recommended)

```bash
# From the project root:
cp -r tangolint-vscode \
      "/mnt/c/Users/$USER/AppData/Local/Programs/VSCode/resources/app/extensions/tangolint-0.1.0"
```

Or, more reliably via the user extensions directory:

```bash
cp -r tangolint-vscode \
      "/mnt/c/Users/$(cmd.exe /C "echo %USERNAME%" 2>/dev/null | tr -d '\r')/.vscode/extensions/tangolint-0.1.0"
```

Then **restart VS Code**.

### Option B — symlink (stays in sync with edits to extension.js)

```bash
ln -s "$(pwd)/tangolint-vscode" \
      "/mnt/c/Users/$(cmd.exe /C 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/.vscode/extensions/tangolint-0.1.0"
```

### Option C — package and install with vsce

```bash
cd tangolint-vscode
npm install -g @vscode/vsce   # one-time install
vsce package                  # creates tangolint-0.1.0.vsix
code --install-extension tangolint-0.1.0.vsix
```

### Option D — development / test run

1. Open the `tangolint-vscode/` folder in VS Code.
2. Press **F5** — an Extension Development Host window opens.
3. Open any `.py` file in a workspace that contains `tangolint.py`.

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| `tangolint.py` | Must be present in the workspace root (or set `tangolint.linterPath`) |
| `tangolint_rules.py` | Must be alongside `tangolint.py` |
| Python 3.9+ | Resolved automatically from the Python extension; override with `tangolint.pythonPath` |

---

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `tangolint.linterPath` | `""` | Absolute path to `tangolint.py`. Auto-detected from workspace root if empty. |
| `tangolint.pythonPath` | `""` | Python interpreter path. Uses the Python extension's active interpreter if empty, then falls back to `python3`. |
| `tangolint.lintOnOpen` | `true` | Lint when a file is opened. |
| `tangolint.lintOnSave` | `true` | Lint when a file is saved. |
| `tangolint.lintOnChange` | `false` | Lint while typing (600 ms debounce). |

Add to your workspace `.vscode/settings.json`:

```json
{
  "tangolint.pythonPath": "/home/dave/.venv/bin/python",
  "tangolint.lintOnChange": true
}
```

---

## Commands

| Command | Description |
|---------|-------------|
| `TangoLint: Lint Current File` | Manually trigger linting on the active editor |

Access via the Command Palette (`Ctrl+Shift+P`) → `TangoLint`.

---

## Status bar

The status bar item (bottom-left, `$(check) PyTango`) shows:

| State | Display |
|-------|---------|
| Running | `↻ PyTango` |
| Clean | `✓ PyTango` |
| Warnings only | `⚠ PyTango: 3W` |
| Errors present | `✕ PyTango: 1E 2W` |

Click it to jump to the Problems panel.

---

## Adding new rules

Edit `tangolint_rules.py` in the project root — see the docstring at the
top of that file for instructions.  The extension picks up changes
automatically on the next lint run (no restart required).
