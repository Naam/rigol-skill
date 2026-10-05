"""Typed waveform recording, playback, and reference-waveform controls.

Command behavior follows sections 3.19 and 3.20 of the April 2025 DHO800/DHO900
Programming Guide. Recording and playback methods that start an operation are
bounded and require ``confirm=True``.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from dho800900 import normalize_channel_source, require_no_errors
from dho800900_models import profile_for


_RECORD = ":RECord:WRECord:"
_PLAY = ":RECord:WREPlay:"


def _bool(value: str) -> bool:
    value = value.strip().upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    raise RuntimeError(f"unexpected instrument boolean: {value!r}")


def _positive_int(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _seconds(value: float, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g} seconds")
    return float(value)


@dataclass(frozen=True)
class RecordingSettings:
    enabled: bool
    running: bool
    frame_count: int
    max_frames: int
    frame_interval_s: float
    completion_beep: bool


@dataclass(frozen=True)
class PlaybackSettings:
    running: bool
    current_frame: int
    current_frame_time: str
    start_frame: int
    end_frame: int
    max_frames: int
    frame_interval_s: float
    mode: str
    direction: str


class Recording:
    """Recording and playback workflows for one connected DHO914S."""

    def __init__(self, scope):
        self.scope = scope

    def settings(self, *, legacy_commands: bool = False) -> RecordingSettings:
        if type(legacy_commands) is not bool:
            raise ValueError("legacy_commands must be bool")
        s = self.scope
        enable_query = ":RECord:ENABle?" if legacy_commands else _RECORD + "ENABle?"
        operate_query = ":RECord:STARt?" if legacy_commands else _RECORD + "OPERate?"
        frame_query = ":RECord:FRAMes?" if legacy_commands else _RECORD + "FRAMes?"
        operate_value = s.query(operate_query).strip().upper()
        if legacy_commands:
            _bool(operate_value)
        elif operate_value not in {"RUN", "STOP"}:
            raise RuntimeError(f"unexpected recording status: {operate_value!r}")
        result = RecordingSettings(
            _bool(s.query(enable_query)),
            _bool(operate_value) if legacy_commands else operate_value == "RUN",
            int(s.query(frame_query)),
            int(s.query(_RECORD + "FMAX?")),
            float(s.query(_RECORD + "FINTerval?")),
            _bool(s.query(_RECORD + "PROMpt?")),
        )
        if result.frame_count < 1 or result.max_frames < 1 or not math.isfinite(result.frame_interval_s):
            raise RuntimeError(f"invalid recording settings: {result}")
        require_no_errors(s)
        return result

    def configure(self, *, frames: int | None = None, interval_s: float | None = None,
                  enabled: bool | None = None, completion_beep: bool | None = None,
                  legacy_commands: bool = False) -> RecordingSettings:
        """Set recording options; frame limits are read from the current memory depth."""
        if frames is not None:
            _positive_int(frames, "frames")
        if interval_s is not None:
            _seconds(interval_s, 1e-8, 1.0, "record interval")
        for name, value in (("enabled", enabled), ("completion_beep", completion_beep)):
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} must be bool")
        if type(legacy_commands) is not bool:
            raise ValueError("legacy_commands must be bool")
        s = self.scope
        current = self.settings(legacy_commands=legacy_commands)
        frame_command = ":RECord:FRAMes" if legacy_commands else _RECORD + "FRAMes"
        enable_command = ":RECord:ENABle" if legacy_commands else _RECORD + "ENABle"
        if frames is not None:
            maximum = current.max_frames
            if frames > maximum:
                raise ValueError(f"frames exceeds current instrument maximum ({maximum})")
            s.write(f"{frame_command} {frames}")
        if interval_s is not None:
            s.write(f"{_RECORD}FINTerval {interval_s:.12g}")
        if enabled is not None:
            s.write(f"{enable_command} {'ON' if enabled else 'OFF'}")
        if completion_beep is not None:
            s.write(f"{_RECORD}PROMpt {'ON' if completion_beep else 'OFF'}")
        require_no_errors(s)
        result = self.settings(legacy_commands=legacy_commands)
        if frames is not None and result.frame_count != frames:
            raise RuntimeError(f"record frame count read back as {result.frame_count}, expected {frames}")
        if interval_s is not None and not math.isclose(result.frame_interval_s, interval_s, rel_tol=1e-7):
            raise RuntimeError("record frame interval did not read back as requested")
        if enabled is not None and result.enabled != enabled:
            raise RuntimeError("record enable state did not read back as requested")
        if completion_beep is not None and result.completion_beep != completion_beep:
            raise RuntimeError("record completion beep did not read back as requested")
        return result

    def set_maximum_frames(self) -> RecordingSettings:
        """Choose the instrument's maximum recordable frame count."""
        self.scope.write(_RECORD + "FRAMes:MAX")
        require_no_errors(self.scope)
        return self.settings()

    def start(self, *, confirm: bool = False, timeout_s: float = 30.0,
              legacy_command: bool = False) -> None:
        """Record until the configured frame count completes or timeout expires."""
        if confirm is not True:
            raise ValueError("recording changes instrument state; pass confirm=True")
        timeout = _seconds(timeout_s, 0.05, 120.0, "recording timeout")
        before = self.settings()
        if not before.enabled:
            raise RuntimeError("enable waveform recording before starting")
        if type(legacy_command) is not bool:
            raise ValueError("legacy_command must be bool")
        expected = min(timeout, before.frame_count * before.frame_interval_s + 1.0)
        deadline = time.monotonic() + expected
        run_command = ":RECord:STARt ON" if legacy_command else _RECORD + "OPERate RUN"
        stop_command = ":RECord:STARt OFF" if legacy_command else _RECORD + "OPERate STOP"
        try:
            self.scope.write(run_command)
            require_no_errors(self.scope)
            while time.monotonic() < deadline:
                query = ":RECord:STARt?" if legacy_command else _RECORD + "OPERate?"
                state = self.scope.query(query).strip().upper()
                if (not _bool(state) if legacy_command else state == "STOP"):
                    return
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            raise TimeoutError("recording did not complete before its time limit")
        finally:
            self.scope.write(stop_command)
            require_no_errors(self.scope)

    def stop(self) -> None:
        self.scope.write(_RECORD + "OPERate STOP")
        require_no_errors(self.scope)

    def playback_settings(self, *, legacy_commands: bool = False) -> PlaybackSettings:
        if type(legacy_commands) is not bool:
            raise ValueError("legacy_commands must be bool")
        s = self.scope
        operate_query = ":RECord:PLAY?" if legacy_commands else _PLAY + "OPERate?"
        current_query = ":RECord:CURRent?" if legacy_commands else _PLAY + "FCURrent?"
        running_value = s.query(operate_query).strip().upper()
        result = PlaybackSettings(
            _bool(running_value) if legacy_commands else running_value == "RUN",
            int(s.query(current_query)),
            s.query(_PLAY + "FCURrent:TIME?").strip(),
            int(s.query(_PLAY + "FSTart?")),
            int(s.query(_PLAY + "FEND?")),
            int(s.query(_PLAY + "FMAX?")),
            float(s.query(_PLAY + "FINTerval?")),
            s.query(_PLAY + "MODE?").strip().upper(),
            s.query(_PLAY + "DIRection?").strip().upper(),
        )
        require_no_errors(s)
        if result.max_frames < 0 or result.frame_interval_s < 0 or not math.isfinite(result.frame_interval_s):
            raise RuntimeError(f"invalid playback settings: {result}")
        if result.mode not in {"REP", "SING", "REPEAT", "SINGLE"}:
            raise RuntimeError(f"unexpected playback mode: {result.mode!r}")
        if result.direction not in {"FORW", "BACK", "FORWARD", "BACKWARD"}:
            raise RuntimeError(f"unexpected playback direction: {result.direction!r}")
        return result

    def play(self, *, start: int, end: int, interval_s: float = 0.1,
             mode: str = "SINGLE", direction: str = "FORWARD",
             timeout_s: float = 30.0, confirm: bool = False,
             legacy_command: bool = False) -> None:
        """Play a bounded frame window; always stop playback on exit."""
        start, end = _positive_int(start, "start"), _positive_int(end, "end")
        timeout = _seconds(timeout_s, 0.05, 120.0, "playback timeout")
        interval = _seconds(interval_s, 0.001, 1.0, "playback interval")
        mode = mode.upper()
        direction = direction.upper()
        if mode not in {"SINGLE", "REPEAT"}:
            raise ValueError("playback mode must be SINGLE or REPEAT")
        if direction not in {"FORWARD", "BACKWARD"}:
            raise ValueError("direction must be FORWARD or BACKWARD")
        if confirm is not True:
            raise ValueError("playback changes instrument state; pass confirm=True")
        if type(legacy_command) is not bool:
            raise ValueError("legacy_command must be bool")
        maximum = int(self.scope.query(_PLAY + "FMAX?"))
        require_no_errors(self.scope)
        if maximum < 1 or end > maximum or start > end:
            raise ValueError(f"frame window must satisfy 1 <= start <= end <= {maximum}")
        s = self.scope
        old_start, old_end = int(s.query(_PLAY + "FSTart?")), int(s.query(_PLAY + "FEND?"))
        require_no_errors(s)
        if start > old_end:
            s.write(f"{_PLAY}FEND {end}")
            s.write(f"{_PLAY}FSTart {start}")
        elif end < old_start:
            s.write(f"{_PLAY}FSTart {start}")
            s.write(f"{_PLAY}FEND {end}")
        else:
            s.write(f"{_PLAY}FSTart {start}")
            s.write(f"{_PLAY}FEND {end}")
        s.write(f"{_PLAY}FINTerval {interval:.12g}")
        s.write(f"{_PLAY}MODE {'REP' if mode == 'REPEAT' else 'SING'}")
        s.write(f"{_PLAY}DIRection {'BACK' if direction == 'BACKWARD' else 'FORW'}")
        require_no_errors(s)
        actual = (int(s.query(_PLAY + "FSTart?")), int(s.query(_PLAY + "FEND?")),
                  float(s.query(_PLAY + "FINTerval?")))
        require_no_errors(s)
        if actual[:2] != (start, end) or not math.isclose(actual[2], interval, rel_tol=1e-7):
            raise RuntimeError(f"playback window read back differently: {actual}")
        deadline = time.monotonic() + timeout
        run_command = ":RECord:PLAY ON" if legacy_command else _PLAY + "OPERate RUN"
        stop_command = ":RECord:PLAY OFF" if legacy_command else _PLAY + "OPERate STOP"
        try:
            s.write(run_command)
            require_no_errors(s)
            while time.monotonic() < deadline:
                state = s.query(":RECord:PLAY?" if legacy_command else _PLAY + "OPERate?").strip().upper()
                if (not _bool(state) if legacy_command else state == "STOP"):
                    return
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            raise TimeoutError("playback did not complete before its time limit")
        finally:
            s.write(stop_command)
            require_no_errors(s)

    def stop_playback(self) -> None:
        self.scope.write(_PLAY + "OPERate STOP")
        require_no_errors(self.scope)

    def current_frame(self, *, legacy_command: bool = False) -> int:
        command = ":RECord:CURRent?" if legacy_command else _PLAY + "FCURrent?"
        value = int(self.scope.query(command))
        require_no_errors(self.scope)
        return value

    def set_current_frame(self, frame: int, *, legacy_command: bool = False,
                          confirm: bool = False) -> int:
        if confirm is not True:
            raise ValueError("setting playback position changes instrument state; pass confirm=True")
        frame = _positive_int(frame, "frame")
        maximum = int(self.scope.query(_PLAY + "FMAX?"))
        require_no_errors(self.scope)
        if frame > maximum:
            raise ValueError(f"frame exceeds recorded maximum ({maximum})")
        command = ":RECord:CURRent" if legacy_command else _PLAY + "FCURrent"
        self.scope.write(f"{command} {frame}")
        require_no_errors(self.scope)
        return self.current_frame(legacy_command=legacy_command)

    def step(self, direction: str, *, confirm: bool = False) -> None:
        if confirm is not True:
            raise ValueError("stepping playback changes instrument state; pass confirm=True")
        direction = direction.upper()
        if direction not in {"BACK", "NEXT"}:
            raise ValueError("step direction must be BACK or NEXT")
        self.scope.write(_PLAY + direction)
        require_no_errors(self.scope)

    def play_from(self, edge: str, *, confirm: bool = False) -> None:
        if confirm is not True:
            raise ValueError("changing playback position changes instrument state; pass confirm=True")
        edge = edge.upper()
        if edge not in {"FIRST", "END"}:
            raise ValueError("edge must be FIRST or END")
        self.scope.write(f"{_PLAY}PLAY {'FFIRst' if edge == 'FIRST' else 'FEND'}")
        require_no_errors(self.scope)


