"""Shared DHO800/DHO900 VISA transport and binary transfers."""

from __future__ import annotations

import re

from dho800900_models import MODELS, InstrumentIdentity, ModelProfile, parse_identity, profile_for


class DHO800900:
    def __init__(self, instrument, *, model: str):
        self.instrument = instrument
        self.identity: InstrumentIdentity | None = None
        try:
            self.profile: ModelProfile = MODELS[model.upper()]
        except (AttributeError, KeyError) as exc:
            raise ValueError(f"unsupported DHO800/DHO900 model {model!r}") from exc

    def write(self, command: str) -> None:
        self._check_command(command)
        self.instrument.write(command)

    def query(self, command: str) -> str:
        self._check_command(command)
        return self.instrument.query(command).strip()

    def _check_command(self, command: str) -> None:
        """Reject guide-known missing hardware even for direct transport calls."""
        text = command.upper().strip()
        path = text.split(None, 1)[0]
        if path.startswith(":SOURCE:"):
            self.profile.require("afg")
        if path.startswith(":BODEPLOT:"):
            self.profile.require("bode")
        if path.startswith(":HISTOGRAM:"):
            self.profile.require("histogram")
        if path.startswith(":LA:") and not self.profile.digital_channels:
            raise NotImplementedError(f"{self.profile.model} has no logic analyzer")
        if re.match(r":(?:TRIGGER|BUS[1-4]):LIN:", path):
            self.profile.require("lin")
        if re.fullmatch(r":(?:TRIGGER|BUS[1-4]):MODE", path) and re.search(r"\sLIN\b", text):
            self.profile.require("lin")
        if re.fullmatch(r":BUS[1-4]:SPI:MODE", path) and re.search(r"\sCS\b", text):
            self.profile.require("spi_cs")
        if re.match(r":BUS[1-4]:SPI:SS:|:TRIGGER:SPI:(?:CS|SLEVEL|MODE)(?:\?|$)", path):
            self.profile.require("spi_cs")
        unquoted = re.sub(r'"(?:[^"]|"")*"', "", text)
        for match in re.finditer(r"(?<![A-Z0-9])CHAN(?:NEL)?([1-4])(?![A-Z0-9])", unquoted):
            self.profile.analog_channel(int(match.group(1)))
        if not self.profile.digital_channels and re.search(r"(?<![A-Z0-9])D(?:1[0-5]|[0-9])(?![A-Z0-9])", unquoted):
            raise NotImplementedError(f"{self.profile.model} has no digital channels")
        if not self.profile.external_trigger and re.search(r"(?<![A-Z0-9])EXT(?![A-Z0-9])", unquoted):
            raise NotImplementedError(f"{self.profile.model} has no EXT input")

    def screenshot(self) -> bytes:
        return self.instrument.query_binary_values(
            ":DISPlay:DATA? PNG", datatype="B", container=bytes,
            header_fmt="ieee", expect_termination=True,
        )

    def setup_data(self) -> bytes:
        return self.instrument.query_binary_values(
            ":SYSTem:SETup?", datatype="B", container=bytes,
            header_fmt="ieee", expect_termination=True,
        )

    def afg_off(self) -> None:
        if self.profile.afg:
            self.write(":SOURce:OUTPut:STATe OFF")

    def errors(self, limit: int = 32) -> list[str]:
        result = []
        for _ in range(limit):
            value = self.query(":SYSTem:ERRor:NEXT?")
            result.append(value)
            if re.match(r"^\+?0\s*,", value):
                return result
        raise RuntimeError("Rigol error queue did not terminate.")


