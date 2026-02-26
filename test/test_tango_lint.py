#!/usr/bin/env python3
"""
lint_demo_device.py — pytangolint demonstration device.

Run:
    python3 pytangolint.py lint_demo_device.py
    python3 pytangolint.py --list-rules

Purpose
-------
This file is **intentionally full of issues** and is divided into three
parts:

 Valid Tango syntax — intentionally NOT flagged by the linter
             Patterns that ruff / pylint / mypy / pylance normally complain
             about but that are perfectly valid in a Tango device server.
             pytangolint stays silent on all of these on purpose.

 Tango-specific issues — caught by T-codes
             Issues only meaningful in a Tango context; a general-purpose
             linter would not catch these at all.

 General Python issues — caught by G-codes
             Issues that ruff / pylint / pylance / mypy would also flag.
             The G-rules duplicate the most important subset so that
             pytangolint is useful without running a second tool.

"""

# ── Imports ───────────────────────────────────────────────────────────────────

# G006 ruff E401 / pylint C0413: two modules on one import line
import os, sys  # noqa (intentional – demonstrates G006)

# G005 ruff F403 / pylint W0401: star import hides individual names and
#          makes it impossible to tell where symbols come from
from tango import *  # noqa (intentional – demonstrates G005)


# Specific imports used by the rest of the file
from tango import DevState
from tango.server import Device, attribute, command, device_property


# 
# Valid Tango syntax that normal linters flag; 
# pytangolint ignores these patterns
# 

class GoodDevice(Device):
    """A well-formed Tango device that demonstrates false-positive avoidance."""

    # Class level attribute descriptor
    # The name 'attribute' is imported from tango.server, then immediately
    # reused as a class-variable name.  This is *required* by the Tango
    # descriptor protocol.
    #
    #   ruff  A003  – "Class variable 'board_temperature' shadows a builtin"
    #                  (ruff groups 'attribute' with builtin-like names)
    #   pylint W0621 – "Redefining name 'attribute' from outer scope"
    #   mypy         – may flag the type of the descriptor as unexpected
    #
    # pytangolint: standard Tango class-variable pattern.
    board_temperature: float = attribute(  # type: ignore[assignment]
        dtype=float,
        description="Board temperature in degrees Celsius",
        unit="°C",
    )

    # PascalCase device_property names
    # Tango convention requires PascalCase for device_property names (T011).
    # This clashes with the Python snake_case naming convention.
    #
    #   pylint C0103 – "Attribute name 'Host' doesn't conform to snake_case"
    #   ruff  N815  – "Class variable 'Host' in class scope should be lowercase"
    #
    # pytangolint: PascalCase is the *correct* Tango convention so no warnings
    Host: str = device_property(dtype=str, mandatory=True)
    Port: int = device_property(dtype=int, default_value=8080)

    #  __init__ override
    # Shouldn't override init, use init_device instead
    #
    # 
    def __init__(self, *args, **kwargs) -> None:
        """Stub __init__; Tango devices initialise in init_device()."""
        super().__init__(*args, **kwargs)
        self._health_state: str  # annotation-only — mypy/pylance flag this
        self._version: str       # same

    # Inherited Tango base-class methods
    # Methods like set_state(), debug_stream(), info_stream() are inherited
    # from the Tango Device base class.  Without stubs they confuse analysers.
    #
    # Mypy would complain something like : "Cannot access attribute 'set_state' for class 'GoodDevice'"
    # pylance complains: "Attribute 'debug_stream' is unknown"
    #
    # pytangolint: no warning — these are valid inherited Tango methods.
    def init_device(self) -> None:
        """Initialise the device."""
        super().init_device()
        self._health_state = "UNKNOWN"
        self._version = "1.0.0"
        self.set_state(DevState.ON)       # pylance/mypy would warn: unknown attribute
        self.debug_stream("Device ready") # pylance/mypywould warn: unknown attribute

    #  PascalCase command method names
    # Tango commands use PascalCase by convention, contradicting PEP 8.
    #
    #   pylint C0103 – "Method name 'TurnOn' doesn't conform to snake_case"
    #   ruff  N802  – "Function name 'TurnOn' should be lowercase"
    #
    # pytangolint: PascalCase is the Tango command convention.
    @command
    def TurnOn(self) -> None:
        """Turn the device on."""
        self.set_state(DevState.ON)
        self.info_stream("Turned on") # pylance/mypy: unknown attribute

    # @attribute read method
    # The @attribute decorator transforms a method into a Tango attribute.
    # Other linters may flag the "unusual" decorated return pattern.
    #
    #   pylint R1711 – "Useless return at end of function or method"
    #                   (pylint does not understand the @attribute intercept)
    #   mypy         – return-type mismatch if the decorator is untyped
    #
    # pytangolint: ✓ no warning — all required fields are present and correct.
    @attribute(dtype=float, description="Board temperature", unit="°C")
    def temperature(self) -> float:
        """Read the current board temperature."""
        return 42.0