@dataclass(frozen=True)
class ReferenceSettings:
    index: int
    source: str
    scale_v: float
    offset_v: float
    color: str
    label: str


class Reference:
    """Configuration and save/readback for one of the ten reference slots."""

    COLORS = {"GRAY": "GRAY", "GREEN": "GREen", "BLUE": "BLUE", "RED": "RED", "ORANGE": "ORANge"}

    def __init__(self, scope, index: int):
        if type(index) is not int or not 1 <= index <= 10:
            raise ValueError("reference index must be 1..10")
        self.scope, self.index = scope, index

    def _query(self, command: str) -> str:
        value = self.scope.query(command).strip()
        require_no_errors(self.scope)
        return value

    def settings(self) -> ReferenceSettings:
        i = self.index
        return ReferenceSettings(
            i, self._query(f":REFerence:SOURce? {i}"),
            float(self._query(f":REFerence:VSCale? {i}")),
            float(self._query(f":REFerence:VOFFset? {i}")),
            self._query(f":REFerence:COLor? {i}"),
            self._query(f":REFerence:LABel:CONTent? {i}"),
        )

    def set_source(self, source: str) -> None:
        if not isinstance(source, str):
            raise ValueError("reference source must be a string")
        source = source.strip().upper()
        if re.fullmatch(r"D(?:[0-9]|1[0-5])", source):
            profile_for(self.scope).source(source, digital=True)
            normalized = source
        elif re.fullmatch(r"MATH[1-4]", source):
            normalized = source
        else:
            normalized = normalize_channel_source(source, profile_for(self.scope))
        self.scope.write(f":REFerence:SOURce {self.index},{normalized}")
        require_no_errors(self.scope)
        if self._query(f":REFerence:SOURce? {self.index}").upper() != normalized.replace("CHANnel", "CHAN"):
            raise RuntimeError("reference source did not read back as requested")

    def set_scale(self, volts_per_division: float, *, probe_ratio: float = 1.0) -> None:
        ratios = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10,
                  20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000)
        if isinstance(probe_ratio, bool) or not isinstance(probe_ratio, (int, float)) or probe_ratio not in ratios:
            raise ValueError("probe ratio must be a supported discrete ratio")
        ratio = float(probe_ratio)
        value = _seconds(volts_per_division, 100e-6 * ratio, 10 * ratio, "reference scale")
        self.scope.write(f":REFerence:VSCale {self.index},{value:.12g}")
        require_no_errors(self.scope)
        if not math.isclose(float(self._query(f":REFerence:VSCale? {self.index}")), value, rel_tol=1e-7):
            raise RuntimeError("reference scale did not read back as requested")

    def set_offset(self, volts: float) -> None:
        scale = float(self._query(f":REFerence:VSCale? {self.index}"))
        value = _seconds(volts, -10 * scale, 10 * scale, "reference offset")
        self.scope.write(f":REFerence:VOFFset {self.index},{value:.12g}")
        require_no_errors(self.scope)
        if not math.isclose(float(self._query(f":REFerence:VOFFset? {self.index}")), value, rel_tol=1e-7, abs_tol=1e-12):
            raise RuntimeError("reference offset did not read back as requested")

    def reset_vertical(self, *, confirm: bool = False) -> None:
        if confirm is not True:
            raise ValueError("resetting reference scale and offset needs confirm=True")
        self.scope.write(f":REFerence:RESet {self.index}")
        require_no_errors(self.scope)

    def select(self) -> None:
        self.scope.write(f":REFerence:CURRent {self.index}")
        require_no_errors(self.scope)

    def save(self, *, confirm: bool = False) -> None:
        if confirm is not True:
            raise ValueError("saving a reference waveform needs confirm=True")
        self.scope.write(f":REFerence:SAVE {self.index}")
        require_no_errors(self.scope)

    def set_color(self, color: str) -> None:
        try:
            value = self.COLORS[color.upper()]
        except (AttributeError, KeyError):
            raise ValueError("color must be GRAY, GREEN, BLUE, RED, or ORANGE") from None
        self.scope.write(f":REFerence:COLor {self.index},{value}")
        require_no_errors(self.scope)
        returned = {"GRAY": "GRAY", "GREEN": "GRE", "BLUE": "BLUE", "RED": "RED", "ORANGE": "ORAN"}[color.upper()]
        if self._query(f":REFerence:COLor? {self.index}").upper() != returned:
            raise RuntimeError("reference color did not read back as requested")

    def set_label(self, text: str) -> None:
        if not isinstance(text, str) or not text or not text.isascii() or any(not c.isprintable() for c in text):
            raise ValueError("reference label must be nonempty printable ASCII")
        quoted = '"' + text.replace('"', '""') + '"'
        self.scope.write(f":REFerence:LABel:CONTent {self.index},{quoted}")
        require_no_errors(self.scope)
        if self._query(f":REFerence:LABel:CONTent? {self.index}") != text:
            raise RuntimeError("reference label did not read back as requested")


def reference_labels_enabled(scope) -> bool:
    value = _bool(scope.query(":REFerence:LABel:ENABle?"))
    require_no_errors(scope)
    return value


def enable_reference_labels(scope, enabled: bool) -> bool:
    if type(enabled) is not bool:
        raise ValueError("enabled must be bool")
    scope.write(f":REFerence:LABel:ENABle {'ON' if enabled else 'OFF'}")
    require_no_errors(scope)
    return reference_labels_enabled(scope)
