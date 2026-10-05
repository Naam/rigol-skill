"""Typed, chunked waveform reads for the Rigol DHO914S."""

from __future__ import annotations

import csv
import math
import re
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import dho800900 as base
from dho800900_models import profile_for


SOURCES = frozenset(
    [f"CHAN{i}" for i in range(1, 5)]
    + [f"MATH{i}" for i in range(1, 5)]
    + [f"D{i}" for i in range(16)]
)
MODES = frozenset({"NORMAL", "MAX", "RAW"})
FORMATS = frozenset({"BYTE", "WORD", "ASCII"})
_MODE_CODE = {"NORMAL": 0, "MAX": 1, "RAW": 2}
_FORMAT_CODE = {"BYTE": 0, "WORD": 1, "ASCII": 2}


@dataclass(frozen=True)
class WaveformRequest:
    source: str
    mode: str = "NORMAL"
    data_format: str = "BYTE"
    points: int = 1000

    def __post_init__(self) -> None:
        source = self.source.upper().replace("CHANNEL", "CHAN")
        mode = self.mode.upper()
        data_format = self.data_format.upper()
        if source not in SOURCES:
            raise ValueError("source must be CHAN1-4, MATH1-4, or D0-D15")
        if mode not in MODES or data_format not in FORMATS:
            raise ValueError("mode must be NORMAL/MAX/RAW and format BYTE/WORD/ASCII")
        if source.startswith("MATH") and mode != "NORMAL":
            raise ValueError("MATH sources support NORMAL mode only")
        if type(self.points) is not int or not 1 <= self.points <= 50_000_000:
            raise ValueError("points must be an integer from 1 to 50,000,000")
        if mode == "NORMAL" and self.points > 1000:
            raise ValueError("NORMAL mode supports at most 1,000 points")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "data_format", data_format)


@dataclass(frozen=True)
class WaveformMetadata:
    source: str
    mode: str
    data_format: str
    points: int
    averages: int
    x_increment_s: float
    x_origin_s: float
    x_reference: float
    y_increment: float
    y_origin: float
    y_reference: float


@dataclass(frozen=True)
class Waveform:
    metadata: WaveformMetadata
    values: array

    def samples(self) -> Iterator[tuple[float, float]]:
        m = self.metadata
        for index, value in enumerate(self.values):
            yield m.x_origin_s + (index - m.x_reference) * m.x_increment_s, value


