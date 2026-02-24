#!/usr/bin/env python3
"""
TangoLint - A linter for PyTango

Applies the rules that live in `tangolint_rules.py`
"""

import argparse
import ast
import sys
import re

from dataclasses import dataclass
from pathlib import Path

import tangolint_rules as rules


@dataclass
class LintIssue:
    """Represents a linting issue found in the code."""

    line: int
    column: int
    severity: str  # 'error', 'warning', 'info'
    code: str
    message: str


class PyTangoLinter(ast.NodeVisitor):
    """AST visitor that dispatches nodes to registered lint rules."""

    #: Tango base class names used to detect device classes.
    _TANGO_BASES = frozenset(
        [
            "Device",
            "DeviceImpl",
            "BaseInterface",
            "base_interface.BaseInterface",
            "SKADevice",
        ]
    )

    def __init__(self, filename: str, disabled_rules: set[str] | None = None):
        self.filename = filename
        self.disabled_rules = disabled_rules or set()
        self.issues: list[LintIssue] = []
        self.current_class: str | None = None
        self.has_tango_import = False
        self.tango_import_name: str | None = None
        self.attribute_names: set[str] = set()
        self.command_names: set[str] = set()
        self.property_names: set[str] = set()
        self.in_device_class = False

        # Build dispatch table: node_type -> [rule, ...]
        self._rule_map: dict[type, list[rules.ASTRule]] = {}
        for rule in rules.get_ast_rules():
            if rule.code in self.disabled_rules:
                continue
            for node_type in rule.handles:
                self._rule_map.setdefault(node_type, []).append(rule)
                # Async functions share the same rules as regular functions.
                if node_type is ast.FunctionDef:
                    self._rule_map.setdefault(
                        ast.AsyncFunctionDef, []
                    ).append(rule)

    def _ctx(self) -> rules.RuleContext:
        """Return a base RuleContext from the current linter state."""
        return rules.RuleContext(
            in_device_class=self.in_device_class,
            current_class=self.current_class,
        )

    def _run(self, node: ast.AST, ctx: rules.RuleContext) -> None:
        """Dispatch all applicable rules for *node* with *ctx*."""
        for rule in self._rule_map.get(type(node), []):
            for violation_node, message in rule.check(node, ctx):
                self.issues.append(
                    LintIssue(
                        line=getattr(violation_node, "lineno", 0),
                        column=getattr(violation_node, "col_offset", 0),
                        severity=rule.severity,
                        code=rule.code,
                        message=message,
                    )
                )

    def generic_visit(self, node: ast.AST) -> None:
        """Dispatch rules for nodes without a dedicated visit_ method."""
        self._run(node, self._ctx())
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if "tango" in alias.name:
                self.has_tango_import = True
                self.tango_import_name = alias.asname or alias.name
        self._run(node, self._ctx())
        ast.NodeVisitor.generic_visit(self, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and "tango" in node.module:
            self.has_tango_import = True
            if node.module == "tango.server":
                self.tango_import_name = "tango.server"
        self._run(node, self._ctx())
        ast.NodeVisitor.generic_visit(self, node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_class, old_in_device = self.current_class, self.in_device_class
        self.current_class = node.name

        base_names: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Attribute):
                base_names.append(f"{rules.get_name(base.value)}.{base.attr}")
            elif isinstance(base, ast.Name):
                base_names.append(base.id)

        self.in_device_class = any(
            any(tb in bn for tb in self._TANGO_BASES) for bn in base_names
        )

        self._run(node, self._ctx())
        ast.NodeVisitor.generic_visit(self, node)
        self.current_class, self.in_device_class = old_class, old_in_device

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        ctx = self._ctx()
        if self.in_device_class:
            for decorator in node.decorator_list:
                dec_info = rules.get_decorator_info(decorator)
                if dec_info:
                    dec_name, kwargs = dec_info
                    if "attribute" in dec_name:
                        ctx.is_tango_attribute = True
                        ctx.attribute_config = kwargs
                        self.attribute_names.add(node.name)
                    elif "command" in dec_name:
                        ctx.is_tango_command = True
                        self.command_names.add(node.name)
        self._run(node, ctx)
        ast.NodeVisitor.generic_visit(self, node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            self.in_device_class
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.Call)
            and "device_property" in rules.get_name(node.value.func)
        ):
            self.property_names.add(node.target.id)
        self._run(node, self._ctx())
        ast.NodeVisitor.generic_visit(self, node)

def _parse_noqa(source: str) -> dict[int, set[str] | None]:
    """Parse noqa annotations.

    Returns a dict as a map to:
    - `None`        — suppress all issues on that line (i.e. if there is a `# noqa`)
    - `set[str]`    — suppress only the listed codes  (i.e. `# noqa: T023, G001`)
    """
    noqa: dict[int, set[str] | None] = {}
    pattern = re.compile(r"#\s*noqa(?::\s*([A-Z0-9,\s]+))?", re.IGNORECASE)
    for lineno, line in enumerate(source.splitlines(), start=1):
        m = pattern.search(line)
        if not m:
            continue
        if m.group(1):
            codes = {c.strip().upper() for c in m.group(1).split(",") if c.strip()}
            noqa[lineno] = codes
        else:
            noqa[lineno] = None  # bare # noqa — suppress everything
    return noqa

