"""Typed file, image, SMB, and shortcut-key operations for the DHO914S."""

from __future__ import annotations

import ipaddress
import math
import re
import time
from dataclasses import dataclass, field

from dho800900 import require_afg_off, require_no_errors


_BOOLS = {"1": True, "ON": True, "0": False, "OFF": False}
_IMAGE_FORMATS = {"PNG", "BMP", "JPG"}
_QUICK_OPERATIONS = {
    "SIMAGE": "SIM", "SWAVE": "SWAV", "SSETUP": "SSET", "AMEASURE": "AME",
    "SRESET": "SRES", "RECORD": "REC", "SSAVE": "SSAV",
}


@dataclass(frozen=True)
class SavePreferences:
    image_invert: bool | None = None
    image_color: str | None = None
    image_format: str | None = None
    image_header: bool | None = None
    overwrite: bool | None = None
    prefix: str | None = None


@dataclass(frozen=True)
class SaveState:
    image_invert: bool
    image_color: str
    image_format: str
    image_header: bool
    overwrite: bool
    prefix: str


@dataclass(frozen=True)
class InstrumentFile:
    kind: str
    path: str


@dataclass(frozen=True)
class SmbSettings:
    server_path: str | None = None
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    autoconnect: bool | None = None


@dataclass(frozen=True)
class SmbState:
    server_path: str
    username: str
    autoconnect: bool
    connected: bool


def _bool(value: str, name: str) -> bool:
    try:
        return _BOOLS[value.strip().upper()]
    except KeyError:
        raise RuntimeError(f"unexpected {name} response: {value!r}") from None


