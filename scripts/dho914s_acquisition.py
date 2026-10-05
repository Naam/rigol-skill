"""Validated DHO914S acquisition, channel, decode, and Bode controls.

Commands follow the April 2025 DHO800/DHO900 Programming Guide, pp. 11-84.
The caller supplies a connected, model-verified Rigol transport.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from dho800900_models import profile_for


@dataclass(frozen=True)
class Field:
    command: str
    kind: str
    allowed: tuple[str, ...] = ()
    low: float = -math.inf
    high: float = math.inf


def enum(command: str, *values: str) -> Field:
    return Field(command, "enum", values)


def number(command: str, low: float, high: float, *, integer: bool = False) -> Field:
    return Field(command, "int" if integer else "float", (), low, high)


def boolean(command: str) -> Field:
    return Field(command, "bool")


CHANNEL_SOURCE = tuple(f"CHANnel{n}" for n in range(1, 5))
DIGITAL_SOURCE = tuple(f"D{n}" for n in range(16))
SOURCE = CHANNEL_SOURCE + DIGITAL_SOURCE
SOURCE_OFF = SOURCE + ("OFF",)

AUTOSET = {
    "peak": boolean("PEAK"), "open_channels": boolean("OPENch"),
    "overlap": boolean("OVERlap"), "keep_coupling": boolean("KEEPcoup"),
    "lock": boolean("LOCK"), "enabled": boolean("ENAble"),
}
ACQUISITION = {
    "averages": number("AVERages", 2, 65536, integer=True),
    "memory_depth": enum("MDEPth", "AUTO", "1K", "10K", "100K", "1M", "5M", "10M", "25M", "50M",
                         "1000", "10000", "100000", "1000000", "5000000", "10000000", "25000000", "50000000",
                         "1E3", "1E4", "1E5", "1E6", "5E6", "1E7", "2.5E7", "5E7"),
    "type": enum("TYPE", "NORMal", "PEAK", "AVERages", "ULTRa"),
    "ultra_mode": enum("ULTRa:MODE", "ADJacent", "OVERlay", "WATerfall", "PERSpective", "MOSaic"),
    "ultra_timeout": number("ULTRa:TIMeout", 1e-6, 1),
    "ultra_max_frames": number("ULTRa:MAXFrame", 1, math.inf, integer=True),
}
CHANNEL = {
    "bandwidth": enum("BWLimit", "OFF", "20M"),
    "coupling": enum("COUPling", "AC", "DC", "GND"),
    "display": boolean("DISPlay"), "invert": boolean("INVert"),
    "offset": number("OFFSet", -100, 100),
    "time_calibration": number("TCALibrate", -100e-9, 100e-9),
    "scale": number("SCALe", 2e-4, 10),
    "probe": enum("PROBe", *(str(x) for x in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000))),
    "label_show": boolean("LABel:SHOW"),
    "label": Field("LABel:CONTent", "label"),
    "units": enum("UNITs", "WATT", "AMPere", "VOLTage", "UNKNown"),
    "vernier": boolean("VERNier"),
    "position": number("POSition", -100, 100),
}
BUS = {
    "mode": enum("MODE", "PARallel", "RS232", "SPI", "IIC", "LIN", "CAN"),
    "display": boolean("DISPlay"),
    "format": enum("FORMat", "HEX", "ASCii", "DEC", "BIN"),
    "event": boolean("EVENt"), "label": boolean("LABel"),
    "position": number("POSition", -250, 250, integer=True),
    "parallel_bus": enum("PARallel:BUS", "D7D0", "D15D8", "D15D0", "D0D7", "D8D15", "D0D15", *CHANNEL_SOURCE, "USER"),
    "parallel_clock": enum("PARallel:CLK", *SOURCE_OFF),
    "parallel_slope": enum("PARallel:SLOPe", "POSitive", "NEGative", "BOTH"),
    "parallel_width": number("PARallel:WIDTh", 1, 4, integer=True),
    "parallel_bit": number("PARallel:BITX", 0, 3, integer=True),
    "parallel_source": enum("PARallel:SOURce", *SOURCE),
    "parallel_endian": enum("PARallel:ENDian", "MSB", "LSB"),
    "parallel_polarity": enum("PARallel:POLarity", "NEGative", "POSitive"),
    "rs232_tx": enum("RS232:TX", *SOURCE_OFF),
    "rs232_rx": enum("RS232:RX", *SOURCE_OFF),
    "rs232_polarity": enum("RS232:POLarity", "POSitive", "NEGative"),
    "rs232_parity": enum("RS232:PARity", "NONE", "ODD", "EVEN"),
    "rs232_endian": enum("RS232:ENDian", "MSB", "LSB"),
    "rs232_baud": number("RS232:BAUD", 1, 20_000_000, integer=True),
    "rs232_data_bits": number("RS232:DBITs", 5, 9, integer=True),
    "rs232_stop_bits": enum("RS232:SBITs", "1", "1.5", "2"),
    "iic_clock": enum("IIC:SCLK:SOURce", *SOURCE),
    "iic_data": enum("IIC:SDA:SOURce", *SOURCE),
    "iic_exchange": boolean("IIC:EXCHange"),
    "iic_address": enum("IIC:ADDRess", "NORMal", "RW"),
    "spi_clock": enum("SPI:SCLK:SOURce", *SOURCE),
    "spi_clock_slope": enum("SPI:SCLK:SLOPe", "POSitive", "NEGative"),
    "spi_miso": enum("SPI:MISO:SOURce", *SOURCE_OFF),
    "spi_mosi": enum("SPI:MOSI:SOURce", *SOURCE_OFF),
    "spi_polarity": enum("SPI:POLarity", "HIGH", "LOW"),
    "spi_miso_polarity": enum("SPI:MISO:POLarity", "HIGH", "LOW"),
    "spi_mosi_polarity": enum("SPI:MOSI:POLarity", "HIGH", "LOW"),
    "spi_data_bits": number("SPI:DBITs", 4, 32, integer=True),
    "spi_endian": enum("SPI:ENDian", "MSB", "LSB"),
    "spi_mode": enum("SPI:MODE", "CS", "TIMeout"),
    "spi_timeout": number("SPI:TIMeout:TIME", 8e-9, 10),
    "spi_select": enum("SPI:SS:SOURce", *SOURCE),
    "spi_select_polarity": enum("SPI:SS:POLarity", "HIGH", "LOW"),
    "can_source": enum("CAN:SOURce", *SOURCE),
    "can_signal": enum("CAN:STYPe", "TX", "RX", "CANH", "CANL", "DIFFerential"),
    "can_baud": number("CAN:BAUD", 10_000, 5_000_000, integer=True),
    "can_sample_point": number("CAN:SPOint", 10, 90, integer=True),
    "lin_parity": boolean("LIN:PARity"),
    "lin_source": enum("LIN:SOURce", *SOURCE),
    "lin_standard": enum("LIN:STANdard", "V1X", "V2X", "MIXed"),
}
BODE = {
    "sweep_type": enum("SWEeptype", "LOG", "LINE"),
    "input": enum("REF:IN", *CHANNEL_SOURCE),
    "output": enum("REF:OUT", *CHANNEL_SOURCE),
    "start_hz": number("STARt", 10, 24_990_000),
    "stop_hz": number("STOP", 100, 25_000_000),
    "points": number("POINts", 10, 300, integer=True),
}
COUNTER = {
    "enabled": boolean("ENABle"),
    "source": enum("SOURce", *SOURCE),
    "mode": enum("MODE", "FREQuency", "PERiod", "TOTalize"),
    "digits": number("NDIGits", 3, 6, integer=True),
    "statistics": boolean("TOTalize:ENABle"),
}


def _value(field: Field, value: object) -> str:
    if field.kind == "bool":
        if type(value) is not bool:
            raise ValueError("boolean setting requires bool")
        return "ON" if value else "OFF"
    if field.kind == "enum":
        if not isinstance(value, str):
            raise ValueError("setting requires a named value")
        for allowed in field.allowed:
            if value.upper() == allowed.upper():
                return allowed
        raise ValueError(f"invalid {field.command}: {value}")
    if field.kind == "label":
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9 _.-]{1,32}", value):
            raise ValueError("label requires 1-32 safe ASCII characters")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("numeric setting requires a finite number")
    if field.kind == "int" and int(value) != value:
        raise ValueError("setting requires an integer")
    if not field.low <= value <= field.high:
        raise ValueError(f"{field.command} outside {field.low:g}..{field.high:g}")
    return str(int(value)) if field.kind == "int" else f"{value:.12g}"


def _check_errors(scope) -> None:
    errors = scope.errors()
    if len(errors) != 1 or not re.match(r"^\+?0\s*,", errors[0]):
        raise RuntimeError(f"instrument errors: {errors}")


def _prefix(group: str, index: int | None = None) -> str:
    if index is not None and (type(index) is not int or not 1 <= index <= 4):
        raise ValueError("channel or bus index must be 1..4")
    return f":{group}{index if index is not None else ''}"


def _memory_points(value: str) -> float:
    value = value.upper()
    if value == "AUTO":
        return 0
    if value.endswith(("K", "M")):
        return float(value[:-1]) * (1000 if value.endswith("K") else 1_000_000)
    return float(value)


def read_settings(scope, group: str, fields: tuple[str, ...] | None = None, index: int | None = None) -> dict[str, str]:
    profile = profile_for(scope)
    if group == "BODeplot":
        profile.require("bode")
    if group == "CHANnel" and index is not None:
        profile.analog_channel(index)
    schemas = {"AUToset": AUTOSET, "ACQuire": ACQUISITION, "CHANnel": CHANNEL,
               "BUS": BUS, "BODeplot": BODE, "COUNter": COUNTER}
    if group not in schemas:
        raise ValueError("unknown settings group")
    schema = schemas[group]
    fields = tuple(schema) if fields is None else tuple(fields)
    if any(field not in schema for field in fields):
        raise ValueError("unknown setting")
    if (group in {"CHANnel", "BUS"}) != (index is not None):
        raise ValueError("channel or bus index required only for indexed groups")
    prefix = _prefix(group, index)
    return {key: scope.query(f"{prefix}:{schema[key].command}?") for key in fields}


def configure_settings(scope, group: str, changes: dict[str, object], index: int | None = None) -> dict[str, str]:
    """Validate all values, force AFG off, write, read back, and check errors."""
    profile = profile_for(scope)
    if group == "BODeplot":
        profile.require("bode")
    if group == "CHANnel" and index is not None:
        profile.analog_channel(index)
    schemas = {"AUToset": AUTOSET, "ACQuire": ACQUISITION, "CHANnel": CHANNEL,
               "BUS": BUS, "BODeplot": BODE, "COUNter": COUNTER}
    if group not in schemas or not changes:
        raise ValueError("unknown group or empty change set")
    schema = schemas[group]
    if any(key not in schema for key in changes):
        raise ValueError("unknown setting")
    if (group in {"CHANnel", "BUS"}) != (index is not None):
        raise ValueError("channel or bus index required only for indexed groups")
    prefix = _prefix(group, index)
    encoded = {key: _value(schema[key], value) for key, value in changes.items()}
    for value in encoded.values():
        if re.fullmatch(r"CHAN(?:NEL)?[1-4]|D(?:1[0-5]|[0-9])|EXT", value.upper()):
            profile.source(value, digital=True, external=True)
    if group == "BUS":
        if encoded.get("mode", "").upper() == "LIN" or any(key.startswith("lin_") for key in encoded):
            profile.require("lin")
        if encoded.get("spi_mode", "").upper() == "CS" or any(key.startswith("spi_select") for key in encoded):
            profile.require("spi_cs")
    if group == "ACQuire" and "memory_depth" in encoded:
        enabled = sum(scope.query(f":CHANnel{n}:DISPlay?").upper() in {"1", "ON"}
                      for n in range(1, profile.analog_channels + 1))
        maximum = profile.max_memory_points(max(1, enabled))
        if _memory_points(encoded["memory_depth"]) > maximum:
            raise ValueError(f"memory depth exceeds {maximum:g} points with {enabled} enabled channels")
    if group == "ACQuire" and "averages" in encoded:
        n = int(encoded["averages"])
        if n & (n - 1):
            raise ValueError("averages must be a power of two")
    if group == "COUNter" and changes.get("statistics") is True and changes.get("mode", "").upper() == "TOTALIZE":
        raise ValueError("statistics are unavailable in totalize mode")
    if group == "BUS" and "parallel_bit" in encoded:
        width = changes.get("parallel_width")
        if width is None:
            width = int(scope.query(f"{prefix}:PARallel:WIDTh?"))
        if int(encoded["parallel_bit"]) >= width:
            raise ValueError("parallel bit must be smaller than bus width")
    if group == "BODeplot":
        if "start_hz" in encoded or "stop_hz" in encoded:
            current_start = float(scope.query(":BODeplot:STARt?"))
            current_stop = float(scope.query(":BODeplot:STOP?"))
            start = float(encoded.get("start_hz", current_start))
            stop = float(encoded.get("stop_hz", current_stop))
            if start >= stop:
                raise ValueError("Bode start must be below stop")
    if group == "CHANnel" and ("offset" in encoded or "position" in encoded):
        scale = float(encoded.get("scale", scope.query(f"{prefix}:SCALe?")))
        limit = 0.5 if scale < 0.0005 else 1 if scale <= 0.065 else 8 if scale <= 0.260 else 20 if scale <= 2.65 else 100
        for key in ("offset", "position"):
            if key in encoded and abs(float(encoded[key])) > limit:
                raise ValueError(f"{key} exceeds the scale-dependent limit of {limit:g} V")
    if group == "CHANnel" and "scale" in encoded:
        probe = float(encoded.get("probe", scope.query(f"{prefix}:PROBe?")))
        scale = float(encoded["scale"])
        if not 0.0002 * probe <= scale <= 10 * probe:
            raise ValueError("scale outside DHO900 probe-dependent range")
    scope.afg_off()
    if group == "BODeplot":
        scope.write(":BODeplot:RUNStop OFF")
        scope.write(":BODeplot:ENABle OFF")
    scope.write("*CLS")
    try:
        items = list(encoded.items())
        if group == "BODeplot" and "start_hz" in encoded and "stop_hz" in encoded:
            if start >= current_stop:
                items.sort(key=lambda item: item[0] != "stop_hz")
            elif stop <= current_start:
                items.sort(key=lambda item: item[0] != "start_hz")
        for key, value in items:
            scope.write(f"{prefix}:{schema[key].command} {value}")
        result = read_settings(scope, group, tuple(changes), index)
        _check_errors(scope)
        for key, requested in encoded.items():
            returned = result[key].strip().upper()
            field = schema[key]
            if group == "ACQuire" and key == "memory_depth" and requested != "AUTO":
                multiplier = 1000 if requested.endswith("K") else 1_000_000 if requested.endswith("M") else 1
                depth = float(requested[:-1]) * multiplier if multiplier != 1 else float(requested)
                if not math.isclose(float(returned.replace("K", "E3").replace("M", "E6")), depth, rel_tol=1e-4):
                    raise RuntimeError(f"{key} readback mismatch: {returned}")
                continue
            if field.kind == "bool" and returned not in ({"1", "ON"} if requested == "ON" else {"0", "OFF"}):
                raise RuntimeError(f"{key} readback mismatch: {returned}")
            if field.kind in {"int", "float"} and not math.isclose(float(returned), float(requested), rel_tol=1e-4, abs_tol=1e-8):
                raise RuntimeError(f"{key} readback mismatch: {returned}")
            normalized = requested.upper().replace("CHANNEL", "CHAN")
            returned_normalized = returned.replace("CHANNEL", "CHAN")
            if field.kind == "enum" and not normalized.startswith(returned_normalized) and not returned_normalized.startswith(normalized):
                raise RuntimeError(f"{key} readback mismatch: {returned}")
            if field.kind == "label" and returned != requested.upper():
                raise RuntimeError(f"{key} readback mismatch: {returned}")
        return result
    finally:
        if group == "BODeplot":
            try:
                scope.write(":BODeplot:RUNStop OFF")
                scope.write(":BODeplot:ENABle OFF")
            finally:
                scope.afg_off()


def acquisition_state(scope) -> dict[str, str]:
    state = read_settings(scope, "ACQuire")
    state["sample_rate"] = scope.query(":ACQuire:SRATe?")
    return state


def bus_data(scope, bus: int) -> str:
    return scope.query(f"{_prefix('BUS', bus)}:DATA?")


def bus_threshold(scope, bus: int, source: str, value: float | None = None) -> str:
    if source not in {"PAL", "TX", "RX", "SCL", "SDA", "CS", "CLK", "MISO", "MOSI", "LIN", "CAN", "PALCLK", "CH1", "CH2", "CH3", "CH4"}:
        raise ValueError("unknown decode threshold source")
    prefix = _prefix("BUS", bus)
    if value is not None:
        numeric = _value(number("THReshold", -1000, 1000), value)
        scope.afg_off()
        scope.write("*CLS")
        scope.write(f"{prefix}:THReshold {numeric},{source}")
    result = scope.query(f"{prefix}:THReshold? {source}")
    _check_errors(scope)
    if value is not None and not math.isclose(float(result), value, rel_tol=1e-4, abs_tol=1e-8):
        raise RuntimeError("threshold readback mismatch")
    return result


def autoset(scope) -> None:
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":AUToset")
    _check_errors(scope)


def acquire(scope, action: str) -> None:
    commands = {"clear": ":CLEar", "run": ":RUN", "stop": ":STOP",
                "single": ":SINGle", "force": ":TFORce"}
    if action not in commands:
        raise ValueError("unknown acquisition action")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(commands[action])
    _check_errors(scope)


def counter_current(scope) -> str:
    return scope.query(":COUNter:CURRent?")


def clear_counter(scope) -> None:
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":COUNter:TOTalize:CLEar")
    _check_errors(scope)


def bode_state(scope) -> dict[str, str]:
    state = read_settings(scope, "BODeplot")
    state["enabled"] = scope.query(":BODeplot:ENABle?")
    state["running"] = scope.query(":BODeplot:RUNStop?")
    return state


def bode_voltage(scope, band: str, amplitude: float | None = None) -> str:
    """Read or set Bode sweep amplitude for a documented frequency band."""
    profile_for(scope).require("bode")
    bands = {"ALL", "10", "100", "1K", "10K", "100K", "1M", "10M", "25M",
             "1000", "10000", "100000", "1000000", "10000000", "25000000",
             "1E1", "1E2", "1E3", "1E4", "1E5", "1E6", "1E7", "2.5E7"}
    if not isinstance(band, str) or band.upper() not in bands:
        raise ValueError("unknown Bode voltage band")
    band = band.upper()
    if amplitude is not None:
        value = _value(number("VOLTage", 0.02, 5), amplitude)
        scope.afg_off()
        scope.write(":BODeplot:RUNStop OFF")
        scope.write(":BODeplot:ENABle OFF")
        scope.write("*CLS")
        try:
            scope.write(f":BODeplot:VOLTage {band},{value}")
            result = scope.query(f":BODeplot:VOLTage? {band}")
            _check_errors(scope)
            if not math.isclose(float(result), amplitude, rel_tol=1e-4, abs_tol=1e-8):
                raise RuntimeError("Bode voltage readback mismatch")
            return result
        finally:
            try:
                scope.write(":BODeplot:RUNStop OFF")
                scope.write(":BODeplot:ENABle OFF")
            finally:
                scope.afg_off()
    result = scope.query(f":BODeplot:VOLTage? {band}")
    _check_errors(scope)
    return result


def run_bode(scope, *, seconds: float, confirmation: str) -> dict[str, str]:
    """Run a bounded sweep after the operator confirms the physical connections."""
    profile_for(scope).require("bode")
    if confirmation != "VERIFIED" or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0.05 <= seconds <= 5:
        raise ValueError("Bode requires VERIFIED and 0.05..5 seconds")
    scope.afg_off()
    try:
        scope.write(":BODeplot:ENABle ON")
        scope.write(":BODeplot:RUNStop ON")
        state = bode_state(scope)
        _check_errors(scope)
        if state["enabled"] not in {"1", "ON"} or state["running"] not in {"1", "ON"}:
            raise RuntimeError("Bode did not start")
        time.sleep(seconds)
        return state
    finally:
        try:
            scope.write(":BODeplot:RUNStop OFF")
            scope.write(":BODeplot:ENABle OFF")
        finally:
            scope.afg_off()
