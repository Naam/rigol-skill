"""Typed analog-channel settings for a DHO914S.

Command ranges follow section 3.6 of the DHO800/DHO900 Programming Guide,
PGA39106-1110 (April 2025).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from dho800900_models import profile_for


PROBE_RATIOS = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2,
                0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000,
                2000, 5000, 10000, 20000, 50000)
UNITS = {"VOLT": "VOLTage", "WATT": "WATT", "AMP": "AMPere", "UNKN": "UNKNown"}
COMMANDS = {
    "bandwidth": "BWLimit", "coupling": "COUPling", "display": "DISPlay",
    "inverted": "INVert", "offset_v": "OFFSet", "time_calibration_s": "TCALibrate",
    "scale_v_div": "SCALe", "probe_ratio": "PROBe", "label_visible": "LABel:SHOW",
    "label": "LABel:CONTent", "units": "UNITs", "vernier": "VERNier",
    "position_v": "POSition",
}
BOOL_FIELDS = {"display", "inverted", "label_visible", "vernier"}
NUMERIC_FIELDS = {"offset_v", "time_calibration_s", "scale_v_div", "probe_ratio", "position_v"}


@dataclass(frozen=True)
class ChannelState:
    number: int
    bandwidth: str
    coupling: str
    display: bool
    inverted: bool
    offset_v: float
    time_calibration_s: float
    scale_v_div: float
    probe_ratio: float
    label_visible: bool
    label: str
    units: str
    vernier: bool
    position_v: float


@dataclass(frozen=True)
class ChannelChanges:
    bandwidth: str | None = None
    coupling: str | None = None
    display: bool | None = None
    inverted: bool | None = None
    offset_v: float | None = None
    time_calibration_s: float | None = None
    scale_v_div: float | None = None
    probe_ratio: float | None = None
    label_visible: bool | None = None
    label: str | None = None
    units: str | None = None
    vernier: bool | None = None
    position_v: float | None = None


def _prefix(number: int, scope=None) -> str:
    profile_for(scope).analog_channel(number)
    return f":CHANnel{number}"


def _errors(scope) -> None:
    errors = scope.errors()
    if len(errors) != 1 or not errors[0].lstrip("+").startswith("0,"):
        raise RuntimeError(f"instrument errors: {errors}")


def _boolean(value: str) -> bool:
    if value.upper() in {"1", "ON"}:
        return True
    if value.upper() in {"0", "OFF"}:
        return False
    raise RuntimeError(f"unexpected boolean readback: {value}")


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return float(value)


def _offset_limit(scale: float) -> float:
    if scale < 0.0005:
        return 0.5
    if scale <= 0.065:
        return 1
    if scale <= 0.260:
        return 8
    if scale <= 2.65:
        return 20
    return 100


def read_channel(scope, number: int) -> ChannelState:
    """Read every documented channel setting into physical units."""
    prefix = _prefix(number, scope)
    raw = {name: scope.query(f"{prefix}:{command}?").strip()
           for name, command in COMMANDS.items()}
    _errors(scope)
    values = {name: (_boolean(value) if name in BOOL_FIELDS else
                     float(value) if name in NUMERIC_FIELDS else
                     value[1:-1].replace('""', '"') if name == "label"
                     and len(value) >= 2 and value[0] == value[-1] == '"' else
                     value.strip('"'))
              for name, value in raw.items()}
    unit = values["units"].upper()
    if unit not in UNITS:
        raise RuntimeError(f"unexpected channel unit: {unit}")
    values["units"] = UNITS[unit]
    return ChannelState(number, **values)


def _encode(changes: ChannelChanges, previous: ChannelState) -> dict[str, str]:
    requested = {field.name: getattr(changes, field.name) for field in fields(changes)
                 if getattr(changes, field.name) is not None}
    if not requested:
        raise ValueError("no channel changes requested")
    for name in BOOL_FIELDS & requested.keys():
        if type(requested[name]) is not bool:
            raise ValueError(f"{name} must be bool")
    for name in NUMERIC_FIELDS & requested.keys():
        _finite(requested[name], name)
    if "bandwidth" in requested and requested["bandwidth"] not in {"20M", "OFF"}:
        raise ValueError("bandwidth must be 20M or OFF")
    if "coupling" in requested and requested["coupling"] not in {"AC", "DC", "GND"}:
        raise ValueError("coupling must be AC, DC, or GND")
    if "units" in requested:
        aliases = {"VOLT": "VOLTage", "VOLTage": "VOLTage", "AMP": "AMPere",
                   "AMPere": "AMPere", "WATT": "WATT", "UNKN": "UNKNown",
                   "UNKNown": "UNKNown"}
        if requested["units"] not in aliases:
            raise ValueError("units must be VOLTage, AMPere, WATT, or UNKNown")
        requested["units"] = aliases[requested["units"]]
    if "label" in requested:
        label = requested["label"]
        if not isinstance(label, str) or not label or any(ord(c) < 32 or ord(c) > 126 or c == ";" for c in label):
            raise ValueError("label must be printable ASCII without SCPI separators")
    probe = requested.get("probe_ratio", previous.probe_ratio)
    if probe not in PROBE_RATIOS:
        raise ValueError("unsupported probe ratio")
    scale = requested.get("scale_v_div", previous.scale_v_div)
    if "scale_v_div" in requested and not 0.0002 * probe <= scale <= 10 * probe:
        raise ValueError("scale outside probe-dependent DHO914S range")
    probe_changes_scale = "probe_ratio" in requested and "scale_v_div" not in requested
    if probe_changes_scale:
        if "offset_v" in requested or "position_v" in requested:
            raise ValueError("set scale explicitly when changing probe and offset or position")
    else:
        limit = _offset_limit(scale)
        for name in ("offset_v", "position_v"):
            value = requested.get(name, getattr(previous, name))
            if abs(value) > limit:
                raise ValueError(f"{name} exceeds {limit:g} V at {scale:g} V/div")
    if "time_calibration_s" in requested and abs(requested["time_calibration_s"]) > 100e-9:
        raise ValueError("time calibration must be within +/-100 ns")
    return {name: ("ON" if value else "OFF") if name in BOOL_FIELDS else
            f"{value:.12g}" if name in NUMERIC_FIELDS else value
            for name, value in requested.items()}


def configure_channel(scope, number: int, changes: ChannelChanges) -> ChannelState:
    """Apply validated channel changes with AFG off and verified readback."""
    _prefix(number, scope)
    if not isinstance(changes, ChannelChanges):
        raise TypeError("changes must be ChannelChanges")
    previous = read_channel(scope, number)
    encoded = _encode(changes, previous)
    if "time_calibration_s" in encoded:
        timebase = float(scope.query(":TIMebase:MAIN:SCALe?"))
        if timebase > 10e-6:
            raise ValueError("time calibration requires timebase <= 10 us/div")
    prefix = _prefix(number, scope)
    scope.afg_off()
    if profile_for(scope).afg and _boolean(scope.query(":SOURce:OUTPut:STATe?")):
        raise RuntimeError("AFG did not confirm OFF")
    scope.write("*CLS")
    # Probe sets the scale range; scale sets the offset and position ranges.
    target_scale = changes.scale_v_div if changes.scale_v_div is not None else previous.scale_v_div
    prior_offsets = {name for name in ("offset_v", "position_v")
                     if name in encoded and abs(getattr(previous, name)) > _offset_limit(target_scale)}
    for name in ("offset_v", "position_v"):
        if name in prior_offsets:
            scope.write(f"{prefix}:{COMMANDS[name]} {encoded[name]}")
    for name in ("probe_ratio", "scale_v_div", "offset_v", "position_v"):
        if name in prior_offsets:
            continue
        if name in encoded:
            scope.write(f"{prefix}:{COMMANDS[name]} {encoded[name]}")
    for name, value in encoded.items():
        if name not in {"probe_ratio", "scale_v_div", "offset_v", "position_v"}:
            if name == "label":
                value = '"' + value.replace('"', '""') + '"'
            scope.write(f"{prefix}:{COMMANDS[name]} {value}")
    _errors(scope)
    current = read_channel(scope, number)
    for name in encoded:
        wanted = getattr(changes, name)
        actual = getattr(current, name)
        if name in NUMERIC_FIELDS:
            match = math.isclose(actual, wanted, rel_tol=1e-4, abs_tol=1e-10)
        elif name == "units":
            match = actual == encoded[name]
        else:
            match = actual == wanted
        if not match:
            raise RuntimeError(f"{name} readback mismatch: {actual!r}")
    return current
