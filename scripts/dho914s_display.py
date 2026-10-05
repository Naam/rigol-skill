"""Typed cursor measurements and display controls for the Rigol DHO914S."""

from __future__ import annotations

import math
from dataclasses import dataclass
from dho800900 import require_no_errors


@dataclass(frozen=True)
class CursorReading:
    ax: float
    ay: float
    bx: float
    by: float
    delta_x: float
    delta_y: float
    inverse_delta_x: float | None = None


@dataclass(frozen=True)
class CursorState:
    mode: str
    indicator: bool
    manual_type: str | None = None
    manual_source: str | None = None
    manual_positions: tuple[float, float, float, float] | None = None
    manual: CursorReading | None = None
    track_sources: tuple[str, str] | None = None
    track_positions: tuple[float, float, float, float] | None = None
    track_mode: str | None = None
    track: CursorReading | None = None
    xy_positions: tuple[float, float, float, float] | None = None
    xy: CursorReading | None = None


@dataclass(frozen=True)
class ManualCursorSettings:
    cursor_type: str | None = None
    source: str | None = None
    ax: float | None = None
    ay: float | None = None
    bx: float | None = None
    by: float | None = None


@dataclass(frozen=True)
class TrackCursorSettings:
    source1: str | None = None
    source2: str | None = None
    ax: float | None = None
    ay: float | None = None
    bx: float | None = None
    by: float | None = None
    axis: str | None = None


@dataclass(frozen=True)
class XyCursorSettings:
    ax: float | None = None
    ay: float | None = None
    bx: float | None = None
    by: float | None = None


@dataclass(frozen=True)
class DisplayState:
    display_type: str
    persistence: str
    waveform_brightness: int
    grid: str
    grid_brightness: int
    rulers: bool
    color_grade: bool
    frozen: bool


@dataclass(frozen=True)
class DisplaySettings:
    display_type: str | None = None
    persistence: str | None = None
    waveform_brightness: int | None = None
    grid: str | None = None
    grid_brightness: int | None = None
    rulers: bool | None = None
    color_grade: bool | None = None
    frozen: bool | None = None


def _number(scope, command: str) -> float:
    result = float(scope.query(command))
    if not math.isfinite(result):
        raise RuntimeError(f"Instrument returned a non-finite value for {command}")
    return result


def _bool(scope, command: str) -> bool:
    value = scope.query(command).upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    raise RuntimeError(f"Instrument returned invalid boolean {value!r} for {command}")


def _source(value: str) -> str:
    normalized = value.upper().replace("CHANNEL", "CHAN")
    if normalized in {f"CHAN{i}" for i in range(1, 5)} | {f"MATH{i}" for i in range(1, 5)} | {"NONE"}:
        return normalized
    raise ValueError("cursor source must be CHAN1-CHAN4, MATH1-MATH4, or NONE")


def _position(value: float | None, name: str) -> float | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite number")
    return value


def _verify_text(scope, command: str, expected: str, normalize=str.upper) -> None:
    actual = normalize(scope.query(command))
    if actual != normalize(expected):
        raise RuntimeError(f"Instrument readback for {command} was {actual!r}; requested {expected!r}")


def _verify_number(scope, command: str, expected: float) -> None:
    actual = _number(scope, command)
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-15):
        raise RuntimeError(f"Instrument readback for {command} was {actual:g}; requested {expected:g}")


def _verify_bool(scope, command: str, expected: bool) -> None:
    actual = _bool(scope, command)
    if actual != expected:
        raise RuntimeError(f"Instrument readback for {command} was {actual}; requested {expected}")


def _apply_updates(scope, updates, readback):
    """Apply a small set transactionally; report if the device defeats rollback."""
    snapshots = [(setter.rsplit(" ", 1)[0], query, scope.query(query).strip())
                 for setter, query, _expected, _verify in updates]
    require_no_errors(scope)
    try:
        for setter, _query, _expected, _verify in updates:
            scope.write(setter)
        require_no_errors(scope)
        for _setter, query, expected, verify in updates:
            verify(scope, query, expected)
        return readback()
    except Exception as cause:
        try:
            for setter, _query, previous in reversed(snapshots):
                scope.write(f"{setter} {previous}")
            require_no_errors(scope)
            for _setter, query, previous in snapshots:
                if scope.query(query).strip() != previous:
                    raise RuntimeError(f"rollback readback did not restore {query}")
        except Exception as rollback_error:
            raise RuntimeError(
                f"Configuration failed ({cause}); rollback failed ({rollback_error}); "
                "instrument state may be partially applied"
            ) from cause
        raise


