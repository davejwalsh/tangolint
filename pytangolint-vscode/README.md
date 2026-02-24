# PyTango Linter — VS Code Extension

Surfaces **pytangolint** diagnostics (squiggles and the Problems panel) for
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

Run `python3 pytangolint.py --list-rules` to see every rule.

---

## Installation

### Option A — copy into the VS Code extensions folder (recommended)

```bash
# From the project root:
cp -r pytangolint-vscode \
      "/mnt/c/Users/$USER/AppData/Local/Programs/VSCode/resources/app/extensions/pytangolint-0.1.0"
```

Or, more reliably via the user extensions directory:

```bash
cp -r pytangolint-vscode \
      "/mnt/c/Users/$(cmd.exe /C "echo %USERNAME%" 2>/dev/null | tr -d '\r')/.vscode/extensions/pytangolint-0.1.0"
```

Then **restart VS Code**.

### Option B — symlink (stays in sync with edits to extension.js)

```bash
ln -s "$(pwd)/pytangolint-vscode" \
      "/mnt/c/Users/$(cmd.exe /C 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/.vscode/extensions/pytangolint-0.1.0"
```

### Option C — package and install with vsce

```bash
cd pytangolint-vscode
npm install -g @vscode/vsce   # one-time install
vsce package                  # creates pytangolint-0.1.0.vsix
code --install-extension pytangolint-0.1.0.vsix
```

### Option D — development / test run

1. Open the `pytangolint-vscode/` folder in VS Code.
2. Press **F5** — an Extension Development Host window opens.
3. Open any `.py` file in a workspace that contains `pytangolint.py`.

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| `pytangolint.py` | Must be present in the workspace root (or set `pytangolint.linterPath`) |
| `pytangolint_rules.py` | Must be alongside `pytangolint.py` |
| Python 3.9+ | Resolved automatically from the Python extension; override with `pytangolint.pythonPath` |

---

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `pytangolint.linterPath` | `""` | Absolute path to `pytangolint.py`. Auto-detected from workspace root if empty. |
| `pytangolint.pythonPath` | `""` | Python interpreter path. Uses the Python extension's active interpreter if empty, then falls back to `python3`. |
| `pytangolint.lintOnOpen` | `true` | Lint when a file is opened. |
| `pytangolint.lintOnSave` | `true` | Lint when a file is saved. |
| `pytangolint.lintOnChange` | `false` | Lint while typing (600 ms debounce). |

Add to your workspace `.vscode/settings.json`:

```json
{
  "pytangolint.pythonPath": "/home/dave/.venv/bin/python",
  "pytangolint.lintOnChange": true
}
```

---

## Commands

| Command | Description |
|---------|-------------|
| `PyTango Linter: Lint Current File` | Manually trigger linting on the active editor |

Access via the Command Palette (`Ctrl+Shift+P`) → `PyTango Linter`.

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

Edit `pytangolint_rules.py` in the project root — see the docstring at the
top of that file for instructions.  The extension picks up changes
automatically on the next lint run (no restart required).
