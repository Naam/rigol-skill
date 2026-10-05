"""Typed DHO914S serial-protocol trigger settings from guide sections 3.27.20-24."""

from __future__ import annotations

from dataclasses import dataclass, fields
import math
import re
from typing import Any

from dho800900_models import profile_for


@dataclass(frozen=True)
class TriggerModeState:
    """Common DHO914S trigger-type selection with its canonical guide name."""

    mode: str


_TRIGGER_MODE_TOKENS = {
    "EDGE": "EDGE", "PULSE": "PULSe", "SLOPE": "SLOPe", "VIDEO": "VIDeo",
    "PATTERN": "PATTern", "DURATION": "DURation", "TIMEOUT": "TIMeout",
    "RUNT": "RUNT", "WINDOWS": "WINDow", "DELAY": "DELay", "SETUPHOLD": "SETup",
    "NTHEDGE": "NEDGe", "RS232": "RS232", "IIC": "IIC", "SPI": "SPI",
    "CAN": "CAN", "LIN": "LIN",
}
_TRIGGER_MODE_READBACK = {
    "EDGE": "EDGE", "PULS": "PULSE", "SLOP": "SLOPE", "VID": "VIDEO",
    "PATT": "PATTERN", "DUR": "DURATION", "TIM": "TIMEOUT", "RUNT": "RUNT",
    "WIND": "WINDOWS", "DEL": "DELAY", "SET": "SETUPHOLD", "NEDG": "NTHEDGE",
    "RS232": "RS232", "IIC": "IIC", "SPI": "SPI", "CAN": "CAN", "LIN": "LIN",
}


def read_trigger_mode(scope: Any) -> TriggerModeState:
    """Read the shared trigger selector, including every DHO914S mode."""
    raw = str(scope.query(":TRIGger:MODE?")).strip().upper()
    try:
        mode = _TRIGGER_MODE_READBACK[raw]
    except KeyError as exc:
        raise ValueError(f"trigger mode readback {raw!r} is not documented for DHO914S") from exc
    from dho800900 import require_no_errors
    require_no_errors(scope)
    return TriggerModeState(mode)


def configure_trigger_mode(scope: Any, mode: str | type) -> TriggerModeState:
    """Select any documented DHO914S trigger mode with verified rollback.

    ``mode`` accepts a documented mode name or one of this module's protocol
    config classes. The complete selector set is supported so switching to a
    protocol mode can always restore the previously active trigger type.
    """
    if isinstance(mode, type) and mode in _SPECS:
        canonical = mode.__name__.removesuffix("Config").upper()
    elif isinstance(mode, str):
        canonical = mode.strip().upper()
    else:
        raise TypeError("mode must be a documented trigger mode name or protocol config class")
    canonical = {"WINDOW": "WINDOWS", "SETUP": "SETUPHOLD"}.get(canonical, canonical)
    if canonical not in _TRIGGER_MODE_TOKENS:
        raise ValueError(f"unsupported DHO914S trigger mode {canonical!r}")
    if canonical == "LIN":
        profile_for(scope).require("lin")

    before = read_trigger_mode(scope)
    from dho800900 import require_afg_off, require_no_errors
    require_afg_off(scope)
    try:
        scope.write(f":TRIGger:MODE {_TRIGGER_MODE_TOKENS[canonical]}")
        require_no_errors(scope)
        result = read_trigger_mode(scope)
        if result.mode != canonical:
            raise RuntimeError(f"Rigol did not apply trigger mode {canonical}: read back {result.mode}")
        return result
    except Exception as exc:
        try:
            scope.write(f":TRIGger:MODE {_TRIGGER_MODE_TOKENS[before.mode]}")
            require_no_errors(scope)
            restored = read_trigger_mode(scope)
            if restored.mode != before.mode:
                raise RuntimeError(f"trigger mode rollback read back {restored.mode}, expected {before.mode}")
        except Exception as restore_error:
            raise RuntimeError(f"trigger mode update failed ({exc}); restoring prior mode failed ({restore_error})") from exc
        raise


