"""Typed DHO914S logic-analyzer and horizontal timebase controls.

Based on DHO800/DHO900 Programming Guide sections 3.13 and 3.26.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from dho800900_models import profile_for

from dho800900 import require_no_errors


def _bool(value: str) -> bool:
    value = value.strip().upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    raise RuntimeError(f"unexpected instrument boolean: {value!r}")


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _digital(channel: str) -> str:
    if not isinstance(channel, str) or not re.fullmatch(r"D(?:[0-9]|1[0-5])", channel.upper()):
        raise ValueError("digital channel must be D0 through D15")
    return channel.upper()


def _pod(pod: int) -> int:
    if type(pod) is not int or pod not in {1, 2}:
        raise ValueError("logic-analyzer pod must be 1 or 2")
    return pod


@dataclass(frozen=True)
class DigitalChannel:
    name: str
    enabled: bool
    label: str


@dataclass(frozen=True)
class LogicPod:
    index: int
    displayed: bool
    threshold_v: float


@dataclass(frozen=True)
class LogicAnalyzerSettings:
    enabled: bool
    active_channel: str
    auto_sort: str
    waveform_size: str
    channels: tuple[DigitalChannel, ...]
    pods: tuple[LogicPod, LogicPod]


class LogicAnalyzer:
    """State and validated operations for DHO900 digital channels D0-D15."""

    def __init__(self, scope):
        if profile_for(scope).digital_channels != 16:
            raise NotImplementedError(f"{profile_for(scope).model} has no digital channels")
        self.scope = scope

    def settings(self) -> LogicAnalyzerSettings:
        s = self.scope
        channels = tuple(
            DigitalChannel(name, _bool(s.query(f":LA:DIGital:ENABle? {name}")),
                           s.query(f":LA:DIGital:LABel? {name}"))
            for name in (f"D{i}" for i in range(16))
        )
        pods = tuple(
            LogicPod(i, _bool(s.query(f":LA:POD{i}:DISPlay?")), float(s.query(f":LA:POD{i}:THReshold?")))
            for i in (1, 2)
        )
        result = LogicAnalyzerSettings(
            _bool(s.query(":LA:ENABle?")), s.query(":LA:ACTive?").strip().upper(),
            s.query(":LA:AUTosort?").strip().upper(), s.query(":LA:SIZE?").strip().upper(),
            channels, pods,
        )
        require_no_errors(s)
        if result.active_channel != "NONE" and result.active_channel not in {c.name for c in channels}:
            raise RuntimeError(f"unexpected active digital channel: {result.active_channel!r}")
        if result.auto_sort not in {"D0D15", "D15D0"} or result.waveform_size not in {"SMAL", "MED", "LARG", "SMALL", "MEDIUM", "LARGE"}:
            raise RuntimeError(f"unexpected logic-analyzer settings: {result}")
        if any(not math.isfinite(p.threshold_v) or not -20 <= p.threshold_v <= 20 for p in pods):
            raise RuntimeError(f"invalid pod threshold readback: {pods}")
        return result

    def enable(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        self.scope.write(f":LA:ENABle {'ON' if enabled else 'OFF'}")
        require_no_errors(self.scope)
        actual = _bool(self.scope.query(":LA:ENABle?"))
        require_no_errors(self.scope)
        if actual != enabled:
            raise RuntimeError("logic-analyzer enable state did not read back as requested")
        return actual

    def set_active(self, channel: str | None) -> str:
        value = "NONE" if channel is None else _digital(channel)
        if value != "NONE" and not _bool(self.scope.query(f":LA:DIGital:ENABle? {value}")):
            require_no_errors(self.scope)
            raise ValueError(f"{value} must be enabled before it can be selected")
        self.scope.write(f":LA:ACTive {value}")
        require_no_errors(self.scope)
        actual = self.scope.query(":LA:ACTive?").strip().upper()
        require_no_errors(self.scope)
        if actual != value:
            raise RuntimeError(f"active channel read back as {actual}, expected {value}")
        return actual

    def set_auto_sort(self, order: str) -> str:
        order = order.upper() if isinstance(order, str) else ""
        if order not in {"D0D15", "D15D0"}:
            raise ValueError("auto-sort order must be D0D15 or D15D0")
        self.scope.write(f":LA:AUTosort {order}")
        require_no_errors(self.scope)
        actual = self.scope.query(":LA:AUTosort?").strip().upper()
        require_no_errors(self.scope)
        if actual != order:
            raise RuntimeError("logic-analyzer sort order did not read back as requested")
        return actual

    def set_channel_enabled(self, channel: str, enabled: bool) -> bool:
        channel = _digital(channel)
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        self.scope.write(f":LA:DIGital:ENABle {channel},{'ON' if enabled else 'OFF'}")
        require_no_errors(self.scope)
        actual = _bool(self.scope.query(f":LA:DIGital:ENABle? {channel}"))
        require_no_errors(self.scope)
        if actual != enabled:
            raise RuntimeError(f"{channel} enable state did not read back as requested")
        return actual

    def set_label(self, channel: str, label: str) -> str:
        channel = _digital(channel)
        if not isinstance(label, str) or not label or not label.isascii() or any(not c.isprintable() for c in label):
            raise ValueError("digital label must be nonempty printable ASCII")
        quoted = '"' + label.replace('"', '""') + '"'
        self.scope.write(f":LA:DIGital:LABel {channel},{quoted}")
        require_no_errors(self.scope)
        actual = self.scope.query(f":LA:DIGital:LABel? {channel}").strip()
        require_no_errors(self.scope)
        if actual != label:
            raise RuntimeError(f"{channel} label did not read back as requested")
        return actual

    def set_pod(self, pod: int, *, displayed: bool | None = None,
                threshold_v: float | None = None) -> LogicPod:
        pod = _pod(pod)
        if displayed is not None and type(displayed) is not bool:
            raise ValueError("displayed must be bool")
        threshold = None if threshold_v is None else _number(threshold_v, "threshold_v")
        if threshold is not None and not -20 <= threshold <= 20:
            raise ValueError("logic threshold must be within -20..20 V")
        s = self.scope
        if displayed is not None:
            s.write(f":LA:POD{pod}:DISPlay {'ON' if displayed else 'OFF'}")
        if threshold is not None:
            s.write(f":LA:POD{pod}:THReshold {threshold:.12g}")
        require_no_errors(s)
        actual = LogicPod(pod, _bool(s.query(f":LA:POD{pod}:DISPlay?")),
                          float(s.query(f":LA:POD{pod}:THReshold?")))
        require_no_errors(s)
        if displayed is not None and actual.displayed != displayed:
            raise RuntimeError("logic pod display state did not read back as requested")
        if threshold is not None and not math.isclose(actual.threshold_v, threshold, rel_tol=1e-7, abs_tol=1e-10):
            raise RuntimeError("logic pod threshold did not read back as requested")
        return actual

    def set_waveform_size(self, size: str) -> str:
        if not isinstance(size, str):
            raise ValueError("waveform size must be SMALL, MEDIUM, or LARGE")
        requested = size.upper()
        accepted = {"SMALL": "SMALl", "MEDIUM": "MEDium", "LARGE": "LARGe"}
        if requested not in accepted:
            raise ValueError("waveform size must be SMALL, MEDIUM, or LARGE")
        if requested == "LARGE":
            enabled_count = sum(_bool(self.scope.query(f":LA:DIGital:ENABle? D{i}")) for i in range(16))
            require_no_errors(self.scope)
            if enabled_count > 8:
                raise ValueError("LARGE waveform size requires no more than 8 enabled digital channels")
        self.scope.write(f":LA:SIZE {accepted[requested]}")
        require_no_errors(self.scope)
        actual = self.scope.query(":LA:SIZE?").strip().upper()
        require_no_errors(self.scope)
        if actual not in {requested, {"SMALL": "SMAL", "MEDIUM": "MED", "LARGE": "LARG"}[requested]}:
            raise RuntimeError(f"logic waveform size read back as {actual!r}")
        return actual

    def delete_group(self, group: int) -> None:
        if type(group) is not int or group not in {1, 2, 3, 4}:
            raise ValueError("digital channel group must be 1..4")
        self.scope.write(f":LA:DELete GROup{group}")
        require_no_errors(self.scope)


@dataclass(frozen=True)
class TimebaseSettings:
    delayed_enabled: bool
    delayed_offset_s: float
    delayed_scale_s_per_div: float
    main_offset_s: float
    main_scale_s_per_div: float
    mode: str
    horizontal_reference: str
    horizontal_position: int
    vernier: bool
    auto_roll: bool
    xy_enabled: bool
    xy_x: str
    xy_y: str
    xy_z: str
    xy_grid: str


_TIME = ":TIMebase:"


def _scale_125(value: float) -> bool:
    if value <= 0:
        return False
    mantissa = value / (10 ** math.floor(math.log10(value)))
    return any(math.isclose(mantissa, base, rel_tol=1e-8) for base in (1.0, 2.0, 5.0))


def _channel(value: str, *, none: bool = False) -> str:
    if none and isinstance(value, str) and value.upper() == "NONE":
        return "NONE"
    if not isinstance(value, str):
        raise ValueError("XY source must be CHAN1 through CHAN4")
    match = re.fullmatch(r"CHAN(?:NEL)?([1-4])", value.upper())
    if not match:
        raise ValueError("XY source must be CHAN1 through CHAN4" + (" or NONE" if none else ""))
    return f"CHANnel{match.group(1)}"


class Timebase:
    """Typed timebase readback and validated main, delay, XY, and run controls."""

    def __init__(self, scope):
        self.scope = scope

    def main_scale(self, value: float | None = None, *, form: str = "MAIN") -> float:
        """Read or set main scale using an optional-header form from the guide."""
        commands = {"BASE": ":TIMebase:SCALe", "MAIN": ":TIMebase:MAIN:SCALe"}
        command = commands.get(form.upper() if isinstance(form, str) else "")
        if command is None:
            raise ValueError("scale form must be BASE or MAIN")
        if value is not None:
            value = _number(value, "main scale")
            if value <= 0:
                raise ValueError("main scale must be positive")
            self.scope.write(f"{command} {value:.12g}")
            require_no_errors(self.scope)
        actual = float(self.scope.query(command + "?"))
        require_no_errors(self.scope)
        if not math.isfinite(actual) or actual <= 0:
            raise RuntimeError(f"invalid main scale readback: {actual}")
        if value is not None and not math.isclose(actual, value, rel_tol=1e-7):
            raise RuntimeError("main scale did not read back as requested")
        return actual

    def main_offset(self, value: float | None = None, *, form: str = "MAIN_OFFSET") -> float:
        """Read or set main offset using one of the guide's optional-header forms."""
        commands = {
            "BASE": ":TIMebase", "MAIN": ":TIMebase:MAIN",
            "OFFSET": ":TIMebase:OFFSet", "MAIN_OFFSET": ":TIMebase:MAIN:OFFSet",
        }
        command = commands.get(form.upper() if isinstance(form, str) else "")
        if command is None:
            raise ValueError("offset form must be BASE, MAIN, OFFSET, or MAIN_OFFSET")
        if value is not None:
            value = _number(value, "main offset")
            scale = float(self.scope.query(":TIMebase:MAIN:SCALe?"))
            current_offset = float(self.scope.query(":TIMebase:MAIN:OFFSet?"))
            status = self.scope.query(":TRIGger:STATus?").strip().upper()
            require_no_errors(self.scope)
            if status != "STOP":
                left = -5 * scale
                if scale <= 0.010:
                    right = 1.0
                elif scale < 10:
                    right = 100 * scale
                elif scale < 200:
                    right = 1000.0
                else:
                    right = 5 * scale
                if not left <= value <= right:
                    raise ValueError(f"main offset outside RUN-state range {left:g}..{right:g} s")
            if not math.isfinite(current_offset):
                raise RuntimeError("invalid main offset readback")
            self.scope.write(f"{command} {value:.12g}")
            require_no_errors(self.scope)
        actual = float(self.scope.query(command + "?"))
        require_no_errors(self.scope)
        if not math.isfinite(actual):
            raise RuntimeError(f"invalid main offset readback: {actual}")
        if value is not None and not math.isclose(actual, value, rel_tol=1e-7, abs_tol=1e-12):
            raise RuntimeError("main offset did not read back as requested")
        return actual

    def settings(self) -> TimebaseSettings:
        s = self.scope
        result = TimebaseSettings(
            _bool(s.query(_TIME + "DELay:ENABle?")), float(s.query(_TIME + "DELay:OFFSet?")),
            float(s.query(_TIME + "DELay:SCALe?")), float(s.query(_TIME + "MAIN:OFFSet?")),
            float(s.query(_TIME + "MAIN:SCALe?")), s.query(_TIME + "MODE?").strip().upper(),
            s.query(_TIME + "HREFerence:MODE?").strip().upper(),
            int(s.query(_TIME + "HREFerence:POSition?")), _bool(s.query(_TIME + "VERNier?")),
            _bool(s.query(_TIME + "ROLL?")), _bool(s.query(_TIME + "XY:ENABle?")),
            s.query(_TIME + "XY:X?").strip().upper(), s.query(_TIME + "XY:Y?").strip().upper(),
            s.query(_TIME + "XY:Z?").strip().upper(), s.query(_TIME + "XY:GRID?").strip().upper(),
        )
        require_no_errors(s)
        finite = (result.delayed_offset_s, result.delayed_scale_s_per_div,
                  result.main_offset_s, result.main_scale_s_per_div)
        if not all(math.isfinite(value) for value in finite) or result.main_scale_s_per_div <= 0 or result.delayed_scale_s_per_div <= 0:
            raise RuntimeError(f"invalid timebase numeric readback: {result}")
        if result.mode not in {"MAIN", "ROLL"} or result.horizontal_reference not in {"CENT", "CENTER", "LB", "RB", "TRIG", "USER"}:
            raise RuntimeError(f"unexpected timebase mode or reference: {result}")
        if not -500 <= result.horizontal_position <= 500:
            raise RuntimeError(f"invalid horizontal reference position: {result.horizontal_position}")
        return result

    def configure_main(self, *, scale_s_per_div: float | None = None,
                       offset_s: float | None = None, mode: str | None = None,
                       horizontal_reference: str | None = None,
                       horizontal_position: int | None = None,
                       vernier: bool | None = None, auto_roll: bool | None = None) -> TimebaseSettings:
        current = self.settings()
        scale = current.main_scale_s_per_div if scale_s_per_div is None else _number(scale_s_per_div, "main scale")
        if scale <= 0:
            raise ValueError("main scale must be positive")
        offset = None if offset_s is None else _number(offset_s, "main offset")
        if mode is not None:
            mode = mode.upper() if isinstance(mode, str) else ""
            if mode not in {"MAIN", "XY", "ROLL"}:
                raise ValueError("timebase mode must be MAIN, XY, or ROLL")
        if horizontal_reference is not None:
            horizontal_reference = horizontal_reference.upper() if isinstance(horizontal_reference, str) else ""
            if horizontal_reference not in {"CENTER", "CENT", "LB", "RB", "TRIG", "USER"}:
                raise ValueError("horizontal reference must be CENTER, LB, RB, TRIG, or USER")
        if horizontal_position is not None and (type(horizontal_position) is not int or not -500 <= horizontal_position <= 500):
            raise ValueError("horizontal position must be an integer from -500 through 500")
        for name, value in (("vernier", vernier), ("auto_roll", auto_roll)):
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} must be bool")
        status = self.scope.query(":TRIGger:STATus?").strip().upper() if offset is not None else ""
        if offset is not None and status != "STOP":
            main_left = -5 * scale
            if scale <= 0.010:
                main_right = 1.0
            elif scale < 10:
                main_right = 100 * scale
            elif scale < 200:
                main_right = 1000.0
            else:
                main_right = 5 * scale
            if not main_left <= offset <= main_right:
                raise ValueError(f"main offset outside RUN-state range {main_left:g}..{main_right:g} s")
        s = self.scope
        if scale_s_per_div is not None:
            s.write(f":TIMebase:MAIN:SCALe {scale:.12g}")
        if offset is not None:
            s.write(f":TIMebase:MAIN:OFFSet {offset:.12g}")
        if mode is not None:
            s.write(f":TIMebase:MODE {mode}")
        if horizontal_reference is not None:
            canonical = "CENTer" if horizontal_reference in {"CENTER", "CENT"} else horizontal_reference
            s.write(f":TIMebase:HREFerence:MODE {canonical}")
        if horizontal_position is not None:
            s.write(f":TIMebase:HREFerence:POSition {horizontal_position}")
        if vernier is not None:
            s.write(f":TIMebase:VERNier {'ON' if vernier else 'OFF'}")
        if auto_roll is not None:
            s.write(f":TIMebase:ROLL {int(auto_roll)}")
        require_no_errors(s)
        result = self.settings()
        if scale_s_per_div is not None and not math.isclose(result.main_scale_s_per_div, scale, rel_tol=1e-7):
            raise RuntimeError("main timebase scale did not read back as requested")
        if offset is not None and not math.isclose(result.main_offset_s, offset, rel_tol=1e-7, abs_tol=1e-12):
            raise RuntimeError("main timebase offset did not read back as requested")
        if horizontal_position is not None and result.horizontal_position != horizontal_position:
            raise RuntimeError("horizontal reference position did not read back as requested")
        if horizontal_reference is not None:
            expected_reference = "CENT" if horizontal_reference in {"CENTER", "CENT"} else horizontal_reference
            if result.horizontal_reference not in {expected_reference, horizontal_reference}:
                raise RuntimeError("horizontal reference did not read back as requested")
        if vernier is not None and result.vernier != vernier:
            raise RuntimeError("timebase vernier did not read back as requested")
        if auto_roll is not None and result.auto_roll != auto_roll:
            raise RuntimeError("automatic roll state did not read back as requested")
        if mode == "ROLL" and result.mode != "ROLL":
            raise RuntimeError("timebase mode did not read back as ROLL")
        if mode == "MAIN" and result.mode != "MAIN":
            raise RuntimeError("timebase mode did not read back as MAIN")
        if mode == "XY" and not result.xy_enabled:
            raise RuntimeError("XY mode did not read back enabled")
        return result

    def configure_delay(self, *, enabled: bool | None = None,
                        scale_s_per_div: float | None = None,
                        offset_s: float | None = None) -> TimebaseSettings:
        current = self.settings()
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        scale = current.delayed_scale_s_per_div if scale_s_per_div is None else _number(scale_s_per_div, "delayed scale")
        if scale_s_per_div is not None and (not _scale_125(scale) or scale > current.main_scale_s_per_div):
            raise ValueError("delayed scale must be a 1-2-5 step no greater than main scale")
        offset = None if offset_s is None else _number(offset_s, "delayed offset")
        if offset is not None:
            main_scale, main_offset = current.main_scale_s_per_div, current.main_offset_s
            left = 5 * main_scale - main_offset
            right = 5 * main_scale + main_offset
            half_delay_range = 5 * scale
            low, high = -(left - half_delay_range), right - half_delay_range
            if not low <= offset <= high:
                raise ValueError(f"delayed offset outside guide range {low:g}..{high:g} s")
        s = self.scope
        if scale_s_per_div is not None:
            s.write(f":TIMebase:DELay:SCALe {scale:.12g}")
        if offset is not None:
            s.write(f":TIMebase:DELay:OFFSet {offset:.12g}")
        if enabled is not None:
            s.write(f":TIMebase:DELay:ENABle {'ON' if enabled else 'OFF'}")
        require_no_errors(s)
        result = self.settings()
        if scale_s_per_div is not None and not math.isclose(result.delayed_scale_s_per_div, scale, rel_tol=1e-7):
            raise RuntimeError("delayed timebase scale did not read back as requested")
        if offset is not None and not math.isclose(result.delayed_offset_s, offset, rel_tol=1e-7, abs_tol=1e-12):
            raise RuntimeError("delayed timebase offset did not read back as requested")
        if enabled is not None and result.delayed_enabled != enabled:
            raise RuntimeError("delayed sweep enable state did not read back as requested")
        return result

    def configure_xy(self, *, enabled: bool | None = None, x: str | None = None,
                     y: str | None = None, z: str | None = None,
                     grid: str | None = None) -> TimebaseSettings:
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        if x is not None:
            x = _channel(x)
        if y is not None:
            y = _channel(y)
        if z is not None:
            z = _channel(z, none=True)
        if grid is not None:
            grid = grid.upper() if isinstance(grid, str) else ""
            if grid not in {"FULL", "HALF", "NONE"}:
                raise ValueError("XY grid must be FULL, HALF, or NONE")
        s = self.scope
        if x is not None:
            s.write(f":TIMebase:XY:X {x}")
        if y is not None:
            s.write(f":TIMebase:XY:Y {y}")
        if z is not None:
            s.write(f":TIMebase:XY:Z {z}")
        if grid is not None:
            s.write(f":TIMebase:XY:GRID {grid}")
        if enabled is not None:
            s.write(f":TIMebase:XY:ENABle {'ON' if enabled else 'OFF'}")
        require_no_errors(s)
        result = self.settings()
        for requested, actual, name in ((x, result.xy_x, "XY X source"), (y, result.xy_y, "XY Y source"),
                                        (z, result.xy_z, "XY Z source"), (grid, result.xy_grid, "XY grid")):
            if requested is not None and actual not in {requested.upper(), requested.replace("CHANnel", "CHAN").upper()}:
                raise RuntimeError(f"{name} did not read back as requested")
        if enabled is not None and result.xy_enabled != enabled:
            raise RuntimeError("XY enable state did not read back as requested")
        return result

    def hotkey(self, action: str, *, confirm: bool = False) -> None:
        if confirm is not True:
            raise ValueError("timebase hotkey changes acquisition state; pass confirm=True")
        action = action.upper() if isinstance(action, str) else ""
        if action not in {"STOP", "RUN", "SINGLE"}:
            raise ValueError("hotkey action must be STOP, RUN, or SINGLE")
        self.scope.write(f":TIMebase:HOTKeys {'SINGle' if action == 'SINGLE' else action}")
        require_no_errors(self.scope)
