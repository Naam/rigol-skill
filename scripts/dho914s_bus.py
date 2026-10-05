"""Typed DHO914S bus decode controls from programming guide section 3.4."""

from __future__ import annotations

import csv
from dataclasses import dataclass, fields

from dho800900_models import profile_for
import io
import math
import re
from typing import Any


@dataclass(frozen=True)
class BusSettings:
    mode: str | None = None
    display: bool | None = None
    data_format: str | None = None
    event_table: bool | None = None
    label: bool | None = None
    position: int | None = None


@dataclass(frozen=True)
class ParallelConfig:
    source: str | None = None
    clock_source: str | None = None
    slope: str | None = None
    width: int | None = None
    bit: int | None = None
    bit_source: str | None = None
    endian: str | None = None
    polarity: str | None = None


@dataclass(frozen=True)
class RS232Config:
    tx: str | None = None
    rx: str | None = None
    polarity: str | None = None
    parity: str | None = None
    endian: str | None = None
    baud: int | None = None
    data_bits: int | None = None
    stop_bits: float | None = None


@dataclass(frozen=True)
class IICConfig:
    clock_source: str | None = None
    data_source: str | None = None
    exchange: bool | None = None
    address_format: str | None = None


@dataclass(frozen=True)
class SPIConfig:
    clock_source: str | None = None
    clock_slope: str | None = None
    miso_source: str | None = None
    mosi_source: str | None = None
    polarity: str | None = None
    miso_polarity: str | None = None
    mosi_polarity: str | None = None
    data_bits: int | None = None
    endian: str | None = None
    mode: str | None = None
    timeout_s: float | None = None
    select_source: str | None = None
    select_polarity: str | None = None


@dataclass(frozen=True)
class CANConfig:
    source: str | None = None
    signal_type: str | None = None
    baud: int | None = None
    sample_point: int | None = None


@dataclass(frozen=True)
class LINConfig:
    parity: bool | None = None
    source: str | None = None
    standard: str | None = None


@dataclass(frozen=True)
class BusEvent:
    timestamp_s: float | None
    values: tuple[str, ...]


@dataclass(frozen=True)
class BusCapture:
    bus: int
    protocol: str
    columns: tuple[str, ...]
    events: tuple[BusEvent, ...]


_PROTOCOLS = {
    ParallelConfig: ("PARallel", "PARallel", {
        "source": ("BUS", "enum", ("D7D0", "D15D8", "D15D0", "D0D7", "D8D15", "D0D15", "CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4", "USER")),
        "clock_source": ("CLK", "source_off", None), "slope": ("SLOPe", "enum", ("POSitive", "NEGative", "BOTH")),
        "width": ("WIDTh", "int", (1, 4)), "bit": ("BITX", "int", (0, None)),
        "bit_source": ("SOURce", "source", None), "endian": ("ENDian", "enum", ("MSB", "LSB")),
        "polarity": ("POLarity", "enum", ("NEGative", "POSitive")),
    }),
    RS232Config: ("RS232", "RS232", {
        "tx": ("TX", "source", None), "rx": ("RX", "source_off", None),
        "polarity": ("POLarity", "enum", ("POSitive", "NEGative")), "parity": ("PARity", "enum", ("NONE", "ODD", "EVEN")),
        "endian": ("ENDian", "enum", ("MSB", "LSB")), "baud": ("BAUD", "int", (1, 20_000_000)),
        "data_bits": ("DBITs", "enum", (5, 6, 7, 8, 9)), "stop_bits": ("SBITs", "enum", (1, 1.5, 2)),
    }),
    IICConfig: ("IIC", "IIC", {
        "clock_source": ("SCLK:SOURce", "source", None), "data_source": ("SDA:SOURce", "source", None),
        "exchange": ("EXCHange", "bool", None), "address_format": ("ADDRess", "enum", ("NORMal", "RW")),
    }),
    SPIConfig: ("SPI", "SPI", {
        "clock_source": ("SCLK:SOURce", "source", None), "clock_slope": ("SCLK:SLOPe", "enum", ("POSitive", "NEGative")),
        "miso_source": ("MISO:SOURce", "source", None), "mosi_source": ("MOSI:SOURce", "source_off", None),
        "polarity": ("POLarity", "enum", ("HIGH", "LOW")), "miso_polarity": ("MISO:POLarity", "enum", ("HIGH", "LOW")),
        "mosi_polarity": ("MOSI:POLarity", "enum", ("HIGH", "LOW")), "data_bits": ("DBITs", "int", (4, 32)),
        "endian": ("ENDian", "enum", ("MSB", "LSB")), "mode": ("MODE", "enum", ("CS", "TIMeout")),
        "timeout_s": ("TIMeout:TIME", "real", (8e-9, 10.0)), "select_source": ("SS:SOURce", "source", None),
        "select_polarity": ("SS:POLarity", "enum", ("HIGH", "LOW")),
    }),
    CANConfig: ("CAN", "CAN", {
        "source": ("SOURce", "source", None), "signal_type": ("STYPe", "enum", ("TX", "RX", "CANH", "CANL", "DIFFerential")),
        "baud": ("BAUD", "int", (10_000, 5_000_000)), "sample_point": ("SPOint", "int", (10, 90)),
    }),
    LINConfig: ("LIN", "LIN", {
        "parity": ("PARity", "bool", None), "source": ("SOURce", "source", None),
        "standard": ("STANdard", "enum", ("V1X", "V2X", "MIXed")),
    }),
}
_MODE_TYPES = {mode: config_type for config_type, (_, mode, _) in _PROTOCOLS.items()}
_ALIASES = {"PAR": "PARallel", "ASC": "ASCii", "POS": "POSitive", "NEG": "NEGative", "MIX": "MIXed", "DIFF": "DIFFerential", "NORM": "NORMal", "TIM": "TIMeout", **{f"CHAN{i}": f"CHANnel{i}" for i in range(1, 5)}}
_PROTOCOL_CONDITIONAL = {
    ParallelConfig: {"width": "source", "bit": "source", "bit_source": "source"},
    SPIConfig: {"timeout_s": "mode", "select_source": "mode", "select_polarity": "mode"},
}
_ORDER_FIRST = {"mode", "source", "width", "bit", "address_format"}