def configure_cursors(
    scope,
    *,
    mode: str | None = None,
    indicator: bool | None = None,
    manual: ManualCursorSettings | None = None,
    track: TrackCursorSettings | None = None,
    xy: XyCursorSettings | None = None,
) -> CursorState:
    """Apply validated cursor settings and return their readback."""
    mode_map = {"OFF": "OFF", "MAN": "MANual", "MANUAL": "MANual", "TRAC": "TRACk", "TRACK": "TRACk", "XY": "XY"}
    if mode is not None and mode.upper() not in mode_map:
        raise ValueError("cursor mode must be OFF, MANual, TRACk, or XY")
    if indicator is not None and type(indicator) is not bool:
        raise ValueError("cursor indicator must be a bool")
    if manual is not None:
        if manual.cursor_type is not None and manual.cursor_type.upper() not in {"TIME", "AMPL", "AMPLITUDE"}:
            raise ValueError("manual cursor type must be TIME or AMPLitude")
        if manual.source is not None:
            _source(manual.source)
        for name in ("ax", "ay", "bx", "by"):
            _position(getattr(manual, name), name)
    if track is not None:
        for source in (track.source1, track.source2):
            if source is not None:
                _source(source)
        if track.axis is not None and track.axis.upper() not in {"X", "Y"}:
            raise ValueError("track axis must be X or Y")
        for name in ("ax", "ay", "bx", "by"):
            _position(getattr(track, name), name)
    if xy is not None:
        for name in ("ax", "ay", "bx", "by"):
            _position(getattr(xy, name), name)
    if mode is not None and mode.upper() == "XY" or xy is not None:
        if scope.query(":TIMebase:MODE?").upper() != "XY":
            raise ValueError("XY cursors require the oscilloscope timebase mode to be XY")

    updates = []
    if mode is not None:
        expected = {"MANual": "MAN", "TRACk": "TRAC", "XY": "XY", "OFF": "OFF"}[mode_map[mode.upper()]]
        updates.append((f":CURSor:MODE {mode_map[mode.upper()]}", ":CURSor:MODE?", expected, _verify_text))
    if indicator is not None:
        updates.append((f":CURSor:MEASure:INDicator {int(indicator)}", ":CURSor:MEASure:INDicator?", indicator, _verify_bool))
    if manual is not None:
        if manual.cursor_type is not None:
            value = "AMPLitude" if manual.cursor_type.upper().startswith("AMPL") else "TIME"
            expected = "AMPL" if value == "AMPLitude" else value
            updates.append((f":CURSor:MANual:TYPE {value}", ":CURSor:MANual:TYPE?", expected, _verify_text))
        if manual.source is not None:
            value = _source(manual.source)
            updates.append((f":CURSor:MANual:SOURce {value}", ":CURSor:MANual:SOURce?", value, _verify_text))
        for field, command in (("ax", "CAX"), ("ay", "CAY"), ("bx", "CBX"), ("by", "CBY")):
            value = getattr(manual, field)
            if value is not None:
                updates.append((f":CURSor:MANual:{command} {value:.12g}", f":CURSor:MANual:{command}?", value, _verify_number))
    if track is not None:
        for field, command in (("source1", "SOURce1"), ("source2", "SOURce2")):
            value = getattr(track, field)
            if value is not None:
                value = _source(value)
                updates.append((f":CURSor:TRACk:{command} {value}", f":CURSor:TRACk:{command}?", value, _verify_text))
        for field, command in (("ax", "CAX"), ("ay", "CAY"), ("bx", "CBX"), ("by", "CBY")):
            value = getattr(track, field)
            if value is not None:
                updates.append((f":CURSor:TRACk:{command} {value:.12g}", f":CURSor:TRACk:{command}?", value, _verify_number))
        if track.axis is not None:
            value = track.axis.upper()
            updates.append((f":CURSor:TRACk:MODE {value}", ":CURSor:TRACk:MODE?", value, _verify_text))
    if xy is not None:
        for field, command in (("ax", "AX"), ("ay", "AY"), ("bx", "BX"), ("by", "BY")):
            value = getattr(xy, field)
            if value is not None:
                updates.append((f":CURSor:XY:{command} {value:.12g}", f":CURSor:XY:{command}?", value, _verify_number))

    scope.afg_off()
    if not updates:
        return read_cursors(scope)
    return _apply_updates(scope, updates, lambda: read_cursors(scope))