@dataclass(frozen=True)
class RS232Config:
    source: str | None = None
    level_v: float | None = None
    polarity: str | None = None
    when: str | None = None
    data: int | None = None
    baud: int | None = None
    width: int | None = None
    stop: float | None = None
    parity: str | None = None


@dataclass(frozen=True)
class IICConfig:
    scl: str | None = None
    clock_level_v: float | None = None
    sda: str | None = None
    data_level_v: float | None = None
    when: str | None = None
    address_width: int | None = None
    address: int | None = None
    direction: str | None = None
    data_bytes: int | None = None
    data: int | None = None
    current_bit: int | None = None
    code: int | None = None


@dataclass(frozen=True)
class SPIConfig:
    clk: str | None = None
    scl: str | None = None
    scl_level_v: float | None = None
    slope: str | None = None
    miso: str | None = None
    sda: str | None = None
    data_level_v: float | None = None
    when: str | None = None
    cs: str | None = None
    cs_level_v: float | None = None
    mode: str | None = None
    timeout_s: float | None = None
    width: int | None = None
    data: int | None = None
    current_bit: int | None = None
    code: int | None = None


@dataclass(frozen=True)
class CANConfig:
    baud: int | None = None
    source: str | None = None
    signal_type: str | None = None
    when: str | None = None
    sample_point: int | None = None
    extended_id: bool | None = None
    define: str | None = None
    data_width: int | None = None
    data: int | None = None
    current_bit: int | None = None
    code: int | None = None
    level_v: float | None = None


@dataclass(frozen=True)
class LINConfig:
    source: str | None = None
    level_v: float | None = None
    standard: str | None = None
    baud: int | None = None
    sample_point: int | None = None
    when: str | None = None
    error: str | None = None
    identifier: int | None = None
    data: int | None = None
    current_bit: int | None = None
    code: int | None = None


# field -> SCPI leaf, kind, documented bounds/enumeration
_SPECS: dict[type, dict[str, tuple[str, str, Any]]] = {
    RS232Config: {
        "source": ("SOURce", "source", None), "level_v": ("LEVel", "real", None),
        "polarity": ("POLarity", "enum", ("POSitive", "NEGative")),
        "when": ("WHEN", "enum", ("STARt", "ERRor", "CERRor", "DATA")),
        "data": ("DATA", "int", (0, None)), "baud": ("BAUD", "int", (1, 20_000_000)),
        "width": ("WIDTh", "enum", (5, 6, 7, 8)),
        "stop": ("STOP", "enum", (1, 1.5, 2)),
        "parity": ("PARity", "enum", ("EVEN", "ODD", "NONE")),
    },
    IICConfig: {
        "scl": ("SCL", "source", None), "clock_level_v": ("CLEVel", "real", None),
        "sda": ("SDA", "source", None), "data_level_v": ("DLEVel", "real", None),
        "when": ("WHEN", "enum", ("STARt", "RESTart", "STOP", "NACKnowledge", "ADDRess", "DATA", "ADATa")),
        "address_width": ("AWIDth", "enum", (7, 8, 10)), "address": ("ADDRess", "int", (0, None)),
        "direction": ("DIRection", "enum", ("READ", "WRITe", "RWRite")),
        "data_bytes": ("DBYTes", "int", (1, 5)), "data": ("DATA", "int", (0, None)),
        "current_bit": ("CURRbit", "int", (0, 39)), "code": ("CODE", "enum", (0, 1, 255)),
    },
    SPIConfig: {
        "clk": ("CLK", "source", None), "scl": ("SCL", "source", None),
        "scl_level_v": ("CLEVel", "real", None),
        "slope": ("SLOPe", "enum", ("POSitive", "NEGative")), "miso": ("MISO", "source", None),
        "sda": ("SDA", "source", None), "data_level_v": ("DLEVel", "real", None),
        "when": ("WHEN", "enum", ("CS", "TIMeout")), "cs": ("CS", "source", None),
        "cs_level_v": ("SLEVel", "real", None), "mode": ("MODE", "enum", ("HIGH", "LOW")),
        "timeout_s": ("TIMeout", "real", (16e-9, 1.0)), "width": ("WIDTh", "int", (4, 32)),
        "data": ("DATA", "int", (0, None)), "current_bit": ("CURRbit", "int", (0, 39)),
        "code": ("CODE", "enum", (0, 1, 255)),
    },
    CANConfig: {
        "baud": ("BAUD", "int", (10_000, 5_000_000)), "source": ("SOURce", "source", None),
        "signal_type": ("STYPe", "enum", ("H", "L", "RXTX", "DIFFerential")),
        "when": ("WHEN", "enum", ("SOF", "EOF", "IDRemote", "OVERload", "IDFRame", "DATaframe", "IDData", "ERFRame", "ERANswer", "ERCHeck", "ERFormat", "ERRandom", "ERBit")),
        "sample_point": ("SPOint", "int", (10, 90)), "extended_id": ("EXTended", "bool", None),
        "define": ("DEFine", "enum", ("DATA", "ID")), "data_width": ("DWIDth", "int", (1, 8)),
        "data": ("DATA", "int", (0, None)), "current_bit": ("CURRbit", "int", (0, 39)),
        "code": ("CODE", "enum", (0, 1, 255)), "level_v": ("LEVel", "real", None),
    },
    LINConfig: {
        "source": ("SOURce", "source", None), "level_v": ("LEVel", "real", None),
        "standard": ("STANdard", "enum", ("1X", "2X", "BOTH")),
        "baud": ("BAUD", "int", (1_000, 20_000_000)), "sample_point": ("SAMPlepoint", "int", (10, 90)),
        "when": ("WHEN", "enum", ("SYNCbreak", "ID", "DATA", "IDData", "SLEep", "WAKeup", "ERRor")),
        "error": ("ERRor", "enum", ("SYNC", "ID", "CHECk")), "identifier": ("ID", "int", (0, 63)),
        "data": ("DATA", "int", (0, None)), "current_bit": ("CURRbit", "int", (0, 39)),
        "code": ("CODE", "enum", (0, 1, 255)),
    },
}