def lint_file(
    filepath: Path, disabled_rules: set[str] | None = None
) -> list[LintIssue]:
    """Lint a Python file for PyTango issues."""
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))

        disabled = disabled_rules or set()

        linter = PyTangoLinter(str(filepath), disabled_rules=disabled)
        linter.visit(tree)

        if not linter.has_tango_import: #This ain't be tango
            return []

        source_issues: list[LintIssue] = []
        for rule in rules.get_source_rules():
            if rule.code in disabled:
                continue
            for line, column, message in rule.check_source(content):
                source_issues.append(
                    LintIssue(
                        line=line,
                        column=column,
                        severity=rule.severity,
                        code=rule.code,
                        message=message,
                    )
                )

        all_issues = sorted(
            linter.issues + source_issues, key=lambda x: (x.line, x.column)
        )

        # Filter # noqa annotations.
        noqa = _parse_noqa(content)
        def _suppressed(issue: LintIssue) -> bool:
            suppression = noqa.get(issue.line)
            if suppression is None and issue.line in noqa:
                return True   # bare # noqa
            if isinstance(suppression, set) and issue.code in suppression:
                return True
            return False

        return [i for i in all_issues if not _suppressed(i)]

    except SyntaxError as e:
        return [
            LintIssue(
                line=e.lineno or 0,
                column=e.offset or 0,
                severity="error",
                code="E999",
                message=f"Syntax error: {e.msg}",
            )
        ]
    except Exception as e:
        return [
            LintIssue(
                line=0,
                column=0,
                severity="error",
                code="E000",
                message=f"Failed to parse file: {e}",
            )
        ]


def format_issue(issue: LintIssue, filename: str) -> str:
    """Pretty."""
    
    severity_colors = {
        "error": "\033[91m",  # Red
        "warning": "\033[93m",  # Yellow
        "info": "\033[94m",  # Blue
    }
    reset = "\033[0m"
    color = severity_colors.get(issue.severity, "")

    return (
        f"{filename}:{issue.line}:{issue.column}: "
        f"{color}{issue.severity}: {issue.code}{reset} {issue.message}"
    )


def print_summary(
    issues: list[LintIssue], filename: str, use_color: bool = True
) -> None:
    """Print a formatted summary of linting issues."""
    if not use_color:
        # Strip color codes for non-terminal output
        global format_issue
        original_format = format_issue

        def no_color_format(issue: LintIssue, fn: str) -> str:
            return original_format(issue, fn).replace("\033[91m", "").replace(
                "\033[93m", ""
            ).replace("\033[94m", "").replace("\033[0m", "")

        format_issue = no_color_format

    if not issues:
        print(f"✓ {filename}: No issues found")
        return

    print(f"\n{'='*80}")
    print(f"PyTango Linter Results: {filename}")
    print(f"{'='*80}\n")

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    for issue in issues:
        print(format_issue(issue, filename))

    print(f"\n{'-'*80}")
    print(
        f"Summary: {len(errors)} error(s), {len(warnings)} warning(s), "
        f"{len(infos)} info message(s)"
    )
    print(f"{'-'*80}\n")


def main() -> int:
    """Main entry point for the linter."""
    parser = argparse.ArgumentParser(
        description="TangoLint - Check PyTango device server code"
    )
    parser.add_argument(
        "files", nargs="*", type=Path, help="Python files to lint"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (non-zero exit code)",
    )
    parser.add_argument(
        "--disable",
        metavar="CODE",
        action="append",
        default=[],
        help="Disable a rule by code (e.g. --disable T001 --disable G007). "
             "May be repeated.",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available rules and exit",
    )

    args = parser.parse_args()

    if args.list_rules:
        all_rules: list[tuple[str, str, str]] = []
        for rule in rules.get_ast_rules() + rules.get_source_rules():  # type: ignore[operator]
            all_rules.append((rule.code, rule.severity, rule.__doc__ or ""))
        all_rules.sort()
        col = max(len(r[0]) for r in all_rules) + 2
        for code, severity, doc in all_rules:
            desc = doc.strip().splitlines()[0] if doc.strip() else ""
            print(f"{code:<{col}} [{severity:<7}]  {desc}")
        return 0

    if not args.files:
        parser.print_help()
        return 0

    disabled = set(args.disable)
    total_errors = 0
    total_warnings = 0
    total_infos = 0

    for filepath in args.files:
        if not filepath.exists():
            print(f"Error: File '{filepath}' not found", file=sys.stderr)
            return 1

        if not filepath.suffix == ".py":
            print(f"Warning: Skipping non-Python file '{filepath}'")
            continue

        issues = lint_file(filepath, disabled_rules=disabled)
        print_summary(issues, str(filepath), use_color=not args.no_color)

        total_errors += sum(1 for i in issues if i.severity == "error")
        total_warnings += sum(1 for i in issues if i.severity == "warning")
        total_infos += sum(1 for i in issues if i.severity == "info")

    if len(args.files) > 1:
        print(f"\n{'='*80}")
        print(
            f"Total: {total_errors} error(s), {total_warnings} warning(s), "
            f"{total_infos} info message(s)"
        )
        print(f"{'='*80}\n")

    if total_errors > 0:
        return 1
    if args.strict and total_warnings > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
