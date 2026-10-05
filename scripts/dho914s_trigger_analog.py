"""Typed analog-trigger controls for the Rigol DHO914S.

The module intentionally supports a bounded, restorable trigger subset. Every
SCPI command is fixed here; callers provide typed settings, not command text.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import TypeAlias

from dho800900_models import profile_for
from dho800900 import DHO800900 as Rigol, require_afg_off, require_no_errors


@dataclass(frozen=True)
class Edge:
    source: str = "CHAN1"
    slope: str = "POS"
    level_v: float = 0.0
    coupling: str | None = "DC"


@dataclass(frozen=True)
class Pulse:
    source: str = "CHAN1"
    polarity: str = "POS"
    when: str = "GRE"
    lower_width_s: float | None = 1e-6
    upper_width_s: float | None = 2e-6
    level_v: float = 0.0


@dataclass(frozen=True)
class Slope:
    source: str = "CHAN1"
    polarity: str = "POS"
    when: str = "GRE"
    lower_time_s: float | None = 1e-6
    upper_time_s: float | None = 2e-6
    window: str = "TA"
    upper_level_v: float = 0.0
    lower_level_v: float = 0.0


@dataclass(frozen=True)
class Video:
    source: str = "CHAN1"
    polarity: str = "POS"
    sync: str = "ALIN"
    line: int = 1
    standard: str = "NTSC"
    level_v: float = 0.0


@dataclass(frozen=True)
class Pattern:
    pattern: tuple[str, str, str, str] = ("X", "X", "X", "X")
    source: str = "CHAN1"
    levels: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class Duration:
    source: str = "CHAN1"
    pattern: tuple[str, str, str, str] = ("X", "X", "X", "X")
    when: str = "GRE"
    lower_time_s: float | None = 1e-6
    upper_time_s: float | None = 1e-6
    levels: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class Timeout:
    source: str = "CHAN1"
    slope: str = "POS"
    time_s: float = 1e-6
    level_v: float = 0.0


@dataclass(frozen=True)
class Runt:
    source: str = "CHAN1"
    polarity: str = "POS"
    when: str = "NONE"
    lower_width_s: float | None = None
    upper_width_s: float | None = None
    lower_level_v: float = -0.5
    upper_level_v: float = 0.5


@dataclass(frozen=True)
class Windows:
    source: str = "CHAN1"
    slope: str = "POS"
    position: str = "ENT"
    time_s: float = 1e-6
    lower_level_v: float = -0.5
    upper_level_v: float = 0.5


@dataclass(frozen=True)
class Delay:
    source_a: str = "CHAN1"
    slope_a: str = "POS"
    source_b: str = "CHAN2"
    slope_b: str = "POS"
    when: str = "GRE"
    lower_time_s: float | None = 1e-6
    upper_time_s: float | None = 2e-6
    level_a_v: float = 0.0
    level_b_v: float = 0.0


@dataclass(frozen=True)
class SetupHold:
    data_source: str = "CHAN2"
    clock_source: str = "CHAN1"
    slope: str = "POS"
    data_type: str = "H"
    condition: str = "SET"
    setup_time_s: float | None = 2e-6
    hold_time_s: float | None = None
    data_level_v: float = 0.0
    clock_level_v: float = 0.0


@dataclass(frozen=True)
class NthEdge:
    source: str = "CHAN1"
    slope: str = "POS"
    idle_time_s: float = 1e-6
    edge_count: int = 1
    level_v: float = 0.0


@dataclass(frozen=True)
class TriggerState:
    config: Edge | Pulse | Slope | Video | Pattern | Duration | Timeout | Runt | Windows | Delay | SetupHold | NthEdge
    sweep: str
    holdoff_s: float | None
    noise_reject: bool | None
    status: str
    position_s: float

    @property
    def mode(self) -> str:
        return type(self.config).__name__.upper()


TriggerConfig: TypeAlias = Edge | Pulse | Slope | Video | Pattern | Duration | Timeout | Runt | Windows | Delay | SetupHold | NthEdge

_SOURCE = re.compile(r"(?:CHAN(?:NEL)?([1-4])|D(1[0-5]|[0-9])|EXT)\Z", re.I)
_VIDEO_LINES = {
    "NTSC": 525, "PALS": 625, "480P": 525, "576P": 625,
    "720P60": 750, "720P50": 750, "720P30": 750, "720P25": 750,
    "720P24": 750, "1080P60": 1125, "1080P50": 1125,
    "1080P30": 1125, "1080P25": 1125, "1080P24": 1125,
    "1080I60": 1125, "1080I50": 1125,
}
_MODE_ABBREVIATIONS = {
    "EDGE": "EDGE", "PULS": "PULSE", "SLOP": "SLOPE", "VID": "VIDEO",
    "PATT": "PATTERN", "DUR": "DURATION", "TIM": "TIMEOUT", "RUNT": "RUNT",
    "WIND": "WINDOWS", "DEL": "DELAY", "SET": "SETUPHOLD", "NEDG": "NTHEDGE",
}
_MODE_TOKENS = {
    Edge: "EDGE", Pulse: "PULSe", Slope: "SLOPe", Video: "VIDeo",
    Pattern: "PATTern", Duration: "DURation", Timeout: "TIMeout", Runt: "RUNT",
    Windows: "WINDows", Delay: "DELay", SetupHold: "SHOLd", NthEdge: "NEDGe",
}
_DIGITAL_AND_ANALOG_SOURCES = tuple([f"CHAN{i}" for i in range(1, 5)] + [f"D{i}" for i in range(16)])


def _choice(value: str, allowed: set[str], label: str) -> str:
    if not isinstance(value, str) or value.upper() not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}")
    return value.upper()


def _source(value: str, *, digital: bool = True) -> tuple[str, int | None]:
    if not isinstance(value, str) or not (match := _SOURCE.fullmatch(value.upper())):
        raise ValueError("source must be CHAN1-CHAN4" + (" or D0-D15" if digital else ""))
    if match.group(1):
        return f"CHANnel{match.group(1)}", int(match.group(1))
    if match.group(2) and digital:
        return f"D{int(match.group(2))}", None
    raise ValueError("source is not supported for this DHO914S trigger mode")


def _source_token(value: str, *, digital: bool = True) -> str:
    canonical, _ = _source(value, digital=digital)
    return canonical


def _number(value: float, low: float, high: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}")


def _level_limit(scope: Rigol, channel: int | None) -> tuple[float, float]:
    if channel is None:
        return -20.0, 20.0
    prefix = f":CHANnel{channel}"
    scale = float(scope.query(f"{prefix}:SCALe?"))
    offset = float(scope.query(f"{prefix}:OFFSet?"))
    return -4.5 * scale - offset, 4.5 * scale - offset


def _validate_levels(scope: Rigol, levels: tuple[tuple[str, float], ...]) -> None:
    seen: set[str] = set()
    for source, value in levels:
        token, channel = _source(source)
        canonical = token.upper()
        if canonical in seen:
            raise ValueError(f"duplicate threshold for {source}")
        seen.add(canonical)
        _number(value, *_level_limit(scope, channel), f"{source} trigger level")


def _pattern(values: tuple[str, ...], allowed: set[str], *, edge_limit: bool = False) -> None:
    if not isinstance(values, tuple) or len(values) != 4:
        raise ValueError("pattern must contain exactly four channel states")
    for item in values:
        _choice(item, allowed, "pattern item")
    if edge_limit and sum(value.upper() in {"R", "F"} for value in values) > 1:
        raise ValueError("pattern allows at most one R or F edge item")


def _validate_time(value: float | None, low: float, high: float, name: str, *, required: bool) -> None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required for this condition")
        return
    _number(value, low, high, name)


def _validate(scope: Rigol, config: TriggerConfig) -> None:
    profile = profile_for(scope)
    for field in ("source", "source_a", "source_b", "data_source", "clock_source"):
        value = getattr(config, field, None)
        if value is not None:
            profile.source(value, digital=True, external=True)
    for source, _ in getattr(config, "levels", ()):
        profile.source(source, digital=True)
    if isinstance(config, Edge):
        _, channel = _source(config.source)
        _choice(config.slope, {"POS", "NEG", "RFAL"}, "edge slope")
        if channel is None:
            if config.coupling is not None:
                raise ValueError("edge coupling is only available for analog channels")
        else:
            if config.coupling is None:
                raise ValueError("edge coupling is required for analog channels")
            _choice({"LFR": "LFREJECT", "HFR": "HFREJECT"}.get(config.coupling.upper(), config.coupling), {"AC", "DC", "LFREJECT", "HFREJECT"}, "edge coupling")
        low, high = _level_limit(scope, channel)
        _number(config.level_v, low, high, "edge level")
    elif isinstance(config, Pulse):
        _, channel = _source(config.source)
        _choice(config.polarity, {"POS", "NEG"}, "pulse polarity")
        when = _choice(config.when, {"GRE", "LESS", "GLES"}, "pulse condition")
        if when in {"GRE", "GLES"}:
            if config.lower_width_s is None:
                raise ValueError("pulse lower width is required for GRE/GLES")
            _number(config.lower_width_s, 1e-9, 10.0, "pulse lower width")
        if when in {"LESS", "GLES"}:
            if config.upper_width_s is None:
                raise ValueError("pulse upper width is required for LESS/GLES")
            _number(config.upper_width_s, 1e-9, 10.0, "pulse upper width")
        if when == "GLES" and config.lower_width_s > config.upper_width_s:
            raise ValueError("pulse lower width must not exceed upper width")
        low, high = _level_limit(scope, channel)
        _number(config.level_v, low, high, "pulse level")
    elif isinstance(config, Slope):
        _, channel = _source(config.source, digital=False)
        _choice(config.polarity, {"POS", "NEG"}, "slope polarity")
        when = _choice(config.when, {"GRE", "LESS", "GLES"}, "slope condition")
        if when in {"GRE", "GLES"}:
            if config.lower_time_s is None:
                raise ValueError("slope lower time is required for GRE/GLES")
            _number(config.lower_time_s, 1e-9, 10.0, "slope lower time")
        if when in {"LESS", "GLES"}:
            if config.upper_time_s is None:
                raise ValueError("slope upper time is required for LESS/GLES")
            _number(config.upper_time_s, 1e-9, 10.0, "slope upper time")
        if when == "GLES" and config.lower_time_s > config.upper_time_s:
            raise ValueError("slope lower time must not exceed upper time")
        _choice(config.window, {"TA", "TB", "TAB"}, "slope window")
        low, high = _level_limit(scope, channel)
        _number(config.upper_level_v, low, high, "slope upper level")
        _number(config.lower_level_v, low, high, "slope lower level")
        if config.lower_level_v > config.upper_level_v:
            raise ValueError("slope lower level must not exceed upper level")
    elif isinstance(config, Video):
        _, channel = _source(config.source, digital=False)
        _choice(config.polarity, {"POS", "NEG"}, "video polarity")
        sync = _choice(config.sync, {"ODDF", "EVEN", "LINE", "ALIN"}, "video sync")
        standard = config.standard.upper()
        if standard == "PALSECAM":
            standard = "PALS"
        standard = _choice(standard, set(_VIDEO_LINES), "video standard")
        if type(config.line) is not int or not 1 <= config.line <= _VIDEO_LINES[standard]:
            raise ValueError(f"video line must be 1-{_VIDEO_LINES[standard]} for {standard}")
        if sync in {"ODDF", "EVEN"} and standard not in {"NTSC", "PALS", "1080I60", "1080I50"}:
            raise ValueError("odd/even field sync requires NTSC, PAL/SECAM, or 1080i")
        low, high = _level_limit(scope, channel)
        _number(config.level_v, low, high, "video level")
    elif isinstance(config, Pattern):
        _pattern(config.pattern, {"H", "L", "X", "R", "F"}, edge_limit=True)
        _source(config.source)
        _validate_levels(scope, config.levels)
    elif isinstance(config, Duration):
        _source(config.source)
        _pattern(config.pattern, {"H", "L", "X"})
        when = _choice(config.when, {"GRE", "LESS", "GLES", "UNGL"}, "duration condition")
        need_lower = when in {"GRE", "GLES", "UNGL"}
        need_upper = when in {"LESS", "GLES", "UNGL"}
        _validate_time(config.lower_time_s, 1e-9, 9.9, "duration lower time", required=need_lower)
        _validate_time(config.upper_time_s, 1.01e-9, 10.0, "duration upper time", required=need_upper)
        if need_lower and need_upper and config.lower_time_s > config.upper_time_s:
            raise ValueError("duration lower time must not exceed upper time")
        _validate_levels(scope, config.levels)
    elif isinstance(config, Timeout):
        token, channel = _source(config.source)
        _choice(config.slope, {"POS", "NEG", "RFAL"}, "timeout slope")
        _number(config.time_s, 1e-9, 10.0, "timeout time")
        _number(config.level_v, *_level_limit(scope, channel), "timeout level")
    elif isinstance(config, Runt):
        _, channel = _source(config.source, digital=False)
        when = _choice(config.when, {"NONE", "GRE", "LESS", "GLES"}, "runt condition")
        _choice(config.polarity, {"POS", "NEG"}, "runt polarity")
        need_lower = when in {"GRE", "GLES"}
        need_upper = when in {"LESS", "GLES"}
        _validate_time(config.lower_width_s, 1e-9, 9.9, "runt lower width", required=need_lower)
        _validate_time(config.upper_width_s, 1.01e-9, 10.0, "runt upper width", required=need_upper)
        if need_lower and need_upper and config.lower_width_s >= config.upper_width_s:
            raise ValueError("runt lower width must be less than upper width")
        low, high = _level_limit(scope, channel)
        _number(config.lower_level_v, low, high, "runt lower level")
        _number(config.upper_level_v, low, high, "runt upper level")
        if config.lower_level_v >= config.upper_level_v:
            raise ValueError("runt lower level must be below upper level")
    elif isinstance(config, Windows):
        _, channel = _source(config.source, digital=False)
        _choice(config.slope, {"POS", "NEG", "RFAL"}, "window slope")
        _choice(config.position, {"EXIT", "ENT", "TIME"}, "window position")
        _number(config.time_s, 1e-9, 10.0, "window time")
        low, high = _level_limit(scope, channel)
        _number(config.lower_level_v, low, high, "window lower level")
        _number(config.upper_level_v, low, high, "window upper level")
        if config.lower_level_v >= config.upper_level_v:
            raise ValueError("window lower level must be below upper level")
    elif isinstance(config, Delay):
        _, channel_a = _source(config.source_a)
        _, channel_b = _source(config.source_b)
        _choice(config.slope_a, {"POS", "NEG"}, "delay source A slope")
        _choice(config.slope_b, {"POS", "NEG"}, "delay source B slope")
        when = _choice(config.when, {"GRE", "LESS", "GLES", "GOUT"}, "delay condition")
        need_lower = when in {"GRE", "GLES", "GOUT"}
        need_upper = when in {"LESS", "GLES", "GOUT"}
        _validate_time(config.lower_time_s, 1e-9, 9.9, "delay lower time", required=need_lower)
        _validate_time(config.upper_time_s, 1.01e-9, 10.0, "delay upper time", required=need_upper)
        if when in {"GLES", "GOUT"} and config.lower_time_s >= config.upper_time_s:
            raise ValueError("delay lower time must be less than upper time")
        _number(config.level_a_v, *_level_limit(scope, channel_a), "delay source A level")
        _number(config.level_b_v, *_level_limit(scope, channel_b), "delay source B level")
    elif isinstance(config, SetupHold):
        _, data_channel = _source(config.data_source)
        _, clock_channel = _source(config.clock_source)
        _choice(config.slope, {"POS", "NEG"}, "setup/hold clock slope")
        _choice(config.data_type, {"H", "L"}, "setup/hold data type")
        condition = _choice(config.condition, {"SET", "HOLD", "SETH"}, "setup/hold condition")
        _validate_time(config.setup_time_s, 1e-9, 10.0, "setup time", required=condition in {"SET", "SETH"})
        _validate_time(config.hold_time_s, 1e-9, 10.0, "hold time", required=condition in {"HOLD", "SETH"})
        _number(config.data_level_v, *_level_limit(scope, data_channel), "data source level")
        _number(config.clock_level_v, *_level_limit(scope, clock_channel), "clock source level")
    elif isinstance(config, NthEdge):
        _, channel = _source(config.source)
        _choice(config.slope, {"POS", "NEG"}, "nth edge slope")
        _number(config.idle_time_s, 16e-9, 10.0, "nth edge idle time")
        if type(config.edge_count) is not int or not 1 <= config.edge_count <= 65535:
            raise ValueError("nth edge count must be an integer from 1 to 65535")
        _number(config.level_v, *_level_limit(scope, channel), "nth edge level")
    else:
        raise TypeError("unsupported DHO914S trigger configuration")


def _query_float(scope: Rigol, command: str) -> float:
    value = float(scope.query(command))
    if not math.isfinite(value):
        raise RuntimeError(f"instrument returned a non-finite value for {command}")
    return value


def _query_bool(scope: Rigol, command: str) -> bool:
    raw = scope.query(command).upper()
    if raw in {"1", "ON"}:
        return True
    if raw in {"0", "OFF"}:
        return False
    raise RuntimeError(f"instrument returned invalid boolean {raw!r} for {command}")


def _read_levels(scope: Rigol, command: str) -> tuple[tuple[str, float], ...]:
    values = []
    for source in _DIGITAL_AND_ANALOG_SOURCES:
        scpi_source = _source_token(source)
        values.append((source, _query_float(scope, f"{command}? {scpi_source}")))
    return tuple(values)


def _read_time(scope: Rigol, command: str, active: bool) -> float | None:
    return _query_float(scope, command) if active else None


def _primary_source(config: TriggerConfig) -> str | None:
    if isinstance(config, Delay):
        return config.source_a
    if isinstance(config, SetupHold):
        return config.data_source
    if isinstance(config, (Edge, Pulse, Pattern, Duration, Timeout, Runt, Windows, NthEdge)):
        return config.source
    return None


def _has_noise_reject(config: TriggerConfig) -> bool:
    source = _primary_source(config)
    return source is None or _source(source)[1] is not None


def _supports_holdoff(config: TriggerConfig) -> bool:
    return not isinstance(config, (Video, Timeout, SetupHold, NthEdge))


def read_trigger(scope: Rigol) -> TriggerState:
    """Read a fully restorable EDGE, PULSE, SLOPE, or VIDEO trigger state."""
    mode_raw = scope.query(":TRIGger:MODE?").upper()
    try:
        mode = _MODE_ABBREVIATIONS[mode_raw]
    except KeyError as exc:
        raise ValueError(f"trigger mode {mode_raw!r} is outside this module's restorable subset") from exc
    sweep = _choice(scope.query(":TRIGger:SWEep?"), {"AUTO", "NORM", "SING"}, "trigger sweep")
    holdoff = None if mode in {"VIDEO", "TIMEOUT", "SETUPHOLD", "NTHEDGE"} else _query_float(scope, ":TRIGger:HOLDoff?")
    if mode == "EDGE":
        source, channel = _source(scope.query(":TRIGger:EDGE:SOURce?"))
        coupling = scope.query(":TRIGger:COUPling?").upper() if channel is not None else None
        config: TriggerConfig = Edge(
            source=f"CHAN{channel}" if channel is not None else source,
            slope=scope.query(":TRIGger:EDGE:SLOPe?"),
            level_v=_query_float(scope, ":TRIGger:EDGE:LEVel?"),
            coupling={"LFR": "LFREJECT", "HFR": "HFREJECT"}.get(coupling, coupling) if coupling is not None else None,
        )
    elif mode == "PULSE":
        source, channel = _source(scope.query(":TRIGger:PULSe:SOURce?"))
        when = scope.query(":TRIGger:PULSe:WHEN?")
        config = Pulse(
            source=f"CHAN{channel}" if channel is not None else source,
            polarity=scope.query(":TRIGger:PULSe:POLarity?"), when=when,
            lower_width_s=_query_float(scope, ":TRIGger:PULSe:LWIDth?") if when.upper().startswith(("GRE", "GLES")) else None,
            upper_width_s=_query_float(scope, ":TRIGger:PULSe:UWIDth?") if when.upper().startswith(("LESS", "GLES")) else None,
            level_v=_query_float(scope, ":TRIGger:PULSe:LEVel?"),
        )
    elif mode == "SLOPE":
        source, channel = _source(scope.query(":TRIGger:SLOPe:SOURce?"))
        when = scope.query(":TRIGger:SLOPe:WHEN?")
        config = Slope(
            source=f"CHAN{channel}",
            polarity=scope.query(":TRIGger:SLOPe:POLarity?"), when=when,
            lower_time_s=_query_float(scope, ":TRIGger:SLOPe:TLOWer?") if when.upper().startswith(("GRE", "GLES")) else None,
            upper_time_s=_query_float(scope, ":TRIGger:SLOPe:TUPPer?") if when.upper().startswith(("LESS", "GLES")) else None,
            window=scope.query(":TRIGger:SLOPe:WINDow?"),
            upper_level_v=_query_float(scope, ":TRIGger:SLOPe:ALEVel?"),
            lower_level_v=_query_float(scope, ":TRIGger:SLOPe:BLEVel?"),
        )
    elif mode == "VIDEO":
        source, channel = _source(scope.query(":TRIGger:VIDeo:SOURce?"), digital=False)
        config = Video(
            source=f"CHAN{channel}",
            polarity=scope.query(":TRIGger:VIDeo:POLarity?"), sync=scope.query(":TRIGger:VIDeo:MODE?"),
            line=int(scope.query(":TRIGger:VIDeo:LINE?")),
            standard=scope.query(":TRIGger:VIDeo:STANdard?"),
            level_v=_query_float(scope, ":TRIGger:VIDeo:LEVel?"),
        )
    elif mode == "PATTERN":
        pattern = tuple(scope.query(":TRIGger:PATTern:PATTern?").upper().split(","))
        source, _ = _source(scope.query(":TRIGger:PATTern:SOURce?"))
        config = Pattern(pattern, source.replace("CHANnel", "CHAN"), _read_levels(scope, ":TRIGger:PATTern:LEVel"))
    elif mode == "DURATION":
        source, _ = _source(scope.query(":TRIGger:DURation:SOURce?"))
        when = scope.query(":TRIGger:DURation:WHEN?")
        config = Duration(
            source.replace("CHANnel", "CHAN"),
            tuple(scope.query(":TRIGger:DURation:TYPE?").upper().split(",")), when,
            _read_time(scope, ":TRIGger:DURation:TLOWer?", when.upper().startswith(("GRE", "GLES", "UNGL"))),
            _read_time(scope, ":TRIGger:DURation:TUPPer?", when.upper().startswith(("LESS", "GLES", "UNGL"))),
            _read_levels(scope, ":TRIGger:DURation:LEVel"),
        )
    elif mode == "TIMEOUT":
        source, _ = _source(scope.query(":TRIGger:TIMeout:SOURce?"))
        config = Timeout(source.replace("CHANnel", "CHAN"),
                         scope.query(":TRIGger:TIMeout:SLOPe?"),
                         _query_float(scope, ":TRIGger:TIMeout:TIME?"),
                         _query_float(scope, ":TRIGger:TIMeout:LEVel?"))
    elif mode == "RUNT":
        source, _ = _source(scope.query(":TRIGger:RUNT:SOURce?"), digital=False)
        when = scope.query(":TRIGger:RUNT:WHEN?")
        config = Runt(source.replace("CHANnel", "CHAN"),
                      scope.query(":TRIGger:RUNT:POLarity?"), when,
                      _read_time(scope, ":TRIGger:RUNT:WLOWer?", when.upper().startswith(("GRE", "GLES"))),
                      _read_time(scope, ":TRIGger:RUNT:WUPPer?", when.upper().startswith(("LESS", "GLES"))),
                      _query_float(scope, ":TRIGger:RUNT:BLEVel?"),
                      _query_float(scope, ":TRIGger:RUNT:ALEVel?"))
    elif mode == "WINDOWS":
        source, _ = _source(scope.query(":TRIGger:WINDows:SOURce?"), digital=False)
        config = Windows(source.replace("CHANnel", "CHAN"),
                         scope.query(":TRIGger:WINDows:SLOPe?"),
                         scope.query(":TRIGger:WINDows:POSition?"),
                         _query_float(scope, ":TRIGger:WINDows:TIME?"),
                         _query_float(scope, ":TRIGger:WINDows:BLEVel?"),
                         _query_float(scope, ":TRIGger:WINDows:ALEVel?"))
    elif mode == "DELAY":
        source_a, _ = _source(scope.query(":TRIGger:DELay:SA?"))
        source_b, _ = _source(scope.query(":TRIGger:DELay:SB?"))
        when = scope.query(":TRIGger:DELay:TYPE?")
        config = Delay(source_a.replace("CHANnel", "CHAN"), scope.query(":TRIGger:DELay:ASLop?"),
                       source_b.replace("CHANnel", "CHAN"), scope.query(":TRIGger:DELay:BSLop?"), when,
                       _read_time(scope, ":TRIGger:DELay:TLOWer?", when.upper().startswith(("GRE", "GLES", "GOUT"))),
                       _read_time(scope, ":TRIGger:DELay:TUPPer?", when.upper().startswith(("LESS", "GLES", "GOUT"))),
                       _query_float(scope, ":TRIGger:DELay:ALEVel?"), _query_float(scope, ":TRIGger:DELay:BLEVel?"))
    elif mode == "SETUPHOLD":
        data_source, data_channel = _source(scope.query(":TRIGger:SHOLd:DSRC?"))
        clock_source, clock_channel = _source(scope.query(":TRIGger:SHOLd:CSRC?"))
        condition = scope.query(":TRIGger:SHOLd:TYPE?")
        config = SetupHold(data_source.replace("CHANnel", "CHAN"), clock_source.replace("CHANnel", "CHAN"),
                           scope.query(":TRIGger:SHOLd:SLOPe?"), scope.query(":TRIGger:SHOLd:PATTern?"), condition,
                           _read_time(scope, ":TRIGger:SHOLd:STIMe?", condition.upper().startswith(("SET", "SETH"))),
                           _read_time(scope, ":TRIGger:SHOLd:HTIMe?", condition.upper().startswith(("HOLD", "SETH"))),
                           _query_float(scope, ":TRIGger:SHOLd:DLEVel?"),
                           _query_float(scope, ":TRIGger:SHOLd:CLEVel?"))
    else:
        source, _ = _source(scope.query(":TRIGger:NEDGe:SOURce?"))
        config = NthEdge(source.replace("CHANnel", "CHAN"), scope.query(":TRIGger:NEDGe:SLOPe?"),
                         _query_float(scope, ":TRIGger:NEDGe:IDLE?"),
                         int(scope.query(":TRIGger:NEDGe:EDGE?")),
                         _query_float(scope, ":TRIGger:NEDGe:LEVel?"))
    _validate(scope, config)
    noise_reject = _query_bool(scope, ":TRIGger:NREJect?") if _has_noise_reject(config) else None
    status = _choice(scope.query(":TRIGger:STATus?"), {"TD", "WAIT", "RUN", "AUTO", "STOP"}, "trigger status")
    position = _query_float(scope, ":TRIGger:POSition?")
    require_no_errors(scope)
    return TriggerState(config, sweep, holdoff, noise_reject, status, position)


def _set_config(scope: Rigol, config: TriggerConfig) -> None:
    scope.write(f":TRIGger:MODE {_MODE_TOKENS[type(config)]}")
    if isinstance(config, Edge):
        scope.write(f":TRIGger:EDGE:SOURce {_source_token(config.source)}")
        scope.write(f":TRIGger:EDGE:SLOPe {config.slope}")
        scope.write(f":TRIGger:EDGE:LEVel {config.level_v:.12g}")
        if config.coupling is not None:
            scope.write(f":TRIGger:COUPling {config.coupling}")
    elif isinstance(config, Pulse):
        scope.write(f":TRIGger:PULSe:SOURce {_source_token(config.source)}")
        scope.write(f":TRIGger:PULSe:POLarity {config.polarity}")
        scope.write(f":TRIGger:PULSe:WHEN {config.when}")
        if config.when in {"GRE", "GLES"}:
            scope.write(f":TRIGger:PULSe:LWIDth {config.lower_width_s:.12g}")
        if config.when in {"LESS", "GLES"}:
            scope.write(f":TRIGger:PULSe:UWIDth {config.upper_width_s:.12g}")
        scope.write(f":TRIGger:PULSe:LEVel {config.level_v:.12g}")
    elif isinstance(config, Slope):
        scope.write(f":TRIGger:SLOPe:SOURce {_source_token(config.source, digital=False)}")
        scope.write(f":TRIGger:SLOPe:POLarity {config.polarity}")
        scope.write(f":TRIGger:SLOPe:WHEN {config.when}")
        if config.when in {"GRE", "GLES"}:
            scope.write(f":TRIGger:SLOPe:TLOWer {config.lower_time_s:.12g}")
        if config.when in {"LESS", "GLES"}:
            scope.write(f":TRIGger:SLOPe:TUPPer {config.upper_time_s:.12g}")
        scope.write(f":TRIGger:SLOPe:WINDow {config.window}")
        scope.write(f":TRIGger:SLOPe:ALEVel {config.upper_level_v:.12g}")
        scope.write(f":TRIGger:SLOPe:BLEVel {config.lower_level_v:.12g}")
    elif isinstance(config, Video):
        scope.write(f":TRIGger:VIDeo:SOURce {_source_token(config.source, digital=False)}")
        scope.write(f":TRIGger:VIDeo:POLarity {config.polarity}")
        scope.write(f":TRIGger:VIDeo:STANdard {'PALSecam' if config.standard.upper() in {'PALS', 'PALSECAM'} else config.standard}")
        scope.write(f":TRIGger:VIDeo:MODE {config.sync}")
        scope.write(f":TRIGger:VIDeo:LINE {config.line}")
        scope.write(f":TRIGger:VIDeo:LEVel {config.level_v:.12g}")
    elif isinstance(config, Pattern):
        scope.write(":TRIGger:PATTern:PATTern " + ",".join(config.pattern))
        scope.write(f":TRIGger:PATTern:SOURce {_source_token(config.source)}")
        _write_levels(scope, ":TRIGger:PATTern:LEVel", config.levels)
    elif isinstance(config, Duration):
        scope.write(f":TRIGger:DURation:SOURce {_source_token(config.source)}")
        scope.write(":TRIGger:DURation:TYPE " + ",".join(config.pattern))
        scope.write(f":TRIGger:DURation:WHEN {config.when}")
        if config.lower_time_s is not None:
            scope.write(f":TRIGger:DURation:TLOWer {config.lower_time_s:.12g}")
        if config.upper_time_s is not None:
            scope.write(f":TRIGger:DURation:TUPPer {config.upper_time_s:.12g}")
        _write_levels(scope, ":TRIGger:DURation:LEVel", config.levels)
    elif isinstance(config, Timeout):
        scope.write(f":TRIGger:TIMeout:SOURce {_source_token(config.source)}")
        scope.write(f":TRIGger:TIMeout:SLOPe {config.slope}")
        scope.write(f":TRIGger:TIMeout:TIME {config.time_s:.12g}")
        scope.write(f":TRIGger:TIMeout:LEVel {config.level_v:.12g}")
    elif isinstance(config, Runt):
        scope.write(f":TRIGger:RUNT:SOURce {_source_token(config.source, digital=False)}")
        scope.write(f":TRIGger:RUNT:POLarity {config.polarity}")
        scope.write(f":TRIGger:RUNT:WHEN {config.when}")
        if config.lower_width_s is not None:
            scope.write(f":TRIGger:RUNT:WLOWer {config.lower_width_s:.12g}")
        if config.upper_width_s is not None:
            scope.write(f":TRIGger:RUNT:WUPPer {config.upper_width_s:.12g}")
        scope.write(f":TRIGger:RUNT:BLEVel {config.lower_level_v:.12g}")
        scope.write(f":TRIGger:RUNT:ALEVel {config.upper_level_v:.12g}")
    elif isinstance(config, Windows):
        scope.write(f":TRIGger:WINDows:SOURce {_source_token(config.source, digital=False)}")
        scope.write(f":TRIGger:WINDows:SLOPe {config.slope}")
        scope.write(f":TRIGger:WINDows:POSition {config.position}")
        scope.write(f":TRIGger:WINDows:TIME {config.time_s:.12g}")
        scope.write(f":TRIGger:WINDows:BLEVel {config.lower_level_v:.12g}")
        scope.write(f":TRIGger:WINDows:ALEVel {config.upper_level_v:.12g}")
    elif isinstance(config, Delay):
        scope.write(f":TRIGger:DELay:SA {_source_token(config.source_a)}")
        scope.write(f":TRIGger:DELay:ASLop {config.slope_a}")
        scope.write(f":TRIGger:DELay:SB {_source_token(config.source_b)}")
        scope.write(f":TRIGger:DELay:BSLop {config.slope_b}")
        scope.write(f":TRIGger:DELay:TYPE {config.when}")
        if config.lower_time_s is not None:
            scope.write(f":TRIGger:DELay:TLOWer {config.lower_time_s:.12g}")
        if config.upper_time_s is not None:
            scope.write(f":TRIGger:DELay:TUPPer {config.upper_time_s:.12g}")
        scope.write(f":TRIGger:DELay:ALEVel {config.level_a_v:.12g}")
        scope.write(f":TRIGger:DELay:BLEVel {config.level_b_v:.12g}")
    elif isinstance(config, SetupHold):
        scope.write(f":TRIGger:SHOLd:DSRC {_source_token(config.data_source)}")
        scope.write(f":TRIGger:SHOLd:CSRC {_source_token(config.clock_source)}")
        scope.write(f":TRIGger:SHOLd:SLOPe {config.slope}")
        scope.write(f":TRIGger:SHOLd:PATTern {config.data_type}")
        scope.write(f":TRIGger:SHOLd:TYPE {config.condition}")
        if config.setup_time_s is not None:
            scope.write(f":TRIGger:SHOLd:STIMe {config.setup_time_s:.12g}")
        if config.hold_time_s is not None:
            scope.write(f":TRIGger:SHOLd:HTIMe {config.hold_time_s:.12g}")
        scope.write(f":TRIGger:SHOLd:DLEVel {config.data_level_v:.12g}")
        scope.write(f":TRIGger:SHOLd:CLEVel {config.clock_level_v:.12g}")
    elif isinstance(config, NthEdge):
        scope.write(f":TRIGger:NEDGe:SOURce {_source_token(config.source)}")
        scope.write(f":TRIGger:NEDGe:SLOPe {config.slope}")
        scope.write(f":TRIGger:NEDGe:IDLE {config.idle_time_s:.12g}")
        scope.write(f":TRIGger:NEDGe:EDGE {config.edge_count}")
        scope.write(f":TRIGger:NEDGe:LEVel {config.level_v:.12g}")


def _write_levels(scope: Rigol, command: str, levels: tuple[tuple[str, float], ...]) -> None:
    for source, value in levels:
        scope.write(f"{command} {_source_token(source)},{value:.12g}")


def restore_trigger(scope: Rigol, state: TriggerState) -> TriggerState:
    """Restore a complete supported snapshot; reject unsupported state before writes."""
    if not isinstance(state, TriggerState) or type(state.config) not in _MODE_TOKENS:
        raise ValueError("state is not a complete supported trigger snapshot")
    _validate(scope, state.config)
    if _has_noise_reject(state.config):
        if type(state.noise_reject) is not bool:
            raise ValueError("noise_reject must be bool for analog trigger sources")
    elif state.noise_reject is not None:
        raise ValueError("noise rejection does not apply to digital trigger sources")
    _choice(state.status, {"TD", "WAIT", "RUN", "AUTO", "STOP"}, "trigger status")
    if not math.isfinite(state.position_s):
        raise ValueError("trigger position must be finite")
    if _supports_holdoff(state.config):
        if state.holdoff_s is None:
            raise ValueError("holdoff is required for this trigger mode")
        _number(state.holdoff_s, 8e-9, 10.0, "trigger holdoff")
    elif state.holdoff_s is not None:
        if isinstance(state.config, Video):
            raise ValueError("video trigger does not support holdoff")
        raise ValueError("this trigger mode does not support holdoff")
    _choice(state.sweep, {"AUTO", "NORM", "SING"}, "trigger sweep")
    require_afg_off(scope)
    _set_config(scope, state.config)
    scope.write(f":TRIGger:SWEep {state.sweep}")
    if _supports_holdoff(state.config):
        scope.write(f":TRIGger:HOLDoff {state.holdoff_s:.12g}")
    if state.noise_reject is not None:
        scope.write(f":TRIGger:NREJect {int(state.noise_reject)}")
    require_no_errors(scope)
    return read_trigger(scope)


def configure_trigger(scope: Rigol, config: TriggerConfig, *, sweep: str | None = None,
                      holdoff_s: float | None = None, noise_reject: bool | None = None) -> TriggerState:
    """Apply a typed trigger configuration and restore the snapshot on SCPI failure."""
    before = read_trigger(scope)
    _validate(scope, config)
    new_sweep = before.sweep if sweep is None else _choice(sweep, {"AUTO", "NORM", "SING"}, "trigger sweep")
    new_holdoff = before.holdoff_s if holdoff_s is None else holdoff_s
    if not _supports_holdoff(config):
        if holdoff_s is not None:
            raise ValueError("this trigger mode does not support holdoff")
        new_holdoff = None
    elif new_holdoff is None:
        new_holdoff = 8e-9
    else:
        _number(new_holdoff, 8e-9, 10.0, "trigger holdoff")
    if _has_noise_reject(config):
        new_noise = (before.noise_reject if before.noise_reject is not None else False) if noise_reject is None else noise_reject
        if type(new_noise) is not bool:
            raise ValueError("noise_reject must be bool for analog trigger sources")
    else:
        if noise_reject is not None:
            raise ValueError("noise rejection does not apply to digital trigger sources")
        new_noise = None
    candidate = TriggerState(config, new_sweep, new_holdoff, new_noise, before.status, before.position_s)
    try:
        restore_trigger(scope, candidate)
    except Exception:
        restore_trigger(scope, before)
        raise
    return read_trigger(scope)