_PREFIX = {RS232Config: "RS232", IICConfig: "IIC", SPIConfig: "SPI", CANConfig: "CAN", LINConfig: "LIN"}
_SELECTOR_FIRST = {"when", "address_width", "width", "data_width", "data_bytes", "define", "extended_id"}
_ENUM_ALIASES = {
    "STAR": "STARt", "CERR": "CERRor", "REST": "RESTart", "NACK": "NACKnowledge",
    "ADDR": "ADDRess", "ADAT": "ADATa", "WRIT": "WRITe", "RWR": "RWRite", "POS": "POSitive",
    "NEG": "NEGative", "SYNC": "SYNCbreak", "SYNCBREAK": "SYNCbreak", "IDD": "IDData",
    "IDDATA": "IDData", "SLE": "SLEep", "WAK": "WAKeup", "OVER": "OVERload",
    "IDR": "IDRemote", "IDFR": "IDFRame", "DAT": "DATaframe", "ERFR": "ERFRame",
    "ERAN": "ERANswer", "ERCH": "ERCHeck", "ERF": "ERFormat",
    "ERB": "ERBit", "DIFF": "DIFFerential",
}


def _path(config_type: type, field: str) -> str:
    return f":TRIGger:{_PREFIX[config_type]}:{_SPECS[config_type][field][0]}"


def _source(value: Any) -> str:
    text = str(value).upper()
    digital = re.fullmatch(r"D(?:[0-9]|1[0-5])", text)
    channel = re.fullmatch(r"CHAN(?:NEL)?([1-4])", text)
    if digital:
        return text
    if channel:
        return f"CHANnel{channel.group(1)}"
    raise ValueError("source must be D0-D15 or CHAN1-CHAN4")


