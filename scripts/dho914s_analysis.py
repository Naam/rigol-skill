"""Typed Math/FFT and histogram workflows for the Rigol DHO914S."""

from __future__ import annotations

from dataclasses import dataclass, fields
import math
import re

from dho800900_models import profile_for
from dho800900 import DHO800900 as Rigol, require_afg_off, require_no_errors


@dataclass(frozen=True)
class MathSettings:
    display: bool | None = None
    operator: str | None = None
    source1: str | None = None
    source2: str | None = None
    logic_source1: str | None = None
    logic_source2: str | None = None
    scale: float | None = None
    offset: float | None = None
    invert: bool | None = None
    reset: bool = False
    grid: str | None = None
    expand: str | None = None
    waveform_type: str | None = None
    fft_source: int | None = None
    fft_window: str | None = None
    fft_unit: str | None = None
    fft_scale: float | None = None
    fft_offset: float | None = None
    fft_hscale_hz: float | None = None
    fft_center_hz: float | None = None
    fft_start_hz: float | None = None
    fft_end_hz: float | None = None
    fft_search_enabled: bool | None = None
    fft_search_count: int | None = None
    fft_search_threshold: float | None = None
    fft_search_excursion: float | None = None
    fft_search_order: str | None = None
    filter_type: str | None = None
    filter_w1_hz: float | None = None
    filter_w2_hz: float | None = None
    logic_sensitivity_div: float | None = None
    differential_distance: int | None = None
    threshold1_v: float | None = None
    threshold2_v: float | None = None
    threshold3_v: float | None = None
    threshold4_v: float | None = None
    label_show: bool | None = None


@dataclass(frozen=True)
class MathState:
    index: int
    values: dict[str, str]


@dataclass(frozen=True)
class FFTPeak:
    rank: int
    frequency_hz: float
    amplitude: float
    amplitude_unit: str


@dataclass(frozen=True)
class HistogramSettings:
    enabled: bool | None = None
    histogram_type: str | None = None
    source: int | None = None
    height_div: int | None = None
    left: float | None = None
    right: float | None = None
    top: float | None = None
    bottom: float | None = None


@dataclass(frozen=True)
class HistogramStatistics:
    fields: dict[str, str]


_OPERATORS = {
    "ADD", "SUBTRACT", "MULTIPLY", "DIVISION", "AND", "OR", "XOR", "NOT",
    "FFT", "INTG", "DIFF", "SQRT", "LG", "LN", "EXP", "ABS",
    "LPASS", "HPASS", "BPASS", "BSTOP", "AXB",
}
_ARITHMETIC = {"ADD", "SUBTRACT", "MULTIPLY", "DIVISION"}
_LOGIC = {"AND", "OR", "XOR", "NOT"}
_FILTER = {"LPASS", "HPASS", "BPASS", "BSTOP"}
_BOOL_FIELDS = {"display", "invert", "fft_search_enabled", "label_show"}
_COMMANDS = {
    "display": "DISPlay", "source1": "SOURce1", "source2": "SOURce2",
    "logic_source1": "LSOurce1", "logic_source2": "LSOurce2", "scale": "SCALe",
    "offset": "OFFSet", "invert": "INVert", "grid": "GRID", "expand": "EXPand",
    "waveform_type": "WAVetype", "fft_source": "FFT:SOURce", "fft_window": "FFT:WINDow",
    "fft_unit": "FFT:UNIT", "fft_scale": "FFT:SCALe", "fft_offset": "FFT:OFFSet",
    "fft_hscale_hz": "FFT:HSCale", "fft_center_hz": "FFT:HCENter",
    "fft_start_hz": "FFT:FREQuency:STARt", "fft_end_hz": "FFT:FREQuency:END",
    "fft_search_enabled": "FFT:SEARch:ENABle", "fft_search_count": "FFT:SEARch:NUM",
    "fft_search_threshold": "FFT:SEARch:THReshold", "fft_search_excursion": "FFT:SEARch:EXCursion",
    "fft_search_order": "FFT:SEARch:ORDer", "filter_type": "FILTer:TYPE",
    "filter_w1_hz": "FILTer:W1", "filter_w2_hz": "FILTer:W2",
    "logic_sensitivity_div": "SENSitivity", "differential_distance": "DISTance",
    "threshold1_v": "THReshold1", "threshold2_v": "THReshold2",
    "threshold3_v": "THReshold3", "threshold4_v": "THReshold4",
    "label_show": "LABel:SHOW",
}
def _index(value: int) -> int:
    if type(value) is not int or value not in range(1, 5):
        raise ValueError("math index must be 1-4")
    return value