def _bus(bus: int) -> int:
    if type(bus) is not int or bus not in (1, 2, 3, 4):
        raise ValueError("bus must be an integer from 1 to 4")
    return bus


def _base(bus: int, leaf: str) -> str:
    return f":BUS{_bus(bus)}:{leaf}"


def _path(bus: int, config_type: type, field: str) -> str:
    group, _, specs = _PROTOCOLS[config_type]
    return _base(bus, f"{group}:{specs[field][0]}")


def _source(value: Any, *, off: bool = False) -> str:
    text = str(value).upper()
    if off and text == "OFF":
        return "OFF"
    if re.fullmatch(r"D(?:[0-9]|1[0-5])", text):
        return text
    match = re.fullmatch(r"CHAN(?:NEL)?([1-4])", text)
    if match:
        return f"CHANnel{match.group(1)}"
    raise ValueError("source must be D0-D15 or CHAN1-CHAN4" + (" or OFF" if off else ""))


def _validate(kind: str, value: Any, bounds: Any, field: str) -> Any:
    if kind in {"source", "source_off"}:
        return _source(value, off=kind == "source_off")
    if kind == "bool":
        if value in (True, 1, "1", "ON", "TRUE"):
            return True
        if value in (False, 0, "0", "OFF", "FALSE"):
            return False
        raise ValueError(f"{field} must be boolean")
    if kind == "enum":
        text = str(value).upper()
        text = _ALIASES.get(text, text).upper()
        result = next((item for item in bounds if str(item).upper() == text), None)
        if result is None:
            raise ValueError(f"{field} must be one of {bounds}")
        return result
    if kind == "int":
        if isinstance(value, bool) or int(value) != float(value):
            raise ValueError(f"{field} must be an integer")
        number = int(value)
        if number < bounds[0] or (bounds[1] is not None and number > bounds[1]):
            raise ValueError(f"{field} must be in [{bounds[0]}, {bounds[1]}]")
        return number
    number = float(value)
    if not math.isfinite(number) or not bounds[0] <= number <= bounds[1]:
        raise ValueError(f"{field} must be finite and in [{bounds[0]}, {bounds[1]}]")
    return number