def _scpi_text(value: str, name: str, *, max_length: int | None = None,
               allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ValueError(f"{name} must be a nonempty string")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(f"{name} must use ASCII characters") from None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{name} cannot contain control characters")
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{name} must be at most {max_length} characters")
    return value


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _returned_text(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def _set_checked(scope, command: str, value: str, query: str, expected: str) -> str:
    scope.write(f"{command} {value}")
    actual = _returned_text(scope.query(query))
    if actual.upper() != expected.upper():
        raise RuntimeError(f"{query} readback mismatch: {actual!r}")
    return actual


def _read_save_state(scope) -> SaveState:
    color = _returned_text(scope.query(":SAVE:IMAGe:COLor?")).upper()
    color = {"COL": "COLOR"}.get(color, color)
    image_format = _returned_text(scope.query(":SAVE:IMAGe:FORMat?")).upper()
    if color not in {"COLOR", "GRAY"}:
        raise RuntimeError(f"unexpected image color response: {color!r}")
    if image_format not in _IMAGE_FORMATS:
        raise RuntimeError(f"unexpected image format response: {image_format!r}")
    header = _bool(scope.query(":SAVE:IMAGe:HEADer?"), "image header")
    invert = _bool(scope.query(":SAVE:IMAGe:INVert?"), "image invert")
    overlap = _bool(scope.query(":SAVE:OVERlap?"), "overwrite")
    prefix = _returned_text(scope.query(":SAVE:PREFix?"))
    return SaveState(invert, color, image_format, header, overlap, prefix)


def configure_save_preferences(scope, settings: SavePreferences, *,
                               confirm_overwrite: bool = False) -> SaveState:
    """Configure save defaults with readback; enabling overlap requires confirmation."""
    if settings.image_invert is not None and type(settings.image_invert) is not bool:
        raise ValueError("image_invert must be bool")
    if settings.image_header is not None and type(settings.image_header) is not bool:
        raise ValueError("image_header must be bool")
    if settings.overwrite is not None and type(settings.overwrite) is not bool:
        raise ValueError("overwrite must be bool")
    color = settings.image_color.upper() if settings.image_color is not None else None
    if color is not None and color not in {"COLOR", "GRAY"}:
        raise ValueError("image_color must be COLOR or GRAY")
    image_format = settings.image_format.upper() if settings.image_format is not None else None
    if image_format is not None and image_format not in _IMAGE_FORMATS:
        raise ValueError("image_format must be PNG, BMP, or JPG")
    prefix = (_scpi_text(settings.prefix, "prefix", max_length=16)
              if settings.prefix is not None else None)
    if prefix is not None and "." in prefix:
        raise ValueError("prefix must not include a file suffix")
    if settings.overwrite is True and confirm_overwrite is not True:
        raise PermissionError("enabling file overwrite requires confirm_overwrite=True")
    if type(confirm_overwrite) is not bool:
        raise ValueError("confirm_overwrite must be bool")

    require_afg_off(scope)
    updates = (
        (settings.image_invert, ":SAVE:IMAGe:INVert", ":SAVE:IMAGe:INVert?", "bool"),
        (color, ":SAVE:IMAGe:COLor", ":SAVE:IMAGe:COLor?", "color"),
        (image_format, ":SAVE:IMAGe:FORMat", ":SAVE:IMAGe:FORMat?", "text"),
        (settings.image_header, ":SAVE:IMAGe:HEADer", ":SAVE:IMAGe:HEADer?", "bool"),
        (settings.overwrite, ":SAVE:OVERlap", ":SAVE:OVERlap?", "bool"),
        (prefix, ":SAVE:PREFix", ":SAVE:PREFix?", "text"),
    )
    require_no_errors(scope)
    for value, command, query, kind in updates:
        if value is None:
            continue
        wire = ("ON" if value else "OFF") if kind == "bool" else (
            "COLor" if value == "COLOR" else "GRAY" if value == "GRAY" else
            "PNG" if value == "PNG" else "BMP" if value == "BMP" else
            "JPG" if value == "JPG" else _quoted(value))
        expected = ("1" if value else "0") if kind == "bool" else (
            "COL" if value == "COLOR" else str(value))
        _set_checked(scope, command, wire, query, expected)
    state = _read_save_state(scope)
    require_no_errors(scope)
    return state


def read_save_state(scope) -> SaveState:
    state = _read_save_state(scope)
    require_no_errors(scope)
    return state


def image_data(scope) -> bytes:
    """Read the displayed bitmap binary block using the instrument's IEEE header."""
    data = scope.instrument.query_binary_values(
        ":SAVE:IMAGe:DATA?", datatype="B", container=bytes,
        header_fmt="ieee", expect_termination=True,
    )
    if not isinstance(data, bytes) or not data:
        raise RuntimeError("instrument returned empty image data")
    require_no_errors(scope)
    return data


def save_status(scope) -> bool:
    status = _bool(scope.query(":SAVE:STATus?"), "save status")
    require_no_errors(scope)
    return status


def _instrument_path(path: str, extensions: set[str]) -> str:
    path = _scpi_text(path, "instrument path")
    match = re.fullmatch(r"([C-Z]):/(.+)", path, flags=re.IGNORECASE)
    if not match:
        raise ValueError("instrument path must start with C:/ or an external drive letter such as D:/")
    components = match.group(2).split("/")
    if any(part in {"", ".", ".."} for part in components):
        raise ValueError("instrument path cannot contain empty, current, or parent components")
    filename = components[-1]
    if len(filename) > 16:
        raise ValueError("instrument filename must be at most 16 characters")
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in extensions:
        raise ValueError(f"filename suffix must be one of {', '.join(sorted(extensions))}")
    return path


def _wait_save(scope, timeout_s: float) -> None:
    if not math.isfinite(timeout_s) or not 0.1 <= timeout_s <= 120:
        raise ValueError("timeout_s must be 0.1 to 120 seconds")
    deadline = time.monotonic() + timeout_s
    while True:
        if _bool(scope.query(":SAVE:STATus?"), "save status"):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("instrument save did not complete before timeout")
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))


def _save_file(scope, kind: str, path: str, extension: set[str], command: str, *,
               confirm_overwrite: bool, timeout_s: float) -> InstrumentFile:
    if type(confirm_overwrite) is not bool:
        raise ValueError("confirm_overwrite must be bool")
    path = _instrument_path(path, extension)
    if not math.isfinite(timeout_s) or not 0.1 <= timeout_s <= 120:
        raise ValueError("timeout_s must be 0.1 to 120 seconds")
    require_afg_off(scope)
    require_no_errors(scope)
    if not save_status(scope):
        raise RuntimeError("another instrument save is still in progress")
    original_overlap = _bool(scope.query(":SAVE:OVERlap?"), "overwrite")
    target_overlap = confirm_overwrite
    changed_overlap = original_overlap != target_overlap
    try:
        if changed_overlap:
            _set_checked(scope, ":SAVE:OVERlap", "ON" if target_overlap else "OFF",
                         ":SAVE:OVERlap?", "1" if target_overlap else "0")
        scope.write(f"{command} {_quoted(path)}")
        _wait_save(scope, timeout_s)
        require_no_errors(scope)
    finally:
        if changed_overlap:
            _set_checked(scope, ":SAVE:OVERlap", "ON" if original_overlap else "OFF",
                         ":SAVE:OVERlap?", "1" if original_overlap else "0")
    return InstrumentFile(kind, path)