def _bool(value: bool) -> str:
    if type(value) is not bool:
        raise ValueError("boolean settings must be bool")
    return "ON" if value else "OFF"


def _finite(name: str, value: float, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return float(value)


def _source(value: str, index: int, *, logic: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("math source must be a source name")
    name = value.upper().replace("CHANNEL", "CHAN")
    allowed = {f"CHAN{i}" for i in range(1, 5)}
    if logic:
        allowed |= {f"D{i}" for i in range(16)}
    else:
        allowed |= {f"REF{i}" for i in range(1, 11)}
        allowed |= {f"MATH{i}" for i in range(1, index)}
    if name not in allowed:
        raise ValueError(f"invalid source for Math{index}: {value}")
    return name


def _operator(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("operator must be a string")
    normalized = {
        "SUBT": "SUBTRACT", "SUBTRACT": "SUBTRACT", "MULT": "MULTIPLY",
        "MULTIPLY": "MULTIPLY", "DIV": "DIVISION", "DIVISION": "DIVISION",
        "LPAS": "LPASS", "LPASS": "LPASS", "HPAS": "HPASS", "HPASS": "HPASS",
        "BPAS": "BPASS", "BPASS": "BPASS", "BST": "BSTOP", "BSTOP": "BSTOP",
    }.get(value.upper(), value.upper())
    if normalized not in _OPERATORS:
        raise ValueError(f"unsupported math operator: {value}")
    return normalized


def _verify_math_settings(state: MathState, changes: dict[str, object], index: int) -> None:
    for name, expected in changes.items():
        if name not in _COMMANDS and name != "operator":
            continue
        actual = state.values.get(name)
        if actual is None:
            raise RuntimeError(f"Math{index} did not return {name} readback")
        if name == "operator":
            matches = _operator(actual) == _operator(str(expected))
        elif name in _BOOL_FIELDS:
            if actual.upper() not in {"0", "1", "OFF", "ON"}:
                raise RuntimeError(f"Math{index} returned invalid boolean for {name}: {actual!r}")
            matches = (actual.upper() in {"1", "ON"}) is expected
        elif name in {"source1", "source2", "logic_source1", "logic_source2"}:
            matches = _source(actual, index, logic=name.startswith("logic_")) == _source(str(expected), index, logic=name.startswith("logic_"))
        elif name == "fft_source":
            matches = actual.upper().replace("CHANNEL", "CHAN") == f"CHAN{expected}"
        elif name in {"fft_window", "fft_search_order", "filter_type"}:
            actual_value = actual.upper()
            expected_value = str(expected).upper()
            aliases = {
                "RECT": "RECTANGLE", "BLAC": "BLACKMAN", "HANN": "HANNING", "HAMM": "HAMMING",
                "FLAT": "FLATTOP", "TRI": "TRIANGLE", "AMP": "AMPORDER", "FREQ": "FREQORDER",
                "LPAS": "LPASS", "HPAS": "HPASS", "BPAS": "BPASS", "BST": "BSTOP",
            }
            matches = aliases.get(actual_value, actual_value) == expected_value
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            try:
                matches = math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-12)
            except ValueError:
                matches = False
        else:
            matches = actual.upper() == str(expected).upper()
        if not matches:
            raise RuntimeError(f"Math{index} readback mismatch for {name}: requested {expected!r}, got {actual!r}")


def configure_math(scope: Rigol, index: int, settings: MathSettings) -> MathState:
    """Apply a validated Math/FFT/filter setup, then return its readback."""
    index = _index(index)
    if not isinstance(settings, MathSettings):
        raise TypeError("settings must be MathSettings")
    if type(settings.reset) is not bool:
        raise ValueError("reset must be bool")
    changes = {f.name: getattr(settings, f.name) for f in fields(settings) if getattr(settings, f.name) is not None}
    changes.pop("reset", None)
    for name in _BOOL_FIELDS & changes.keys():
        _bool(changes[name])
    current = scope.query(f":MATH{index}:OPERator?")
    operator = _operator(settings.operator) if settings.operator is not None else _operator(current)
    fft_fields = {name for name in changes if name.startswith("fft_")}
    if fft_fields and operator != "FFT":
        raise ValueError("FFT settings require operator FFT")
    filter_fields = {name for name in changes if name.startswith("filter_")}
    if filter_fields and operator not in _FILTER:
        raise ValueError("filter settings require a filter operator")
    logic_fields = {name for name in changes if name.startswith("logic_") or name.startswith("threshold")}
    if logic_fields and operator not in _LOGIC:
        raise ValueError("logic thresholds and sensitivity require a logic operator")
    if "source1" in changes and operator in _LOGIC | {"FFT"}:
        raise ValueError(f"source1 is not valid for operator {operator}")
    if "differential_distance" in changes and operator != "DIFF":
        raise ValueError("differential_distance requires operator DIFF")
    for name in ("source1", "source2"):
        if name in changes:
            if name == "source2" and operator not in _ARITHMETIC:
                raise ValueError("source2 is only valid for arithmetic operators")
            changes[name] = _source(changes[name], index)
    for name in ("logic_source1", "logic_source2"):
        if name in changes:
            if operator not in _LOGIC or name == "logic_source2" and operator == "NOT":
                raise ValueError(f"{name} is not valid for operator {operator}")
            changes[name] = _source(changes[name], index, logic=True)
    for name in ("source1", "source2", "logic_source1", "logic_source2"):
        if name in changes and (changes[name].startswith("CHAN") or changes[name].startswith("D")):
            profile_for(scope).source(changes[name], digital=name.startswith("logic_"))
    for name in ("scale", "offset", "invert"):
        if name in changes and (operator in _LOGIC | {"FFT"}):
            raise ValueError(f"{name} is not valid for operator {operator}")
    if "fft_source" in changes and (type(changes["fft_source"]) is not int or changes["fft_source"] not in range(1, 5)):
        raise ValueError("fft_source must be channel 1-4")
    if "fft_source" in changes:
        profile_for(scope).analog_channel(changes["fft_source"])
    choices = {
        "grid": {"FULL", "HALF", "NONE"}, "expand": {"GND", "CENTER"},
        "waveform_type": {"MAIN", "ZOOM"},
        "fft_window": {"RECTANGLE", "BLACKMAN", "HANNING", "HAMMING", "FLATTOP", "TRIANGLE"},
        "fft_unit": {"VRMS", "DB"}, "fft_search_order": {"AMPORDER", "FREQORDER"},
        "filter_type": _FILTER,
    }
    for name, valid in choices.items():
        if name in changes:
            value = str(changes[name]).upper()
            if value not in valid:
                raise ValueError(f"invalid {name}: {changes[name]}")
            changes[name] = value
    for name in ("fft_scale", "fft_hscale_hz", "logic_sensitivity_div"):
        if name in changes and _finite(name, changes[name], 1e-9 if name == "fft_scale" else 0.1 if name == "logic_sensitivity_div" else 10) <= 0:
            raise ValueError(f"{name} must be positive")
    if "fft_scale" in changes and changes["fft_scale"] > 5e9:
        raise ValueError("fft_scale must not exceed 5 G")
    if "scale" in changes:
        if _finite("scale", changes["scale"]) <= 0:
            raise ValueError("scale must be positive")
    if "offset" in changes:
        _finite("offset", changes["offset"], -1e9, 1e9)
    for name in ("fft_offset", "fft_center_hz", "fft_start_hz", "fft_end_hz", "fft_search_threshold", "fft_search_excursion", "filter_w1_hz", "filter_w2_hz", "threshold1_v", "threshold2_v", "threshold3_v", "threshold4_v"):
        if name in changes:
            _finite(name, changes[name], 0 if name in {"fft_start_hz", "fft_end_hz", "fft_search_excursion", "filter_w1_hz", "filter_w2_hz"} else None)
    if "fft_offset" in changes:
        _finite("fft_offset", changes["fft_offset"], -1e9, 1e9)
    if "fft_center_hz" in changes:
        _finite("fft_center_hz", changes["fft_center_hz"], 5, 1e9)
    if "fft_hscale_hz" in changes and changes["fft_hscale_hz"] > 1e9:
        raise ValueError("fft_hscale_hz must be 10 Hz to 1 GHz")
    if "fft_search_count" in changes and (type(changes["fft_search_count"]) is not int or changes["fft_search_count"] not in range(1, 16)):
        raise ValueError("fft_search_count must be 1-15")
    if "differential_distance" in changes and (type(changes["differential_distance"]) is not int or changes["differential_distance"] not in range(1, 1001)):
        raise ValueError("differential_distance must be 1-1000")
    if settings.fft_start_hz is not None or settings.fft_end_hz is not None:
        start = settings.fft_start_hz if settings.fft_start_hz is not None else float(scope.query(f":MATH{index}:FFT:FREQuency:STARt?"))
        end = settings.fft_end_hz if settings.fft_end_hz is not None else float(scope.query(f":MATH{index}:FFT:FREQuency:END?"))
        if start < 0 or end > 1e9 or end - start < 10:
            raise ValueError("FFT frequency range must be 0-1 GHz with at least 10 Hz span")
    if "fft_search_threshold" in changes:
        current_unit = scope.query(f":MATH{index}:FFT:UNIT?").upper()
        unit = str(changes.get("fft_unit", current_unit)).upper()
        if unit != current_unit and not {"fft_scale", "fft_offset"} <= changes.keys():
            raise ValueError("changing FFT units with a threshold requires explicit FFT scale and offset")
        vertical_scale = float(changes.get("fft_scale", scope.query(f":MATH{index}:FFT:SCALe?")))
        vertical_offset = float(changes.get("fft_offset", scope.query(f":MATH{index}:FFT:OFFSet?")))
        low, high = -4 * vertical_scale - vertical_offset, 4 * vertical_scale - vertical_offset
        threshold = changes["fft_search_threshold"]
        if not low <= threshold <= high or unit == "VRMS" and threshold < 0:
            raise ValueError("FFT search threshold is outside the current unit and vertical range")
    if "fft_search_excursion" in changes:
        current_unit = scope.query(f":MATH{index}:FFT:UNIT?").upper()
        unit = str(changes.get("fft_unit", current_unit)).upper()
        if unit != current_unit and "fft_scale" not in changes:
            raise ValueError("changing FFT units with an excursion requires an explicit FFT scale")
        fft_scale = float(changes.get("fft_scale", scope.query(f":MATH{index}:FFT:SCALe?")))
        if changes["fft_search_excursion"] > 8 * fft_scale:
            raise ValueError("FFT search excursion cannot exceed eight vertical divisions")
    for channel in range(1, 5):
        key = f"threshold{channel}_v"
        if key in changes:
            scale = float(scope.query(f":CHANnel{channel}:SCALe?"))
            offset = float(scope.query(f":CHANnel{channel}:OFFSet?"))
            low, high = -4 * scale - offset, 4 * scale - offset
            value = changes[key]
            step = scale / 10
            if not low <= value <= high or abs((value - low) / step - round((value - low) / step)) > 1e-6:
                raise ValueError(f"{key} must fit the channel range and use a scale/10 step")
    if "filter_w1_hz" in changes or "filter_w2_hz" in changes:
        filter_type = _operator(str(changes.get("filter_type", scope.query(f":MATH{index}:FILTer:TYPE?"))))
        time_scale = float(scope.query(":TIMebase:MAIN:SCALe?"))
        sample_rate = 100 / time_scale
        low = 0.005 * sample_rate
        high1 = (0.095 if filter_type in {"BPASS", "BSTOP"} else 0.1) * sample_rate
        high2 = 0.1 * sample_rate
        w1 = float(changes.get("filter_w1_hz", scope.query(f":MATH{index}:FILTer:W1?")))
        w2 = float(changes.get("filter_w2_hz", scope.query(f":MATH{index}:FILTer:W2?")))
        step = 0.005 * sample_rate
        if "filter_w2_hz" in changes and filter_type not in {"BPASS", "BSTOP"}:
            raise ValueError("filter_w2_hz is only available for band-pass or band-stop filters")
        if not (low <= w1 <= high1 and abs((w1-low)/step-round((w1-low)/step)) < 1e-6):
            raise ValueError("filter_w1_hz is outside its timebase-derived range or step")
        if filter_type in {"BPASS", "BSTOP"} and not (0.01*sample_rate <= w2 <= high2 and w2 > w1 and abs((w2-low)/step-round((w2-low)/step)) < 1e-6):
            raise ValueError("filter_w2_hz must be above W1 and on the timebase-derived step")
    if changes.get("waveform_type") == "ZOOM":
        if operator == "FFT":
            raise ValueError("FFT does not support ZOOM waveform type")
        if scope.query(":TIMebase:DELay:ENABle?").upper() not in {"1", "ON"}:
            raise ValueError("ZOOM waveform type requires delayed sweep to be enabled")
    require_afg_off(scope)
    if settings.operator is not None:
        scope.write(f":MATH{index}:OPERator {operator}")
    ordered = list(changes.items())
    if "filter_w1_hz" in changes and "filter_w2_hz" in changes:
        old_w2 = float(scope.query(f":MATH{index}:FILTer:W2?"))
        w1, w2 = changes["filter_w1_hz"], changes["filter_w2_hz"]
        ordered = [(n, v) for n, v in ordered if n not in {"filter_w1_hz", "filter_w2_hz"}]
        pair = [("filter_w2_hz", w2), ("filter_w1_hz", w1)] if w1 >= old_w2 else [("filter_w1_hz", w1), ("filter_w2_hz", w2)]
        ordered.extend(pair)
    if "fft_start_hz" in changes and "fft_end_hz" in changes:
        old_end = float(scope.query(f":MATH{index}:FFT:FREQuency:END?"))
        start, end = changes["fft_start_hz"], changes["fft_end_hz"]
        ordered = [(n, v) for n, v in ordered if n not in {"fft_start_hz", "fft_end_hz"}]
        ordered.extend([("fft_end_hz", end), ("fft_start_hz", start)] if start >= old_end else [("fft_start_hz", start), ("fft_end_hz", end)])
    if "display" in changes:
        ordered = [(name, value) for name, value in ordered if name != "display"] + [("display", changes["display"])]
    for name, value in ordered:
        if name not in _COMMANDS:
            continue
        if name in _BOOL_FIELDS:
            value = _bool(value)
        elif name == "fft_source":
            value = f"CHANnel{value}"
        elif name == "fft_window":
            value = {"RECTANGLE":"RECTangle", "BLACKMAN":"BLACkman", "HANNING":"HANNing", "HAMMING":"HAMMing", "FLATTOP":"FLATtop", "TRIANGLE":"TRIangle"}[value]
        elif name == "fft_search_order":
            value = "AMPorder" if value == "AMPORDER" else "FREQorder"
        elif name == "filter_type":
            value = {"LPASS":"LPASs", "HPASS":"HPASs", "BPASS":"BPASs", "BSTOP":"BSTop"}[value]
        elif name in {"source1", "source2", "logic_source1", "logic_source2"}:
            value = "CHANnel" + value[4:] if value.startswith("CHAN") else value
        else:
            value = str(value)
        scope.write(f":MATH{index}:{_COMMANDS[name]} {value}")
    if settings.reset:
        scope.write(f":MATH{index}:RESet")
    require_no_errors(scope)
    state = read_math(scope, index)
    requested = dict(changes)
    if settings.operator is not None:
        requested["operator"] = operator
    _verify_math_settings(state, requested, index)
    return state


def read_math(scope: Rigol, index: int) -> MathState:
    index = _index(index)
    raw_operator = scope.query(f":MATH{index}:OPERator?")
    operator = _operator(raw_operator)
    values: dict[str, str] = {"operator": raw_operator}
    relevant = {"display", "grid", "expand", "waveform_type", "label_show"}
    if operator in _ARITHMETIC:
        relevant |= {"source1", "source2", "scale", "offset", "invert"}
    elif operator in _LOGIC:
        relevant |= {"logic_source1", "logic_sensitivity_div", "threshold1_v", "threshold2_v", "threshold3_v", "threshold4_v"}
        if operator != "NOT":
            relevant.add("logic_source2")
    else:
        relevant |= {"source1", "scale", "offset", "invert"}
    if operator == "FFT":
        relevant = {"display", "fft_source", "fft_window", "fft_unit", "fft_scale", "fft_offset", "fft_hscale_hz", "fft_center_hz", "fft_start_hz", "fft_end_hz", "fft_search_enabled", "fft_search_count", "fft_search_threshold", "fft_search_excursion", "fft_search_order", "label_show"}
    if operator in _FILTER:
        relevant |= {"filter_type", "filter_w1_hz", "filter_w2_hz"}
    if operator == "DIFF":
        relevant.add("differential_distance")
    for name, command in _COMMANDS.items():
        if name not in relevant:
            continue
        values[name] = scope.query(f":MATH{index}:{command}?")
    values["fft_title"] = scope.query(f":MATH{index}:WINDow:TITLe?")
    require_no_errors(scope)
    return MathState(index, values)


def read_fft_search_results(scope: Rigol, index: int) -> tuple[FFTPeak, ...]:
    index = _index(index)
    raw = scope.query(f":MATH{index}:FFT:SEARch:RES?")
    require_no_errors(scope)
    prefix = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
    rows: list[FFTPeak] = []
    for line in raw.splitlines():
        line = line.strip().strip("[]")
        if not line:
            continue
        match = re.fullmatch(rf"(\d+)\s*,\s*({number})\s*(Hz|kHz|MHz|GHz)\s*,\s*({number})\s*([A-Za-z]+)", line, re.IGNORECASE)
        if not match:
            raise ValueError(f"unrecognized FFT peak row: {line!r}")
        rank, frequency, unit, amplitude, amplitude_unit = match.groups()
        canonical = next((name for name in prefix if name.lower() == unit.lower()), None)
        if canonical is None:
            raise ValueError(f"unsupported FFT frequency unit: {unit}")
        rows.append(FFTPeak(int(rank), float(frequency) * prefix[canonical], float(amplitude), amplitude_unit))
    return tuple(rows)


_HIST_COMMANDS = {
    "enabled": "ENABle", "histogram_type": "TYPE", "source": "SOURce",
    "height_div": "HEIGht", "left": "RANGe:LEFT", "right": "RANGe:RIGHt",
    "top": "RANGe:TOP", "bottom": "RANGe:BOTTom",
}


def configure_histogram(scope: Rigol, settings: HistogramSettings) -> HistogramSettings:
    profile_for(scope).require("histogram")
    if not isinstance(settings, HistogramSettings):
        raise TypeError("settings must be HistogramSettings")
    changes = {f.name: getattr(settings, f.name) for f in fields(settings) if getattr(settings, f.name) is not None}
    if "enabled" in changes:
        _bool(changes["enabled"])
    if "histogram_type" in changes:
        kind = str(changes["histogram_type"]).upper()
        if kind not in {"HORIZONTAL", "VERTICAL"}:
            raise ValueError("histogram_type must be HORIZONTAL or VERTICAL")
        changes["histogram_type"] = kind
    if "source" in changes and (type(changes["source"]) is not int or changes["source"] not in range(1, 5)):
        raise ValueError("histogram source must be channel 1-4")
    if "height_div" in changes and (type(changes["height_div"]) is not int or changes["height_div"] not in range(1, 5)):
        raise ValueError("height_div must be 1-4")
    for name in ("left", "right", "top", "bottom"):
        if name in changes:
            changes[name] = _finite(name, changes[name])
    old_left = float(scope.query(":HISTogram:RANGe:LEFT?"))
    old_right = float(scope.query(":HISTogram:RANGe:RIGHt?"))
    old_top = float(scope.query(":HISTogram:RANGe:TOP?"))
    old_bottom = float(scope.query(":HISTogram:RANGe:BOTTom?"))
    left = changes.get("left", old_left)
    right = changes.get("right", old_right)
    top = changes.get("top", old_top)
    bottom = changes.get("bottom", old_bottom)
    if left >= right or bottom >= top:
        raise ValueError("histogram limits require left < right and bottom < top")
    source = changes.get("source", int(re.search(r"(\d+)$", scope.query(":HISTogram:SOURce?")).group(1)))
    kind = changes.get("histogram_type", scope.query(":HISTogram:TYPE?")).upper()
    if any(name in changes for name in ("left", "right")):
        scale = float(scope.query(":TIMebase:MAIN:SCALe?"))
        offset = float(scope.query(":TIMebase:MAIN:OFFSet?"))
        low, high = offset - 5*scale, offset + 5*scale
        if not (low <= left < right <= high):
            raise ValueError("horizontal histogram limits must fit the visible timebase range")
    if any(name in changes for name in ("top", "bottom")):
        scale = float(scope.query(f":CHANnel{source}:SCALe?"))
        offset = float(scope.query(f":CHANnel{source}:OFFSet?"))
        low, high = -4*scale-offset, 4*scale-offset
        if not (low <= bottom < top <= high):
            raise ValueError("vertical histogram limits must fit the selected channel range")
    require_afg_off(scope)
    ordered = [(name, value) for name, value in changes.items() if name not in {"enabled", "left", "right", "top", "bottom"}]
    if "left" in changes and "right" in changes:
        pair = [("right", right), ("left", left)] if left >= old_right else [("left", left), ("right", right)]
        ordered.extend(pair)
    else:
        ordered.extend((name, changes[name]) for name in ("left", "right") if name in changes)
    if "top" in changes and "bottom" in changes:
        pair = [("top", top), ("bottom", bottom)] if bottom >= old_top else [("bottom", bottom), ("top", top)] if top <= old_bottom else [("top", top), ("bottom", bottom)]
        ordered.extend(pair)
    else:
        ordered.extend((name, changes[name]) for name in ("top", "bottom") if name in changes)
    if "enabled" in changes:
        ordered.append(("enabled", changes["enabled"]))
    for name, value in ordered:
        command = _HIST_COMMANDS[name]
        if name == "enabled":
            value = _bool(value)
        elif name == "histogram_type":
            value = "HORizontal" if value == "HORIZONTAL" else "VERTical"
        elif name == "source":
            value = f"CHANnel{value}"
        scope.write(f":HISTogram:{command} {value}")
    require_no_errors(scope)
    result = read_histogram(scope)
    for name, expected in changes.items():
        actual = getattr(result, name)
        if name == "histogram_type":
            matches = actual == expected
        elif name in {"left", "right", "top", "bottom"}:
            matches = math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-12)
        else:
            matches = actual == expected
        if not matches:
            raise RuntimeError(f"histogram readback mismatch for {name}: requested {expected!r}, got {actual!r}")
    return result


def read_histogram(scope: Rigol) -> HistogramSettings:
    profile_for(scope).require("histogram")
    values = {name: scope.query(f":HISTogram:{command}?") for name, command in _HIST_COMMANDS.items()}
    require_no_errors(scope)
    enable_text = values["enabled"].upper()
    if enable_text not in {"1", "0", "ON", "OFF"}:
        raise ValueError(f"invalid histogram enabled state: {values['enabled']!r}")
    kind = values["histogram_type"].upper()
    if not (kind.startswith("HOR") or kind.startswith("VERT")):
        raise ValueError(f"invalid histogram type: {values['histogram_type']!r}")
    source_match = re.fullmatch(r"CHAN(?:NEL)?([1-4])", values["source"].upper())
    if not source_match:
        raise ValueError(f"invalid histogram source: {values['source']!r}")
    try:
        height = int(float(values["height_div"]))
        left, right = float(values["left"]), float(values["right"])
        top, bottom = float(values["top"]), float(values["bottom"])
    except ValueError as exc:
        raise ValueError("instrument returned invalid histogram numeric readback") from exc
    if height not in range(1, 5) or not all(math.isfinite(v) for v in (left, right, top, bottom)):
        raise ValueError("instrument returned out-of-range histogram readback")
    if left >= right or bottom >= top:
        raise ValueError("instrument returned unordered histogram limits")
    return HistogramSettings(
        enabled=enable_text in {"1", "ON"},
        histogram_type="HORIZONTAL" if kind.startswith("HOR") else "VERTICAL",
        source=int(source_match.group(1)), height_div=height,
        left=left, right=right, top=top, bottom=bottom,
    )


def read_histogram_statistics(scope: Rigol) -> HistogramStatistics:
    profile_for(scope).require("histogram")
    raw = scope.query(":HISTogram:STATistics:RESult?")
    require_no_errors(scope)
    contents = raw.strip().strip("[]")
    parsed = {}
    for item in contents.split(","):
        if ":" in item:
            key, value = item.split(":", 1)
            parsed[key.strip()] = value.strip()
    if not parsed:
        raise ValueError(f"unrecognized histogram statistics response: {raw!r}")
    return HistogramStatistics(parsed)
