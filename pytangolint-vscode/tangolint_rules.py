"""Lint rules for TangoLint.

To add a new rule
-----------------
1. Create a subclass of ``ASTRule`` (for AST-based checks) or ``SourceRule``
   (for source-text checks).
2. Set the class attributes::

       code     = "X001"       # unique rule code
       severity = "warning"    # 'error', 'warning', or 'info'
       handles  = (ast.Xyz,)   # AST node type(s) that trigger check()
                               # (ASTRule only; omit for SourceRule)

3. Implement the check method and ``yield`` each violation::

       # ASTRule:
       def check(self, node, ctx):
           if <condition>:
               yield node, "human-readable message"

       # SourceRule:
       def check_source(self, source):
           if <condition>:
               yield line_number, column, "human-readable message"

The rule is registered automatically; no further wiring is required.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Iterator

# ── Auto-registration registries ──────────────────────────────────────────────

_AST_RULES: list[ASTRule] = []
_SOURCE_RULES: list[SourceRule] = []


# ── Rule context ──────────────────────────────────────────────────────────────


@dataclass
class RuleContext:
    """Linter state provided to every rule when it runs."""

    in_device_class: bool = False
    current_class: str | None = None
    # Populated for FunctionDef nodes inside device classes:
    is_tango_attribute: bool = False
    is_tango_command: bool = False
    attribute_config: dict[str, Any] = field(default_factory=dict)


# ── Base classes ──────────────────────────────────────────────────────────────


class ASTRule:
    """Base class for rules that inspect AST nodes.

    Subclass, set ``code``, ``severity``, and ``handles``, then implement
    ``check``.  The subclass is registered automatically.
    """

    code: str = ""
    severity: str = "warning"
    #: AST node types that trigger ``check``.
    handles: tuple[type[ast.AST], ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.code:  # skip the abstract base itself
            _AST_RULES.append(cls())

    def check(
        self, node: ast.AST, ctx: RuleContext
    ) -> Iterator[tuple[ast.AST, str]]:
        """Yield ``(node, message)`` for each violation found."""
        return
        yield  # pragma: no cover — makes this a generator


class SourceRule:
    """Base class for rules that inspect raw source text.

    Subclass, set ``code`` and ``severity``, then implement
    ``check_source``.  The subclass is registered automatically.
    """

    code: str = ""
    severity: str = "info"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.code:
            _SOURCE_RULES.append(cls())

    def check_source(self, source: str) -> Iterator[tuple[int, int, str]]:
        """Yield ``(line, column, message)`` for each violation found."""
        return
        yield  # pragma: no cover


# ── AST helpers (available to rule implementations) ───────────────────────────


def get_name(node: ast.expr) -> str:
    """Return the dotted name of a Name, Attribute, or Call node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{get_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return get_name(node.func)
    return ""


def get_constant_value(node: ast.expr) -> Any:
    """Return the value of an ``ast.Constant`` node, or ``None``."""
    return node.value if isinstance(node, ast.Constant) else None


def get_decorator_info(
    decorator: ast.expr,
) -> tuple[str, dict[str, Any]] | None:
    """Return ``(name, kwargs_dict)`` for a decorator, or ``None``."""
    kwargs: dict[str, Any] = {}
    if isinstance(decorator, ast.Call):
        for keyword in decorator.keywords:
            if keyword.arg:
                kwargs[keyword.arg] = get_constant_value(keyword.value)
        return get_name(decorator.func), kwargs
    if isinstance(decorator, (ast.Name, ast.Attribute)):
        return get_name(decorator), {}
    return None


def has_call_to(node: ast.AST, func_name: str) -> bool:
    """Return ``True`` if *node* or any descendant calls *func_name*."""
    return any(
        isinstance(child, ast.Call) and func_name in get_name(child.func)
        for child in ast.walk(node)
    )


# ── Public accessors ──────────────────────────────────────────────────────────


def get_ast_rules() -> list[ASTRule]:
    """Return all registered AST rules."""
    return list(_AST_RULES)


def get_source_rules() -> list[SourceRule]:
    """Return all registered source-text rules."""
    return list(_SOURCE_RULES)


# ══════════════════════════════════════════════════════════════════════════════
# Tango-specific rules  (T-codes)
# ══════════════════════════════════════════════════════════════════════════════


class T001_DeviceClassNaming(ASTRule):
    """Device class name should start with an uppercase letter."""

    code = "T001"
    severity = "warning"
    handles = (ast.ClassDef,)

    def check(self, node: ast.ClassDef, ctx: RuleContext):  # type: ignore[override]
        if ctx.in_device_class and not node.name[0].isupper():
            yield node, f"Device class '{node.name}' should start with uppercase letter"


class T010_PropertyMissingAnnotation(ASTRule):
    """device_property must have a type annotation."""

    code = "T010"
    severity = "error"
    handles = (ast.AnnAssign,)

    def check(self, node: ast.AnnAssign, ctx: RuleContext):  # type: ignore[override]
        if not ctx.in_device_class or not isinstance(node.target, ast.Name):
            return
        if (
            isinstance(node.value, ast.Call)
            and "device_property" in get_name(node.value.func)
            and node.annotation is None
        ):
            yield node, f"Device property '{node.target.id}' must have type annotation"


class T011_PropertyNaming(ASTRule):
    """device_property name should use PascalCase."""

    code = "T011"
    severity = "warning"
    handles = (ast.AnnAssign,)

    def check(self, node: ast.AnnAssign, ctx: RuleContext):  # type: ignore[override]
        if not ctx.in_device_class or not isinstance(node.target, ast.Name):
            return
        if (
            isinstance(node.value, ast.Call)
            and "device_property" in get_name(node.value.func)
            and not node.target.id[0].isupper()
        ):
            yield node, f"Device property '{node.target.id}' should use PascalCase"


class T020_AttributeMissingDocstring(ASTRule):
    """Tango @attribute method should have a docstring."""

    code = "T020"
    severity = "warning"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if ctx.is_tango_attribute and not ast.get_docstring(node):
            yield node, f"Attribute '{node.name}' should have a docstring"


class T021_AttributeMissingReturnType(ASTRule):
    """Tango @attribute method must have a return-type annotation."""

    code = "T021"
    severity = "error"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if ctx.is_tango_attribute and node.returns is None:
            yield node, f"Attribute '{node.name}' must have return type annotation"


class T022_AttributeNameMismatch(ASTRule):
    """Attribute 'name' config key differs from the method name."""

    code = "T022"
    severity = "info"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if not ctx.is_tango_attribute:
            return
        configured_name = ctx.attribute_config.get("name")
        if configured_name and configured_name != node.name:
            yield node, (
                f"Attribute name '{configured_name}' differs from method name '{node.name}'"
            )


class T023_AttributeMissingDescription(ASTRule):
    """Tango @attribute should include a 'description' parameter."""

    code = "T023"
    severity = "warning"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if ctx.is_tango_attribute and "description" not in ctx.attribute_config:
            yield node, f"Attribute '{node.name}' should have 'description' parameter"


class T024_AttributeMissingUnit(ASTRule):
    """Tango @attribute may need a 'unit' parameter."""

    code = "T024"
    severity = "info"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if (
            ctx.is_tango_attribute
            and "unit" not in ctx.attribute_config
            and not node.name.endswith("Status")
        ):
            yield node, f"Attribute '{node.name}' may need 'unit' parameter"


class T025_AttributeMissingQualityCheck(ASTRule):
    """Tango @attribute body may need quality validation via set_validity."""

    code = "T025"
    severity = "info"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if not ctx.is_tango_attribute:
            return
        # Exclude a leading docstring from the body count so that a simple
        # "docstring + return" does not trigger a spurious warning.
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            body = body[1:]
        if not has_call_to(node, "set_validity") and len(body) > 1:
            yield node, f"Attribute '{node.name}' may need quality validation"


class T030_CommandMissingDocstring(ASTRule):
    """Tango @command method should have a docstring."""

    code = "T030"
    severity = "warning"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if ctx.is_tango_command and not ast.get_docstring(node):
            yield node, f"Command '{node.name}' should have a docstring"


class T031_CommandNaming(ASTRule):
    """Tango @command name should use PascalCase."""

    code = "T031"
    severity = "info"
    handles = (ast.FunctionDef,)

    _COMMON = {"Init", "On", "Off", "State", "Status", "Standby", "Reset"}

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if (
            ctx.is_tango_command
            and node.name not in self._COMMON
            and not node.name[0].isupper()
        ):
            yield node, f"Command '{node.name}' should use PascalCase"

class T032_DoNotOverrideInit(ASTRule):
    """Tango device classes must not override __init__; use init_device() instead."""

    code = "T032"
    severity = "error"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if not ctx.in_device_class:
            return

        if node.name == "__init__":
            yield node, (
                f"Device class '{ctx.current_class}' must not override '__init__'; "
                "override 'init_device()' instead"
            )


# ══════════════════════════════════════════════════════════════════════════════
# General rules  (G-codes) — standard Python, safe for Tango code
# ══════════════════════════════════════════════════════════════════════════════


class G001_BareExcept(ASTRule):
    """Bare except clause catches every exception; specify the type."""

    code = "G001"
    severity = "warning"
    handles = (ast.ExceptHandler,)

    def check(self, node: ast.ExceptHandler, ctx: RuleContext):  # type: ignore[override]
        if node.type is None:
            yield node, (
                "Bare except clause catches all exceptions; specify the exception type"
            )


class G002_EmptyExcept(ASTRule):
    """Empty except block silently swallows exceptions."""

    code = "G002"
    severity = "warning"
    handles = (ast.ExceptHandler,)

    def check(self, node: ast.ExceptHandler, ctx: RuleContext):  # type: ignore[override]
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            yield node, (
                "Empty except block silently swallows exceptions; "
                "add error handling or a comment"
            )


class G003_SingletonComparison(ASTRule):
    """Use 'is'/'is not' when comparing against None, True, or False."""

    code = "G003"
    severity = "warning"
    handles = (ast.Compare,)

    @staticmethod
    def _message(op: ast.cmpop, val: Any) -> str | None:
        if val is not None and val is not True and val is not False:
            return None
        name = repr(val)
        if isinstance(op, ast.Eq):
            return f"Use 'is {name}' instead of '== {name}'"
        if isinstance(op, ast.NotEq):
            return f"Use 'is not {name}' instead of '!= {name}'"
        return None

    def check(self, node: ast.Compare, ctx: RuleContext):  # type: ignore[override]
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(comparator, ast.Constant):
                if msg := self._message(op, comparator.value):
                    yield node, msg
        # Also catch the reversed form: None == x, True != x, etc.
        if isinstance(node.left, ast.Constant) and node.ops:
            if msg := self._message(node.ops[0], node.left.value):
                yield node, msg


class G004_MutableDefault(ASTRule):
    """Mutable default argument; use None and initialise inside the function."""

    code = "G004"
    severity = "warning"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        all_defaults = node.args.defaults + [
            d for d in node.args.kw_defaults if d is not None
        ]
        for default in all_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                yield node, (
                    f"Mutable default argument in '{node.name}'; "
                    "use None and initialise inside the function"
                )
                return  # one warning per function is enough


class G005_StarImport(ASTRule):
    """Star import pollutes the namespace; import names explicitly."""

    code = "G005"
    severity = "warning"
    handles = (ast.ImportFrom,)

    def check(self, node: ast.ImportFrom, ctx: RuleContext):  # type: ignore[override]
        for alias in node.names:
            if alias.name == "*":
                yield node, (
                    f"Star import 'from {node.module} import *' "
                    "pollutes the namespace; import names explicitly"
                )


class G006_MultipleImports(ASTRule):
    """Multiple modules on one import line; use separate statements."""

    code = "G006"
    severity = "info"
    handles = (ast.Import,)

    def check(self, node: ast.Import, ctx: RuleContext):  # type: ignore[override]
        if len(node.names) > 1:
            yield node, (
                "Multiple imports on one line; "
                "use a separate import statement for each module"
            )


class G007_LineTooLong(SourceRule):
    """Line exceeds the maximum allowed length."""

    code = "G007"
    severity = "info"
    max_length: int = 88

    def check_source(self, source: str):  # type: ignore[override]
        for lineno, line in enumerate(source.splitlines(), start=1):
            length = len(line.rstrip("\r\n"))
            if length > self.max_length:
                yield lineno, self.max_length + 1, (
                    f"Line too long ({length} > {self.max_length} characters)"
                )


class G008_PrintInDeviceMethod(ASTRule):
    """print() in a device class method; use Tango stream methods instead."""

    code = "G008"
    severity = "info"
    handles = (ast.FunctionDef,)

    def check(self, node: ast.FunctionDef, ctx: RuleContext):  # type: ignore[override]
        if not ctx.in_device_class:
            return
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "print"
            ):
                yield child, (
                    f"print() in device method '{node.name}'; "
                    "use Tango stream methods "
                    "(self.debug_stream, self.info_stream, etc.) instead"
                )