def _read_reading(scope, prefix: str, inverse: bool) -> CursorReading:
    base = f":CURSor:{prefix}:"
    return CursorReading(
        _number(scope, base + "AXValue?"), _number(scope, base + "AYValue?"),
        _number(scope, base + "BXValue?"), _number(scope, base + "BYValue?"),
        _number(scope, base + "XDELta?"), _number(scope, base + "YDELta?"),
        _number(scope, base + "IXDelta?") if inverse else None,
    )


def _positions(scope, prefix: str, fields: tuple[str, ...]) -> tuple[float, ...]:
    return tuple(_number(scope, f":CURSor:{prefix}:{field}?") for field in fields)


def read_cursors(scope) -> CursorState:
    """Read the active cursor mode, settings, marker values, and deltas."""
    modes = {"OFF": "OFF", "MAN": "MANual", "TRAC": "TRACk", "XY": "XY"}
    mode_token = scope.query(":CURSor:MODE?").upper()
    if mode_token not in modes:
        raise RuntimeError(f"Instrument returned unknown cursor mode {mode_token!r}")
    mode = modes[mode_token]
    indicator = _bool(scope, ":CURSor:MEASure:INDicator?")
    state = CursorState(mode=mode, indicator=indicator)
    if mode == "MANual":
        ctype = scope.query(":CURSor:MANual:TYPE?").upper()
        source = _source(scope.query(":CURSor:MANual:SOURce?"))
        positions = _positions(scope, "MANual", ("CAX", "CAY", "CBX", "CBY"))
        reading = _read_reading(scope, "MANual", True)
        state = CursorState(mode, indicator, manual_type={"AMPL": "AMPLitude"}.get(ctype, ctype), manual_source=source,
                            manual_positions=positions, manual=reading)
    elif mode == "TRACk":
        source1 = _source(scope.query(":CURSor:TRACk:SOURce1?"))
        source2 = _source(scope.query(":CURSor:TRACk:SOURce2?"))
        positions = _positions(scope, "TRACk", ("CAX", "CAY", "CBX", "CBY"))
        axis = scope.query(":CURSor:TRACk:MODE?").upper()
        if axis not in {"X", "Y"}:
            raise RuntimeError(f"Instrument returned invalid track axis {axis!r}")
        state = CursorState(mode, indicator, track_sources=(source1, source2), track_positions=positions,
                            track_mode=axis, track=_read_reading(scope, "TRACk", True))
    elif mode == "XY":
        positions = _positions(scope, "XY", ("AX", "AY", "BX", "BY"))
        state = CursorState(mode, indicator, xy_positions=positions, xy=_read_reading(scope, "XY", False))
    require_no_errors(scope)
    return state


def read_display(scope) -> DisplayState:
    """Read display configuration in useful Python types."""
    state = DisplayState(
        display_type=scope.query(":DISPlay:TYPE?").upper(),
        persistence=scope.query(":DISPlay:GRADing:TIME?").upper(),
        waveform_brightness=int(scope.query(":DISPlay:WBRightness?")),
        grid=scope.query(":DISPlay:GRID?").upper(),
        grid_brightness=int(scope.query(":DISPlay:GBRightness?")),
        rulers=_bool(scope, ":DISPlay:RULers?"),
        color_grade=_bool(scope, ":DISPlay:COLor?"),
        frozen=_bool(scope, ":DISPlay:WHOLd?"),
    )
    if state.display_type not in {"VECT", "VECTORS"} or state.grid not in {"FULL", "HALF", "NONE"}:
        raise RuntimeError("Instrument returned an unsupported display mode")
    if state.persistence not in {"MIN", "0.1", "0.2", "0.5", "1", "2", "5", "10", "INF", "INFINITE"}:
        raise RuntimeError(f"Instrument returned unsupported persistence {state.persistence!r}")
    if not 1 <= state.waveform_brightness <= 100 or not 0 <= state.grid_brightness <= 100:
        raise RuntimeError("Instrument returned brightness outside the documented range")
    require_no_errors(scope)
    return state