def connect(resource: str | None = None, backend: str = "@py", *,
            expected_model: str | None = None):
    """Discover a guide-listed scope and return manager, scope, resource, identity."""
    if expected_model is not None and expected_model.upper() not in MODELS:
        raise ValueError(f"unsupported DHO800/DHO900 model {expected_model!r}")
    try:
        import pyvisa
    except ImportError as exc:
        raise SystemExit("Install skills/rigol-dho900/requirements.txt first.") from exc
    manager = pyvisa.ResourceManager(backend)
    candidates = (resource,) if resource else manager.list_resources()
    for candidate in candidates:
        instrument = None
        try:
            instrument = manager.open_resource(candidate)
            instrument.timeout = 5000
            instrument.chunk_size = 1024 * 1024
            instrument.read_termination = "\n"
            instrument.write_termination = "\n"
            raw_identity = instrument.query("*IDN?").strip()
            identity = parse_identity(raw_identity)
            if expected_model is not None and identity.model != expected_model.upper():
                if hasattr(instrument, "close"):
                    instrument.close()
                continue
            scope = DHO800900(instrument, model=identity.model)
            scope.identity = identity
            return manager, scope, candidate, raw_identity
        except Exception:
            if instrument is not None and hasattr(instrument, "close"):
                instrument.close()
            if resource:
                raise
    raise SystemExit(f"No Rigol {expected_model or 'DHO800/DHO900'} instrument found.")


MEASUREMENT_TYPES = (
    "VMAX", "VMIN", "VPP", "VTOP", "VBASE", "VAMP", "VAVG", "VRMS",
    "OVERSHOOT", "PRESHOOT", "MAREA", "MPAREA", "PERIOD", "FREQUENCY",
    "RTIME", "FTIME", "PWIDTH", "NWIDTH", "PDUTY", "NDUTY",
    "TVMAX", "TVMIN", "PSLEWRATE", "NSLEWRATE", "VUPPER", "VMID",
    "VLOWER", "VARIANCE", "PVRMS", "PPULSES", "NPULSES", "PEDGES",
    "NEDGES", "RRDELAY", "RFDELAY", "FRDELAY", "FFDELAY",
    "RRPHASE", "RFPHASE", "FRPHASE", "FFPHASE", "ACRMS",
)
DUAL_MEASUREMENTS = {"RRDELAY", "RFDELAY", "FRDELAY", "FFDELAY",
                     "RRPHASE", "RFPHASE", "FRPHASE", "FFPHASE"}
DIGITAL_MEASUREMENTS = {"PERIOD", "FREQUENCY", "PWIDTH", "NWIDTH", "PDUTY", "NDUTY"} | DUAL_MEASUREMENTS
CHANNEL_SOURCES = tuple(f"CHAN{i}" for i in range(1, 5))


def require_no_errors(scope: DHO800900) -> None:
    errors = scope.errors()
    if len(errors) != 1:
        raise RuntimeError(f"Rigol rejected a command: {errors}")


def normalize_channel_source(source: str, profile: ModelProfile,
                             *, external: bool = False) -> str:
    normalized = profile.source(source, external=external)
    return normalized if normalized == "EXT" else f"CHANnel{normalized[4:]}"


def normalize_measure_source(source: str, item: str, profile: ModelProfile) -> str:
    if re.fullmatch(r"D(?:[0-9]|1[0-5])", source.upper()):
        if item not in DIGITAL_MEASUREMENTS:
            raise ValueError(f"{item} does not support digital channels")
        profile.source(source, digital=True)
        return source.upper()
    if re.fullmatch(r"MATH[1-4]", source.upper()):
        return source.upper()
    return normalize_channel_source(source, profile)


def normalize_counter_source(source: str, profile: ModelProfile) -> str:
    if re.fullmatch(r"D(?:[0-9]|1[0-5])", source.upper()):
        profile.source(source, digital=True)
        return source.upper()
    return normalize_channel_source(source, profile, external=True)


def require_afg_off(scope: DHO800900) -> None:
    if not profile_for(scope).afg:
        return
    scope.afg_off()
    if scope.query(":SOURce:OUTPut:STATe?") not in {"0", "OFF"}:
        raise RuntimeError("Rigol AFG did not confirm OFF.")


def require_confirmation(value: str) -> None:
    if value != "VERIFIED":
        raise SystemExit("Refusing to energize: pass --confirmed VERIFIED after physical verification.")
