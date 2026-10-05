---
name: rigol-dho900
description: Control Rigol DHO800/DHO900 oscilloscopes through model capability profiles and typed Python operations. DHO914S has full offline programming-guide coverage.
---

# Rigol DHO800/DHO900

Use this skill to discover a scope, check its model and firmware, configure supported features, and collect readback, measurements, and waveform data through the Python library.

This repository is published under [PolyForm Noncommercial 1.0.0](LICENSE). Commercial use requires separate permission from the copyright holder.

## Source and coverage

The command source is Rigol's [DHO800/DHO900 Programming Guide](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf), publication PGA39106-1110 (April 2025), software 00.01.03. Consult the guide before changing a command. [COVERAGE.md](COVERAGE.md) tracks the 565 leaf entries and simulated tests. The **565/565 offline coverage claim is for DHO914S only**; live firmware acceptance is separate.

`dho800900_models.py` defines profiles for the eight guide-listed models, including analog channel count, bandwidth, EXT input, digital channels, LIN, SPI CS, histogram, memory depth, AFG, and Bode. `dho800900.connect()` reads `*IDN?` and attaches the correct profile. Pass `expected_model` when a script requires one model. Direct construction of `DHO800900` requires an explicit model. Shared domain operations use that profile to reject unsupported sources and features; other models do not yet have a complete command coverage claim.

The parsed `scope.identity` contains manufacturer, model, serial, and firmware. Its `guide_status` is `matched`, `different`, or `unknown` based on the first three firmware components compared with the guide's software version. A match describes documentation alignment, not proof that every command works on that instrument. When a newer guide is available, compare its command behavior before adding version-specific code.

## Use the Python API

From the skill directory, set `PYTHONPATH=scripts`. The following mini script only reads instrument state and returns a typed identity, channel state, and waveform metadata:

```python
from dho800900 import connect
from dho914s_channels import read_channel
from dho914s_waveforms import DHO800900Waveforms, WaveformRequest

manager, scope, resource, _ = connect()
try:
    print(resource, scope.identity, scope.identity.guide_status)
    print(read_channel(scope, 1))
    print(DHO800900Waveforms(scope).metadata(WaveformRequest("CHAN1")))
    print(scope.errors())
finally:
    scope.afg_off()
    scope.instrument.close()
    manager.close()
```

`read_channel` returns a `ChannelState` with values in physical units. `DHO800900Waveforms.read(WaveformRequest(...))` returns calibrated samples and metadata; `export_csv(request, path)` streams large captures. For measurements from a stopped frame, import `Request, read_frozen` from `dho914s_measurements` and call `read_frozen(scope, (Request("VTOP", "CHAN1"),))`. It returns typed `Result` objects. A stopped frame can still be stale: verify acquisition and trigger state before interpreting it as a fresh capture. The `dho914s_` filenames are retained for compatibility; shared operations accept any correctly profiled family scope.

Configure channels, acquisition, trigger, analysis, saving, and system features through their domain functions and inspect returned readback. The domain modules are `dho914s_channels.py`, `dho914s_acquisition.py`, `dho914s_trigger_analog.py`, `dho914s_trigger_protocol.py`, `dho914s_measurements.py`, `dho914s_waveforms.py`, `dho914s_analysis.py`, `dho914s_display.py`, `dho914s_search.py`, `dho914s_recording.py`, `dho914s_save.py`, and `dho914s_system.py`. Use the typed AFG and Bode operations for generator output rather than an ad hoc raw SCPI script.

## Instrument state and outputs

- Verify `scope.identity.model`, firmware, and required capabilities before configuring the instrument.
- Before a new acquisition, preserve any needed samples and call `clear_waveforms(scope)` before arming. `:CLEar` removes displayed waveforms; it does not prove a new trigger.
- AFG and Bode runs require explicit `confirmation="VERIFIED"`, a bounded duration, and output shutdown in `finally`. Host-timed AFG runs are limited to 50 ms–5 s; USB or LAN timing is not a precise pulse generator.
- Setup restore, recall, and reset require `confirm_no_dut=True` because a saved setup may change outputs or acquisition state. The system API quiesces acquisition, mask AUX, and AFG before and after those operations. AUX output exercise is bounded to at most 5 s and restores the previous mode.
- Check the SCPI error queue and readback after configuration. Exported screenshots and waveforms describe instrument state; verify acquisition status before treating them as new data.

## Offline verification

```bash
DHO914S_REQUIRE_FULL_COVERAGE=1 PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts -p 'test_*.py'
```