def save_image(scope, path: str, *, confirm_overwrite: bool = False,
               timeout_s: float = 30) -> InstrumentFile:
    return _save_file(scope, "image", path, {".png", ".bmp", ".jpg"},
                      ":SAVE:IMAGe", confirm_overwrite=confirm_overwrite, timeout_s=timeout_s)


def save_setup(scope, path: str, *, confirm_overwrite: bool = False,
               timeout_s: float = 30) -> InstrumentFile:
    return _save_file(scope, "setup", path, {".stp"}, ":SAVE:SETup",
                      confirm_overwrite=confirm_overwrite, timeout_s=timeout_s)


def save_waveform(scope, path: str, *, confirm_overwrite: bool = False,
                  timeout_s: float = 30) -> InstrumentFile:
    return _save_file(scope, "waveform", path, {".bin", ".csv"}, ":SAVE:WAVeform",
                      confirm_overwrite=confirm_overwrite, timeout_s=timeout_s)


def save_memory_waveform(scope, path: str, *, confirm_overwrite: bool = False,
                         timeout_s: float = 30) -> InstrumentFile:
    return _save_file(scope, "memory_waveform", path, {".bin", ".csv", ".wfm"},
                      ":SAVE:MEMory:WAVeform", confirm_overwrite=confirm_overwrite,
                      timeout_s=timeout_s)


def _smb_path(value: str) -> str:
    path = _scpi_text(value, "SMB server path")
    match = re.fullmatch(r"\\\\([^\\]+)\\([A-Za-z]+)", path)
    if not match:
        raise ValueError("SMB path must be \\\\IPv4-address\\ShareName")
    try:
        ipaddress.IPv4Address(match.group(1))
    except ipaddress.AddressValueError:
        raise ValueError("SMB path must contain a valid IPv4 address") from None
    return path


def read_smb(scope) -> SmbState:
    state = SmbState(
        _returned_text(scope.query(":SAVe:SMB:SERVerpath?")),
        _returned_text(scope.query(":SAVe:SMB:USERname?")),
        _bool(scope.query(":SAVe:SMB:AUToconnect?"), "SMB autoconnect"),
        _bool(scope.query(":SAVe:SMB:CONState?"), "SMB connection"),
    )
    require_no_errors(scope)
    return state


def read_smb_password(scope) -> str:
    """Read the configured SMB password; call only when the secret is needed."""
    password = _returned_text(scope.query(":SAVe:SMB:PASSword?"))
    require_no_errors(scope)
    return password


def configure_smb(scope, settings: SmbSettings) -> SmbState:
    updates: list[tuple[str, str, str]] = []
    if settings.server_path is not None:
        updates.append((":SAVe:SMB:SERVerpath", _quoted(_smb_path(settings.server_path)),
                        _smb_path(settings.server_path)))
    if settings.username is not None:
        username = _scpi_text(settings.username, "SMB username", allow_empty=True)
        updates.append((":SAVe:SMB:USERname", _quoted(username), username))
    if settings.password is not None:
        password = _scpi_text(settings.password, "SMB password", allow_empty=True)
        updates.append((":SAVe:SMB:PASSword", _quoted(password), password))
    if settings.autoconnect is not None and type(settings.autoconnect) is not bool:
        raise ValueError("SMB autoconnect must be bool")
    require_afg_off(scope)
    require_no_errors(scope)
    for command, wire, expected in updates:
        scope.write(f"{command} {wire}")
        actual = _returned_text(scope.query(command + "?"))
        if actual != expected:
            raise RuntimeError(f"{command}? readback mismatch")
    if settings.password is not None and read_smb_password(scope) != settings.password:
        raise RuntimeError("SMB password readback mismatch")
    if settings.autoconnect is not None:
        _set_checked(scope, ":SAVe:SMB:AUToconnect",
                     "ON" if settings.autoconnect else "OFF",
                     ":SAVe:SMB:AUToconnect?", "1" if settings.autoconnect else "0")
    state = read_smb(scope)
    if settings.server_path is not None and state.server_path != settings.server_path:
        raise RuntimeError("SMB server path readback mismatch")
    if settings.username is not None and state.username != settings.username:
        raise RuntimeError("SMB username readback mismatch")
    if settings.autoconnect is not None and state.autoconnect != settings.autoconnect:
        raise RuntimeError("SMB autoconnect readback mismatch")
    require_no_errors(scope)
    return state


