#!/usr/bin/env python3
"""DHO800/DHO900 command-line control and compatible Python helpers."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from dho800900 import (DHO800900, CHANNEL_SOURCES, DIGITAL_MEASUREMENTS,
    DUAL_MEASUREMENTS, MEASUREMENT_TYPES, connect as connect_family,
    normalize_channel_source, normalize_counter_source, normalize_measure_source,
    require_afg_off, require_confirmation, require_no_errors)
from dho800900_models import MODELS, ModelProfile, profile_for


class Waveform(NamedTuple):
    channel: int | str
    mode: str
    x_increment_s: float
    x_origin_s: float
    x_reference: float
    voltage_v: array

    def samples(self):
        for index, voltage in enumerate(self.voltage_v):
            yield self.x_origin_s + (index - self.x_reference) * self.x_increment_s, voltage

    def to_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time_s", "voltage_v"))
            writer.writerows(self.samples())


class WaveformParameters(NamedTuple):
    x_increment_s: float
    x_origin_s: float
    x_reference: float
    y_increment_v: float
    y_origin: float
    y_reference: float


def normalize_waveform_source(source: int | str, profile: ModelProfile = MODELS["DHO914S"]) -> str:
    if type(source) is int:
        profile.analog_channel(source)
        return f"CHANnel{source}"
    if not isinstance(source, str):
        raise ValueError("waveform source must be CHAN1-4, D0-15, or MATH1-4")
    value = source.upper().replace("CHANNEL", "CHAN")
    if re.fullmatch(r"CHAN[1-4]", value):
        profile.source(value)
        return f"CHANnel{value[4:]}"
    if re.fullmatch(r"D(?:[0-9]|1[0-5])", value):
        profile.source(value, digital=True)
        return value
    if re.fullmatch(r"MATH[1-4]", value):
        return value
    raise ValueError("waveform source must be CHAN1-4, D0-15, or MATH1-4")


def read_waveform_parameters(scope: Rigol) -> WaveformParameters:
    """Query the six XY-axis parameter commands in waveform section 3.28."""
    values = [float(scope.query(f":WAVeform:{command}?")) for command in
              ("XINCrement", "XORigin", "XREFerence", "YINCrement", "YORigin", "YREFerence")]
    if not all(math.isfinite(value) for value in values) or values[0] <= 0 or values[3] == 0:
        raise RuntimeError("invalid waveform axis parameters")
    require_no_errors(scope)
    return WaveformParameters(*values)

class Rigol(DHO800900):
    """Compatibility transport for scripts that instantiate a DHO914S directly."""

    def __init__(self, instrument, *, model: str = "DHO914S"):
        super().__init__(instrument, model=model)


def connect(resource: str | None, backend: str, *, expected_model: str | None = "DHO914S"):
    manager, scope, candidate, identity = connect_family(
        resource, backend, expected_model=expected_model)
    return manager, scope, candidate, identity


def set_and_query(scope: Rigol, set_command: str, query_command: str) -> str:
    scope.write(set_command)
    return scope.query(query_command)


def configure_channel(
    scope: Rigol,
    channel: int,
    *,
    display: bool | None = None,
    probe_ratio: float | None = None,
    coupling: str | None = None,
    inverted: bool | None = None,
    bandwidth: str | None = None,
    scale: float | None = None,
    offset: float | None = None,
) -> dict[str, object]:
    """Configure one analog channel with the generator forced off."""
    profile_for(scope).analog_channel(channel)
    if probe_ratio is not None and (not math.isfinite(probe_ratio) or probe_ratio <= 0):
        raise ValueError("probe ratio must be positive")
    if coupling is not None and coupling.upper() not in {"AC", "DC", "GND"}:
        raise ValueError("coupling must be AC, DC, or GND")
    if bandwidth is not None and bandwidth.upper() not in {"OFF", "20M"}:
        raise ValueError("bandwidth must be OFF or 20M")
    if scale is not None and (not math.isfinite(scale) or scale <= 0):
        raise ValueError("scale must be positive")
    if offset is not None and not math.isfinite(offset):
        raise ValueError("offset must be finite")
    scope.afg_off()
    scope.write("*CLS")
    prefix = f":CHANnel{channel}"
    values = {
        "DISPlay": None if display is None else int(display),
        "PROBe": None if probe_ratio is None else f"{probe_ratio:g}",
        "COUPling": None if coupling is None else coupling.upper(),
        "INVert": None if inverted is None else int(inverted),
        "BWLimit": None if bandwidth is None else bandwidth.upper(),
        "SCALe": scale,
        "OFFSet": offset,
    }
    for name, value in values.items():
        if value is not None:
            scope.write(f"{prefix}:{name} {value}")
    require_no_errors(scope)
    state = readback(scope)["channels"][f"rigol_ch{channel}"]
    if probe_ratio is not None and float(state["probe_ratio"]) != probe_ratio:
        raise RuntimeError(f"CH{channel} probe ratio did not change to {probe_ratio:g}X")
    return state


def configure_acquisition(
    scope: Rigol,
    *,
    acquisition_type: str | None = None,
    memory_depth: str | None = None,
    averages: int | None = None,
    timebase: float | None = None,
    time_offset: float | None = None,
) -> dict[str, object]:
    """Configure acquisition and horizontal controls with the generator off."""
    if acquisition_type is not None and not re.fullmatch(r"[A-Za-z]+", acquisition_type):
        raise ValueError("acquisition type must be one SCPI token")
    if memory_depth is not None and not re.fullmatch(r"(?:AUTO|\d+(?:\.\d+)?[KMG]?)", memory_depth.upper()):
        raise ValueError("memory depth must be AUTO or a numeric SCPI value")
    if timebase is not None and (not math.isfinite(timebase) or timebase <= 0):
        raise ValueError("timebase must be positive")
    if time_offset is not None and not math.isfinite(time_offset):
        raise ValueError("time offset must be finite")
    scope.afg_off()
    scope.write("*CLS")
    if acquisition_type is not None:
        scope.write(f":ACQuire:TYPE {acquisition_type}")
    if averages is not None:
        if not 2 <= averages <= 65536:
            raise ValueError("averages must be 2-65536")
        scope.write(f":ACQuire:AVERages {averages}")
    if memory_depth is not None:
        scope.write(f":ACQuire:MDEPth {memory_depth}")
    if timebase is not None:
        scope.write(f":TIMebase:MAIN:SCALe {timebase}")
    if time_offset is not None:
        scope.write(f":TIMebase:MAIN:OFFSet {time_offset}")
    require_no_errors(scope)
    state = readback(scope)
    return {
        "acquisition": state["acquisition"],
        "timebase_s_per_div": state["timebase_s_per_div"],
        "time_offset_s": state["time_offset_s"],
    }


def configure_edge_trigger(
    scope: Rigol,
    *,
    source: str,
    slope: str,
    level: float,
    sweep: str = "NORMal",
    coupling: str = "DC",
) -> dict[str, object]:
    """Configure an edge trigger with the generator off."""
    source = normalize_channel_source(source, profile_for(scope), external=True)
    if slope.upper() not in {"POSITIVE", "NEGATIVE", "RFALL"}:
        raise ValueError("slope must be POSitive, NEGative, or RFALl")
    if sweep.upper() not in {"AUTO", "NORMAL", "SINGLE"}:
        raise ValueError("sweep must be AUTO, NORMal, or SINGle")
    if coupling.upper() not in {"AC", "DC", "LFR", "HFR"}:
        raise ValueError("trigger coupling must be AC, DC, LFR, or HFR")
    if not math.isfinite(level):
        raise ValueError("trigger level must be finite")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":TRIGger:MODE EDGE")
    scope.write(f":TRIGger:EDGE:SOURce {source}")
    scope.write(f":TRIGger:EDGE:SLOPe {slope}")
    scope.write(f":TRIGger:EDGE:LEVel {level}")
    scope.write(f":TRIGger:COUPling {coupling}")
    scope.write(f":TRIGger:SWEep {sweep}")
    require_no_errors(scope)
    return readback(scope)["trigger"]


def configure_pulse_trigger(
    scope: Rigol, *, source: str, polarity: str, when: str,
    level: float, lower_width: float | None = None, upper_width: float | None = None,
    holdoff: float | None = None, sweep: str = "NORMal",
) -> dict[str, object]:
    """Configure width trigger; do not arm or enable any output."""
    source = normalize_counter_source(source, profile_for(scope))
    polarity = polarity.upper()
    when = when.upper()
    if polarity not in {"POSITIVE", "NEGATIVE"}:
        raise ValueError("polarity must be POSITIVE or NEGATIVE")
    if when not in {"GREATER", "LESS", "GLESS"}:
        raise ValueError("when must be GREATER, LESS, or GLESS")
    if sweep.upper() not in {"AUTO", "NORMAL", "SINGLE"}:
        raise ValueError("sweep must be AUTO, NORMAL, or SINGLE")
    if not math.isfinite(level):
        raise ValueError("level must be finite")
    if when in {"GREATER", "GLESS"} and (lower_width is None or not 1e-9 <= lower_width <= 10):
        raise ValueError("lower width must be 1 ns to 10 s")
    if when in {"LESS", "GLESS"} and (upper_width is None or not 1e-9 <= upper_width <= 10):
        raise ValueError("upper width must be 1 ns to 10 s")
    if when == "GLESS" and lower_width >= upper_width:
        raise ValueError("lower width must be smaller than upper width")
    if holdoff is not None and (not math.isfinite(holdoff) or not 8e-9 <= holdoff <= 10):
        raise ValueError("holdoff must be 8 ns to 10 s")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":TRIGger:MODE PULSe")
    scope.write(f":TRIGger:PULSe:SOURce {source}")
    scope.write(f":TRIGger:PULSe:POLarity {polarity}")
    scope.write(f":TRIGger:PULSe:WHEN {when}")
    if lower_width is not None and when in {"GREATER", "GLESS"}:
        scope.write(f":TRIGger:PULSe:LWIDth {lower_width}")
    if upper_width is not None and when in {"LESS", "GLESS"}:
        scope.write(f":TRIGger:PULSe:UWIDth {upper_width}")
    scope.write(f":TRIGger:PULSe:LEVel {level}")
    if holdoff is not None:
        scope.write(f":TRIGger:HOLDoff {holdoff}")
    scope.write(f":TRIGger:SWEep {sweep}")
    require_no_errors(scope)
    return readback(scope)["trigger"]


def configure_square_afg(
    scope: Rigol,
    *,
    frequency: float,
    amplitude: float,
    offset: float,
    duty: float,
    phase: float = 0,
) -> dict[str, object]:
    """Configure the square-wave generator without enabling its output."""
    profile_for(scope).require("afg")
    if not all(math.isfinite(value) for value in (frequency, amplitude, offset, duty, phase)):
        raise ValueError("AFG values must be finite")
    if frequency <= 0 or amplitude <= 0 or not 1 <= duty <= 99:
        raise ValueError("frequency/amplitude must be positive and duty must be 1-99%")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":SOURce:FUNCtion SQUare")
    scope.write(f":SOURce:FREQuency {frequency}")
    scope.write(f":SOURce:VOLTage:AMPLitude {amplitude}")
    scope.write(f":SOURce:VOLTage:OFFSet {offset}")
    scope.write(f":SOURce:PHASe {phase}")
    scope.write(f":SOURce:FUNCtion:SQUare:DUTY {duty}")
    scope.afg_off()
    require_no_errors(scope)
    state = readback(scope)
    return {key: value for key, value in state.items() if key.startswith("afg_")}


def configure_dvm(scope: Rigol, *, source: str, mode: str = "DC", enabled: bool = True) -> dict[str, str]:
    """Set the asynchronous digital voltmeter without changing instrument outputs."""
    source = normalize_channel_source(source, profile_for(scope))
    mode = mode.upper()
    if mode not in {"ACRMS", "DC", "DCRMS"}:
        raise ValueError("DVM mode must be ACRMS, DC, or DCRMS")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(f":DVM:SOURce {source}")
    scope.write(f":DVM:MODE {mode}")
    scope.write(f":DVM:ENABle {'ON' if enabled else 'OFF'}")
    state = {"source": scope.query(":DVM:SOURce?"), "mode": scope.query(":DVM:MODE?"),
             "enabled": scope.query(":DVM:ENABle?")}
    require_no_errors(scope)
    if (state["source"] != source.replace("CHANnel", "CHAN")
            or state["mode"] != {"ACRMS": "ACRM", "DC": "DC", "DCRMS": "DCRM"}[mode]
            or state["enabled"] != str(int(enabled))):
        raise RuntimeError(f"DVM readback differs from requested settings: {state}")
    return state


def configure_counter(
    scope: Rigol, *, source: str, mode: str = "FREQUENCY", digits: int = 4,
    statistics: bool = False, enabled: bool = True,
) -> dict[str, str]:
    """Set the frequency/period/event counter without changing instrument outputs."""
    source = normalize_counter_source(source, profile_for(scope))
    mode = mode.upper()
    if mode not in {"FREQUENCY", "PERIOD", "TOTALIZE"}:
        raise ValueError("counter mode must be FREQUENCY, PERIOD, or TOTALIZE")
    if not 3 <= digits <= 6:
        raise ValueError("counter digits must be 3-6")
    if statistics and mode == "TOTALIZE":
        raise ValueError("counter statistics are unavailable in TOTALIZE mode")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(f":COUNter:SOURce {source}")
    scope.write(f":COUNter:MODE {mode}")
    scope.write(f":COUNter:NDIGits {digits}")
    scope.write(f":COUNter:TOTalize:ENABle {'ON' if statistics else 'OFF'}")
    scope.write(f":COUNter:ENABle {'ON' if enabled else 'OFF'}")
    state = {"source": scope.query(":COUNter:SOURce?"),
             "mode": scope.query(":COUNter:MODE?"),
             "digits": scope.query(":COUNter:NDIGits?"),
             "statistics": scope.query(":COUNter:TOTalize:ENABle?"),
             "enabled": scope.query(":COUNter:ENABle?")}
    require_no_errors(scope)
    if (state["source"] != source.replace("CHANnel", "CHAN")
            or not state["mode"].upper().startswith(mode[:3])
            or state["digits"] != str(digits)
            or state["statistics"] != str(int(statistics))
            or state["enabled"] != str(int(enabled))):
        raise RuntimeError(f"counter readback differs from requested settings: {state}")
    return state


def read_dvm(scope: Rigol) -> str:
    return scope.query(":DVM:CURRent?")


def read_counter(scope: Rigol) -> str:
    return scope.query(":COUNter:CURRent?")


def clear_counter(scope: Rigol) -> None:
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":COUNter:TOTalize:CLEar")
    require_no_errors(scope)


def configure_measurement_statistics(scope: Rigol, *, count: int, enabled: bool) -> dict[str, str]:
    if not 2 <= count <= 100_000:
        raise ValueError("measurement statistics count must be 2-100000")
    scope.afg_off()
    scope.write("*CLS")
    scope.write(f":MEASure:STATistic:COUNt {count}")
    scope.write(f":MEASure:STATistic:DISPlay {'ON' if enabled else 'OFF'}")
    state = {"count": scope.query(":MEASure:STATistic:COUNt?"),
             "enabled": scope.query(":MEASure:STATistic:DISPlay?")}
    require_no_errors(scope)
    if state != {"count": str(count), "enabled": str(int(enabled))}:
        raise RuntimeError(f"measurement statistics readback differs: {state}")
    return state


def measurement_statistic(
    scope: Rigol, *, item: str, source: str, result: str = "CURRENT",
    source_b: str | None = None, add: bool = False,
) -> float | str:
    item = item.upper()
    result = result.upper()
    if item not in MEASUREMENT_TYPES:
        raise ValueError(f"unsupported measurement item {item}")
    if result not in {"MAXIMUM", "MINIMUM", "CURRENT", "AVERAGES", "DEVIATION", "CNT"}:
        raise ValueError(f"unsupported statistic result {result}")
    source = normalize_measure_source(source, item, profile_for(scope))
    if source_b is not None:
        if item not in DUAL_MEASUREMENTS:
            raise ValueError(f"{item} does not take a second source")
        source_b = normalize_measure_source(source_b, item, profile_for(scope))
    suffix = f"{item},{source}" + (f",{source_b}" if source_b else "")
    if add:
        scope.afg_off()
        scope.write("*CLS")
        scope.write(f":MEASure:STATistic:ITEM {suffix}")
        require_no_errors(scope)
    raw = scope.query(f":MEASure:STATistic:ITEM? {result},{suffix}")
    try:
        value = float(raw)
        return value if math.isfinite(value) and abs(value) < 9e37 else "unavailable"
    except ValueError:
        return raw


def reset_measurement_statistics(scope: Rigol) -> None:
    scope.afg_off()
    scope.write("*CLS")
    scope.write(":MEASure:STATistic:RESet")
    require_no_errors(scope)


def timed_afg(scope: Rigol, seconds: float, confirmation: str) -> float:
    """Enable AFG for a bounded host-timed interval and guarantee shutdown."""
    profile_for(scope).require("afg")
    require_confirmation(confirmation)
    if not math.isfinite(seconds) or not 0.05 <= seconds <= 5.0:
        raise ValueError("host-timed AFG duration must be 0.05-5.0 seconds")
    require_afg_off(scope)
    try:
        scope.write(":SOURce:OUTPut:STATe ON")
        started = time.monotonic()
        if scope.query(":SOURce:OUTPut:STATe?") not in {"1", "ON"}:
            raise RuntimeError("Rigol AFG did not confirm ON.")
        time.sleep(max(0, started + seconds - time.monotonic()))
    finally:
        scope.afg_off()
    return time.monotonic() - started


def clear_waveforms(scope: Rigol) -> None:
    """Clear displayed traces with AFG off and acquisition stopped; not a reset."""
    scope.afg_off()
    scope.write(":STOP")
    wait_for(scope, {"STOP"}, 1.0)
    scope.write(":CLEar")
    require_no_errors(scope)


def observe_for(scope: Rigol, seconds: float) -> bytes:
    """Acquire briefly with AFG off, freeze, then return the screen image."""
    if not math.isfinite(seconds) or not 0.05 <= seconds <= 5.0:
        raise ValueError("acquisition duration must be 0.05-5.0 seconds")
    clear_waveforms(scope)
    try:
        scope.write(":RUN")
        time.sleep(seconds)
    finally:
        try:
            scope.write(":STOP")
        finally:
            scope.afg_off()
    wait_for(scope, {"STOP"}, 1.0)
    return scope.screenshot()


def readback(scope: Rigol) -> dict[str, object]:
    profile = profile_for(scope)
    channels: dict[str, object] = {}
    for channel in range(1, profile.analog_channels + 1):
        prefix = f":CHANnel{channel}"
        channels[f"rigol_ch{channel}"] = {
            "display": scope.query(f"{prefix}:DISPlay?"),
            "probe_ratio": scope.query(f"{prefix}:PROBe?"),
            "coupling": scope.query(f"{prefix}:COUPling?"),
            "inverted": scope.query(f"{prefix}:INVert?"),
            "bandwidth": scope.query(f"{prefix}:BWLimit?"),
            "scale_v_per_div": float(scope.query(f"{prefix}:SCALe?")),
            "offset_v": float(scope.query(f"{prefix}:OFFSet?")),
        }
    trigger_mode = scope.query(":TRIGger:MODE?")
    trigger = {"mode": trigger_mode, "sweep": scope.query(":TRIGger:SWEep?"),
               "holdoff_s": float(scope.query(":TRIGger:HOLDoff?"))}
    if trigger_mode.upper().startswith("PULS"):
        trigger.update(source=scope.query(":TRIGger:PULSe:SOURce?"),
                       polarity=scope.query(":TRIGger:PULSe:POLarity?"),
                       when=scope.query(":TRIGger:PULSe:WHEN?"),
                       level_v=float(scope.query(":TRIGger:PULSe:LEVel?")))
        if trigger["when"].upper().startswith(("GRE", "GLES")):
            trigger["lower_width_s"] = float(scope.query(":TRIGger:PULSe:LWIDth?"))
        if trigger["when"].upper().startswith(("LESS", "GLES")):
            trigger["upper_width_s"] = float(scope.query(":TRIGger:PULSe:UWIDth?"))
    else:
        trigger.update(source=scope.query(":TRIGger:EDGE:SOURce?"),
                       slope=scope.query(":TRIGger:EDGE:SLOPe?"),
                       level_v=float(scope.query(":TRIGger:EDGE:LEVel?")),
                       coupling=scope.query(":TRIGger:COUPling?"))
    state = {
        "identity": scope.query("*IDN?"),
        "scpi_version": scope.query(":SYSTem:VERSion?"),
        "run_state": scope.query(":TRIGger:STATus?"),
        "timebase_s_per_div": float(scope.query(":TIMebase:MAIN:SCALe?")),
        "time_offset_s": float(scope.query(":TIMebase:MAIN:OFFSet?")),
        "acquisition": {
            "type": scope.query(":ACQuire:TYPE?"),
            "averages": int(float(scope.query(":ACQuire:AVERages?"))),
            "memory_depth_points": scope.query(":ACQuire:MDEPth?"),
            "sample_rate_sa_per_s": float(scope.query(":ACQuire:SRATe?")),
        },
        "trigger": trigger,
        "channels": channels,
    }
    if profile.afg:
        state.update(
            afg_output=scope.query(":SOURce:OUTPut:STATe?"),
            afg_function=scope.query(":SOURce:FUNCtion?"),
            afg_frequency_hz=float(scope.query(":SOURce:FREQuency?")),
            afg_amplitude_vpp=float(scope.query(":SOURce:VOLTage:AMPLitude?")),
            afg_offset_v=float(scope.query(":SOURce:VOLTage:OFFSet?")),
            afg_phase_deg=float(scope.query(":SOURce:PHASe?")),
            afg_duty_percent=float(scope.query(":SOURce:FUNCtion:SQUare:DUTY?")),
        )
    return state


def wait_for(scope: Rigol, accepted: set[str], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = scope.query(":TRIGger:STATus?").upper()
        if status in accepted:
            return status
        time.sleep(0.02)
    raise TimeoutError(f"Rigol trigger did not reach {sorted(accepted)} within {timeout:.2f} s")


def capture_point(scope: Rigol, evidence_dir: Path, timeout: float, confirmation: str) -> Path:
    profile_for(scope).require("afg")
    require_confirmation(confirmation)
    clear_waveforms(scope)
    try:
        scope.write(":SINGle")
        wait_for(scope, {"WAIT", "RUN"}, 1.0)
        scope.write(":SOURce:OUTPut:STATe ON")
        wait_for(scope, {"STOP"}, timeout)
    finally:
        scope.afg_off()
    scope.write(":STOP")
    return collect_evidence(scope, evidence_dir, "capture")


def timed_capture(
    scope: Rigol,
    evidence_dir: Path,
    seconds: float,
    timeout: float,
    confirmation: str,
) -> tuple[float, Path]:
    """Arm a single acquisition, enable AFG for a bounded interval, then collect evidence."""
    profile_for(scope).require("afg")
    clear_waveforms(scope)
    try:
        scope.write(":SINGle")
        wait_for(scope, {"WAIT", "RUN"}, 1.0)
        elapsed = timed_afg(scope, seconds, confirmation)
        wait_for(scope, {"STOP"}, timeout)
    finally:
        scope.afg_off()
        scope.write(":STOP")
    return elapsed, collect_evidence(scope, evidence_dir, "timed")


def settled_capture(scope: Rigol, settle: float, maximum: float, confirmation: str) -> bytes:
    """Freeze a bounded continuous acquisition after the AFG has settled."""
    profile_for(scope).require("afg")
    require_confirmation(confirmation)
    if not (0.05 <= settle < maximum <= 5.0):
        raise ValueError("require 0.05 <= settle < maximum <= 5 seconds")
    clear_waveforms(scope)
    try:
        scope.write(":RUN")
        wait_for(scope, {"WAIT", "RUN", "TD", "AUTO"}, 1.0)
        scope.write(":SOURce:OUTPut:STATe ON")
        started = time.monotonic()
        if scope.query(":SOURce:OUTPut:STATe?") not in {"1", "ON"}:
            raise RuntimeError("Rigol AFG did not confirm ON.")
        time.sleep(settle)
        trigger_status = scope.query(":TRIGger:STATus?").upper()
        if trigger_status == "WAIT":
            raise RuntimeError("Rigol did not acquire a trigger while AFG was ON.")
        scope.write(":STOP")
        wait_for(scope, {"STOP"}, max(0.01, maximum - (time.monotonic() - started)))
    finally:
        try:
            scope.afg_off()
        finally:
            scope.write(":STOP")
    wait_for(scope, {"STOP"}, 1.0)
    return scope.screenshot()


def query_measurement(scope: Rigol, item: str, source: str, source_b: str | None = None) -> float | str:
    item = item.upper()
    if item not in MEASUREMENT_TYPES:
        raise SystemExit(f"Unsupported measurement {item}; use measurement-types to list choices.")
    try:
        source = normalize_measure_source(source, item, profile_for(scope))
        if source_b is not None:
            if item not in DUAL_MEASUREMENTS:
                raise ValueError(f"{item} does not take a second source")
            source_b = normalize_measure_source(source_b, item, profile_for(scope))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    raw = scope.query(f":MEASure:ITEM? {item},{source}" + (f",{source_b}" if source_b else ""))
    try:
        value = float(raw)
        return value if math.isfinite(value) and abs(value) < 9e37 else "unavailable"
    except ValueError:
        return raw


def annotate_capture(scope: Rigol, items: list[str]) -> bytes:
    """Add measurements to a frozen capture without changing instrument outputs."""
    parsed = []
    for spec in items:
        parts = spec.upper().split(":")
        if len(parts) not in {2, 3} or parts[0] not in MEASUREMENT_TYPES:
            raise ValueError(f"Invalid measurement {spec}; use ITEM:SOURCE[:SOURCE_B]")
        item = parts[0]
        if len(parts) == 3 and item not in DUAL_MEASUREMENTS:
            raise ValueError(f"{item} does not take a second source")
        parsed.append((item, ",".join(normalize_measure_source(source, item, profile_for(scope))
                                      for source in parts[1:])))
    if profile_for(scope).afg and scope.query(":SOURce:OUTPut:STATe?") not in {"0", "OFF"}:
        raise RuntimeError("AFG must be off to annotate a frozen capture.")
    if scope.query(":TRIGger:STATus?").upper() != "STOP":
        raise RuntimeError("Acquisition must be stopped to annotate a frozen capture.")
    scope.write("*CLS")
    for item, source in parsed:
        scope.write(f":MEASure:ITEM {item},{source}")
    require_no_errors(scope)
    time.sleep(0.2)
    return scope.screenshot()


def apply_state(scope: Rigol, state: dict[str, object]) -> None:
    """Restore the readable operating state while always leaving the AFG off."""
    scope.afg_off()
    scope.write(":STOP")
    scope.write("*CLS")
    try:
        for channel in range(1, 5):
            values = state["channels"][f"rigol_ch{channel}"]
            prefix = f":CHANnel{channel}"
            scope.write(f"{prefix}:DISPlay {values['display']}")
            scope.write(f"{prefix}:PROBe {values['probe_ratio']}")
            scope.write(f"{prefix}:COUPling {values['coupling']}")
            scope.write(f"{prefix}:INVert {values['inverted']}")
            scope.write(f"{prefix}:BWLimit {values['bandwidth']}")
            scope.write(f"{prefix}:SCALe {values['scale_v_per_div']}")
            scope.write(f"{prefix}:OFFSet {values['offset_v']}")

        acquisition = state["acquisition"]
        scope.write(f":ACQuire:TYPE {acquisition['type']}")
        if str(acquisition["type"]).upper().startswith("AVER"):
            scope.write(f":ACQuire:AVERages {acquisition['averages']}")
        scope.write(f":ACQuire:MDEPth {acquisition['memory_depth_points']}")
        scope.write(f":TIMebase:MAIN:SCALe {state['timebase_s_per_div']}")
        scope.write(f":TIMebase:MAIN:OFFSet {state['time_offset_s']}")

        trigger = state["trigger"]
        scope.write(f":TRIGger:MODE {trigger['mode']}")
        if str(trigger["mode"]).upper().startswith("PULS"):
            scope.write(f":TRIGger:PULSe:SOURce {trigger['source']}")
            scope.write(f":TRIGger:PULSe:POLarity {trigger['polarity']}")
            scope.write(f":TRIGger:PULSe:WHEN {trigger['when']}")
            if "lower_width_s" in trigger:
                scope.write(f":TRIGger:PULSe:LWIDth {trigger['lower_width_s']}")
            if "upper_width_s" in trigger:
                scope.write(f":TRIGger:PULSe:UWIDth {trigger['upper_width_s']}")
            scope.write(f":TRIGger:PULSe:LEVel {trigger['level_v']}")
        elif str(trigger["mode"]).upper().startswith("EDGE"):
            scope.write(f":TRIGger:EDGE:SOURce {trigger['source']}")
            scope.write(f":TRIGger:EDGE:SLOPe {trigger['slope']}")
            scope.write(f":TRIGger:EDGE:LEVel {trigger['level_v']}")
            scope.write(f":TRIGger:COUPling {trigger['coupling']}")
        else:
            raise ValueError(f"restore does not support {trigger['mode']} trigger state")
        if "holdoff_s" in trigger:
            scope.write(f":TRIGger:HOLDoff {trigger['holdoff_s']}")
        scope.write(f":TRIGger:SWEep {trigger['sweep']}")

        scope.write(f":SOURce:FUNCtion {state['afg_function']}")
        scope.write(f":SOURce:FREQuency {state['afg_frequency_hz']}")
        scope.write(f":SOURce:VOLTage:AMPLitude {state['afg_amplitude_vpp']}")
        scope.write(f":SOURce:VOLTage:OFFSet {state['afg_offset_v']}")
        scope.write(f":SOURce:PHASe {state['afg_phase_deg']}")
        scope.write(f":SOURce:FUNCtion:SQUare:DUTY {state['afg_duty_percent']}")
        errors = scope.errors()
        if not re.match(r"^\+?0\s*,", errors[-1]) or len(errors) != 1:
            raise RuntimeError(f"Rigol rejected restored settings: {errors}")
    finally:
        scope.afg_off()


def restore_state(scope: Rigol, path: Path) -> dict[str, object]:
    requested = json.loads(path.read_text(encoding="utf-8"))
    original = readback(scope)
    for state in (requested, original):
        if not str(state["trigger"]["mode"]).upper().startswith(("EDGE", "PULS")):
            raise ValueError("restore requires EDGE or PULSE trigger state")
    try:
        apply_state(scope, requested)
    except Exception:
        apply_state(scope, original)
        raise
    return readback(scope)


def collect_evidence(scope: Rigol, root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = root / f"{stamp}-{label}"
    output.mkdir(parents=True, exist_ok=False)
    (output / "screen.png").write_bytes(scope.screenshot())
    (output / "setup.bin").write_bytes(scope.setup_data())
    (output / "settings.json").write_text(
        json.dumps(readback(scope), indent=2) + "\n", encoding="utf-8"
    )
    for channel in range(1, profile_for(scope).analog_channels + 1):
        save_visible_waveform(scope, channel, output / f"rigol-ch{channel}.csv")
    return output


def save_visible_waveform(scope: Rigol, channel: int, path: Path) -> None:
    save_waveform(scope, channel, path, "NORMal", 1000)


def read_waveform(
    scope: Rigol, channel: int | str, *, mode: str = "NORMAL", points: int = 1000,
    data_format: str = "BYTE",
) -> Waveform:
    """Return a calibrated waveform using the DHO914S preamble conversion."""
    source = normalize_waveform_source(channel, profile_for(scope))
    source_is_math = source.startswith("MATH")
    if type(points) is not int:
        raise ValueError("points must be an integer")
    mode = mode.upper()
    data_format = data_format.upper()
    if mode not in {"NORMAL", "MAXIMUM", "RAW"} or data_format not in {"BYTE", "WORD", "ASCII"}:
        raise ValueError("mode must be NORMAL/MAXIMUM/RAW and format BYTE/WORD/ASCII")
    if source_is_math and mode != "NORMAL":
        raise ValueError("Math sources support NORMAL waveform mode only")
    if not 1 <= points <= (1000 if mode == "NORMAL" else 50_000_000):
        raise ValueError("points exceed the selected mode's guide limit")
    run_state = scope.query(":TRIGger:STATus?").upper()
    if mode == "RAW" and run_state != "STOP":
        raise RuntimeError("RAW waveform requires a stopped acquisition")
    if mode == "MAXIMUM" and run_state != "STOP" and points > 1000:
        raise ValueError("MAXIMUM mode in RUN state is limited to 1000 screen points")
    require_afg_off(scope)
    previous = {name: scope.query(f":WAVeform:{name}?") for name in
                ("SOURce", "MODE", "FORMat", "POINts", "STARt", "STOP")}
    try:
        scope.write("*CLS")
        scope.write(":WAVeform:STARt 1")
        scope.write(":WAVeform:STOP 1")
        scope.write(":WAVeform:POINts 1")
        scope.write(f":WAVeform:SOURce {source}")
        mode_command = {"NORMAL": "NORMal", "MAXIMUM": "MAXimum", "RAW": "RAW"}[mode]
        format_command = {"BYTE": "BYTE", "WORD": "WORD", "ASCII": "ASCii"}[data_format]
        scope.write(f":WAVeform:MODE {mode_command}")
        scope.write(f":WAVeform:FORMat {format_command}")
        scope.write(f":WAVeform:POINts {points}")
        require_no_errors(scope)
        preamble = scope.query(":WAVeform:PREamble?").split(",")
        if len(preamble) != 10:
            raise RuntimeError(f"invalid waveform preamble: {preamble}")
        if (int(float(preamble[0])) != {"BYTE": 0, "WORD": 1, "ASCII": 2}[data_format]
                or int(float(preamble[1])) != {"NORMAL": 0, "MAXIMUM": 1, "RAW": 2}[mode]):
            raise RuntimeError("waveform format or mode differs from requested settings")
        if int(float(preamble[2])) != points:
            raise RuntimeError(f"waveform preamble reports {preamble[2]} points, requested {points}")
        x_increment, x_origin, x_reference = map(float, preamble[4:7])
        y_increment, y_origin, y_reference = map(float, preamble[7:10])
        if (not all(math.isfinite(v) for v in (x_increment, x_origin, x_reference,
                                                y_increment, y_origin, y_reference))
                or x_increment <= 0 or y_increment == 0):
            raise RuntimeError("non-finite waveform preamble")
        values = array("d")
        for start in range(1, points + 1, 250_000):
            stop = min(start + 249_999, points)
            scope.write(f":WAVeform:STOP {stop}")
            scope.write(f":WAVeform:STARt {start}")
            if data_format in {"BYTE", "WORD"}:
                word = data_format == "WORD"
                raw = scope.instrument.query_binary_values(
                    ":WAVeform:DATA?", datatype="H" if word else "B",
                    container=list if word else bytes, is_big_endian=False if word else None,
                    header_fmt="ieee", expect_termination=True,
                )
                chunk = ((sample - y_origin - y_reference) * y_increment for sample in raw)
            else:
                raw = scope.query(":WAVeform:DATA?")
                chunk = (float(sample) for sample in raw.split(",") if sample)
            before = len(values)
            values.extend(chunk)
            if len(values) - before != stop - start + 1:
                raise RuntimeError(f"waveform returned {len(values) - before} of {stop - start + 1} points")
        require_no_errors(scope)
        return Waveform(channel, mode, x_increment, x_origin, x_reference, values)
    finally:
        scope.write(":WAVeform:STARt 1")
        scope.write(":WAVeform:STOP 1")
        scope.write(":WAVeform:POINts 1")
        scope.write(":WAVeform:MODE NORMal")
        scope.write(f":WAVeform:SOURce {previous['SOURce']}")
        scope.write(f":WAVeform:MODE {previous['MODE']}")
        scope.write(f":WAVeform:FORMat {previous['FORMat']}")
        scope.write(f":WAVeform:POINts {previous['POINts']}")
        scope.write(f":WAVeform:STOP {previous['STOP']}")
        scope.write(f":WAVeform:STARt {previous['STARt']}")
        require_no_errors(scope)


def save_waveform(scope: Rigol, channel: int, path: Path, mode: str, points: int,
                  data_format: str = "ASCII") -> None:
    read_waveform(scope, channel, mode=mode, points=points,
                  data_format=data_format).to_csv(path)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--resource", help="VISA resource; omit to discover a DHO800/DHO900")
    result.add_argument("--backend", default="@py", help="PyVISA backend (default: @py)")
    result.add_argument("--expected-model", choices=tuple(MODELS), default="DHO914S",
                        help="require this model (default: DHO914S)")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    sub.add_parser("state")
    sub.add_parser("channels")
    sub.add_parser("measurement-types")
    sub.add_parser("dvm")
    sub.add_parser("counter")
    sub.add_parser("clear-counter")
    sub.add_parser("reset-statistics")
    sub.add_parser("errors")
    sub.add_parser("clear", help="Clear waveforms, leaving acquisition stopped and AFG off")

    screenshot = sub.add_parser("screenshot")
    screenshot.add_argument("--output", type=Path, required=True)

    observe = sub.add_parser("observe-for")
    observe.add_argument("--seconds", type=float, default=0.25)
    observe.add_argument("--output", type=Path, required=True)

    measure = sub.add_parser("measure")
    measure.add_argument("--item", required=True)
    measure.add_argument("--source", required=True)
    measure.add_argument("--source-b")

    dvm = sub.add_parser("set-dvm")
    dvm.add_argument("--source", required=True)
    dvm.add_argument("--mode", choices=("ACRMS", "DC", "DCRMS"), default="DC")
    dvm.add_argument("--disable", action="store_true")

    counter = sub.add_parser("set-counter")
    counter.add_argument("--source", required=True)
    counter.add_argument("--mode", choices=("FREQUENCY", "PERIOD", "TOTALIZE"), default="FREQUENCY")
    counter.add_argument("--digits", type=int, default=4)
    counter.add_argument("--statistics", action="store_true")
    counter.add_argument("--disable", action="store_true")

    stats = sub.add_parser("set-statistics")
    stats.add_argument("--count", type=int, required=True)
    stats.add_argument("--disable", action="store_true")

    statistic = sub.add_parser("statistic")
    statistic.add_argument("--item", required=True)
    statistic.add_argument("--source", required=True)
    statistic.add_argument("--source-b")
    statistic.add_argument("--result", default="CURRENT")
    statistic.add_argument("--add", action="store_true")

    annotate = sub.add_parser("annotate-capture")
    annotate.add_argument("--item", action="append", required=True, help="ITEM:CHAN1-CHAN4; repeat as needed")
    annotate.add_argument("--output", type=Path, required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--output-dir", type=Path, required=True)
    snapshot.add_argument("--label", default="snapshot")

    waveform = sub.add_parser("waveform")
    waveform.add_argument("--channel", type=int, required=True)
    waveform.add_argument("--mode", choices=("NORMAL", "RAW"), default="NORMAL")
    waveform.add_argument("--points", type=int, default=1000)
    waveform.add_argument("--format", choices=("ASCII", "BYTE"), default="ASCII")
    waveform.add_argument("--output", type=Path, required=True)

    restore = sub.add_parser("restore")
    restore.add_argument("--state", type=Path, required=True)
    restore.add_argument("--confirmed", required=True)

    channel = sub.add_parser("set-channel")
    channel.add_argument("--channel", type=int, choices=range(1, 5), required=True)
    channel.add_argument("--display", choices=("ON", "OFF"))
    channel.add_argument("--probe-ratio", type=float)
    channel.add_argument("--coupling", choices=("DC", "AC", "GND"))
    channel.add_argument("--invert", choices=("ON", "OFF"))
    channel.add_argument("--bandwidth")
    channel.add_argument("--scale", type=float)
    channel.add_argument("--offset", type=float)

    acquisition = sub.add_parser("set-acquisition")
    acquisition.add_argument("--type", dest="acquisition_type")
    acquisition.add_argument("--memory-depth")
    acquisition.add_argument("--averages", type=int)
    acquisition.add_argument("--timebase", type=float)
    acquisition.add_argument("--time-offset", type=float)

    trigger = sub.add_parser("set-trigger")
    trigger.add_argument("--source", required=True)
    trigger.add_argument("--slope", choices=("POSitive", "NEGative", "RFALl"), required=True)
    trigger.add_argument("--level", type=float, required=True)
    trigger.add_argument("--sweep", choices=("AUTO", "NORMal", "SINGle"), default="NORMal")
    trigger.add_argument("--coupling", choices=("DC", "AC", "LFR", "HFR"), default="DC")

    pulse = sub.add_parser("set-pulse-trigger")
    pulse.add_argument("--source", required=True)
    pulse.add_argument("--polarity", choices=("POSITIVE", "NEGATIVE"), required=True)
    pulse.add_argument("--when", choices=("GREATER", "LESS", "GLESS"), required=True)
    pulse.add_argument("--level", type=float, required=True)
    pulse.add_argument("--lower-width", type=float)
    pulse.add_argument("--upper-width", type=float)
    pulse.add_argument("--holdoff", type=float)
    pulse.add_argument("--sweep", choices=("AUTO", "NORMAL", "SINGLE"), default="NORMAL")

    afg = sub.add_parser("set-afg")
    afg.add_argument("--frequency", type=float, required=True)
    afg.add_argument("--amplitude", type=float, required=True)
    afg.add_argument("--offset", type=float, required=True)
    afg.add_argument("--duty", type=float, required=True)
    afg.add_argument("--phase", type=float, default=0)

    sub.add_parser("run")
    sub.add_parser("stop")
    sub.add_parser("single")

    afg_for = sub.add_parser("afg-for")
    afg_for.add_argument("--seconds", type=float, required=True)
    afg_for.add_argument("--confirmed", required=True)

    timed = sub.add_parser("timed-capture")
    timed.add_argument("--seconds", type=float, required=True)
    timed.add_argument("--timeout", type=float, default=1.0)
    timed.add_argument("--evidence-dir", type=Path, default=Path("evidence/rigol"))
    timed.add_argument("--confirmed", required=True)

    settled = sub.add_parser("settled-capture")
    settled.add_argument("--settle", type=float, required=True)
    settled.add_argument("--maximum", type=float, required=True)
    settled.add_argument("--output", type=Path, required=True)
    settled.add_argument("--confirmed", required=True)

    verify = sub.add_parser("verify")

    capture = sub.add_parser("capture")
    capture.add_argument("--confirmed", required=True)
    capture.add_argument("--timeout", type=float, default=1.0)
    capture.add_argument("--evidence-dir", type=Path, default=Path("evidence/rigol"))

    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manager, scope, resource, identity = connect(
        args.resource, args.backend, expected_model=args.expected_model)
    try:
        if args.command == "discover":
            print(json.dumps({"resource": resource, "identity": identity}, indent=2))
        elif args.command in {"state", "verify"}:
            print(json.dumps(readback(scope), indent=2))
        elif args.command == "channels":
            print(json.dumps(readback(scope)["channels"], indent=2))
        elif args.command == "dvm":
            print(read_dvm(scope))
        elif args.command == "counter":
            print(read_counter(scope))
        elif args.command == "clear-counter":
            clear_counter(scope)
        elif args.command == "reset-statistics":
            reset_measurement_statistics(scope)
        elif args.command == "set-dvm":
            print(json.dumps(configure_dvm(scope, source=args.source, mode=args.mode,
                                           enabled=not args.disable), indent=2))
        elif args.command == "set-counter":
            print(json.dumps(configure_counter(scope, source=args.source, mode=args.mode,
                                               digits=args.digits, statistics=args.statistics,
                                               enabled=not args.disable), indent=2))
        elif args.command == "set-statistics":
            print(json.dumps(configure_measurement_statistics(scope, count=args.count,
                                                               enabled=not args.disable), indent=2))
        elif args.command == "statistic":
            print(measurement_statistic(scope, item=args.item, source=args.source,
                                        source_b=args.source_b, result=args.result,
                                        add=args.add))
        elif args.command == "measurement-types":
            print(json.dumps(MEASUREMENT_TYPES, indent=2))
        elif args.command == "measure":
            print(json.dumps({args.item.upper(): query_measurement(scope, args.item, args.source,
                                                                    args.source_b)}, indent=2))
        elif args.command == "annotate-capture":
            screen = annotate_capture(scope, args.item)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(screen)
            print(args.output)
        elif args.command == "errors":
            print(json.dumps(scope.errors(), indent=2))
        elif args.command == "clear":
            clear_waveforms(scope)
            print("Waveforms cleared; acquisition stopped and AFG off.")
        elif args.command == "screenshot":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(scope.screenshot())
            print(args.output)
        elif args.command == "observe-for":
            screen = observe_for(scope, args.seconds)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(screen)
            print(json.dumps({
                "screen": str(args.output),
                "acquisition": scope.query(":TRIGger:STATus?"),
                "afg_output": scope.query(":SOURce:OUTPut:STATe?"),
            }, indent=2))
        elif args.command == "snapshot":
            print(collect_evidence(scope, args.output_dir, args.label))
        elif args.command == "waveform":
            save_waveform(scope, args.channel, args.output, args.mode, args.points, args.format)
            print(args.output)
        elif args.command == "restore":
            if args.confirmed != "RESTORE":
                raise SystemExit("Refusing restore: pass --confirmed RESTORE after reviewing the state file.")
            print(json.dumps(restore_state(scope, args.state), indent=2))
        elif args.command == "set-channel":
            print(json.dumps(configure_channel(
                scope,
                args.channel,
                display=None if args.display is None else args.display == "ON",
                probe_ratio=args.probe_ratio,
                coupling=args.coupling,
                inverted=None if args.invert is None else args.invert == "ON",
                bandwidth=args.bandwidth,
                scale=args.scale,
                offset=args.offset,
            ), indent=2))
        elif args.command == "set-acquisition":
            print(json.dumps(configure_acquisition(
                scope,
                acquisition_type=args.acquisition_type,
                memory_depth=args.memory_depth,
                averages=args.averages,
                timebase=args.timebase,
                time_offset=args.time_offset,
            ), indent=2))
        elif args.command == "set-trigger":
            print(json.dumps(configure_edge_trigger(
                scope,
                source=args.source,
                slope=args.slope,
                level=args.level,
                sweep=args.sweep,
                coupling=args.coupling,
            ), indent=2))
        elif args.command == "set-pulse-trigger":
            print(json.dumps(configure_pulse_trigger(
                scope, source=args.source, polarity=args.polarity, when=args.when,
                level=args.level, lower_width=args.lower_width, upper_width=args.upper_width,
                holdoff=args.holdoff, sweep=args.sweep,
            ), indent=2))
        elif args.command == "set-afg":
            print(json.dumps(configure_square_afg(
                scope,
                frequency=args.frequency,
                amplitude=args.amplitude,
                offset=args.offset,
                duty=args.duty,
                phase=args.phase,
            ), indent=2))
        elif args.command in {"run", "stop", "single"}:
            if args.command == "stop":
                scope.afg_off()
            else:
                clear_waveforms(scope)
            scope.write({"run": ":RUN", "stop": ":STOP", "single": ":SINGle"}[args.command])
            print(json.dumps({"trigger_status": scope.query(":TRIGger:STATus?")}, indent=2))
        elif args.command == "afg-for":
            elapsed = timed_afg(scope, args.seconds, args.confirmed)
            print(json.dumps({
                "requested_seconds": args.seconds,
                "host_elapsed_seconds": elapsed,
                "afg_output": scope.query(":SOURce:OUTPut:STATe?"),
            }, indent=2))
        elif args.command == "timed-capture":
            elapsed, output = timed_capture(
                scope, args.evidence_dir, args.seconds, args.timeout, args.confirmed
            )
            print(json.dumps({
                "requested_seconds": args.seconds,
                "host_elapsed_seconds": elapsed,
                "evidence": str(output),
                "afg_output": scope.query(":SOURce:OUTPut:STATe?"),
            }, indent=2))
        elif args.command == "settled-capture":
            screen = settled_capture(scope, args.settle, args.maximum, args.confirmed)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(screen)
            print(json.dumps({
                "screen": str(args.output),
                "afg_output": scope.query(":SOURce:OUTPut:STATe?"),
                "acquisition": scope.query(":TRIGger:STATus?"),
            }, indent=2))
        elif args.command == "capture":
            print(capture_point(scope, args.evidence_dir, args.timeout, args.confirmed))
        return 0
    finally:
        try:
            scope.afg_off()
        finally:
            scope.instrument.close()
            manager.close()


if __name__ == "__main__":
    sys.exit(main())