def _parse(kind: str, text: str, bounds: Any, field: str) -> Any:
    if kind == "bool":
        if text.upper() in {"1", "ON", "TRUE"}:
            return True
        if text.upper() in {"0", "OFF", "FALSE"}:
            return False
        raise ValueError(f"invalid boolean returned for {field}: {text}")
    if kind == "int":
        number = float(text)
        if not number.is_integer():
            raise ValueError(f"invalid integer returned for {field}: {text}")
        return int(number)
    if kind == "real":
        return _validate(kind, text, bounds, field)
    return _validate(kind, text, bounds, field)


def _check_errors(scope: Any) -> None:
    from dho800900 import require_no_errors
    require_no_errors(scope)


def read_settings(scope: Any, bus: int) -> BusSettings:
    """Read the common bus display and decode settings."""
    bus = _bus(bus)
    vals = {}
    for field, path, kind, bounds in (
        ("mode", "MODE", "enum", ("PARallel", "RS232", "SPI", "IIC", "LIN", "CAN")),
        ("display", "DISPlay", "bool", None), ("data_format", "FORMat", "enum", ("HEX", "ASCii", "DEC", "BIN")),
        ("event_table", "EVENt", "bool", None), ("label", "LABel", "bool", None),
        ("position", "POSition", "int", (-250, 250)),
    ):
        raw = scope.query(_base(bus, path) + "?")
        vals[field] = _parse(kind, raw, bounds, field)
    _check_errors(scope)
    return BusSettings(**vals)


def configure_settings(scope: Any, bus: int, changes: BusSettings) -> BusSettings:
    """Apply common bus settings; mode switches are staged separately from protocol setup."""
    bus = _bus(bus)
    if not isinstance(changes, BusSettings):
        raise TypeError("changes must be BusSettings")
    before = read_settings(scope, bus)
    requested = {item.name: getattr(changes, item.name) for item in fields(changes) if getattr(changes, item.name) is not None}
    bounds = {"mode": ("enum", ("PARallel", "RS232", "SPI", "IIC", "LIN", "CAN")),
              "display": ("bool", None), "data_format": ("enum", ("HEX", "ASCii", "DEC", "BIN")),
              "event_table": ("bool", None), "label": ("bool", None), "position": ("int", (-250, 250))}
    normalized = {key: _validate(bounds[key][0], value, bounds[key][1], key) for key, value in requested.items()}
    current_mode = before.mode
    target_mode = normalized.get("mode", current_mode)
    if target_mode == "LIN" and current_mode != "LIN":
        profile_for(scope).require("lin")
    if "mode" in requested and any(key != "mode" for key in requested) and target_mode != current_mode:
        raise ValueError("change the bus mode first, then configure that protocol separately")
    if normalized.get("event_table", before.event_table) and not normalized.get("display", before.display):
        raise ValueError("enable bus display before enabling its event table")
    if "label" in requested and normalized["label"] and not normalized.get("display", before.display):
        raise ValueError("enable bus display before enabling its label")
    scope.afg_off()
    _check_errors(scope)

    def apply(state: BusSettings) -> None:
        for key in ("mode", "display", "data_format", "event_table", "label", "position"):
            value = getattr(state, key)
            if value is None:
                continue
            wire = int(value) if key in {"display", "event_table", "label"} else value
            scope.write(f"{_base(bus, {'mode':'MODE','display':'DISPlay','data_format':'FORMat','event_table':'EVENt','label':'LABel','position':'POSition'}[key])} {wire}")
        _check_errors(scope)

    try:
        for key in ("mode", "display", "data_format", "event_table", "label", "position"):
            if key not in normalized:
                continue
            wire = int(normalized[key]) if key in {"display", "event_table", "label"} else normalized[key]
            leaf = {"mode":"MODE", "display":"DISPlay", "data_format":"FORMat", "event_table":"EVENt", "label":"LABel", "position":"POSition"}[key]
            scope.write(f"{_base(bus, leaf)} {wire}")
        _check_errors(scope)
        state = read_settings(scope, bus)
        for key, expected in normalized.items():
            actual = getattr(state, key)
            matches = math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12) if key == "position" else actual == expected
            if not matches:
                raise RuntimeError(f"Rigol did not apply {key}: requested {expected!r}, read back {actual!r}")
        return state
    except Exception as exc:
        try:
            apply(before)
        except Exception as restore_error:
            raise RuntimeError(f"bus settings update failed ({exc}); restoring prior settings failed ({restore_error})") from exc
        raise


