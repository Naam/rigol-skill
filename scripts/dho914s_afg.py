"""Typed, bounded access to the DHO914S built-in waveform generator."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from dho800900_models import profile_for

from dho800900 import require_confirmation, require_no_errors


_CARRIER_MAX_HZ = {
    "SINusoid": 25_000_000.0,
    "SQUare": 15_000_000.0,
    "RAMP": 150_000.0,
    "ARB": 10_000_000.0,
}
_CARRIER_NAMES = {name.upper(): name for name in (*_CARRIER_MAX_HZ, "DC", "NOISe")}
_CARRIER_MIN_HZ = 0.002
_MAX_AMPLITUDE_VPP = 10.0
_MOD_FUNCTIONS = {
    "SINusoid": "SIN", "SQUare": "SQU", "TRIangle": "TRI",
    "UPRamp": "UPR", "DNRamp": "DNR", "NOISe": "NOIS",
}
_CARRIER_FUNCTIONS = {
    "SIN": "SINusoid", "SQU": "SQUare", "RAMP": "RAMP", "DC": "DC",
    "NOIS": "NOISe", "ARB": "ARB",
}
_MOD_FUNCTION_READBACK = {value: key for key, value in _MOD_FUNCTIONS.items()}


def _finite(name: str, value: float, low: float, high: float) -> None:
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")


def _carrier_limits(function: str, frequency_hz: float | None) -> tuple[float, float]:
    if function in {"DC", "NOISe"}:
        if frequency_hz is not None:
            raise ValueError(f"{function} has no frequency parameter")
        return _MAX_AMPLITUDE_VPP, _MAX_AMPLITUDE_VPP
    if function not in _CARRIER_MAX_HZ:
        raise ValueError("function must be SINusoid, SQUare, RAMP, DC, NOISe, or ARB")
    if frequency_hz is None:
        raise ValueError(f"{function} requires frequency_hz")
    _finite("carrier frequency", frequency_hz, _CARRIER_MIN_HZ, _CARRIER_MAX_HZ[function])
    return 5.0 if frequency_hz > 10_000_000 else 10.0, _CARRIER_MAX_HZ[function]


@dataclass(frozen=True)
class CarrierConfig:
    function: str = "SINusoid"
    frequency_hz: float | None = 1_000.0
    amplitude_vpp: float = 6.0
    offset_v: float = 0.0
    phase_deg: float = 0.0
    ramp_symmetry_percent: float | None = None
    square_duty_percent: float | None = None

    def __post_init__(self) -> None:
        function = self.function.upper()
        aliases = {"SIN": "SINusoid", "SINE": "SINusoid", "SQU": "SQUare",
                   "SQUARE": "SQUare", "NOIS": "NOISe", "NOISE": "NOISe",
                   **_CARRIER_NAMES}
        function = aliases.get(function, self.function)
        object.__setattr__(self, "function", function)
        max_amplitude, _ = _carrier_limits(function, self.frequency_hz)
        _finite("amplitude", self.amplitude_vpp, 0.002, max_amplitude)
        _finite("phase", self.phase_deg, 0.0, 360.0)
        max_offset = (max_amplitude - self.amplitude_vpp) / 2.0
        _finite("offset", self.offset_v, -max_offset, max_offset)
        if self.ramp_symmetry_percent is not None:
            if function != "RAMP":
                raise ValueError("ramp_symmetry_percent is only valid for RAMP")
            _finite("ramp symmetry", self.ramp_symmetry_percent, 0.0, 100.0)
        if self.square_duty_percent is not None:
            if function != "SQUare":
                raise ValueError("square_duty_percent is only valid for SQUare")
            _finite("square duty", self.square_duty_percent, 0.0, 100.0)


@dataclass(frozen=True)
class ModulationConfig:
    kind: str
    internal_frequency_hz: float = 100.0
    internal_function: str = "SINusoid"
    depth_percent: float | None = None
    deviation_hz_or_deg: float | None = None

    def __post_init__(self) -> None:
        kind = self.kind.upper()
        if kind not in {"AM", "FM", "PM"}:
            raise ValueError("modulation kind must be AM, FM, or PM")
        object.__setattr__(self, "kind", kind)
        _finite("modulation frequency", self.internal_frequency_hz, 0.002, 1_000_000.0)
        function = self.internal_function.upper()
        aliases = {"SIN": "SINusoid", "SINE": "SINusoid", "SQU": "SQUare",
                   "SQUARE": "SQUare", "TRI": "TRIangle", "TRIANGLE": "TRIangle",
                   "UPR": "UPRamp", "UPRAMP": "UPRamp", "DNR": "DNRamp",
                   "DNRAMP": "DNRamp", "NOIS": "NOISe", "NOISE": "NOISe",
                   **{name.upper(): name for name in _MOD_FUNCTIONS}}
        function = aliases.get(function, self.internal_function)
        if function not in _MOD_FUNCTIONS:
            raise ValueError("unsupported internal modulation function")
        object.__setattr__(self, "internal_function", function)
        if kind == "AM":
            if self.depth_percent is None or self.deviation_hz_or_deg is not None:
                raise ValueError("AM requires depth_percent and does not take deviation")
            _finite("AM depth", self.depth_percent, 0.0, 120.0)
        elif self.depth_percent is not None or self.deviation_hz_or_deg is None:
            raise ValueError(f"{kind} requires deviation_hz_or_deg and does not take depth")
        elif kind == "FM":
            _finite("FM deviation", self.deviation_hz_or_deg, 0.002, 25_000_000.0)
        else:
            _finite("PM deviation", self.deviation_hz_or_deg, 0.0, 360.0)


@dataclass(frozen=True)
class AFGState:
    output_enabled: bool
    modulation_enabled: bool
    carrier: CarrierConfig
    modulation: ModulationConfig


class DHO900SAFG:
    """AFG controls for the DHO914S and DHO924S; output runs are bounded."""

    def __init__(self, scope):
        profile_for(scope).require("afg")
        self.scope = scope

    def _inactive(self) -> None:
        if self.scope.query(":SOURce:OUTPut:STATe?").upper() not in {"0", "OFF"}:
            raise RuntimeError("AFG output must be off before configuration")
        if self.scope.query(":SOURce:MOD:STATe?").upper() not in {"0", "OFF"}:
            raise RuntimeError("modulation output must be off before configuration")

    def read_carrier(self) -> CarrierConfig:
        raw_function = self.scope.query(":SOURce:FUNCtion?").upper()
        try:
            function = _CARRIER_FUNCTIONS[raw_function]
        except KeyError as exc:
            raise RuntimeError(f"unknown carrier function readback: {raw_function}") from exc
        frequency = None if function in {"DC", "NOISe"} else float(
            self.scope.query(":SOURce:FREQuency?"))
        values = dict(function=function, frequency_hz=frequency,
                      amplitude_vpp=float(self.scope.query(":SOURce:VOLTage:AMPLitude?")),
                      offset_v=float(self.scope.query(":SOURce:VOLTage:OFFSet?")),
                      phase_deg=float(self.scope.query(":SOURce:PHASe?")))
        if function == "RAMP":
            values["ramp_symmetry_percent"] = float(
                self.scope.query(":SOURce:FUNCtion:RAMP:SYMMetry?"))
        if function == "SQUare":
            values["square_duty_percent"] = float(
                self.scope.query(":SOURce:FUNCtion:SQUare:DUTY?"))
        return CarrierConfig(**values)

    def set_carrier(self, config: CarrierConfig) -> CarrierConfig:
        if not isinstance(config, CarrierConfig):
            raise TypeError("config must be CarrierConfig")
        self._inactive()
        current = self.read_carrier()
        self.scope.write(":SOURce:VOLTage:OFFSet 0")
        frequency_first = (config.frequency_hz is not None and
                           current.function in _CARRIER_MAX_HZ and
                           config.frequency_hz <= _CARRIER_MAX_HZ[current.function])
        if frequency_first:
            self.scope.write(f":SOURce:FREQuency {config.frequency_hz:.12g}")
        self.scope.write(":SOURce:FUNCtion " + config.function)
        if config.frequency_hz is not None and not frequency_first:
            self.scope.write(f":SOURce:FREQuency {config.frequency_hz:.12g}")
        self.scope.write(f":SOURce:VOLTage:AMPLitude {config.amplitude_vpp:.12g}")
        self.scope.write(f":SOURce:VOLTage:OFFSet {config.offset_v:.12g}")
        self.scope.write(f":SOURce:PHASe {config.phase_deg:.12g}")
        if config.ramp_symmetry_percent is not None:
            self.scope.write(f":SOURce:FUNCtion:RAMP:SYMMetry {config.ramp_symmetry_percent:.12g}")
        if config.square_duty_percent is not None:
            self.scope.write(f":SOURce:FUNCtion:SQUare:DUTY {config.square_duty_percent:.12g}")
        require_no_errors(self.scope)
        state = self.read_carrier()
        if (state.function != config.function
                or (state.frequency_hz is None) != (config.frequency_hz is None)
                or (state.frequency_hz is not None and config.frequency_hz is not None
                    and not math.isclose(state.frequency_hz, config.frequency_hz, rel_tol=1e-6))
                or not math.isclose(state.amplitude_vpp, config.amplitude_vpp, rel_tol=1e-6)
                or not math.isclose(state.offset_v, config.offset_v, abs_tol=1e-9)
                or not math.isclose(state.phase_deg, config.phase_deg, abs_tol=1e-6)
                or (config.ramp_symmetry_percent is not None and not math.isclose(
                    state.ramp_symmetry_percent, config.ramp_symmetry_percent, abs_tol=1e-6))
                or (config.square_duty_percent is not None and not math.isclose(
                    state.square_duty_percent, config.square_duty_percent, abs_tol=1e-6))):
            raise RuntimeError(f"carrier readback differs: expected {config}, got {state}")
        return state

    def read_modulation(self) -> ModulationConfig:
        kind = self.scope.query(":SOURce:MOD:TYPe?").upper()
        if kind == "AM":
            value = dict(depth_percent=float(self.scope.query(":SOURce:MOD:AM:DEPTh?")))
        elif kind == "FM":
            value = dict(deviation_hz_or_deg=float(
                self.scope.query(":SOURce:MOD:FM:DEViation?")))
        elif kind == "PM":
            value = dict(deviation_hz_or_deg=float(
                self.scope.query(":SOURce:MOD:PM:DEViation?")))
        else:
            raise RuntimeError(f"unknown modulation type readback: {kind}")
        value["internal_frequency_hz"] = float(self.scope.query(
            f":SOURce:MOD:{kind}:INTernal:FREQuency?"))
        raw_function = self.scope.query(f":SOURce:MOD:{kind}:INTernal:FUNCtion?").upper()
        try:
            value["internal_function"] = _MOD_FUNCTION_READBACK[raw_function]
        except KeyError as exc:
            raise RuntimeError(f"unknown internal modulation function: {raw_function}") from exc
        return ModulationConfig(kind=kind, **value)

    def set_modulation(self, config: ModulationConfig) -> ModulationConfig:
        if not isinstance(config, ModulationConfig):
            raise TypeError("config must be ModulationConfig")
        self._inactive()
        carrier = self.read_carrier()
        if config.kind == "FM":
            if carrier.frequency_hz is None:
                raise ValueError("FM requires a frequency carrier")
            _, max_frequency = _carrier_limits(carrier.function, carrier.frequency_hz)
            if config.deviation_hz_or_deg > carrier.frequency_hz:
                raise ValueError("FM deviation cannot exceed carrier frequency")
            if carrier.frequency_hz + config.deviation_hz_or_deg > max_frequency + 1_000:
                raise ValueError("FM carrier plus deviation exceeds carrier range")
        kind = config.kind
        self.scope.write(f":SOURce:MOD:TYPe {kind}")
        if kind == "AM":
            self.scope.write(f":SOURce:MOD:AM:DEPTh {config.depth_percent:.12g}")
        elif kind == "FM":
            self.scope.write(f":SOURce:MOD:FM:DEViation {config.deviation_hz_or_deg:.12g}")
        else:
            self.scope.write(f":SOURce:MOD:PM:DEViation {config.deviation_hz_or_deg:.12g}")
        self.scope.write(f":SOURce:MOD:{kind}:INTernal:FREQuency {config.internal_frequency_hz:.12g}")
        self.scope.write(f":SOURce:MOD:{kind}:INTernal:FUNCtion {config.internal_function}")
        require_no_errors(self.scope)
        state = self.read_modulation()
        state_values = (state.kind == config.kind
                        and math.isclose(state.internal_frequency_hz,
                                         config.internal_frequency_hz, rel_tol=1e-6)
                        and state.internal_function == config.internal_function
                        and ((config.depth_percent is None and state.depth_percent is None)
                             or (config.depth_percent is not None and state.depth_percent is not None
                                 and math.isclose(state.depth_percent, config.depth_percent,
                                                  abs_tol=1e-6)))
                        and ((config.deviation_hz_or_deg is None
                              and state.deviation_hz_or_deg is None)
                             or (config.deviation_hz_or_deg is not None
                                 and state.deviation_hz_or_deg is not None
                                 and math.isclose(state.deviation_hz_or_deg,
                                                  config.deviation_hz_or_deg, rel_tol=1e-6))))
        if not state_values:
            raise RuntimeError(f"modulation readback differs: expected {config}, got {state}")
        return state

    def read_state(self) -> AFGState:
        output = self.scope.query(":SOURce:OUTPut:STATe?").upper()
        modulation_enabled = self.scope.query(":SOURce:MOD:STATe?").upper()
        if output not in {"0", "1", "ON", "OFF"} or modulation_enabled not in {
                "0", "1", "ON", "OFF"}:
            raise RuntimeError("invalid AFG state readback")
        require_no_errors(self.scope)
        return AFGState(output in {"1", "ON"}, modulation_enabled in {"1", "ON"},
                        self.read_carrier(), self.read_modulation())

    def _off(self) -> None:
        failures = []
        for command in (":SOURce:MOD:STATe OFF", ":SOURce:OUTPut:STATe OFF"):
            try:
                self.scope.write(command)
            except Exception as exc:
                failures.append(exc)
        try:
            require_no_errors(self.scope)
        except Exception as exc:
            failures.append(exc)
        for command in (":SOURce:MOD:STATe?", ":SOURce:OUTPut:STATe?"):
            try:
                if self.scope.query(command).upper() not in {"0", "OFF"}:
                    failures.append(RuntimeError(f"{command} did not confirm OFF"))
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise RuntimeError(f"failed to shut down AFG output: {failures}")

    def run(self, carrier: CarrierConfig, *, seconds: float,
            confirmation: str, modulation: ModulationConfig | None = None) -> AFGState:
        """Run a configured carrier for 50 ms–5 s, then disable modulation and output."""
        require_confirmation(confirmation)
        _finite("AFG run duration", seconds, 0.05, 5.0)
        self._off()
        try:
            self.set_carrier(carrier)
            if modulation is not None:
                self.set_modulation(modulation)
            self.scope.write(":SOURce:OUTPut:STATe ON")
            if modulation is not None:
                self.scope.write(":SOURce:MOD:STATe ON")
            require_no_errors(self.scope)
            start = time.monotonic()
            state = self.read_state()
            if not state.output_enabled or state.modulation_enabled != (modulation is not None):
                raise RuntimeError("AFG enable readback differs from requested run")
            time.sleep(max(0.0, start + seconds - time.monotonic()))
        finally:
            self._off()
        return self.read_state()


DHO914SAFG = DHO900SAFG
