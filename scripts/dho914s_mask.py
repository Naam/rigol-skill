"""Typed pass/fail mask controls for the DHO914S."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from dho800900 import require_confirmation, require_no_errors


def _bool(value: str, name: str) -> bool:
    value = value.strip().upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    raise RuntimeError(f"invalid {name} readback: {value}")


def _integer(value: str, name: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise RuntimeError(f"invalid {name} readback: {value}") from exc
    if result < 0:
        raise RuntimeError(f"negative {name} readback: {value}")
    return result


@dataclass(frozen=True)
class MaskConfig:
    source_channel: int = 1
    horizontal_div: float = 0.24
    vertical_div: float = 0.48
    output_event: str = "FAIL"
    output_pulse_s: float = 1e-6

    def __post_init__(self) -> None:
        if type(self.source_channel) is not int or self.source_channel not in range(1, 5):
            raise ValueError("mask source_channel must be 1-4")
        if not math.isfinite(self.horizontal_div) or not 0.01 <= self.horizontal_div <= 2:
            raise ValueError("horizontal_div must be 0.01-2 div")
        if not math.isfinite(self.vertical_div) or not 0.04 <= self.vertical_div <= 2:
            raise ValueError("vertical_div must be 0.04-2 div")
        event = self.output_event.upper()
        if event not in {"FAIL", "PASS"}:
            raise ValueError("output_event must be FAIL or PASS")
        object.__setattr__(self, "output_event", event)
        if not math.isfinite(self.output_pulse_s) or not 100e-9 <= self.output_pulse_s <= 10e-3:
            raise ValueError("output_pulse_s must be 100 ns-10 ms")


@dataclass(frozen=True)
class MaskMetrics:
    passed: int
    failed: int
    total: int


@dataclass(frozen=True)
class MaskState:
    enabled: bool
    operating: str
    aux_output_enabled: bool
    config: MaskConfig


class DHO914SMask:
    """Configure masks and run pass/fail tests with bounded AUX output pulses."""

    def __init__(self, scope):
        self.scope = scope

    def _off(self) -> None:
        failures = []
        for command in (":MASK:OPERate STOP", ":MASK:OUTPut:ENABle OFF", ":MASK:ENABle OFF"):
            try:
                self.scope.write(command)
            except Exception as exc:
                failures.append(exc)
        try:
            require_no_errors(self.scope)
            if self.scope.query(":MASK:OPERate?").strip().upper() != "STOP":
                raise RuntimeError("mask operation did not stop")
            if _bool(self.scope.query(":MASK:OUTPut:ENABle?"), "AUX output enable"):
                raise RuntimeError("AUX output remained enabled")
            if _bool(self.scope.query(":MASK:ENABle?"), "mask enable"):
                raise RuntimeError("mask remained enabled")
            require_no_errors(self.scope)
        except Exception as exc:
            failures.append(exc)
        if failures:
            raise RuntimeError(f"failed to stop mask/AUX output: {failures}")

    def read_metrics(self) -> MaskMetrics:
        failed = _integer(self.scope.query(":MASK:FAILed?"), "failed frame count")
        passed = _integer(self.scope.query(":MASK:PASSed?"), "passed frame count")
        total = _integer(self.scope.query(":MASK:TOTal?"), "total frame count")
        require_no_errors(self.scope)
        if passed + failed > total:
            raise RuntimeError("pass/fail counts exceed total frame count")
        return MaskMetrics(passed, failed, total)

    def read_state(self) -> MaskState:
        enabled = _bool(self.scope.query(":MASK:ENABle?"), "mask enable")
        source = self.scope.query(":MASK:SOURce?").upper()
        if source not in {f"CHAN{i}" for i in range(1, 5)}:
            raise RuntimeError(f"invalid mask source readback: {source}")
        operating = self.scope.query(":MASK:OPERate?").upper()
        if operating not in {"RUN", "STOP"}:
            raise RuntimeError(f"invalid mask operation readback: {operating}")
        output_enabled = _bool(self.scope.query(":MASK:OUTPut:ENABle?"), "AUX output enable")
        event = self.scope.query(":MASK:OUTPut:EVENt?").upper()
        config = MaskConfig(
            source_channel=int(source[-1]),
            horizontal_div=float(self.scope.query(":MASK:X?")),
            vertical_div=float(self.scope.query(":MASK:Y?")),
            output_event=event,
            output_pulse_s=float(self.scope.query(":MASK:OUTPut:TIME?")),
        )
        require_no_errors(self.scope)
        return MaskState(enabled, operating, output_enabled, config)

    def configure(self, config: MaskConfig) -> MaskConfig:
        if not isinstance(config, MaskConfig):
            raise TypeError("config must be MaskConfig")
        self._off()
        try:
            self.scope.write(f":MASK:SOURce CHANnel{config.source_channel}")
            self.scope.write(f":MASK:X {config.horizontal_div:.12g}")
            self.scope.write(f":MASK:Y {config.vertical_div:.12g}")
            self.scope.write(f":MASK:OUTPut:EVENt {config.output_event}")
            self.scope.write(f":MASK:OUTPut:TIME {config.output_pulse_s:.12g}")
            self.scope.write(":MASK:ENABle ON")
            self.scope.write(":MASK:CREate")
            require_no_errors(self.scope)
            readback = self.read_state().config
            if (readback.source_channel != config.source_channel
                    or not math.isclose(readback.horizontal_div, config.horizontal_div,
                                         rel_tol=1e-6)
                    or not math.isclose(readback.vertical_div, config.vertical_div,
                                        rel_tol=1e-6)
                    or readback.output_event != config.output_event
                    or not math.isclose(readback.output_pulse_s, config.output_pulse_s,
                                        rel_tol=1e-6)):
                raise RuntimeError(f"mask readback differs: expected {config}, got {readback}")
            return readback
        finally:
            self._off()

    def reset_metrics(self) -> None:
        state = self.read_state()
        if state.operating != "STOP" or state.aux_output_enabled:
            raise RuntimeError("stop pass/fail and disable AUX output before resetting metrics")
        self.scope.write(":MASK:RESet")
        require_no_errors(self.scope)

    def run(self, *, seconds: float, confirmation: str,
            config: MaskConfig | None = None, aux_output: bool = True) -> MaskMetrics:
        """Run for 50 ms–5 s; optionally pulse AUX on the configured PASS/FAIL event."""
        require_confirmation(confirmation)
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0.05 <= seconds <= 5:
            raise ValueError("mask run duration must be 0.05-5 seconds")
        if type(aux_output) is not bool:
            raise TypeError("aux_output must be bool")
        if config is not None:
            self.configure(config)
        self._off()
        try:
            self.scope.write(":MASK:ENABle ON")
            require_no_errors(self.scope)
            if not _bool(self.scope.query(":MASK:ENABle?"), "mask enable"):
                raise RuntimeError("mask test did not enable")
            if aux_output:
                self.scope.write(":MASK:OUTPut:ENABle ON")
                require_no_errors(self.scope)
                if not _bool(self.scope.query(":MASK:OUTPut:ENABle?"), "AUX output enable"):
                    raise RuntimeError("AUX output did not enable")
            self.scope.write(":MASK:OPERate RUN")
            require_no_errors(self.scope)
            if self.scope.query(":MASK:OPERate?").upper() != "RUN":
                raise RuntimeError("pass/fail test did not start")
            time.sleep(seconds)
        finally:
            self._off()
        return self.read_metrics()