def read_protocol(scope: Any, bus: int, config_type: type) -> Any:
    """Read configuration for the selected protocol, marking mode-only fields as None."""
    bus = _bus(bus)
    if config_type not in _PROTOCOLS:
        raise TypeError("unsupported bus protocol config")
    if config_type is LINConfig:
        profile_for(scope).require("lin")
    common = read_settings(scope, bus)
    protocol = _MODE_TYPES[common.mode]
    if protocol is not config_type:
        raise ValueError(f"bus {bus} is in {common.mode} mode, not {config_type.__name__}")
    if config_type is SPIConfig and scope.query(_path(bus, config_type, "mode") + "?").strip().upper() == "CS":
        profile_for(scope).require("spi_cs")
    fieldspec = _PROTOCOLS[config_type][2]
    values: dict[str, Any] = {}
    order = list(fieldspec)
    for selector in ("source", "mode"):
        if selector in order:
            order.remove(selector)
            order.insert(0, selector)
    for field in order:
        leaf, kind, bounds = fieldspec[field]
        mode = str(values.get("mode", "")).upper()
        source = str(values.get("source", "")).upper()
        if config_type is ParallelConfig and field in {"width", "bit", "bit_source"} and source != "USER":
            values[field] = None
            continue
        if config_type is SPIConfig and field in {"timeout_s"} and mode != "TIMEOUT":
            values[field] = None
            continue
        if config_type is SPIConfig and field in {"select_source", "select_polarity"} and mode != "CS":
            values[field] = None
            continue
        raw = scope.query(_path(bus, config_type, field) + "?")
        values[field] = _parse(kind, raw, bounds, field)
    _check_errors(scope)
    return config_type(**values)


def configure_protocol(scope: Any, bus: int, changes: Any) -> Any:
    """Validate and apply a protocol config with rollback from its current-mode snapshot."""
    bus = _bus(bus)
    config_type = type(changes)
    if config_type not in _PROTOCOLS:
        raise TypeError("changes must be a supported bus protocol config")
    if config_type is LINConfig:
        profile_for(scope).require("lin")
    before = read_protocol(scope, bus, config_type)
    requested = {item.name: getattr(changes, item.name) for item in fields(changes) if getattr(changes, item.name) is not None}
    specs = _PROTOCOLS[config_type][2]
    normalized = {key: _validate(specs[key][1], value, specs[key][2], key) for key, value in requested.items()}
    for key in requested:
        if getattr(before, key) is None:
            raise ValueError(f"cannot safely set {key} while it is unavailable in the current decode mode; enable it first")
    if config_type is ParallelConfig:
        effective = {item.name: getattr(before, item.name) for item in fields(before)}
        effective.update(normalized)
        if "width" in requested and effective.get("source") != "USER":
            raise ValueError("parallel width requires source='USER'")
        if "bit" in requested and effective.get("source") != "USER":
            raise ValueError("parallel bit requires source='USER'")
        if "bit_source" in requested and effective.get("source") != "USER":
            raise ValueError("parallel bit_source requires source='USER'")
        if "bit" in requested and effective.get("width") is not None and normalized["bit"] >= effective["width"]:
            raise ValueError("bit must be less than width")
        if "width" in requested and effective.get("bit") is not None and effective["bit"] >= effective["width"] and "bit" not in requested:
            raise ValueError("set bit in the same update when shrinking width below the selected bit")
        if "bit_source" in requested and "bit" not in requested and "bit" not in normalized:
            if before.bit is None:
                raise ValueError("set the selected bit before assigning its channel source")
    if config_type is SPIConfig:
        effective_mode = normalized.get("mode", before.mode)
        if effective_mode == "CS":
            profile_for(scope).require("spi_cs")
        if "timeout_s" in requested and effective_mode != "TIMeout":
            raise ValueError("timeout_s is valid only in TIMeout mode")
        if any(key in requested for key in ("select_source", "select_polarity")) and effective_mode != "CS":
            raise ValueError("SS source and polarity are valid only in CS mode")

    scope.afg_off()
    _check_errors(scope)
    leaf_order = list(specs)
    ordered = sorted(leaf_order, key=lambda key: (key not in _ORDER_FIRST, leaf_order.index(key)))

    def apply(state: Any) -> None:
        for key in ordered:
            value = getattr(state, key)
            if value is None:
                continue
            kind = specs[key][1]
            wire = int(value) if kind == "bool" else value
            scope.write(f"{_path(bus, config_type, key)} {wire}")
        _check_errors(scope)

    try:
        for key in ordered:
            if key not in normalized:
                continue
            kind = specs[key][1]
            wire = int(normalized[key]) if kind == "bool" else normalized[key]
            scope.write(f"{_path(bus, config_type, key)} {wire}")
        _check_errors(scope)
        state = read_protocol(scope, bus, config_type)
        for key, expected in normalized.items():
            actual = getattr(state, key)
            kind = specs[key][1]
            matches = math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12) if kind == "real" else actual == expected
            if not matches:
                raise RuntimeError(f"Rigol did not apply {key}: requested {expected!r}, read back {actual!r}")
        return state
    except Exception as exc:
        try:
            apply(before)
        except Exception as restore_error:
            raise RuntimeError(f"protocol decode update failed ({exc}); restoring prior settings failed ({restore_error})") from exc
        raise