# 
# Section B — Tango-specific issues - this produces T-codes
# 
# A general-purpose linter (ruff, pylint, mypy, pylance) would NOT catch
# any of the issues below — they are only meaningful in a Tango context.


class badDevice(Device):  # T001: class name must start with uppercase
    """Device demonstrating Tango-specific rule violations."""

    # T011  device_property name must be PascalCase
    host: str = device_property(dtype=str, mandatory=True)

    # T020  @attribute method must have a docstring
    # T021  @attribute method must have a return-type annotation
    # T023  @attribute must have a 'description' parameter
    # T024  @attribute may need a 'unit' parameter
    # T025  @attribute body has >1 statement but no set_validity() call
    @attribute(dtype=float)
    def voltage(self):          # missing return type → T021
        raw = 3.3               # two statements in body → T025 fires
        return raw              # no docstring, no description, no unit

    # T022 'name' config key differs from the method name
    @attribute(
        dtype=str,
        name="VoltageName",     # T022: VoltageName != voltage_label
        description="Voltage channel label",
        unit="",
    )
    def voltage_label(self) -> str:
        """Read the voltage channel label."""
        return "V_MAIN"
    # T030  @command method must have a docstring
    # T031  @command name must be PascalCase
    @command
    def turn_off(self) -> None:  # no docstring T030; lowercase T031
        self.set_state(DevState.OFF)

# 
# General Python stuff - G-codes
# 
# Every issue below would be caught by ruff / pylint / pylance / mypy.
# The G-rules mean you only need pytangolint for Tango files.

class AnotherDevice(Device):
    """Device demonstrating general Python rule violations."""

    Port: int = device_property(dtype=int, default_value=9090)

    def __init__(self, *args, **kwargs) -> None:
        """Init."""
        super().__init__(*args, **kwargs)
        self._data: list[float]

    def init_device(self) -> None:
        """Initialise."""
        super().init_device()
        self._data = []

    # G004 ruff B006 / pylint W0102: mutable [] as a default argument
    #          is shared across all calls — mutations persist between calls.
    def configure(self, options: list[str] = []) -> None:  # G004
        """Configure the device."""
        pass

    # G008 ruff T201 / pylint C0325: print() inside a Tango device method.
    #          Use self.debug_stream() / self.info_stream() etc. instead.
    def status_check(self) -> None:
        """Check device status."""
        print("checking status")  # G008

    # G003  ruff E711 / pylint C0121: identity comparisons should use
    #          'is None' / 'is not None', not '==' / '!='
    # T025  also fires: multiple real statements with no set_validity() call
    @attribute(dtype=float, description="Output voltage", unit="V")
    def output_voltage(self) -> float:
        """Read output voltage."""
        value = self._read_hardware()
        if value == None:       # G003: use 'is None'
            return 0.0
        if value != None:       # G003: use 'is not None'
            return float(value)
        return 0.0

    def _read_hardware(self) -> float | None:
        """Read a value from hardware with intentionally poor error handling."""
        try:
            return 5.0
        except:                 # G001: ruff E722 / pylint W0702 
            pass                # G002: ruff B012 / pylint W0107 

    # G007  ruff E501 / pylint C0301: line longer than 88 characters
    LONG_DESCRIPTION: str = "This string is intentionally long to demonstrate G007, which flags lines exceeding 88 characters"  # noqa
