"""Capabilities explicitly distinguished in the DHO800/DHO900 programming guide.

PGA39106-1110, April 2025: model tables pp. 1-2; memory p. 20;
LIN p. 25; SPI CS p. 56; Bode p. 64; EXT p. 82; histogram p. 117;
logic analyzer p. 133; AFG p. 275.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


GUIDE_PUBLICATION = "PGA39106-1110"
GUIDE_SOFTWARE = "00.01.03"


@dataclass(frozen=True)
class InstrumentIdentity:
    manufacturer: str
    model: str
    serial: str
    firmware: str

    @property
    def guide_status(self) -> str:
        """A version match is documentation alignment, not live acceptance."""
        parts = re.match(r"^V?(\d+)\.(\d+)\.(\d+)(?:\.|$)", self.firmware.upper())
        if parts is None:
            return "unknown"
        version = tuple(map(int, parts.groups()))
        return "matched" if version == tuple(map(int, GUIDE_SOFTWARE.split("."))) else "different"


def parse_identity(response: str) -> InstrumentIdentity:
    fields = [field.strip() for field in response.split(",")]
    if len(fields) < 4 or "RIGOL" not in fields[0].upper() or fields[1].upper() not in MODELS:
        raise ValueError("*IDN? did not identify a documented Rigol DHO800/DHO900 model")
    return InstrumentIdentity(fields[0], fields[1].upper(), fields[2], fields[3])


@dataclass(frozen=True)
class ModelProfile:
    model: str
    family: str
    analog_channels: int
    bandwidth_hz: int
    external_trigger: bool
    digital_channels: int
    spi_cs: bool
    lin: bool
    histogram: bool
    afg: bool
    bode: bool
    memory_points_by_enabled_channels: tuple[int, int, int]

    def require(self, capability: str) -> None:
        if capability not in {"external_trigger", "spi_cs", "lin", "histogram", "afg", "bode"}:
            raise ValueError(f"unknown capability {capability!r}")
        if not getattr(self, capability):
            raise NotImplementedError(f"{self.model} does not support {capability}")

    def analog_channel(self, number: int) -> int:
        if type(number) is not int or not 1 <= number <= self.analog_channels:
            raise ValueError(f"{self.model} analog channel must be 1..{self.analog_channels}")
        return number

    def source(self, value: str, *, digital: bool = False, external: bool = False) -> str:
        if not isinstance(value, str):
            raise ValueError("source must be a channel name")
        source = value.strip().upper().replace("CHANNEL", "CHAN")
        match = re.fullmatch(r"CHAN([1-4])", source)
        if match:
            self.analog_channel(int(match.group(1)))
            return source
        match = re.fullmatch(r"D(1[0-5]|[0-9])", source)
        if match and digital and int(match.group(1)) < self.digital_channels:
            return source
        if source == "EXT" and external and self.external_trigger:
            return source
        raise ValueError(f"{source!r} is not a supported {self.model} source")

    def max_memory_points(self, enabled_analog_channels: int) -> int:
        if type(enabled_analog_channels) is not int or not 1 <= enabled_analog_channels <= self.analog_channels:
            raise ValueError("enabled channel count is outside this model's range")
        return self.memory_points_by_enabled_channels[min(enabled_analog_channels, 3) - 1]


def _profile(model: str, channels: int, bandwidth_mhz: int) -> ModelProfile:
    family = "DHO900" if model.startswith("DHO9") else "DHO800"
    dho900 = family == "DHO900"
    generator = model in {"DHO914S", "DHO924S"}
    return ModelProfile(
        model=model, family=family, analog_channels=channels,
        bandwidth_hz=bandwidth_mhz * 1_000_000,
        external_trigger=model in {"DHO802", "DHO812"},
        digital_channels=16 if dho900 else 0,
        spi_cs=dho900 or channels == 4,
        lin=dho900, histogram=dho900, afg=generator, bode=generator,
        memory_points_by_enabled_channels=(50_000_000, 25_000_000, 10_000_000)
        if dho900 else (25_000_000, 10_000_000, 5_000_000),
    )


MODELS = {model: _profile(model, channels, bandwidth) for model, channels, bandwidth in (
    ("DHO802", 2, 70), ("DHO804", 4, 70),
    ("DHO812", 2, 100), ("DHO814", 4, 100),
    ("DHO914", 4, 125), ("DHO914S", 4, 125),
    ("DHO924", 4, 250), ("DHO924S", 4, 250),
)}


def profile_for_identity(identity: str) -> ModelProfile:
    return MODELS[parse_identity(identity).model]


def profile_for(scope) -> ModelProfile:
    """Require an explicit model profile on every transport."""
    try:
        return scope.profile
    except AttributeError as exc:
        raise ValueError("scope has no model profile") from exc
