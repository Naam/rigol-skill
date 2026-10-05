"""Typed search and navigation workflows for the Rigol DHO914S (guide 3.22-3.23)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from dho800900 import normalize_channel_source, require_afg_off, require_no_errors
from dho800900_models import profile_for


_SEARCH_ENUMS = {
    "mode": ("EDGE", "PULSE"),
    "edge_slope": ("POSITIVE", "NEGATIVE", "EITHER"),
    "pulse_polarity": ("POSITIVE", "NEGATIVE"),
    "pulse_qualifier": ("GREATER", "LESS", "GLESS"),
}
_NAV_ENUMS = {
    "mode": ("TIME", "SEARCH", "FRAME"),
    "speed": ("HIGH", "NORMAL", "LOW"),
    "frame_display": ("ADJACENT", "OVERLAY", "WATERFALL", "PERSPECTIVE", "MOSAIC"),
}
_SHORT = {
    "EDGE": "EDGE", "PULSE": "PULS", "POSITIVE": "POS", "NEGATIVE": "NEG",
    "EITHER": "EITH", "GREATER": "GRE", "LESS": "LESS", "GLESS": "GLES",
    "TIME": "TIME", "SEARCH": "SEAR", "FRAME": "FRAM", "HIGH": "HIGH",
    "NORMAL": "NORM", "LOW": "LOW", "ADJACENT": "ADJ", "OVERLAY": "OVER",
    "WATERFALL": "WAT", "PERSPECTIVE": "PERS", "MOSAIC": "MOS",
}


@dataclass(frozen=True)
class SearchSettings:
    mode: str = "EDGE"
    enabled: bool = True
    edge_slope: str = "POSITIVE"
    edge_source: str = "CHAN1"
    edge_threshold_v: float = 0.0
    pulse_polarity: str = "POSITIVE"
    pulse_qualifier: str = "GREATER"
    pulse_source: str = "CHAN1"
    pulse_lower_s: float = 1e-6
    pulse_upper_s: float = 2e-6
    pulse_threshold_v: float = 0.0


@dataclass(frozen=True)
class SearchState:
    settings: SearchSettings
    event_count: int
    selected_event: int


@dataclass(frozen=True)
class NavigationSettings:
    mode: str = "TIME"
    enabled: bool = True
    speed: str = "NORMAL"
    frame_display: str = "ADJACENT"
    frame_start: int | None = None
    frame_end: int | None = None


@dataclass(frozen=True)
class NavigationState:
    settings: NavigationSettings
    time_playing: bool
    frame_playing: bool
    frame_start: int
    frame_end: int
    maximum_frames: int


def _enum(name: str, value: str, choices: dict[str, tuple[str, ...]]) -> str:
    result = value.upper()
    if result not in choices[name]:
        raise ValueError(f"{name} must be one of {', '.join(choices[name])}")
    return result


def _bool(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized in {"1", "ON"}:
        return True
    if normalized in {"0", "OFF"}:
        return False
    raise RuntimeError(f"unexpected boolean response: {value!r}")


def _number(value: str, name: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise RuntimeError(f"unexpected {name} response: {value!r}") from None
    if not math.isfinite(number):
        raise RuntimeError(f"non-finite {name} response: {value!r}")
    return number


def _integer(value: str, name: str, minimum: int = 0) -> int:
    try:
        number = int(value)
    except ValueError:
        raise RuntimeError(f"unexpected {name} response: {value!r}") from None
    if number < minimum:
        raise RuntimeError(f"invalid {name}: {number}")
    return number


def _afg_off(scope) -> None:
    require_afg_off(scope)


def _stopped(scope) -> None:
    if scope.query(":TRIGger:STATus?").upper() != "STOP":
        raise RuntimeError("acquisition must be STOPped for navigation")


def _voltage_limit(scope, source: str, factor: float) -> tuple[float, float]:
    channel = normalize_channel_source(source, profile_for(scope))
    scale = _number(scope.query(f":{channel}:SCALe?"), f"{channel} scale")
    offset = _number(scope.query(f":{channel}:OFFSet?"), f"{channel} offset")
    if scale <= 0:
        raise RuntimeError(f"invalid {channel} scale: {scale}")
    return -factor * scale - offset, factor * scale - offset


def _validate_search(settings: SearchSettings, profile) -> SearchSettings:
    mode = _enum("mode", settings.mode, _SEARCH_ENUMS)
    slope = _enum("edge_slope", settings.edge_slope, _SEARCH_ENUMS)
    polarity = _enum("pulse_polarity", settings.pulse_polarity, _SEARCH_ENUMS)
    qualifier = _enum("pulse_qualifier", settings.pulse_qualifier, _SEARCH_ENUMS)
    edge_source = normalize_channel_source(settings.edge_source, profile)
    pulse_source = normalize_channel_source(settings.pulse_source, profile)
    if type(settings.enabled) is not bool:
        raise ValueError("enabled must be bool")
    for name, value in (("edge threshold", settings.edge_threshold_v),
                        ("pulse threshold", settings.pulse_threshold_v)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    for name, value in (("pulse lower width", settings.pulse_lower_s),
                        ("pulse upper width", settings.pulse_upper_s)):
        if not math.isfinite(value) or not 800e-12 <= value <= 10:
            raise ValueError(f"{name} must be 800 ps to 10 s")
    if qualifier == "GLESS" and settings.pulse_lower_s >= settings.pulse_upper_s:
        raise ValueError("GLESS search requires lower pulse width < upper pulse width")
    return SearchSettings(mode, settings.enabled, slope, edge_source,
                          settings.edge_threshold_v, polarity, qualifier, pulse_source,
                          settings.pulse_lower_s, settings.pulse_upper_s,
                          settings.pulse_threshold_v)


def configure_search(scope, settings: SearchSettings) -> SearchState:
    """Set edge/pulse search parameters and return verified instrument state."""
    settings = _validate_search(settings, profile_for(scope))
    _afg_off(scope)
    low, high = _voltage_limit(scope, settings.edge_source, 4.5)
    if not low <= settings.edge_threshold_v <= high:
        raise ValueError(f"edge threshold must be {low:g} to {high:g} V")
    low, high = _voltage_limit(scope, settings.pulse_source, 5.0)
    if not low <= settings.pulse_threshold_v <= high:
        raise ValueError(f"pulse threshold must be {low:g} to {high:g} V")
    require_no_errors(scope)
    commands = (
        (":SEARch:EDGE:SLOPe", settings.edge_slope),
        (":SEARch:EDGE:SOURce", settings.edge_source),
        (":SEARch:EDGE:THReshold", settings.edge_threshold_v),
        (":SEARch:PULSe:POLarity", settings.pulse_polarity),
        (":SEARch:PULSe:QUALifier", settings.pulse_qualifier),
        (":SEARch:PULSe:SOURce", settings.pulse_source),
        (":SEARch:PULSe:LWIDth", settings.pulse_lower_s),
        (":SEARch:PULSe:UWIDth", settings.pulse_upper_s),
        (":SEARch:PULSe:THReshold", settings.pulse_threshold_v),
        (":SEARch:MODE", settings.mode),
        (":SEARch:STATe", "ON" if settings.enabled else "OFF"),
    )
    for command, value in commands:
        scope.write(f"{command} {value}")
    state = read_search(scope)
    if state.settings != settings:
        raise RuntimeError(f"search readback differs from requested settings: {state.settings}")
    require_no_errors(scope)
    return state


def read_search(scope) -> SearchState:
    """Read configured search criteria and the current event-table position."""
    values = {
        "enabled": _bool(scope.query(":SEARch:STATe?")),
        "mode": scope.query(":SEARch:MODE?").upper(),
        "edge_slope": scope.query(":SEARch:EDGE:SLOPe?").upper(),
        "edge_source": scope.query(":SEARch:EDGE:SOURce?").upper(),
        "edge_threshold_v": _number(scope.query(":SEARch:EDGE:THReshold?"), "edge threshold"),
        "pulse_polarity": scope.query(":SEARch:PULSe:POLarity?").upper(),
        "pulse_qualifier": scope.query(":SEARch:PULSe:QUALifier?").upper(),
        "pulse_source": scope.query(":SEARch:PULSe:SOURce?").upper(),
        "pulse_upper_s": _number(scope.query(":SEARch:PULSe:UWIDth?"), "pulse upper width"),
        "pulse_lower_s": _number(scope.query(":SEARch:PULSe:LWIDth?"), "pulse lower width"),
        "pulse_threshold_v": _number(scope.query(":SEARch:PULSe:THReshold?"), "pulse threshold"),
    }
    # The guide abbreviates enum query replies; normalize those to public values.
    reverse = {short: full for full, short in _SHORT.items()}
    for field in ("mode", "edge_slope", "pulse_polarity", "pulse_qualifier"):
        values[field] = reverse.get(values[field], values[field])
    values["edge_source"] = values["edge_source"].replace("CHAN", "CHANnel")
    values["pulse_source"] = values["pulse_source"].replace("CHAN", "CHANnel")
    settings = _validate_search(SearchSettings(**values), profile_for(scope))
    count = _integer(scope.query(":SEARch:COUNt?"), "search event count")
    selected = _integer(scope.query(":SEARch:EVENt?"), "selected search event")
    if selected > count:
        raise RuntimeError(f"selected search event {selected} exceeds event count {count}")
    require_no_errors(scope)
    return SearchState(settings, count, selected)


def select_search_event(scope, event: int) -> float:
    """Select a 1-based event (0 aliases the first event) and return its time in seconds."""
    if type(event) is not int or event < 0:
        raise ValueError("event must be 0 (first event) or a positive integer")
    _afg_off(scope)
    require_no_errors(scope)
    count = _integer(scope.query(":SEARch:COUNt?"), "search event count")
    if count == 0 or event > count:
        raise ValueError(f"event must be 0 (first) or between 1 and {count}")
    if not _bool(scope.query(":SEARch:STATe?")):
        raise RuntimeError("search must be enabled before selecting an event")
    require_no_errors(scope)
    scope.write(f":SEARch:EVENt {event}")
    selected = _integer(scope.query(":SEARch:EVENt?"), "selected search event")
    expected = event or 1
    if selected != expected:
        raise RuntimeError(f"selected event readback differs: {selected}")
    value = _number(scope.query(f":SEARch:VALue? {expected}"), "search event time")
    require_no_errors(scope)
    return value


def _validate_navigation(settings: NavigationSettings) -> NavigationSettings:
    mode = _enum("mode", settings.mode, _NAV_ENUMS)
    speed = _enum("speed", settings.speed, _NAV_ENUMS)
    display = _enum("frame_display", settings.frame_display, _NAV_ENUMS)
    if type(settings.enabled) is not bool:
        raise ValueError("enabled must be bool")
    for name, value in (("frame_start", settings.frame_start), ("frame_end", settings.frame_end)):
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError(f"{name} must be a positive integer")
    return NavigationSettings(mode, settings.enabled, speed, display,
                              settings.frame_start, settings.frame_end)


def _nav_mode(scope) -> str:
    raw = scope.query(":NAVigate:MODE?").upper()
    return {"SEAR": "SEARCH", "FRAM": "FRAME"}.get(raw, raw)


def _frame_state(scope) -> tuple[int, int, int]:
    maximum = _integer(scope.query(":ACQuire:ULTRa:MAXFrame?"), "maximum frame count", 1)
    start = _integer(scope.query(":NAVigate:FRAMe:STARt:FRAMe?"), "start frame", 1)
    end = _integer(scope.query(":NAVigate:FRAMe:END:FRAMe?"), "end frame", 1)
    if start > end or end > maximum:
        raise RuntimeError(f"invalid instrument frame range: {start}..{end} of {maximum}")
    return start, end, maximum


def read_navigation(scope) -> NavigationState:
    """Read navigation mode, playback flags, and frame segment range."""
    speed_raw = scope.query(":NAVigate:TIME:SPEed?").upper()
    display_raw = scope.query(":NAVigate:FRAMe:DISPlay:MODE?").upper()
    start, end, maximum = _frame_state(scope)
    settings = NavigationSettings(
        mode=_nav_mode(scope),
        enabled=_bool(scope.query(":NAVigate:ENABle?")),
        speed={"NORM": "NORMAL"}.get(speed_raw, speed_raw),
        frame_display={"ADJ": "ADJACENT", "OVER": "OVERLAY", "WAT": "WATERFALL",
                       "PERS": "PERSPECTIVE", "MOS": "MOSAIC"}.get(display_raw, display_raw),
        frame_start=start, frame_end=end,
    )
    state = NavigationState(settings,
                            _bool(scope.query(":NAVigate:TIME:PLAY?")),
                            _bool(scope.query(":NAVigate:FRAMe:PLAY?")),
                            start, end, maximum)
    require_no_errors(scope)
    return state


def configure_navigation(scope, settings: NavigationSettings) -> NavigationState:
    """Configure navigation; checks STOP state and mode-specific dependencies."""
    settings = _validate_navigation(settings)
    _afg_off(scope)
    _stopped(scope)
    if settings.mode == "TIME" and scope.query(":TIMebase:MODE?").upper() not in {"MAIN", "YT"}:
        raise RuntimeError("time navigation requires YT (MAIN) timebase mode")
    if settings.mode == "SEARCH" and not _bool(scope.query(":SEARch:STATe?")):
        raise RuntimeError("search navigation requires search to be enabled")
    if settings.mode == "FRAME":
        if scope.query(":ACQuire:TYPE?").upper() not in {"ULTR", "ULTRA"}:
            raise RuntimeError("frame navigation requires UltraAcquire mode")
        if _nav_mode(scope) != "FRAME":
            raise RuntimeError("Frame mode is selected automatically by UltraAcquire and cannot be changed")
    if _bool(scope.query(":NAVigate:TIME:PLAY?")) or _bool(scope.query(":NAVigate:FRAMe:PLAY?")):
        raise RuntimeError("stop navigation playback before changing settings")
    require_no_errors(scope)
    start = end = None
    if settings.mode == "FRAME":
        current_start, current_end, maximum = _frame_state(scope)
        start = settings.frame_start if settings.frame_start is not None else current_start
        end = settings.frame_end if settings.frame_end is not None else current_end
        if start > maximum or end > maximum or start > end:
            raise ValueError(f"frame range must satisfy 1 <= start <= end <= {maximum}")
        if _bool(scope.query(":NAVigate:FRAMe:PLAY?")) and (start, end) != (current_start, current_end):
            raise RuntimeError("cannot change frame range during frame playback")
        require_no_errors(scope)
        if start > current_end:
            scope.write(f":NAVigate:FRAMe:END:FRAMe {end}")
            scope.write(f":NAVigate:FRAMe:STARt:FRAMe {start}")
        else:
            scope.write(f":NAVigate:FRAMe:STARt:FRAMe {start}")
            scope.write(f":NAVigate:FRAMe:END:FRAMe {end}")
        scope.write(f":NAVigate:FRAMe:DISPlay:MODE {settings.frame_display}")
    if settings.mode == "TIME":
        scope.write(f":NAVigate:TIME:SPEed {settings.speed}")
    if settings.mode != "FRAME":
        scope.write(f":NAVigate:MODE {settings.mode}")
    scope.write(f":NAVigate:ENABle {'ON' if settings.enabled else 'OFF'}")
    state = read_navigation(scope)
    if state.settings.mode != settings.mode or state.settings.enabled != settings.enabled:
        raise RuntimeError(f"navigation readback differs from requested settings: {state}")
    if settings.mode == "TIME" and state.settings.speed != settings.speed:
        raise RuntimeError(f"navigation speed readback differs: {state.settings.speed}")
    if settings.mode == "FRAME" and (
            state.settings.frame_display != settings.frame_display or
            (settings.frame_start is not None and state.frame_start != start) or
            (settings.frame_end is not None and state.frame_end != end)):
        raise RuntimeError(f"frame navigation readback differs: {state}")
    require_no_errors(scope)
    return state


_ACTIONS = {
    "TIME": {"START": ":NAVigate:TIME:STARt", "END": ":NAVigate:TIME:END",
             "NEXT": ":NAVigate:TIME:NEXT", "BACK": ":NAVigate:TIME:BACK"},
    "SEARCH": {"START": ":NAVigate:SEARch:STARt", "END": ":NAVigate:SEARch:END",
                "NEXT": ":NAVigate:SEARch:NEXT", "BACK": ":NAVigate:SEARch:BACK"},
    "FRAME": {"START": ":NAVigate:FRAMe:STARt", "END": ":NAVigate:FRAMe:END",
              "NEXT": ":NAVigate:FRAMe:NEXT", "BACK": ":NAVigate:FRAMe:BACK"},
}


def navigate(scope, action: str) -> None:
    """Move to START, END, NEXT, or BACK in the active navigation mode."""
    action = action.upper()
    mode = _nav_mode(scope)
    if action not in _ACTIONS.get(mode, {}):
        raise ValueError("action must be START, END, NEXT, or BACK")
    _afg_off(scope)
    _stopped(scope)
    if not _bool(scope.query(":NAVigate:ENABle?")):
        raise RuntimeError("navigation must be enabled")
    if mode == "TIME" and scope.query(":TIMebase:MODE?").upper() not in {"MAIN", "YT"}:
        raise RuntimeError("time navigation requires YT (MAIN) timebase mode")
    if mode == "SEARCH" and not _bool(scope.query(":SEARch:STATe?")):
        raise RuntimeError("search navigation requires search to be enabled")
    if mode == "FRAME" and scope.query(":ACQuire:TYPE?").upper() not in {"ULTR", "ULTRA"}:
        raise RuntimeError("frame navigation requires UltraAcquire mode")
    require_no_errors(scope)
    scope.write(_ACTIONS[mode][action])
    require_no_errors(scope)


def set_navigation_play(scope, enabled: bool, *, mode: str | None = None) -> bool:
    """Start/stop playback explicitly; pass TIME or FRAME when mode is ambiguous."""
    if type(enabled) is not bool:
        raise ValueError("enabled must be bool")
    selected = _enum("mode", mode, {"mode": ("TIME", "FRAME")}) if mode else _nav_mode(scope)
    if selected not in {"TIME", "FRAME"}:
        raise ValueError("playback mode must be TIME or FRAME")
    _afg_off(scope)
    _stopped(scope)
    if not _bool(scope.query(":NAVigate:ENABle?")) or _nav_mode(scope) != selected:
        raise RuntimeError(f"navigation must be enabled in {selected} mode")
    if selected == "TIME" and scope.query(":TIMebase:MODE?").upper() not in {"MAIN", "YT"}:
        raise RuntimeError("time navigation requires YT (MAIN) timebase mode")
    if selected == "FRAME" and scope.query(":ACQuire:TYPE?").upper() not in {"ULTR", "ULTRA"}:
        raise RuntimeError("frame navigation requires UltraAcquire mode")
    require_no_errors(scope)
    command = {"TIME": ":NAVigate:TIME:PLAY", "FRAME": ":NAVigate:FRAMe:PLAY"}[selected]
    scope.write(f"{command} {'ON' if enabled else 'OFF'}")
    actual = _bool(scope.query(f"{command}?"))
    if actual != enabled:
        raise RuntimeError("navigation playback readback differs")
    require_no_errors(scope)
    return actual
