"""Typed status, LAN, and system controls for a Rigol DHO914S."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
import time

from dho800900_models import InstrumentIdentity as Identity, parse_identity, profile_for


def _query(scope, command: str) -> str:
    return scope.query(command).strip()


def _write(scope, command: str) -> None:
    scope.write(command)
    if hasattr(scope, "errors"):
        errors = scope.errors()
        if len(errors) != 1:
            raise RuntimeError(f"Rigol rejected {command!r}: {errors}")


def _int(scope, command: str, low: int, high: int) -> int:
    raw = _query(scope, command).upper()
    value = 1 if raw in {"ON", "TRUE"} else 0 if raw in {"OFF", "FALSE"} else int(raw)
    if not low <= value <= high:
        raise RuntimeError(f"Unexpected reply to {command}: {value}")
    return value


def _bool(value: bool) -> str:
    if type(value) is not bool:
        raise ValueError("value must be bool")
    return "ON" if value else "OFF"


def _confirm(confirm: bool, operation: str) -> None:
    if confirm is not True:
        raise PermissionError(f"{operation} requires confirm=True")


def _confirm_no_dut(value: bool, operation: str) -> None:
    if value is not True:
        raise PermissionError(f"{operation} requires explicit confirm_no_dut=True")


def _finite_timeout(scope) -> float:
    instrument = getattr(scope, "instrument", None)
    timeout = getattr(instrument, "timeout", None)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30_000:
        raise ValueError("instrument must have a finite VISA timeout no greater than 30 seconds")
    return float(timeout)


def _quiesce_outputs(scope) -> None:
    """Stop all documented event sources that can drive AUX, then turn AFG off."""
    failures = []
    for command in (":STOP", ":MASK:OPERate STOP", ":MASK:OUTPut:ENABle OFF",
                    ":SOURce:OUTPut:STATe OFF"):
        try:
            scope.write(command)
        except Exception as exc:
            failures.append(exc)
    try:
        state = _query(scope, ":SOURce:OUTPut:STATe?").upper()
        if state not in {"0", "OFF"}:
            failures.append(RuntimeError(f"AFG output remained enabled: {state!r}"))
    except Exception as exc:
        failures.append(exc)
    try:
        state = _query(scope, ":TRIGger:STATus?").upper()
        if state != "STOP":
            failures.append(RuntimeError(f"acquisition remained active: {state!r}"))
    except Exception as exc:
        failures.append(exc)
    try:
        state = _query(scope, ":MASK:OPERate?").upper()
        if state != "STOP":
            failures.append(RuntimeError(f"pass/fail test remained active: {state!r}"))
    except Exception as exc:
        failures.append(exc)
    try:
        state = _int(scope, ":MASK:OUTPut:ENABle?", 0, 1)
        if state != 0:
            failures.append(RuntimeError("pass/fail AUX output remained enabled"))
    except Exception as exc:
        failures.append(exc)
    try:
        if hasattr(scope, "errors"):
            errors = scope.errors()
            if len(errors) != 1:
                failures.append(RuntimeError(f"instrument errors during output shutdown: {errors}"))
    except Exception as exc:
        failures.append(exc)
    if failures:
        raise RuntimeError(f"could not verify output quiescence: {failures}")


@dataclass(frozen=True)
class LanSettings:
    dhcp: bool
    auto_ip: bool
    manual: bool
    ip_address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    dns: str | None = None
    mdns: bool | None = None
    host_name: str | None = None
    description: str | None = None

    def __post_init__(self):
        for field in ("dhcp", "auto_ip", "manual"):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f"{field} must be bool")
        if self.mdns is not None and type(self.mdns) is not bool:
            raise TypeError("mdns must be bool or None")
        for field in ("ip_address", "subnet_mask", "gateway", "dns", "host_name", "description"):
            value = getattr(self, field)
            if value is not None and type(value) is not str:
                raise TypeError(f"{field} must be str or None")


@dataclass(frozen=True)
class SystemStatus:
    aux_output: str
    beeper: bool
    power_on: str
    power_status: str
    locked: bool
    autoscale: bool
    analog_channels: int
    modules: tuple[int, ...]
    grids: int
    scpi_version: str
    dg_present: bool
    keyboard_check: str


def identity(scope) -> Identity:
    result = parse_identity(_query(scope, "*IDN?"))
    if result.model != profile_for(scope).model:
        raise RuntimeError(f"Expected {profile_for(scope).model} identity, received {result.model}")
    return result


def read_status(scope) -> SystemStatus:
    aux = _query(scope, ":SYSTem:AOUTput?").upper()
    pon = _query(scope, ":SYSTem:PON?").upper()
    pstatus = _query(scope, ":SYSTem:PSTatus?").upper()
    modules = tuple(int(part) for part in _query(scope, ":SYSTem:MODules?").split(","))
    status = SystemStatus(
        aux_output=aux,
        beeper=_int(scope, ":SYSTem:BEEPer?", 0, 1) == 1,
        power_on=pon,
        power_status=pstatus,
        locked=_int(scope, ":SYSTem:LOCKed?", 0, 1) == 1,
        autoscale=_int(scope, ":SYSTem:AUToscale?", 0, 1) == 1,
        analog_channels=_int(scope, ":SYSTem:RAMount?", 1, 4),
        modules=modules,
        grids=_int(scope, ":SYSTem:GAMount?", 1, 10),
        scpi_version=_query(scope, ":SYSTem:VERSion?"),
        dg_present=_int(scope, ":SYSTem:DGSTatus?", 0, 1) == 1,
        keyboard_check=_query(scope, ":SYSTem:KEYBOARDCheck?").lower(),
    )
    if aux not in {"TOUT", "PFA"} or pon not in {"LAT", "DEF"} or pstatus not in {"DEF", "OPEN"}:
        raise RuntimeError(f"Unexpected system status values: {status}")
    return status


def exercise_aux_output(scope, mode: str, *, duration_s: float | None,
                        confirm_no_dut: bool = False) -> str:
    """Run the selected AUX event source briefly, then restore the mode and stop it."""
    _confirm_no_dut(confirm_no_dut, "temporarily selecting AUX OUT mode")
    if not isinstance(mode, str) or mode.upper() not in {"TOUT", "PFAIL", "PFAILURE"}:
        raise ValueError("AUX OUT mode must be TOUT or PFAil")
    if isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) or not 0 < duration_s <= 5:
        raise ValueError("AUX OUT duration must be greater than zero and at most 5 seconds")
    _finite_timeout(scope)
    requested = "TOUT" if mode.upper() == "TOUT" else "PFAil"
    expected = "TOUT" if requested == "TOUT" else "PFA"
    _quiesce_outputs(scope)
    previous = _query(scope, ":SYSTem:AOUTput?").upper()
    if previous not in {"TOUT", "PFA", "PFAIL"}:
        raise RuntimeError(f"unknown AUX OUT mode {previous!r}; refusing to change it")
    try:
        _write(scope, f":SYSTem:AOUTput {requested}")
        actual = _query(scope, ":SYSTem:AOUTput?").upper()
        if actual != expected:
            raise RuntimeError(f"AUX OUT mode read back {actual!r}, expected {expected!r}")
        if requested == "TOUT":
            _write(scope, ":RUN")
        else:
            _write(scope, ":MASK:OUTPut:ENABle ON")
            _write(scope, ":MASK:OPERate RUN")
        time.sleep(duration_s)
        return actual
    finally:
        try:
            _quiesce_outputs(scope)
            _write(scope, f":SYSTem:AOUTput {'TOUT' if previous == 'TOUT' else 'PFAil'}")
            restored = _query(scope, ":SYSTem:AOUTput?").upper()
            if restored != ("TOUT" if previous == "TOUT" else "PFA"):
                raise RuntimeError(f"AUX OUT mode restoration read back {restored!r}")
        finally:
            _quiesce_outputs(scope)


def configure_system(scope, *, beeper: bool | None = None, power_on: str | None = None,
                     power_status: str | None = None, locked: bool | None = None,
                     autoscale: bool | None = None, aux_output: str | None = None,
                     confirm_aux: bool = False, aux_duration_s: float | None = None) -> SystemStatus:
    """Set system preferences or run and restore a bounded AUX mode."""
    if power_on is not None and power_on.upper() not in {"LAT", "LATEST", "DEF", "DEFAULT"}:
        raise ValueError("power_on must be LATest or DEFault")
    if power_status is not None and power_status.upper() not in {"DEF", "DEFAULT", "OPEN"}:
        raise ValueError("power_status must be DEFault or OPEN")
    if aux_output is not None:
        if any(value is not None for value in (beeper, power_on, power_status,
                                                locked, autoscale)):
            raise ValueError("configure AUX OUT separately from persistent system preferences")
        exercise_aux_output(scope, aux_output, duration_s=aux_duration_s,
                            confirm_no_dut=confirm_aux)
        return read_status(scope)
    requested = {}
    if beeper is not None:
        requested[":SYSTem:BEEPer"] = (_bool(beeper), "1" if beeper else "0")
    if power_on is not None:
        value = "LAT" if power_on.upper().startswith("LAT") else "DEF"
        requested[":SYSTem:PON"] = (value, value)
    if power_status is not None:
        value = "OPEN" if power_status.upper() == "OPEN" else "DEF"
        requested[":SYSTem:PSTatus"] = (value, value)
    if locked is not None:
        requested[":SYSTem:LOCKed"] = (_bool(locked), "1" if locked else "0")
    if autoscale is not None:
        requested[":SYSTem:AUToscale"] = (_bool(autoscale), "1" if autoscale else "0")
    old = {key: _query(scope, key + "?") for key in requested}
    try:
        for key, (value, expected) in requested.items():
            _write(scope, f"{key} {value}")
            actual = _query(scope, key + "?").upper()
            equivalent = {"ON": "1", "OFF": "0"}
            if equivalent.get(actual, actual) != expected:
                raise RuntimeError(f"{key} readback {actual!r}, expected {expected!r}")
    except Exception:
        for key, value in old.items():
            try:
                _write(scope, f"{key} {value}")
            except Exception:
                pass
        raise
    return read_status(scope)


def error_queue(scope, limit: int = 32, *, short_form: bool = False) -> tuple[tuple[int, str], ...]:
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError("limit must be 1-256")
    if type(short_form) is not bool:
        raise ValueError("short_form must be bool")
    result = []
    for _ in range(limit):
        raw = _query(scope, ":SYSTem:ERRor?" if short_form else ":SYSTem:ERRor:NEXT?")
        match = re.fullmatch(r'\s*([+-]?\d+)\s*,\s*"(.*)"\s*', raw)
        if not match:
            raise RuntimeError(f"Malformed error queue reply: {raw!r}")
        code, message = int(match.group(1)), match.group(2)
        if code == 0:
            return tuple(result)
        result.append((code, message))
    raise RuntimeError("Error queue did not terminate within limit")


def status_registers(scope) -> dict[str, int]:
    """Read/write status registers explicitly; ESR/STB queries are clear-on-read."""
    return {"ese": _int(scope, "*ESE?", 0, 255), "esr": _int(scope, "*ESR?", 0, 255),
            "sre": _int(scope, "*SRE?", 0, 255), "stb": _int(scope, "*STB?", 0, 255)}


def operation_complete(scope, *, query: bool = True) -> bool | None:
    if type(query) is not bool:
        raise ValueError("query must be bool")
    if query:
        return _int(scope, "*OPC?", 0, 1) == 1
    _write(scope, "*OPC")
    return None


def set_status_enable(scope, *, event_mask: int | None = None,
                      service_mask: int | None = None) -> dict[str, int]:
    for name, value in (("event_mask", event_mask), ("service_mask", service_mask)):
        if value is not None and (type(value) is not int or not 0 <= value <= 255):
            raise ValueError(f"{name} must be an integer 0-255")
    if event_mask is not None:
        _write(scope, f"*ESE {event_mask}")
        if _int(scope, "*ESE?", 0, 255) != event_mask:
            raise RuntimeError("*ESE readback mismatch")
    if service_mask is not None:
        _write(scope, f"*SRE {service_mask}")
        if _int(scope, "*SRE?", 0, 255) != service_mask:
            raise RuntimeError("*SRE readback mismatch")
    # Avoid reading ESR/STB here: both queries clear their registers.
    return {"ese": _int(scope, "*ESE?", 0, 255), "sre": _int(scope, "*SRE?", 0, 255)}


def _valid_ipv4(value: str, *, instrument_address: bool = False) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"invalid IPv4 address: {value!r}") from exc
    if instrument_address and (int(value.split(".")[0]) > 223 or int(value.split(".")[0]) == 127):
        raise ValueError("instrument IP/gateway/DNS first octet must be 0-223 except 127")
    return str(address)


def _read_lan(scope) -> LanSettings:
    def flag(command):
        return _int(scope, command, 0, 1) == 1
    return LanSettings(
        dhcp=flag(":LAN:DHCP?"), auto_ip=flag(":LAN:AUToip?"), manual=flag(":LAN:MANual?"),
        ip_address=_query(scope, ":LAN:IPADdress?"), subnet_mask=_query(scope, ":LAN:SMASk?"),
        gateway=_query(scope, ":LAN:GATeway?"), dns=_query(scope, ":LAN:DNS?"),
        mdns=flag(":LAN:MDNS?"), host_name=_query(scope, ":LAN:HOST:NAME?"),
        description=_query(scope, ":LAN:DESCription?"),
    )


def read_lan(scope) -> tuple[LanSettings, dict[str, str]]:
    settings = _read_lan(scope)
    details = {
        "mac": _query(scope, ":LAN:MAC?"), "dhcp_server": _query(scope, ":LAN:DSERver?"),
        "status": _query(scope, ":LAN:STATus?"),
        "visa_default": _query(scope, ":LAN:VISA?"),
        "visa_lxi": _query(scope, ":LAN:VISA? LXI"),
        "visa_usb": _query(scope, ":LAN:VISA? USB"),
        "visa_socket": _query(scope, ":LAN:VISA? SOCKet"),
    }
    if not re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", details["mac"]):
        raise RuntimeError(f"Malformed MAC address: {details['mac']!r}")
    return settings, details


def visa_address(scope, kind: str | None = None) -> str:
    if kind is None:
        return _query(scope, ":LAN:VISA?")
    aliases = {"USB": "USB", "LXI": "LXI", "SOCKET": "SOCKet"}
    try:
        normalized = aliases[kind.upper()]
    except (AttributeError, KeyError) as exc:
        raise ValueError("kind must be USB, LXI, SOCKET, or None") from exc
    return _query(scope, f":LAN:VISA? {normalized}")


def _write_modes(scope, target: LanSettings, old: LanSettings) -> None:
    modes = (("manual", target.manual, ":LAN:MANual"),
             ("auto_ip", target.auto_ip, ":LAN:AUToip"), ("dhcp", target.dhcp, ":LAN:DHCP"))
    for name, enabled, command in modes:
        if enabled and not getattr(old, name):
            _write(scope, f"{command} ON")
    for name, enabled, command in modes:
        if not enabled and getattr(old, name):
            _write(scope, f"{command} OFF")


def _restore_lan(scope, old: LanSettings) -> None:
    current = _read_lan(scope)
    temporary = LanSettings(False, False, True)
    _write_modes(scope, temporary, current)
    for field, command in (("ip_address", ":LAN:IPADdress"), ("subnet_mask", ":LAN:SMASk"),
                           ("gateway", ":LAN:GATeway"), ("dns", ":LAN:DNS")):
        _write(scope, f"{command} {getattr(old, field)}")
    _write(scope, f":LAN:MDNS {_bool(old.mdns)}")
    _write(scope, f':LAN:HOST:NAME "{old.host_name}"')
    _write(scope, f':LAN:DESCription "{old.description}"')
    temporary_with_old_modes = LanSettings(old.dhcp, old.auto_ip, old.manual)
    _write_modes(scope, temporary_with_old_modes, temporary)
    _write(scope, ":LAN:APPLy")


def configure_lan(scope, settings: LanSettings, *, confirm: bool = False) -> tuple[LanSettings, dict[str, str]]:
    """Apply LAN changes; this can drop the current control connection."""
    _confirm(confirm, "LAN reconfiguration")
    if not isinstance(settings, LanSettings):
        raise TypeError("settings must be LanSettings")
    if not any((settings.dhcp, settings.auto_ip, settings.manual)):
        raise ValueError("at least one LAN address mode must remain enabled")
    if any((settings.ip_address, settings.subnet_mask, settings.gateway, settings.dns)) and (
        not settings.manual or settings.dhcp or settings.auto_ip
    ):
        raise ValueError("static address fields require manual=True and DHCP/Auto IP disabled")
    addresses = {
        "ip_address": _valid_ipv4(settings.ip_address, instrument_address=True) if settings.ip_address else None,
        "gateway": _valid_ipv4(settings.gateway, instrument_address=True) if settings.gateway else None,
        "dns": _valid_ipv4(settings.dns, instrument_address=True) if settings.dns else None,
    }
    if settings.subnet_mask:
        try:
            addresses["subnet_mask"] = str(ipaddress.IPv4Network("0.0.0.0/" + settings.subnet_mask).netmask)
        except (ipaddress.NetmaskValueError, ValueError) as exc:
            raise ValueError("subnet_mask must be a contiguous IPv4 netmask") from exc
    for name in ("host_name", "description"):
        value = getattr(settings, name)
        if value is not None and (not value or any(ch in value for ch in '\r\n"')):
            raise ValueError(f"{name} must be nonempty and contain no quotes or newlines")
    old, _ = read_lan(scope)
    try:
        _write_modes(scope, settings, old)
        if settings.manual:
            for field, command in (("ip_address", ":LAN:IPADdress"), ("subnet_mask", ":LAN:SMASk"),
                                   ("gateway", ":LAN:GATeway"), ("dns", ":LAN:DNS")):
                value = addresses.get(field)
                if value is not None and value != getattr(old, field):
                    _write(scope, f"{command} {value}")
        if settings.mdns is not None and settings.mdns != old.mdns:
            _write(scope, f":LAN:MDNS {_bool(settings.mdns)}")
        for field, command in (("host_name", ":LAN:HOST:NAME"), ("description", ":LAN:DESCription")):
            value = getattr(settings, field)
            if value is not None and value != getattr(old, field):
                _write(scope, f'{command} "{value}"')
        _write(scope, ":LAN:APPLy")
        actual, details = read_lan(scope)
        for name in ("dhcp", "auto_ip", "manual", "mdns"):
            expected = getattr(settings, name)
            if expected is not None and getattr(actual, name) != expected:
                raise RuntimeError(f"LAN {name} readback mismatch: {getattr(actual, name)!r}")
        for name, value in addresses.items():
            if value is not None and getattr(actual, name) != value:
                raise RuntimeError(f"LAN {name} readback mismatch: {getattr(actual, name)!r}")
        for name in ("host_name", "description"):
            expected = getattr(settings, name)
            if expected is not None and getattr(actual, name) != expected:
                raise RuntimeError(f"LAN {name} readback mismatch")
    except Exception as error:
        try:
            _restore_lan(scope, old)
        except Exception as rollback_error:
            raise RuntimeError(
                f"LAN update failed ({error}); restoring the previous settings also failed "
                f"({rollback_error}); the connection may have dropped during apply"
            ) from error
        raise
    return actual, details


def _block(data: bytes) -> bytes:
    if not isinstance(data, bytes) or not data:
        raise ValueError("setup data must be nonempty bytes")
    if len(data) < 3 or data[:1] != b"#" or data[1:2] not in b"123456789":
        raise ValueError("setup data must have a valid IEEE 488.2 definite-length block header")
    digits = data[1] - ord("0")
    end = 2 + digits
    if len(data) < end or not data[2:end].isdigit():
        raise ValueError("setup data has an invalid IEEE block length")
    count = int(data[2:end])
    if len(data) != end + count:
        raise ValueError("setup block byte count does not match payload")
    return data


def read_setup(scope) -> bytes:
    payload = scope.instrument.query_binary_values(
        ":SYSTem:SETup?", datatype="B", container=bytes, header_fmt="ieee",
        expect_termination=True,
    )
    data = f"#{len(str(len(payload)))}{len(payload)}".encode("ascii") + payload
    _block(data)
    return data


def restore_setup(scope, data: bytes, *, confirm_no_dut: bool = False) -> None:
    _confirm_no_dut(confirm_no_dut, "restoring instrument setup")
    block = _block(data)
    if len(block) > 1_000_000:
        raise ValueError("setup block exceeds the 1 MB transfer limit")
    _finite_timeout(scope)
    instrument = getattr(scope, "instrument", None)
    if instrument is None or not hasattr(instrument, "write_raw"):
        raise TypeError("scope instrument must support write_raw for binary setup data")
    _quiesce_outputs(scope)
    try:
        instrument.write_raw(b":SYSTem:SETup " + block)
        if hasattr(scope, "errors"):
            errors = scope.errors()
            if len(errors) != 1:
                raise RuntimeError(f"Rigol rejected setup data: {errors}")
        _write(scope, "*OPC")
        if _int(scope, "*OPC?", 0, 1) != 1:
            raise RuntimeError("Setup restore did not complete")
    finally:
        _quiesce_outputs(scope)


def save_register(scope, register: int) -> None:
    if type(register) is not int or not 0 <= register <= 49:
        raise ValueError("register must be 0-49")
    _write(scope, f"*SAV {register}")
    _write(scope, "*OPC")
    if _int(scope, "*OPC?", 0, 1) != 1:
        raise RuntimeError("Save did not complete")


def recall_register(scope, *, confirm_no_dut: bool = False) -> None:
    _confirm_no_dut(confirm_no_dut, "recalling settings from nonvolatile memory")
    _finite_timeout(scope)
    _quiesce_outputs(scope)
    try:
        _write(scope, "*RCL")
        if _int(scope, "*OPC?", 0, 1) != 1:
            raise RuntimeError("Recall did not complete")
    finally:
        _quiesce_outputs(scope)


def reset(scope, *, confirm_no_dut: bool = False, system: bool = False) -> None:
    _confirm_no_dut(confirm_no_dut, "system restart" if system else "factory reset")
    _finite_timeout(scope)
    _quiesce_outputs(scope)
    try:
        _write(scope, ":SYSTem:RESet" if system else "*RST")
        if not system and _int(scope, "*OPC?", 0, 1) != 1:
            raise RuntimeError("Factory reset did not complete")
    finally:
        _quiesce_outputs(scope)


def clear_status(scope, *, confirm: bool = False) -> None:
    _confirm(confirm, "clearing event registers and error queue")
    _write(scope, "*CLS")


def wait_complete(scope) -> None:
    _write(scope, "*WAI")


def self_test(scope) -> tuple[bool, tuple[tuple[int, str], ...]]:
    passed = _int(scope, "*TST?", 0, 1) == 0
    return passed, error_queue(scope)