class DHO800900Waveforms:
    """Read selected waveforms, restoring the instrument's previous selection."""

    def __init__(self, scope, *, chunk_points: int = 250_000):
        if type(chunk_points) is not int or not 1 <= chunk_points <= 250_000:
            raise ValueError("chunk_points must be from 1 to 250,000")
        self.scope = scope
        self.chunk_points = chunk_points

    def _check_request(self, request: WaveformRequest) -> None:
        profile = profile_for(self.scope)
        if request.source.startswith("CHAN") or request.source.startswith("D"):
            profile.source(request.source, digital=True)
        if request.points > profile.max_memory_points(1):
            raise ValueError(f"{profile.model} waveform request exceeds its memory limit")

    def metadata(self, request: WaveformRequest) -> WaveformMetadata:
        """Read waveform scaling and selection metadata without transferring samples."""
        self._check_request(request)
        if request.mode == "RAW" and self.scope.query(":TRIGger:STATus?").upper() != "STOP":
            raise RuntimeError("RAW waveform requires a stopped acquisition")
        base.require_afg_off(self.scope)
        names = ("SOURce", "MODE", "FORMat", "POINts", "STARt", "STOP")
        previous = {name: self.scope.query(f":WAVeform:{name}?") for name in names}
        try:
            self._select(request)
            base.require_no_errors(self.scope)
            return self._metadata(request)
        finally:
            self._restore(previous)

    def read(self, request: WaveformRequest) -> Waveform:
        self._check_request(request)
        if request.points > 1_000_000:
            raise ValueError("in-memory reads are limited to 1,000,000 points; use export_csv")
        values = array("d")
        metadata: WaveformMetadata | None = None
        chunks = self._read_chunks(request)
        try:
            for metadata, chunk in chunks:
                values.extend(chunk)
        finally:
            chunks.close()
        assert metadata is not None
        return Waveform(metadata, values)

    def export_csv(self, request: WaveformRequest, path: str | Path) -> WaveformMetadata:
        """Stream up to 50M points to CSV without retaining the capture in memory."""
        self._check_request(request)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time_s", "value"))
            metadata: WaveformMetadata | None = None
            offset = 0
            chunks = self._read_chunks(request)
            try:
                for metadata, chunk in chunks:
                    writer.writerows(
                        (metadata.x_origin_s + (offset + i - metadata.x_reference)
                         * metadata.x_increment_s, value)
                        for i, value in enumerate(chunk)
                    )
                    offset += len(chunk)
            finally:
                chunks.close()
        assert metadata is not None
        return metadata

    def _read_chunks(self, request: WaveformRequest) -> Iterator[tuple[WaveformMetadata, array]]:
        if request.mode == "RAW" and self.scope.query(":TRIGger:STATus?").upper() != "STOP":
            raise RuntimeError("RAW waveform requires a stopped acquisition")
        base.require_afg_off(self.scope)
        names = ("SOURce", "MODE", "FORMat", "POINts", "STARt", "STOP")
        previous = {name: self.scope.query(f":WAVeform:{name}?") for name in names}
        try:
            self._select(request)
            base.require_no_errors(self.scope)
            metadata = self._metadata(request)
            for start in range(1, request.points + 1, self.chunk_points):
                stop = min(start + self.chunk_points - 1, request.points)
                self._set_window(start, stop)
                samples = self._data(request.data_format)
                expected = stop - start + 1
                if len(samples) != expected:
                    raise RuntimeError(f"waveform returned {len(samples)} of {expected} points")
                if request.data_format == "ASCII":
                    values = array("d", samples)
                else:
                    m = metadata
                    values = array("d", (
                        (sample - m.y_origin - m.y_reference) * m.y_increment
                        for sample in samples
                    ))
                yield metadata, values
            base.require_no_errors(self.scope)
        finally:
            self._restore(previous)

    def _select(self, request: WaveformRequest) -> None:
        # Reset the point window before changing mode/source to avoid stale bounds.
        self.scope.write(":WAVeform:STARt 1")
        self.scope.write(":WAVeform:STOP 1")
        self.scope.write(":WAVeform:POINts 1")
        source = f"CHANnel{request.source[4:]}" if request.source.startswith("CHAN") else request.source
        self.scope.write(f":WAVeform:SOURce {source}")
        self.scope.write(f":WAVeform:MODE {request.mode}")
        self.scope.write(f":WAVeform:FORMat {request.data_format}")
        self.scope.write(f":WAVeform:POINts {request.points}")

    def _set_window(self, start: int, stop: int) -> None:
        # Expand first, then contract, so neither write creates an invalid interval.
        current_start = int(self.scope.query(":WAVeform:STARt?"))
        current_stop = int(self.scope.query(":WAVeform:STOP?"))
        if start >= current_stop:
            self.scope.write(f":WAVeform:STOP {stop}")
            self.scope.write(f":WAVeform:STARt {start}")
        elif stop <= current_start:
            self.scope.write(f":WAVeform:STARt {start}")
            self.scope.write(f":WAVeform:STOP {stop}")
        else:
            self.scope.write(f":WAVeform:STARt {start}")
            self.scope.write(f":WAVeform:STOP {stop}")

    def _metadata(self, request: WaveformRequest) -> WaveformMetadata:
        fields = self.scope.query(":WAVeform:PREamble?").split(",")
        if len(fields) != 10:
            raise RuntimeError(f"invalid waveform preamble: {fields}")
        values = [float(item) for item in fields]
        if int(values[0]) != _FORMAT_CODE[request.data_format] or int(values[1]) != _MODE_CODE[request.mode]:
            raise RuntimeError("waveform preamble does not match the requested mode and format")
        if not 1 <= int(values[2]) <= 50_000_000:
            raise RuntimeError("waveform preamble reports an invalid point count")
        if not all(math.isfinite(value) for value in values[2:]):
            raise RuntimeError("waveform preamble contains a non-finite value")
        if values[4] <= 0 or (request.data_format != "ASCII" and values[7] == 0):
            raise RuntimeError("waveform preamble contains an invalid scale")
        return WaveformMetadata(
            request.source, request.mode, request.data_format, int(values[2]), int(values[3]),
            *values[4:10],
        )

    def _data(self, data_format: str) -> list[float] | bytes:
        if data_format == "ASCII":
            raw = self.scope.query(":WAVeform:DATA?")
            try:
                values = [float(item) for item in raw.rstrip("\r\n").split(",") if item]
            except ValueError as exc:
                raise RuntimeError("instrument returned malformed ASCII waveform data") from exc
            if not all(math.isfinite(value) for value in values):
                raise RuntimeError("instrument returned non-finite waveform data")
            return values
        datatype = "B" if data_format == "BYTE" else "H"
        # Guide specifies 16-bit WORDs without byte order; follow PyVISA's default.
        return self.scope.instrument.query_binary_values(
            ":WAVeform:DATA?", datatype=datatype, container=list,
            is_big_endian=False, header_fmt="ieee", expect_termination=True,
        )

    def _restore(self, previous: dict[str, str]) -> None:
        self.scope.write(":WAVeform:STARt 1")
        self.scope.write(":WAVeform:STOP 1")
        self.scope.write(":WAVeform:POINts 1")
        self.scope.write(":WAVeform:MODE NORMal")
        self.scope.write(f":WAVeform:SOURce {previous['SOURce']}")
        self.scope.write(f":WAVeform:FORMat {previous['FORMat']}")
        self.scope.write(f":WAVeform:MODE {previous['MODE']}")
        self.scope.write(f":WAVeform:POINts {previous['POINts']}")
        old_start = int(previous["STARt"])
        old_stop = int(previous["STOP"])
        self._set_window(old_start, old_stop)
        base.require_no_errors(self.scope)


DHO914SWaveforms = DHO800900Waveforms