def read_thresholds(scope: Any, bus: int, types: tuple[str, ...]) -> dict[str, float]:
    bus = _bus(bus)
    if not types or any(t.upper() not in {"PAL", "TX", "RX", "SCL", "SDA", "CS", "CLK", "MISO", "MOSI", "LIN", "CAN", "PALCLK", "CH1", "CH2", "CH3", "CH4"} for t in types):
        raise ValueError("types must contain supported threshold source names")
    result = {}
    for source in types:
        key = source.upper()
        result[key] = float(scope.query(f"{_base(bus, 'THReshold')}? {key}"))
    _check_errors(scope)
    return result


def configure_thresholds(scope: Any, bus: int, values: dict[str, float]) -> dict[str, float]:
    bus = _bus(bus)
    if not values:
        raise ValueError("at least one threshold is required")
    allowed = {"PAL", "TX", "RX", "SCL", "SDA", "CS", "CLK", "MISO", "MOSI", "LIN", "CAN", "PALCLK", "CH1", "CH2", "CH3", "CH4"}
    thresholds = {str(key).upper(): float(value) for key, value in values.items()}
    if any(key not in allowed for key in thresholds):
        raise ValueError(f"threshold type must be one of {sorted(allowed)}")
    if any(not math.isfinite(value) for value in thresholds.values()):
        raise ValueError("threshold values must be finite")
    settings = read_settings(scope, bus)
    mode = settings.mode.upper()
    source_for = {"PAL": ("PARallel", "source"), "PALCLK": ("PARallel", "clock_source"), "TX": ("RS232", "tx"),
                  "RX": ("RS232", "rx"), "SCL": ("IIC", "clock_source"), "SDA": ("IIC", "data_source"),
                  "CS": ("SPI", "select_source"), "CLK": ("SPI", "clock_source"), "MISO": ("SPI", "miso_source"),
                  "MOSI": ("SPI", "mosi_source"), "LIN": ("LIN", "source"), "CAN": ("CAN", "source")}
    channel_by_type = {"CH1": "CHANnel1", "CH2": "CHANnel2", "CH3": "CHANnel3", "CH4": "CHANnel4"}
    for key in thresholds:
        if key in channel_by_type:
            source = channel_by_type[key]
        else:
            expected_mode, field = source_for[key]
            if mode != expected_mode.upper():
                raise ValueError(f"{key} threshold requires {expected_mode} decoding mode")
            config_type = _MODE_TYPES[settings.mode]
            config = read_protocol(scope, bus, config_type)
            source = getattr(config, field)
            if source == "OFF" or source is None:
                raise ValueError(f"{key} threshold requires its decode source to be enabled")
            if key == "PAL" and source == "USER":
                source = config.bit_source
        if isinstance(source, str) and source.startswith("D"):
            low, high = -20.0, 20.0
        elif isinstance(source, str) and source.startswith("CHAN"):
            channel = int(source[-1])
            scale = float(scope.query(f":CHANnel{channel}:SCALe?"))
            offset = float(scope.query(f":CHANnel{channel}:OFFSet?"))
            low, high = -5 * scale - offset, 5 * scale - offset
        else:
            low, high = -math.inf, math.inf
        if not low <= thresholds[key] <= high:
            raise ValueError(f"{key} threshold must be in [{low:g}, {high:g}] V")
    before = read_thresholds(scope, bus, tuple(thresholds))
    scope.afg_off()
    _check_errors(scope)
    try:
        for key, value in thresholds.items():
            scope.write(f"{_base(bus, 'THReshold')} {value:g},{key}")
        _check_errors(scope)
        result = read_thresholds(scope, bus, tuple(thresholds))
        for key, expected in thresholds.items():
            if not math.isclose(result[key], expected, rel_tol=1e-9, abs_tol=1e-12):
                raise RuntimeError(f"Rigol did not apply {key} threshold: requested {expected}, read back {result[key]}")
        return result
    except Exception as exc:
        try:
            for key, value in before.items():
                scope.write(f"{_base(bus, 'THReshold')} {value:g},{key}")
            _check_errors(scope)
        except Exception as restore_error:
            raise RuntimeError(f"threshold update failed ({exc}); restoring prior values failed ({restore_error})") from exc
        raise