def connect_smb(scope) -> SmbState:
    require_afg_off(scope)
    require_no_errors(scope)
    scope.write(":SAVe:SMB:CONNect")
    state = read_smb(scope)
    if not state.connected:
        raise RuntimeError("SMB connection did not become active")
    return state


def disconnect_smb(scope) -> SmbState:
    require_afg_off(scope)
    require_no_errors(scope)
    scope.write(":SAVe:SMB:DISConnect")
    state = read_smb(scope)
    if state.connected:
        raise RuntimeError("SMB connection remained active")
    return state


def _quiesce_recalled_state(scope) -> None:
    failures = []
    for command in (":STOP", ":MASK:OPERate STOP", ":MASK:OUTPut:ENABle OFF",
                    ":MASK:ENABle OFF", ":SOURce:OUTPut:STATe OFF"):
        try:
            scope.write(command)
        except Exception as error:
            failures.append(f"{command}: {error}")
    checks = (
        (":TRIGger:STATus?", {"STOP"}, "acquisition did not stop"),
        (":MASK:OPERate?", {"STOP"}, "mask operation did not stop"),
        (":MASK:OUTPut:ENABle?", {"0", "OFF"}, "mask AUX output remained enabled"),
        (":MASK:ENABle?", {"0", "OFF"}, "mask remained enabled"),
        (":SOURce:OUTPut:STATe?", {"0", "OFF"}, "AFG remained enabled"),
    )
    for command, expected, error in checks:
        try:
            if scope.query(command).strip().upper() not in expected:
                failures.append(error)
        except Exception as failure:
            failures.append(f"{command}: {failure}")
    try:
        require_no_errors(scope)
    except Exception as error:
        failures.append(str(error))
    if failures:
        raise RuntimeError(f"failed to quiesce recalled scope outputs: {failures}")


def load_setup(scope, path: str, *, confirm_no_dut: bool = False) -> str:
    """Load a setup with no DUT; bound recall and quiesce acquisition, mask AUX, and AFG."""
    if confirm_no_dut is not True:
        raise PermissionError("loading a setup requires confirm_no_dut=True")
    path = _instrument_path(path, {".stp"})
    instrument = getattr(scope, "instrument", None)
    timeout_ms = getattr(instrument, "timeout", None)
    if (type(timeout_ms) not in {int, float} or not math.isfinite(timeout_ms) or
            timeout_ms <= 0):
        raise RuntimeError("setup load requires a finite VISA instrument timeout")
    instrument.timeout = min(timeout_ms, 5000)
    try:
        require_no_errors(scope)
        _quiesce_recalled_state(scope)
        try:
            scope.write(f":LOAD:SETup {_quoted(path)}")
            if scope.query("*OPC?").strip() != "1":
                raise RuntimeError("setup load did not complete")
            require_no_errors(scope)
        finally:
            _quiesce_recalled_state(scope)
    finally:
        instrument.timeout = timeout_ms
    return path


def configure_quick_operation(scope, operation: str) -> str:
    """Choose the function assigned to the scope's quick-operation shortcut key."""
    operation = operation.upper()
    if operation not in _QUICK_OPERATIONS:
        raise ValueError(f"operation must be one of {', '.join(_QUICK_OPERATIONS)}")
    require_afg_off(scope)
    require_no_errors(scope)
    scope.write(f":QUICk:OPERation {operation}")
    actual = scope.query(":QUICk:OPERation?").strip().upper()
    if actual != _QUICK_OPERATIONS[operation]:
        raise RuntimeError(f"quick operation readback mismatch: {actual!r}")
    require_no_errors(scope)
    return operation


def read_quick_operation(scope) -> str:
    actual = scope.query(":QUICk:OPERation?").strip().upper()
    reverse = {value: key for key, value in _QUICK_OPERATIONS.items()}
    try:
        result = reverse[actual]
    except KeyError:
        raise RuntimeError(f"unexpected quick operation response: {actual!r}") from None
    require_no_errors(scope)
    return result