def configure_display(scope, settings: DisplaySettings) -> DisplayState:
    """Set supported display controls; clear and screenshot are separate actions."""
    display_type = None if settings.display_type is None else settings.display_type.upper()
    if display_type is not None and display_type not in {"VECT", "VECTORS"}:
        raise ValueError("display type must be VECTors")
    persistence = None if settings.persistence is None else settings.persistence.upper()
    valid_persistence = {"MIN", "0.1", "0.2", "0.5", "1", "2", "5", "10", "INFINITE", "INF"}
    if persistence is not None and persistence not in valid_persistence:
        raise ValueError("persistence must be MIN, 0.1, 0.2, 0.5, 1, 2, 5, 10, or INFinite")
    grid = None if settings.grid is None else settings.grid.upper()
    if grid is not None and grid not in {"FULL", "HALF", "NONE"}:
        raise ValueError("grid must be FULL, HALF, or NONE")
    if settings.waveform_brightness is not None and (type(settings.waveform_brightness) is not int or not 1 <= settings.waveform_brightness <= 100):
        raise ValueError("waveform brightness must be an integer from 1 to 100")
    if settings.grid_brightness is not None and (type(settings.grid_brightness) is not int or not 0 <= settings.grid_brightness <= 100):
        raise ValueError("grid brightness must be an integer from 0 to 100")
    for name in ("rulers", "color_grade", "frozen"):
        value = getattr(settings, name)
        if value is not None and type(value) is not bool:
            raise ValueError(f"{name} must be a bool")
    updates = []
    if display_type is not None:
        updates.append((":DISPlay:TYPE VECTors", ":DISPlay:TYPE?", "VECT", _verify_text))
    if persistence is not None:
        value = {"INFINITE": "INFinite", "INF": "INFinite"}.get(persistence, persistence)
        expected = "INF" if persistence in {"INFINITE", "INF"} else persistence
        updates.append((f":DISPlay:GRADing:TIME {value}", ":DISPlay:GRADing:TIME?", expected, _verify_text))
    for command, query, value in (
        ("WBRightness", "WBRightness?", settings.waveform_brightness),
        ("GRID", "GRID?", grid),
        ("GBRightness", "GBRightness?", settings.grid_brightness),
        ("RULers", "RULers?", settings.rulers),
        ("COLor", "COLor?", settings.color_grade),
        ("WHOLd", "WHOLd?", settings.frozen),
    ):
        if value is not None:
            verifier = _verify_bool if type(value) is bool else _verify_number if isinstance(value, int) else _verify_text
            expected = float(value) if isinstance(value, int) and not isinstance(value, bool) else value
            updates.append((f":DISPlay:{command} {int(value) if isinstance(value, bool) else value}",
                            f":DISPlay:{query}", expected, verifier))
    scope.afg_off()
    if not updates:
        return read_display(scope)
    return _apply_updates(scope, updates, lambda: read_display(scope))


def clear_display(scope) -> None:
    """Clear the displayed waveforms."""
    scope.afg_off()
    scope.write(":DISPlay:CLEar")
    require_no_errors(scope)


def screenshot(scope, image_type: str | None = None) -> bytes:
    """Read a TMC binary screenshot as BMP, PNG, or JPG bytes."""
    kind = "BMP" if image_type is None else image_type.upper()
    if kind not in {"BMP", "PNG", "JPG"}:
        raise ValueError("screenshot format must be BMP, PNG, or JPG")
    payload = scope.instrument.query_binary_values(
        ":DISPlay:DATA?" if image_type is None else f":DISPlay:DATA? {kind}", datatype="B", container=bytes,
        header_fmt="ieee", expect_termination=True,
    )
    require_no_errors(scope)
    return payload
