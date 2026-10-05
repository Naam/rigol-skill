"""Typed, read-only measurements from an already frozen DHO914S capture.

Based on DHO800/DHO900 Programming Guide 3.17.2, 3.17.5-3.17.8.
Statistics describe the instrument's existing accumulation, which may predate
this capture. Configure statistics before acquiring when that history matters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import permutations

from dho800900_models import profile_for
from dho800900 import (
    DUAL_MEASUREMENTS, MEASUREMENT_TYPES, normalize_measure_source,
    normalize_channel_source, normalize_counter_source, require_no_errors,
)


def _require_afg_off(scope) -> None:
    if profile_for(scope).afg and scope.query(":SOURce:OUTPut:STATe?").upper() not in {"0", "OFF"}:
        raise RuntimeError("AFG must be OFF")


_VOLTAGE = {"VMAX", "VMIN", "VPP", "VTOP", "VBASE", "VAMP", "VAVG", "VRMS",
            "VUPPER", "VMID", "VLOWER", "PVRMS", "ACRMS"}
_TIME = {"PERIOD", "RTIME", "FTIME", "PWIDTH", "NWIDTH", "TVMAX", "TVMIN"} | {
    item for item in DUAL_MEASUREMENTS if item.endswith("DELAY")}
_COUNT = {"PPULSES", "NPULSES", "PEDGES", "NEDGES"}
_UNIT = {**dict.fromkeys(_VOLTAGE, "V"), **dict.fromkeys(_TIME, "s"),
         **dict.fromkeys(_COUNT, "count"),
         "FREQUENCY": "Hz", "MAREA": "V*s", "MPAREA": "V*s",
         "PSLEWRATE": "V/s", "NSLEWRATE": "V/s", "VARIANCE": "V^2",
         "OVERSHOOT": "ratio", "PRESHOOT": "ratio",
         **dict.fromkeys((item for item in DUAL_MEASUREMENTS if item.endswith("PHASE")), "deg")}
_STAT_TYPES = {"MAXIMUM", "MINIMUM", "CURRENT", "AVERAGES", "DEVIATION", "CNT"}


@dataclass(frozen=True)
class Request:
    item: str
    source: str
    source_b: str | None = None


@dataclass(frozen=True)
class StatisticRequest:
    measurement: Request
    result: str


@dataclass(frozen=True)
class Result:
    item: str
    sources: tuple[str, ...]
    value: float | None
    status: str
    unit: str | None
    raw: str
    statistic: str | None = None


@dataclass(frozen=True)
class StatisticSettings:
    count: int
    enabled: bool

    def __post_init__(self) -> None:
        if type(self.count) is not int or not 2 <= self.count <= 100_000:
            raise ValueError("statistics count must be 2-100000")
        if type(self.enabled) is not bool:
            raise ValueError("statistics enabled must be bool")


@dataclass(frozen=True)
class MeasurementSetup:
    source: str | None = None
    all_measurement_source: str | None = None
    threshold_max: int | None = None
    threshold_mid: int | None = None
    threshold_min: int | None = None
    phase_source_a: str | None = None
    phase_source_b: str | None = None
    delay_source_a: str | None = None
    delay_source_b: str | None = None
    threshold_source: str | None = None
    threshold_type: str | None = None
    area: str | None = None
    indicator: bool | None = None
    counter_enabled: bool | None = None
    counter_source: str | None = None
    amplitude_type: str | None = None
    amplitude_top: str | None = None
    amplitude_base: str | None = None
    category: int | None = None
    clear_items: bool = False
    reset_thresholds: bool = False


@dataclass(frozen=True)
class MeasurementConfiguration:
    source: str
    all_measurement_source: str
    threshold_max: int
    threshold_mid: int
    threshold_min: int
    phase_source_a: str
    phase_source_b: str
    delay_source_a: str
    delay_source_b: str
    threshold_source: str
    threshold_type: str
    area: str
    indicator: bool
    counter_enabled: bool
    counter_source: str
    amplitude_type: str
    amplitude_top: str | None
    amplitude_base: str | None
    category: int


_SETUP_COMMANDS = {
    "source": ":MEASure:SOURce",
    "all_measurement_source": ":MEASure:AMSource",
    "threshold_max": ":MEASure:SETup:MAX",
    "threshold_mid": ":MEASure:SETup:MID",
    "threshold_min": ":MEASure:SETup:MIN",
    "phase_source_a": ":MEASure:SETup:PSA",
    "phase_source_b": ":MEASure:SETup:PSB",
    "delay_source_a": ":MEASure:SETup:DSA",
    "delay_source_b": ":MEASure:SETup:DSB",
    "threshold_source": ":MEASure:THReshold:SOURce",
    "threshold_type": ":MEASure:THReshold:TYPE",
    "area": ":MEASure:AREA",
    "indicator": ":MEASure:INDicator",
    "counter_enabled": ":MEASure:COUNter:ENABle",
    "counter_source": ":MEASure:COUNter:SOURce",
    "amplitude_type": ":MEASure:AMP:TYPE",
    "amplitude_top": ":MEASure:AMP:MANual:TOP",
    "amplitude_base": ":MEASure:AMP:MANual:BASE",
    "category": ":MEASure:CATegory",
}


def _setup_source(value: str, *, digital: bool = True, math: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError("measurement source must be a string")
    source = value.upper().replace("CHANNEL", "CHAN")
    allowed = {f"CHAN{i}" for i in range(1, 5)}
    if digital:
        allowed |= {f"D{i}" for i in range(16)}
    if math:
        allowed |= {f"MATH{i}" for i in range(1, 5)}
    if source not in allowed:
        raise ValueError(f"unsupported DHO914S measurement source: {value}")
    return f"CHANnel{source[4:]}" if source.startswith("CHAN") else source


def _response_bool(raw: str, name: str) -> bool:
    value = raw.strip().upper()
    if value not in {"0", "1", "OFF", "ON"}:
        raise ValueError(f"invalid {name} response: {raw!r}")
    return value in {"1", "ON"}


def read_measurement_setup(scope) -> MeasurementConfiguration:
    """Read the shared auto-measure setup with DHO914S source validation."""
    actual = {name: scope.query(f"{command}?") for name, command in _SETUP_COMMANDS.items()}
    require_no_errors(scope)
    source = _setup_source(actual["source"])
    am_source_raw = actual["all_measurement_source"].upper()
    am_source = "OFF" if am_source_raw == "OFF" else _setup_source(actual["all_measurement_source"], digital=False, math=False)
    threshold_source = _setup_source(actual["threshold_source"], digital=False)
    counter_raw = actual["counter_source"].upper()
    counter_source = _setup_source(counter_raw, math=False)
    threshold_type_raw = actual["threshold_type"].upper()
    if threshold_type_raw.startswith("PERC"):
        threshold_type = "PERCENT"
    elif threshold_type_raw.startswith("ABS"):
        threshold_type = "ABSOLUTE"
    else:
        raise ValueError(f"invalid measurement threshold type: {actual['threshold_type']!r}")
    area = actual["area"].upper()
    if area not in {"MAIN", "ZOOM"}:
        raise ValueError(f"invalid measurement area: {actual['area']!r}")
    amp_type = actual["amplitude_type"].upper()
    if amp_type not in {"AUTO", "MAN", "MANUAL"}:
        raise ValueError(f"invalid amplitude method: {actual['amplitude_type']!r}")
    amp_top = amp_base = None
    if amp_type != "AUTO":
        amp_top = _amp_selection(actual["amplitude_top"])
        amp_base = _amp_selection(actual["amplitude_base"])
    try:
        maximum, middle, minimum = (int(actual[name]) for name in ("threshold_max", "threshold_mid", "threshold_min"))
        category = int(actual["category"])
    except ValueError as exc:
        raise ValueError("invalid numeric measurement setup response") from exc
    if not minimum < middle < maximum:
        raise ValueError("instrument returned unordered measurement thresholds")
    if threshold_type == "PERCENT" and not (0 <= minimum < middle < maximum <= 100):
        raise ValueError("instrument returned percentage thresholds outside 0-100")
    if category not in range(3):
        raise ValueError(f"invalid measurement category: {category}")
    return MeasurementConfiguration(
        source, am_source, maximum, middle, minimum,
        _setup_source(actual["phase_source_a"]), _setup_source(actual["phase_source_b"]),
        _setup_source(actual["delay_source_a"]), _setup_source(actual["delay_source_b"]),
        threshold_source, threshold_type, area,
        _response_bool(actual["indicator"], "measurement indicator"),
        _response_bool(actual["counter_enabled"], "measurement counter"),
        counter_source, "AUTO" if amp_type == "AUTO" else "MANUAL", amp_top, amp_base, category,
    )


def _amp_selection(value: str) -> str:
    value = value.upper()
    if value.startswith("HIST"):
        return "HISTOGRAM"
    if value.startswith("MAXM"):
        return "MAXMIN"
    raise ValueError(f"invalid manual amplitude selection: {value!r}")


def _threshold_order(scope, changes: dict[str, object], threshold_type: str) -> tuple[str, ...]:
    names = ("threshold_min", "threshold_mid", "threshold_max")
    old = {name: int(scope.query(f"{_SETUP_COMMANDS[name]}?")) for name in names}
    target = {name: int(changes.get(name, old[name])) for name in names}
    minimum, middle, maximum = target["threshold_min"], target["threshold_mid"], target["threshold_max"]
    if not minimum < middle < maximum:
        raise ValueError("threshold values must satisfy MIN < MID < MAX")
    if threshold_type == "PERCENT" and not 0 <= minimum < middle < maximum <= 100:
        raise ValueError("percentage thresholds must satisfy 0 <= MIN < MID < MAX <= 100")
    requested = tuple(name for name in names if name in changes)
    for order in permutations(requested):
        state = dict(old)
        for name in order:
            state[name] = target[name]
            if not state["threshold_min"] < state["threshold_mid"] < state["threshold_max"]:
                break
        else:
            return order
    raise ValueError("threshold changes cannot be applied without crossing MIN, MID, MAX")


def configure_measurement_setup(scope, settings: MeasurementSetup) -> MeasurementConfiguration:
    """Apply DHO914S measurement source, threshold, cursor, counter and amplitude settings."""
    if not isinstance(settings, MeasurementSetup):
        raise TypeError("settings must be MeasurementSetup")
    for name in ("clear_items", "reset_thresholds"):
        value = getattr(settings, name)
        if type(value) is not bool:
            raise ValueError(f"{name} must be bool")
    for name in ("indicator", "counter_enabled"):
        value = getattr(settings, name)
        if value is not None and type(value) is not bool:
            raise ValueError(f"{name} must be bool")
    changes = {name: getattr(settings, name) for name in _SETUP_COMMANDS if getattr(settings, name) is not None}
    normalized_sources = {
        "source": dict(digital=True, math=True),
        "phase_source_a": dict(digital=True, math=True),
        "phase_source_b": dict(digital=True, math=True),
        "delay_source_a": dict(digital=True, math=True),
        "delay_source_b": dict(digital=True, math=True),
        "threshold_source": dict(digital=False, math=True),
        "counter_source": dict(digital=True, math=False),
    }
    for name, options in normalized_sources.items():
        if name in changes:
            changes[name] = _setup_source(changes[name], **options)
    if "all_measurement_source" in changes:
        value = str(changes["all_measurement_source"]).upper()
        changes["all_measurement_source"] = "OFF" if value == "OFF" else _setup_source(value, digital=False, math=False)
    if "threshold_type" in changes:
        threshold_type = str(changes["threshold_type"]).upper()
        if threshold_type not in {"PERCENT", "PERCENTAGE", "ABSOLUTE", "ABS"}:
            raise ValueError("threshold_type must be PERCENT or ABSOLUTE")
        changes["threshold_type"] = "PERCENT" if threshold_type.startswith("PERC") else "ABSOLUTE"
    else:
        threshold_type = scope.query(":MEASure:THReshold:TYPE?").upper()
        threshold_type = "PERCENT" if threshold_type.startswith("PERC") else "ABSOLUTE" if threshold_type.startswith("ABS") else "INVALID"
    if threshold_type == "INVALID":
        raise ValueError("instrument returned an invalid measurement threshold type")
    if "area" in changes:
        area = str(changes["area"]).upper()
        if area not in {"MAIN", "ZOOM"}:
            raise ValueError("area must be MAIN or ZOOM")
        changes["area"] = area
        if area == "ZOOM" and scope.query(":TIMebase:DELay:ENABle?").upper() not in {"1", "ON"}:
            raise ValueError("ZOOM measurement area requires delayed sweep enabled")
    for name in ("amplitude_type",):
        if name in changes:
            value = str(changes[name]).upper()
            if value not in {"AUTO", "MANUAL", "MAN"}:
                raise ValueError("amplitude_type must be AUTO or MANUAL")
            changes[name] = "AUTO" if value == "AUTO" else "MANUAL"
    for name in ("amplitude_top", "amplitude_base"):
        if name in changes:
            changes[name] = _amp_selection(changes[name])
    if any(name in changes for name in ("amplitude_top", "amplitude_base")):
        amp_type = changes.get("amplitude_type", scope.query(":MEASure:AMP:TYPE?")).upper()
        if amp_type.startswith("AUTO"):
            raise ValueError("manual amplitude selections require amplitude_type MANUAL")
    for name in ("threshold_max", "threshold_mid", "threshold_min"):
        if name in changes and type(changes[name]) is not int:
            raise ValueError(f"{name} must be an integer")
    if "category" in changes and (type(changes["category"]) is not int or changes["category"] not in range(3)):
        raise ValueError("category must be 0, 1, or 2")
    threshold_fields = {name for name in changes if name in {"threshold_max", "threshold_mid", "threshold_min"}}
    order = _threshold_order(scope, changes, threshold_type) if threshold_fields else ()
    if settings.reset_thresholds and threshold_fields:
        raise ValueError("reset_thresholds cannot be combined with explicit threshold values")
    _require_afg_off(scope)
    require_no_errors(scope)
    if settings.clear_items:
        scope.write(":MEASure:CLEar")
    if settings.reset_thresholds:
        scope.write(":MEASure:THReshold:DEFault")
    ordered = [(name, value) for name, value in changes.items()
               if name not in threshold_fields and name != "threshold_type"]
    for name in ("threshold_type",):
        if name in changes:
            ordered.insert(0, (name, changes[name]))
    ordered.extend((name, changes[name]) for name in order)
    for name, value in ordered:
        command = _SETUP_COMMANDS[name]
        if name in {"indicator", "counter_enabled"}:
            value = "ON" if value else "OFF"
        elif name == "threshold_type":
            value = "PERCent" if value == "PERCENT" else "ABSolute"
        elif name == "area":
            value = "ZOOM" if value == "ZOOM" else "MAIN"
        elif name == "amplitude_type":
            value = "AUTO" if value == "AUTO" else "MANual"
        elif name in {"amplitude_top", "amplitude_base"}:
            value = "HISTogram" if value == "HISTOGRAM" else "MAXMin"
        scope.write(f"{command} {value}")
    require_no_errors(scope)
    result = read_measurement_setup(scope)
    _verify_setup(result, changes)
    return result


def _verify_setup(actual: MeasurementConfiguration, requested: dict[str, object]) -> None:
    aliases = {"PERCENT": "PERCENT", "ABSOLUTE": "ABSOLUTE", "MANUAL": "MANUAL", "HISTOGRAM": "HISTOGRAM", "MAXMIN": "MAXMIN"}
    for name, expected in requested.items():
        actual_value = getattr(actual, name)
        if isinstance(expected, str):
            matches = aliases.get(str(actual_value).upper(), str(actual_value).upper()) == aliases.get(expected.upper(), expected.upper())
        else:
            matches = actual_value == expected
        if not matches:
            raise RuntimeError(f"measurement setup readback mismatch for {name}: requested {expected!r}, got {actual_value!r}")


def clear_measurements(scope) -> None:
    _require_afg_off(scope)
    scope.write(":MEASure:CLEar")
    require_no_errors(scope)


def reset_measurement_thresholds(scope) -> MeasurementConfiguration:
    return configure_measurement_setup(scope, MeasurementSetup(reset_thresholds=True))


def read_measurement_counter(scope) -> Result:
    """Read the measurement counter result from section 3.17.23 in hertz."""
    _safe_frozen(scope)
    result = _result("COUNTER", ("COUNTER",), scope.query(":MEASure:COUNter:VALue?"))
    require_no_errors(scope)
    return Result(result.item, result.sources, result.value, result.status, "Hz", result.raw)


def _normalized(request: Request, scope) -> tuple[str, tuple[str, ...]]:
    item = request.item.upper()
    if item not in MEASUREMENT_TYPES:
        raise ValueError(f"unsupported measurement item {request.item}")
    if (request.source_b is None) == (item in DUAL_MEASUREMENTS):
        raise ValueError(f"{item} requires exactly {'two' if item in DUAL_MEASUREMENTS else 'one'} source(s)")
    sources = (normalize_measure_source(request.source, item, profile_for(scope)),)
    if request.source_b is not None:
        sources += (normalize_measure_source(request.source_b, item, profile_for(scope)),)
    return item, sources


def _safe_frozen(scope) -> None:
    _require_afg_off(scope)
    if scope.query(":TRIGger:STATus?").upper() != "STOP":
        raise RuntimeError("acquisition must be STOPped")
    require_no_errors(scope)


def _result(item: str, sources: tuple[str, ...], raw: str,
            statistic: str | None = None) -> Result:
    raw = raw.strip()
    try:
        value = float(raw)
    except ValueError:
        if raw not in {"*****", ""}:
            raise RuntimeError(f"unexpected {item} response: {raw!r}") from None
        value = math.nan
    valid = math.isfinite(value) and abs(value) < 9e37
    unit = "count" if statistic == "CNT" else _UNIT.get(item)
    return Result(item, sources, value if valid else None,
                  "valid" if valid else "unavailable", unit, raw, statistic)


def _statistics_settings(scope, expected: StatisticSettings) -> None:
    actual = (scope.query(":MEASure:STATistic:COUNt?"),
              scope.query(":MEASure:STATistic:DISPlay?"))
    if actual != (str(expected.count), str(int(expected.enabled))):
        raise RuntimeError(f"statistics settings differ: {actual}")


def configure_statistics(scope, settings: StatisticSettings,
                         items: tuple[Request, ...]) -> None:
    """Configure accumulation before acquisition; never starts acquisition."""
    normalized = tuple(_normalized(item, scope) for item in items)
    if len(normalized) > 10:
        raise ValueError("instrument statistics display supports at most 10 items")
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate statistics items")
    _require_afg_off(scope)
    require_no_errors(scope)
    scope.write(f":MEASure:STATistic:COUNt {settings.count}")
    for item, sources in normalized:
        scope.write(f":MEASure:STATistic:ITEM {item},{','.join(sources)}")
    scope.write(f":MEASure:STATistic:DISPlay {'ON' if settings.enabled else 'OFF'}")
    _statistics_settings(scope, settings)
    require_no_errors(scope)


def read_frozen(scope, measurements: tuple[Request, ...], *,
                statistics: tuple[StatisticRequest, ...] = (),
                statistic_settings: StatisticSettings | None = None) -> tuple[Result, ...]:
    """Query one stopped frame; statistics are prior instrument history."""
    if statistics and (statistic_settings is None or not statistic_settings.enabled):
        raise ValueError("enabled statistic_settings required for statistics")
    commands = []
    for request in measurements:
        item, sources = _normalized(request, scope)
        commands.append((item, sources, None, f":MEASure:ITEM? {item},{','.join(sources)}"))
    for request in statistics:
        item, sources = _normalized(request.measurement, scope)
        kind = request.result.upper()
        if kind not in _STAT_TYPES:
            raise ValueError(f"unsupported statistic result {request.result}")
        commands.append((item, sources, kind,
                         f":MEASure:STATistic:ITEM? {kind},{item},{','.join(sources)}"))
    _safe_frozen(scope)
    if statistic_settings is not None:
        _statistics_settings(scope, statistic_settings)
    results = tuple(_result(item, sources, scope.query(command), kind)
                    for item, sources, kind, command in commands)
    require_no_errors(scope)
    return results


def read_dvm(scope, *, source: str, mode: str) -> Result:
    """Read the live DVM, independently of any frozen waveform (3.10.1-3.10.4)."""
    source = normalize_channel_source(source, profile_for(scope))
    mode = mode.upper()
    if mode not in {"ACRMS", "DC", "DCRMS"}:
        raise ValueError("DVM mode must be ACRMS, DC, or DCRMS")
    _require_afg_off(scope)
    require_no_errors(scope)
    actual = (scope.query(":DVM:SOURce?"), scope.query(":DVM:MODE?"),
              scope.query(":DVM:ENABle?"))
    if actual != (source.replace("CHANnel", "CHAN"),
                  {"ACRMS": "ACRM", "DC": "DC", "DCRMS": "DCRM"}[mode], "1"):
        raise RuntimeError(f"DVM settings differ: {actual}")
    result = _result("DVM", (source,), scope.query(":DVM:CURRent?"))
    require_no_errors(scope)
    return Result(result.item, result.sources, result.value, result.status, "V", result.raw)


def read_counter(scope, *, source: str, mode: str) -> Result:
    """Read the live counter, independently of any frozen waveform (3.7.1-3.7.4)."""
    source = normalize_counter_source(source, profile_for(scope))
    mode = mode.upper()
    if mode not in {"FREQUENCY", "PERIOD", "TOTALIZE"}:
        raise ValueError("counter mode must be FREQUENCY, PERIOD, or TOTALIZE")
    _require_afg_off(scope)
    require_no_errors(scope)
    actual = (scope.query(":COUNter:SOURce?"), scope.query(":COUNter:MODE?"),
              scope.query(":COUNter:ENABle?"))
    if (actual[0] != source.replace("CHANnel", "CHAN") or
            not actual[1].upper().startswith(mode[:3]) or actual[2] != "1"):
        raise RuntimeError(f"counter settings differ: {actual}")
    result = _result("COUNTER", (source,), scope.query(":COUNter:CURRent?"))
    require_no_errors(scope)
    return Result(result.item, result.sources, result.value, result.status,
                  {"FREQUENCY": "Hz", "PERIOD": "s", "TOTALIZE": "count"}[mode], result.raw)