def _decode_tmc(raw: bytes) -> bytes:
    if not raw.startswith(b"#") or len(raw) < 2 or not raw[1:2].isdigit():
        raise ValueError("BUS DATA response is not an IEEE definite-length block")
    digits = int(raw[1:2])
    if digits == 0:
        payload = raw[2:].rstrip(b"\r\n")
        return payload
    header_end = 2 + digits
    if len(raw) < header_end:
        raise ValueError("truncated BUS DATA block length")
    length_text = raw[2:header_end]
    if not length_text.isdigit():
        raise ValueError("invalid BUS DATA block length")
    count = int(length_text)
    payload = raw[header_end:header_end + count]
    if len(payload) != count:
        raise ValueError("truncated BUS DATA block payload")
    return payload


def _time_seconds(value: str) -> float | None:
    match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(s|ms|us|µs|μs|ns)?\s*", value, re.I)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    scale = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ns": 1e-9}[unit]
    return number * scale


def read_events(scope: Any, bus: int) -> BusCapture:
    """Read the instrument's TMC event-table block and return parsed CSV events."""
    bus = _bus(bus)
    scope.afg_off()
    raw = scope.instrument.query_raw(_base(bus, "DATA?"))
    payload = _decode_tmc(raw)
    text = payload.decode("utf-8-sig")
    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError("BUS DATA block contains no event table")
    protocol = lines[0].strip().upper()
    rows = list(csv.reader(io.StringIO("\n".join(lines[1:]))))
    if not rows:
        raise ValueError("BUS DATA block contains no CSV header")
    columns = tuple(cell.strip() for cell in rows[0] if cell.strip())
    if not columns:
        raise ValueError("BUS DATA block contains an empty CSV header")
    time_column = next((i for i, name in enumerate(columns) if name.lower() == "time"), None)
    events = []
    for row in rows[1:]:
        values = tuple(cell.strip() for cell in row[:len(columns)])
        if not values or all(not value for value in values):
            continue
        timestamp = _time_seconds(values[time_column]) if time_column is not None and time_column < len(values) else None
        events.append(BusEvent(timestamp, values))
    _check_errors(scope)
    return BusCapture(bus, protocol, columns, tuple(events))


def export_events(scope: Any, bus: int, path: str, *, allow_overwrite: bool = False) -> None:
    """Export a stopped bus event table to instrument storage as CSV."""
    bus = _bus(bus)
    if not allow_overwrite:
        raise ValueError("the instrument overwrites existing files; pass allow_overwrite=True after choosing a safe path")
    if not isinstance(path, str) or not path.lower().endswith(".csv") or any(ch in path for ch in '\"\r\n') or not path.strip():
        raise ValueError("path must be a non-empty CSV path without quotes or line breaks")
    settings = read_settings(scope, bus)
    if not settings.event_table:
        raise ValueError("enable the bus event table before export")
    if scope.query(":TRIGger:STATus?").upper() != "STOP":
        raise RuntimeError("stop acquisition before exporting bus events")
    scope.afg_off()
    _check_errors(scope)
    scope.write(f'{_base(bus, "EEXPort")} "{path}"')
    _check_errors(scope)