def _canonical(kind: str, value: Any, bounds: Any, field: str) -> Any:
    if kind == "source":
        return _source(value)
    if kind == "enum":
        choices = bounds
        if isinstance(value, bool):
            candidate = value
        else:
            text = str(value).upper()
            exact = next((choice for choice in choices if str(choice).upper() == text), None)
            candidate = exact if exact is not None else _ENUM_ALIASES.get(text, str(value))
            candidate = next((choice for choice in choices if str(choice).upper() == str(candidate).upper()), candidate)
            if candidate not in choices:
                prefixes = [choice for choice in choices if str(choice).upper().startswith(text)]
                candidate = prefixes[0] if len(prefixes) == 1 else candidate
        if candidate not in choices:
            raise ValueError(f"{field} must be one of {choices}")
        return candidate
    if kind == "bool":
        if value in (True, 1, "1", "ON", "TRUE"):
            return True
        if value in (False, 0, "0", "OFF", "FALSE"):
            return False
        raise ValueError(f"{field} must be bool")
    if kind == "int":
        if isinstance(value, bool) or int(value) != float(value):
            raise ValueError(f"{field} must be an integer")
        number = int(value)
        low, high = bounds
        if number < low or (high is not None and number > high):
            raise ValueError(f"{field} must be in [{low}, {high}]")
        return number
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    if bounds and not bounds[0] <= number <= bounds[1]:
        raise ValueError(f"{field} must be in [{bounds[0]}, {bounds[1]}]")
    return number


def _parse(kind: str, value: str, bounds: Any, field: str) -> Any:
    if kind == "int":
        number = float(value)
        if not number.is_integer():
            raise ValueError(f"instrument returned non-integer {field}: {value}")
        return int(number)
    if kind == "real":
        return _canonical(kind, value, bounds, field)
    if kind == "bool":
        if value.upper() in {"1", "ON", "TRUE"}:
            return True
        if value.upper() in {"0", "OFF", "FALSE"}:
            return False
        raise ValueError(f"instrument returned invalid boolean {field}: {value}")
    return _canonical(kind, value, bounds, field)


def read_trigger(scope: Any, config_type: type) -> Any:
    """Read every documented field for one protocol into its typed state object."""
    if config_type not in _SPECS:
        raise TypeError("config_type must be RS232Config, IICConfig, SPIConfig, CANConfig, or LINConfig")
    if config_type is LINConfig:
        profile_for(scope).require("lin")
    values = {}
    ordered = list(_SPECS[config_type])
    for selector in ("address_width", "when"):
        if selector in ordered:
            ordered.remove(selector)
            ordered.insert(0, selector)
    for field in ordered:
        _, kind, bounds = _SPECS[config_type][field]
        when = str(values.get("when", "")).upper()
        conditional = {
            RS232Config: {"data": {"DATA"}, "width": {"DATA"}},
            IICConfig: {"address_width": {"ADDRESS", "ADATA"}, "address": {"ADDRESS", "ADATA"}, "direction": {"ADDRESS", "ADATA"}, "data_bytes": {"DATA", "ADATA"}, "data": {"DATA", "ADATA"}, "current_bit": {"DATA", "ADATA"}, "code": {"DATA", "ADATA"}},
            SPIConfig: {"cs": {"CS"}, "cs_level_v": {"CS"}, "mode": {"CS"}, "timeout_s": {"TIMEOUT"}},
            CANConfig: {"extended_id": {"IDREMOTE", "IDR", "IDFRAME", "IDFR"}, "define": {"DATAFRAME", "DAT", "IDDATA", "IDD"}, "data_width": {"DATAFRAME", "DAT", "IDDATA", "IDD"}, "data": {"DATAFRAME", "DAT", "IDDATA", "IDD"}},
            LINConfig: {"error": {"ERROR", "ERR"}, "identifier": {"ID", "IDDATA", "IDD"}, "data": {"DATA"}},
        }.get(config_type, {})
        allowed_when = conditional.get(field)
        if allowed_when and when not in allowed_when:
            values[field] = None
            continue
        if config_type is IICConfig and field == "direction" and values.get("address_width") == 8:
            values[field] = None
            continue
        raw = scope.query(f"{_path(config_type, field)}?")
        values[field] = _parse(kind, raw, bounds, field)
    from dho800900 import require_no_errors
    require_no_errors(scope)
    return config_type(**values)


