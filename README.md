# TangoLint

A linter for PyTango that avoids the annoying complaints
from mypy/ruff etc, and adds some hopefully useful Tango
specific linting hints.

For non-Tango files, it attempts to lint using ``ruff``
and ``mypy``

---

## Installation

### VS Code extension (recommended)

1. Download and extract the latest https://github.com/davejwalsh/tangolint/releases .
2. Extract the files somewhere.
2. Open VS Code / Extensions panel (`Ctrl+Shift+X`) 
3. Click the three dots menu and select 'Install from VSIX'
3. Select the downloaded `tangolint-0.1.0.vsix` file from your download location and reload the window.

### CLI

Copy `pytangolint.py` and `pytangolint_rules.py` into your project (they must stay together), then run:

```bash
python3 pytangolint.py mydevice.py
```

Requires Python 3.9+. No third-party dependencies.

---

## VS Code usage

Once installed the extension lints automatically on File Open and File Save (we could do it while typing too, but this
is currently disabled).

Issues appear as squiggles in the editor and in the Problems panel (`Ctrl+Shift+M`).
The status bar item (bottom-left) shows a live summary — click it to jump to the Problems panel.

To manually lint the active file: `Ctrl+Shift+P` → `PyTango Linter: Lint Current File`

### Settings

Open VS Code Settings (`Ctrl+,`) and search for **PyTango** to see all options.

| Setting | Default | Description |
|---------|---------|-------------|
| `pytangolint.lintOnOpen` | `true` | Lint when a file is opened |
| `pytangolint.lintOnSave` | `true` | Lint when a file is saved |
| `pytangolint.lintOnChange` | `false` | Lint while typing (600 ms debounce) |
| `pytangolint.pythonPath` | `""` | Python interpreter to use (auto-detected if empty) |
| `pytangolint.linterPath` | `""` | Path to a custom `pytangolint.py` (uses bundled copy if empty) |

#### Enabling / disabling individual rules

Each rule has its own toggle under PyTango Linter › Rules in the Settings UI.
Untick a rule to silence it globally across all files.

You can also set them in `.vscode/settings.json`:

```json
{
  "pytangolint.rules.T024": false,
  "pytangolint.rules.G007": false
}
```

---

## Command-line usage

```bash
# Lint one or more files
python3 pytangolint.py mydevice.py

# Lint multiple files
python3 pytangolint.py src/**/*.py

# Treat warnings as errors (non-zero exit on any warning)
python3 pytangolint.py --strict mydevice.py

# Disable specific rules for this run
python3 pytangolint.py --disable T024 --disable G007 mydevice.py

# List all rules
python3 pytangolint.py --list-rules

# No colour output (e.g. for CI logs)
python3 pytangolint.py --no-color mydevice.py
```

---

## Suppressing warnings inline

Use standard `# noqa` comments to suppress issues on a specific line:

```python
from tango import *           # noqa          — suppress everything on this line
def voltage(self):            # noqa: T020    — suppress one rule
x = get_val()                 # noqa: T023, G001  — suppress multiple rules
```

---

## Rules

### Tango-specific (T-codes)

| Code | Severity | Description |
|------|----------|-------------|
| T001 | warning | Device class name should start with an uppercase letter |
| T010 | error | `device_property` must have a type annotation |
| T011 | warning | `device_property` name should use PascalCase |
| T020 | warning | Tango `@attribute` method should have a docstring |
| T021 | error | Tango `@attribute` method must have a return-type annotation |
| T022 | info | Attribute `name` config key differs from the method name |
| T023 | warning | Tango `@attribute` should include a `description` parameter |
| T024 | info | Tango `@attribute` may need a `unit` parameter |
| T025 | info | Tango `@attribute` body may need quality validation via `set_validity` |
| T030 | warning | Tango `@command` method should have a docstring |
| T031 | info | Tango `@command` name should use PascalCase |
| T032 | error | Tango device classes must not override `__init__`; use `init_device()` instead |

### General Python (G-codes)

| Code | Severity | Description |
|------|----------|-------------|
| G001 | warning | Bare `except:` clause catches every exception; specify the type |
| G002 | warning | Empty `except` block silently swallows exceptions |
| G003 | warning | Use `is`/`is not` when comparing against `None`, `True`, or `False` |
| G004 | warning | Mutable default argument; use `None` and initialise inside the function |
| G005 | warning | Star import pollutes the namespace; import names explicitly |
| G006 | info | Multiple modules on one `import` line; use separate statements |
| G007 | info | Line exceeds the maximum allowed length (88 characters) |
| G008 | info | `print()` in a device class method; use Tango stream methods instead |

---

## Adding custom rules

Edit `pytangolint_rules.py`. Each rule is a class — no registration needed:

```python
class T033_MyCheck(ASTRule):
    """One-line description shown in --list-rules."""

    code     = "T033"
    severity = "warning"          # 'error', 'warning', or 'info'
    handles  = (ast.FunctionDef,) # AST node type(s) that trigger the check

    def check(self, node, ctx):
        if <condition>:
            yield node, "Human-readable message"
```

See the docstring at the top of `pytangolint_rules.py` for the full guide.

---

## Repository

https://github.com/davejwalsh/pytangolint