def configure_trigger(scope: Any, config: Any) -> Any:
    """Validate, apply, and read back a protocol config; restore the full prior state on error."""
    config_type = type(config)
    if config_type not in _SPECS:
        raise TypeError("config must be a protocol config dataclass")
    if config_type is LINConfig:
        profile_for(scope).require("lin")
    requested = {field.name: getattr(config, field.name) for field in fields(config) if getattr(config, field.name) is not None}
    mode_before = read_trigger_mode(scope)
    current = read_trigger(scope, config_type)
    effective = {field.name: getattr(current, field.name) for field in fields(current)}
    effective.update(requested)
    normalized = {}
    for field, value in effective.items():
        if value is None:
            continue
        kind, bounds = _SPECS[config_type][field][1:]
        normalized[field] = _canonical(kind, value, bounds, field)
        if kind == "source":
            profile_for(scope).source(str(normalized[field]), digital=True)
    if config_type is IICConfig:
        if any(name in requested for name in ("address_width", "address", "direction")) and normalized.get("when") not in {"ADDRess", "ADATa"}:
            raise ValueError("IIC address settings are valid only for ADDRess or ADATa")
        if any(name in requested for name in ("data_bytes", "data", "current_bit", "code")) and normalized.get("when") not in {"DATA", "ADATa"}:
            raise ValueError("IIC data settings are valid only for DATA or ADATa")
        if "address" in requested and normalized.get("address_width") is None:
            raise ValueError("set address_width when setting address if the current width is unavailable")
        if "address" in requested and normalized["address"] >= 1 << normalized["address_width"]:
            raise ValueError("address does not fit address_width")
        if normalized.get("address_width") == 8 and ("direction" in requested):
            raise ValueError("IIC direction is unavailable when address_width is 8")
        if "data" in requested and normalized.get("data_bytes") is None:
            raise ValueError("set data_bytes when setting data if the current byte count is unavailable")
        if "data" in requested and normalized["data"] >= 1 << (8 * normalized["data_bytes"]):
            raise ValueError("data does not fit data_bytes")
    if config_type is RS232Config:
        for name in ("data", "width"):
            if name in requested and normalized.get("when") != "DATA":
                raise ValueError(f"RS232 {name} is valid only when when='DATA'")
        if "data" in requested and normalized.get("width") is None:
            raise ValueError("set width when setting data if the current width is unavailable")
        if "data" in requested and normalized["data"] >= 1 << normalized["width"]:
            raise ValueError("data does not fit RS232 width")
    if config_type is SPIConfig:
        if normalized.get("when", "").upper() == "CS":
            profile_for(scope).require("spi_cs")
        if "cs" in requested and normalized["when"] != "CS":
            raise ValueError("SPI cs is valid only when when='CS'")
        if "cs_level_v" in requested and normalized["when"] != "CS":
            raise ValueError("SPI cs_level_v is valid only when when='CS'")
        if "mode" in requested and normalized["when"] != "CS":
            raise ValueError("SPI mode is valid only when when='CS'")
        if "timeout_s" in requested and normalized["when"] != "TIMeout":
            raise ValueError("SPI timeout_s is valid only when when='TIMeout'")
        if "data" in normalized and normalized["data"] >= 1 << normalized["width"]:
            raise ValueError("data does not fit SPI width")
    if config_type is CANConfig:
        if "extended_id" in requested and normalized["when"] not in {"IDRemote", "IDFRame"}:
            raise ValueError("CAN extended_id is valid only for IDRemote or IDFRame")
        if "define" in requested and normalized["when"] not in {"DATaframe", "IDData"}:
            raise ValueError("CAN define is valid only for DATAframe or IDData")
        if "data_width" in requested and normalized["when"] not in {"DATaframe", "IDData"}:
            raise ValueError("CAN data_width is valid only for DATAframe or IDData")
        if "data" in requested and normalized["when"] not in {"DATaframe", "IDData"}:
            raise ValueError("CAN data is valid only for DATAframe or IDData")
        if "data" in requested and normalized["data"] >= 1 << 40:
            raise ValueError("CAN data exceeds the documented 40-bit range")
    if config_type is LINConfig:
        if "error" in requested and normalized["when"] != "ERRor":
            raise ValueError("LIN error is valid only when when='ERRor'")
        if "identifier" in requested and normalized["when"] not in {"ID", "IDData"}:
            raise ValueError("LIN identifier is valid only for ID or IDData")
        if "data" in requested and normalized["when"] != "DATA":
            raise ValueError("LIN data is valid only when when='DATA'")
        if "data" in requested and normalized["data"] >= 1 << 64:
            raise ValueError("LIN data exceeds the documented 64-bit range")

    # An inactive conditional value cannot be snapshotted. Require a separate
    # selector call so a later failure can restore every setting it may mutate.
    for field in requested:
        if getattr(current, field) is None:
            raise ValueError(f"cannot safely set {field} while it is unavailable in the current trigger condition; select the condition first")

    level_source = {
        RS232Config: {"level_v": "source"},
        IICConfig: {"clock_level_v": "scl", "data_level_v": "sda"},
        SPIConfig: {"scl_level_v": "scl", "data_level_v": "miso", "cs_level_v": "cs"},
        CANConfig: {"level_v": "source"}, LINConfig: {"level_v": "source"},
    }[config_type]
    for field, source_field in level_source.items():
        if field not in requested:
            continue
        source = normalized[source_field]
        value = normalized[field]
        if source.startswith("D"):
            low, high = -20.0, 20.0
        else:
            channel = int(source[-1])
            scale = float(scope.query(f":CHANnel{channel}:SCALe?"))
            offset = float(scope.query(f":CHANnel{channel}:OFFSet?"))
            low, high = -4.5 * scale - offset, 4.5 * scale - offset
        if not low <= value <= high:
            raise ValueError(f"{field} must be in the source level range [{low:g}, {high:g}] V")

    from dho800900 import require_no_errors
    before = current
    scope.afg_off()
    require_no_errors(scope)

    def apply(state: Any) -> None:
        values = {f.name: getattr(state, f.name) for f in fields(state)}
        ordered = sorted(values, key=lambda name: (name not in _SELECTOR_FIRST, list(_SPECS[config_type]).index(name)))
        for name in ordered:
            value = values[name]
            if value is None:
                continue
            if config_type is IICConfig and name == "direction" and values.get("address_width") == 8:
                continue
            leaf, kind, _ = _SPECS[config_type][name]
            wire = int(value) if kind == "bool" else value
            if kind == "source":
                wire = _source(value)
            scope.write(f"{_path(config_type, name)} {wire}")
        require_no_errors(scope)

    try:
        # Apply only requested fields in selector-first order; a failed write restores the complete snapshot.
        partial = config_type(**{field.name: normalized[field.name] if field.name in requested else None for field in fields(config)})
        partial_values = {f.name: getattr(partial, f.name) for f in fields(partial) if getattr(partial, f.name) is not None}
        ordered = sorted(partial_values, key=lambda name: (name not in _SELECTOR_FIRST, list(_SPECS[config_type]).index(name)))
        for name in ordered:
            leaf, kind, _ = _SPECS[config_type][name]
            value = partial_values[name]
            wire = int(value) if kind == "bool" else value
            scope.write(f"{_path(config_type, name)} {wire}")
        require_no_errors(scope)
        state = read_trigger(scope, config_type)
        for name, expected in normalized.items():
            if name not in requested:
                continue
            actual = getattr(state, name)
            kind = _SPECS[config_type][name][1]
            matches = math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12) if kind == "real" else actual == expected
            if not matches:
                raise RuntimeError(f"Rigol did not apply {name}: requested {expected!r}, read back {actual!r}")
        configure_trigger_mode(scope, config_type)
        return state
    except Exception as exc:
        try:
            apply(before)
            require_no_errors(scope)
            configure_trigger_mode(scope, mode_before.mode)
        except Exception as restore_error:
            raise RuntimeError(f"protocol trigger update failed ({exc}); restoring prior state failed ({restore_error})") from exc
        raise
