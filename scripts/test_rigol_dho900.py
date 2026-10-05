#!/usr/bin/env python3

import importlib.util
import json
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("rigol_dho900.py")
SPEC = importlib.util.spec_from_file_location("rigol_dho900", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeInstrument:
    def __init__(self):
        self.commands = []
        self.statuses = ["STOP", "WAIT", "STOP"]
        self.afg_output = "0"
        self.probe_ratio = "1"
        self.identity = "RIGOL TECHNOLOGIES,DHO914S,TEST,00.01.05"
        self.settings = {":TRIGger:MODE": "EDGE", ":TRIGger:HOLDoff": "8e-9",
                         ":TRIGger:SWEep": "NORM"}

    def write(self, command):
        self.commands.append(command)
        if command == ":SOURce:OUTPut:STATe ON":
            self.afg_output = "1"
        elif command == ":SOURce:OUTPut:STATe OFF":
            self.afg_output = "0"
        elif command.startswith(":CHANnel1:PROBe "):
            self.probe_ratio = command.rsplit(" ", 1)[1]
        elif command.startswith((":DVM:", ":COUNter:", ":TRIGger:",
                                 ":MEASure:STATistic:")) and " " in command:
            key, value = command.split(" ", 1)
            self.settings[key] = {"ON": "1", "OFF": "0", "ACRMS": "ACRM",
                                  "DCRMS": "DCRM", "FREQUENCY": "FREQ",
                                  "PERIOD": "PER", "TOTALIZE": "TOT",
                                  "PULSe": "PULS", "GLESS": "GLES",
                                  "POSITIVE": "POS", "NEGATIVE": "NEG"}.get(value, value.replace("CHANnel", "CHAN"))

    def query(self, command):
        self.commands.append(command)
        if command == "*IDN?":
            return self.identity
        if command == ":SYSTem:ERRor:NEXT?":
            return '0,"No error"'
        if command == ":SOURce:OUTPut:STATe?":
            return self.afg_output
        if command == ":CHANnel1:PROBe?":
            return self.probe_ratio
        if command.startswith((":DVM:", ":COUNter:")) and command.endswith("?"):
            return self.settings.get(command[:-1], "0")
        if command.startswith(":MEASure:STATistic:ITEM?"):
            return "1.0"
        if command.startswith(":MEASure:STATistic:") and command.endswith("?"):
            return self.settings.get(command[:-1], "0")
        if command.startswith(":TRIGger:") and command.endswith("?") and command != ":TRIGger:STATus?":
            return self.settings.get(command[:-1], "0")
        if command == ":TRIGger:STATus?":
            return self.statuses.pop(0) if self.statuses else "STOP"
        if command == ":DISPlay:DATA? PNG":
            raise AssertionError("binary query expected")
        if command.startswith(":MEASure:ITEM?"):
            return "1.0"
        if command == ":WAVeform:XINCrement?":
            return "1e-6"
        if command == ":WAVeform:XORigin?":
            return "0"
        if command == ":WAVeform:PREamble?":
            return "2,0,1000,1,1e-6,0,0,1,0,0"
        if command == ":WAVeform:DATA?":
            return ",".join(["0"] * 1000)
        return "0"

    def query_binary_values(self, command, *_args, **_kwargs):
        self.commands.append(command)
        return b"PNG"


class RigolSafetyTest(unittest.TestCase):
    def test_coverage_inventory(self):
        checklist = MODULE_PATH.parent.parent.joinpath("COVERAGE.md").read_text()
        entries = re.findall(r"^- \[([ x])\] `(3\.(?:\d+\.)+\d+)`", checklist, re.M)
        self.assertEqual(len(entries), 565)
        self.assertEqual(len({identifier for _, identifier in entries}), 565)
        if os.getenv("DHO914S_REQUIRE_FULL_COVERAGE") == "1":
            self.assertTrue(all(mark == "x" for mark, _ in entries),
                            "full coverage requires every guide entry checked")

    def test_binary_waveform_returns_scaled_samples_and_restores_selection(self):
        class BinaryFake(FakeInstrument):
            def query(self, command):
                if command == ":WAVeform:PREamble?":
                    self.commands.append(command)
                    return "0,0,4,1,0.5,-1,0,0.1,10,128"
                if command.startswith(":WAVeform:") and command.endswith("?"):
                    self.commands.append(command)
                    return {":WAVeform:SOURce?": "CHAN1", ":WAVeform:MODE?": "NORM",
                            ":WAVeform:FORMat?": "ASC", ":WAVeform:POINts?": "1000",
                            ":WAVeform:STARt?": "1", ":WAVeform:STOP?": "1000"}[command]
                return super().query(command)

            def query_binary_values(self, command, *_args, **_kwargs):
                self.commands.append(command)
                return bytes((138, 139, 140, 141))

        fake = BinaryFake()
        waveform = MODULE.read_waveform(MODULE.Rigol(fake), 2, points=4)
        self.assertEqual(waveform.channel, 2)
        self.assertEqual([round(v, 3) for v in waveform.voltage_v], [0, 0.1, 0.2, 0.3])
        self.assertEqual([t for t, _ in waveform.samples()], [-1, -0.5, 0, 0.5])
        self.assertEqual(fake.commands[-3], ":WAVeform:STOP 1000")
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_waveform_rejects_noninteger_selection_before_io(self):
        fake = FakeInstrument()
        with self.assertRaises(ValueError):
            MODULE.read_waveform(MODULE.Rigol(fake), True)
        with self.assertRaises(ValueError):
            MODULE.read_waveform(MODULE.Rigol(fake), 1, points=2.5)
        self.assertEqual(fake.commands, [])

    def test_binary_waveform_rejects_short_transfer_and_restores_selection(self):
        class ShortBinaryFake(FakeInstrument):
            def query(self, command):
                if command == ":WAVeform:PREamble?":
                    self.commands.append(command)
                    return "0,0,4,1,0.5,-1,0,0.1,10,128"
                return super().query(command)

            def query_binary_values(self, command, *_args, **_kwargs):
                self.commands.append(command)
                return bytes((138, 139))

        fake = ShortBinaryFake()
        with self.assertRaisesRegex(RuntimeError, "returned 2 of 4 points"):
            MODULE.read_waveform(MODULE.Rigol(fake), 2, points=4)
        self.assertEqual(fake.commands[-3], ":WAVeform:STOP 0")

    def test_binary_waveform_chunks_raw_memory_without_losing_points(self):
        class ChunkFake(FakeInstrument):
            start = 1
            stop = 1000

            def write(self, command):
                super().write(command)
                if command.startswith(":WAVeform:STARt "):
                    value = int(command.split()[-1])
                    if value > self.stop:
                        raise RuntimeError("start exceeds stop")
                    self.start = value
                elif command.startswith(":WAVeform:STOP "):
                    value = int(command.split()[-1])
                    if value < self.start:
                        raise RuntimeError("stop precedes start")
                    self.stop = value

            def query(self, command):
                if command == ":WAVeform:PREamble?":
                    self.commands.append(command)
                    return "0,2,250001,1,1e-9,0,0,0.01,0,128"
                if command == ":WAVeform:STARt?":
                    return "1"
                if command == ":WAVeform:STOP?":
                    return "1000"
                return super().query(command)

            def query_binary_values(self, command, *_args, **_kwargs):
                self.commands.append(command)
                return bytes((128,)) * (self.stop - self.start + 1)

        fake = ChunkFake()
        waveform = MODULE.read_waveform(MODULE.Rigol(fake), 1, mode="RAW", points=250001)
        self.assertEqual(len(waveform.voltage_v), 250001)
        self.assertEqual(fake.commands.count(":WAVeform:DATA?"), 2)
        self.assertIn(":WAVeform:STARt 250001", fake.commands)
        self.assertEqual(waveform.voltage_v[-1], 0)

    def test_waveform_word_and_ascii_formats_return_volts(self):
        class FormatFake(FakeInstrument):
            def __init__(self, fmt, data):
                super().__init__()
                self.fmt = fmt
                self.data = data
                self.settings.update({":WAVeform:SOURce": "CHAN1", ":WAVeform:MODE": "NORM",
                                      ":WAVeform:FORMat": "BYTE", ":WAVeform:POINts": "1000",
                                      ":WAVeform:STARt": "1", ":WAVeform:STOP": "1000"})

            def query(self, command):
                if command == ":WAVeform:PREamble?":
                    self.commands.append(command)
                    fmt_id = {"BYTE": 0, "WORD": 1, "ASCII": 2}[self.fmt]
                    y_ref = 32768 if self.fmt == "WORD" else 0
                    y_inc = 0.01
                    return f"{fmt_id},0,4,1,0.5,-1,0,{y_inc},0,{y_ref}"
                if command == ":WAVeform:DATA?" and self.fmt == "ASCII":
                    self.commands.append(command)
                    return "1.25,-0.5,0,2"
                if command.startswith(":WAVeform:") and command.endswith("?"):
                    self.commands.append(command)
                    return self.settings.get(command[:-1], "0")
                return super().query(command)

            def query_binary_values(self, command, *_args, **kwargs):
                self.commands.append(command)
                self.assert_word_options = kwargs
                return self.data

        word_fake = FormatFake("WORD", [32768, 32778, 32758, 33068])
        word = MODULE.read_waveform(MODULE.Rigol(word_fake), "CHAN1", points=4,
                                    data_format="WORD")
        self.assertEqual(list(word.voltage_v), [0, 0.1, -0.1, 3.0])
        self.assertEqual(word.mode, "NORMAL")
        self.assertIn(":WAVeform:FORMat WORD", word_fake.commands)
        self.assertEqual(word_fake.assert_word_options["datatype"], "H")
        self.assertFalse(word_fake.assert_word_options["is_big_endian"])

        ascii_fake = FormatFake("ASCII", [])
        ascii_wave = MODULE.read_waveform(MODULE.Rigol(ascii_fake), "D7", points=4,
                                          data_format="ASCII")
        self.assertEqual(list(ascii_wave.voltage_v), [1.25, -0.5, 0, 2])
        self.assertIn(":WAVeform:SOURce D7", ascii_fake.commands)
        self.assertIn(":WAVeform:FORMat ASCii", ascii_fake.commands)

    def test_waveform_axis_parameters_are_typed_and_validated(self):
        class AxisFake(FakeInstrument):
            values = {":WAVeform:XINCrement?": "2e-9", ":WAVeform:XORigin?": "-1e-6",
                      ":WAVeform:XREFerence?": "50", ":WAVeform:YINCrement?": "0.02",
                      ":WAVeform:YORigin?": "0.1", ":WAVeform:YREFerence?": "127"}

            def query(self, command):
                if command in self.values:
                    self.commands.append(command)
                    return self.values[command]
                return super().query(command)

        fake = AxisFake()
        parameters = MODULE.read_waveform_parameters(MODULE.Rigol(fake))
        self.assertEqual(parameters.x_increment_s, 2e-9)
        self.assertEqual(parameters.x_origin_s, -1e-6)
        self.assertEqual(parameters.y_reference, 127)
        self.assertEqual(sum(command in fake.values for command in fake.commands), 6)

        fake.values[":WAVeform:YINCrement?"] = "nan"
        with self.assertRaisesRegex(RuntimeError, "invalid waveform axis"):
            MODULE.read_waveform_parameters(MODULE.Rigol(fake))

    def test_connect_accepts_only_dho914s(self):
        self.assertEqual(MODULE.parser().parse_args(["discover"]).expected_model, "DHO914S")
        self.assertEqual(MODULE.parser().parse_args(
            ["--expected-model", "DHO812", "discover"]).expected_model, "DHO812")
        instruments = {name: FakeInstrument() for name in ("other", "wanted")}
        instruments["other"].identity = "RIGOL TECHNOLOGIES,DHO924S,TEST,00.01.05"

        class Manager:
            def list_resources(self):
                return tuple(instruments)

            def open_resource(self, name):
                return instruments[name]

        manager = Manager()
        with patch.dict(sys.modules, {"pyvisa": types.SimpleNamespace(ResourceManager=lambda _: manager)}):
            _, _, resource, identity = MODULE.connect(None, "@py")
        self.assertEqual(resource, "wanted")
        self.assertIn("DHO914S", identity)
        with patch.dict(sys.modules, {"pyvisa": types.SimpleNamespace(ResourceManager=lambda _: manager)}):
            _, family_scope, resource, _ = MODULE.connect(None, "@py", expected_model="DHO924S")
        self.assertEqual(resource, "other")
        self.assertEqual(family_scope.profile.model, "DHO924S")

    def test_family_connect_detects_model_and_guide_alignment(self):
        from dho800900 import connect

        fake = FakeInstrument()
        fake.identity = "RIGOL TECHNOLOGIES,DHO812,SERIAL,00.01.05.00.02"

        class Manager:
            def list_resources(self):
                return ("USB::scope",)

            def open_resource(self, name):
                return fake

        with patch.dict(sys.modules, {"pyvisa": types.SimpleNamespace(ResourceManager=lambda _: Manager())}):
            _, scope, resource, _ = connect()
        self.assertEqual(resource, "USB::scope")
        self.assertEqual(scope.profile.model, "DHO812")
        self.assertEqual(scope.identity.guide_status, "different")

    def test_measurement_statistics_setup_query_and_reset(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        self.assertEqual(MODULE.configure_measurement_statistics(scope, count=1000,
                                                                  enabled=True)["enabled"], "1")
        self.assertEqual(MODULE.measurement_statistic(scope, item="VPP", source="CHAN2",
                                                      result="MAXIMUM", add=True), 1.0)
        MODULE.reset_measurement_statistics(scope)
        self.assertIn(":MEASure:STATistic:ITEM VPP,CHANnel2", fake.commands)
        self.assertIn(":MEASure:STATistic:ITEM? MAXIMUM,VPP,CHANnel2", fake.commands)
        self.assertIn(":MEASure:STATistic:RESet", fake.commands)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_guide_checklist_has_every_leaf_once(self):
        checklist = MODULE_PATH.parent.parent.joinpath("COVERAGE.md").read_text()
        commands = re.findall(r"^- \[[ x]\] `(3(?:\.\d+)+)` `([:*][^`]+)` — guide p\. (\d+)$",
                              checklist, re.M)
        self.assertEqual(len(commands), 565)
        self.assertEqual(len({section for section, _, _ in commands}), 565)

    def test_pulse_trigger_widths_readback_and_restore_without_output(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        trigger = MODULE.configure_pulse_trigger(scope, source="D3", polarity="NEGATIVE",
                                                 when="GLESS", level=1.5,
                                                 lower_width=1e-6, upper_width=2e-6,
                                                 holdoff=1e-5)
        self.assertEqual(trigger["source"], "D3")
        self.assertEqual(trigger["when"], "GLES")
        self.assertEqual(trigger["lower_width_s"], 1e-6)
        self.assertEqual(trigger["upper_width_s"], 2e-6)
        MODULE.apply_state(scope, MODULE.readback(scope))
        self.assertIn(":TRIGger:PULSe:UWIDth 2e-06", fake.commands)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_pulse_trigger_rejects_invalid_width_without_writes(self):
        fake = FakeInstrument()
        with self.assertRaises(ValueError):
            MODULE.configure_pulse_trigger(MODULE.Rigol(fake), source="CHAN1",
                                           polarity="POSITIVE", when="GLESS", level=1,
                                           lower_width=2e-6, upper_width=1e-6)
        self.assertEqual(fake.commands, [])

    def test_dvm_and_counter_cover_manufacturer_commands_without_afg_on(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        self.assertEqual(MODULE.configure_dvm(scope, source="CHAN2", mode="DCRMS")["mode"], "DCRM")
        self.assertEqual(MODULE.configure_counter(scope, source="D15", mode="PERIOD",
                                                  statistics=True)["source"], "D15")
        MODULE.clear_counter(scope)
        MODULE.read_dvm(scope)
        self.assertIn(":DVM:CURRent?", fake.commands)
        MODULE.read_counter(scope)
        self.assertIn(":COUNter:CURRent?", fake.commands)
        self.assertIn(":COUNter:TOTalize:CLEar", fake.commands)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_counter_rejects_incompatible_totalize_statistics(self):
        fake = FakeInstrument()
        with self.assertRaises(ValueError):
            MODULE.configure_counter(MODULE.Rigol(fake), source="CHAN1", mode="TOTALIZE",
                                     statistics=True)
        self.assertNotIn(":COUNter:ENABle ON", fake.commands)

    def test_measurement_accepts_all_guide_items_and_digital_limits(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        self.assertEqual(len(MODULE.MEASUREMENT_TYPES), 42)
        MODULE.query_measurement(scope, "RRDELAY", "D0", "CHAN2")
        self.assertIn(":MEASure:ITEM? RRDELAY,D0,CHANnel2", fake.commands)
        with self.assertRaises(SystemExit):
            MODULE.query_measurement(scope, "VMAX", "D0")
        MODULE.annotate_capture(scope, ["RRDELAY:D0:CHAN2"])
        self.assertIn(":MEASure:ITEM RRDELAY,D0,CHANnel2", fake.commands)

    def test_clear_stops_before_clearing_without_reset_or_energizing(self):
        fake = FakeInstrument()
        fake.statuses = ["STOP"]
        fake.afg_output = "1"
        MODULE.clear_waveforms(MODULE.Rigol(fake))
        self.assertEqual(fake.commands[:4], [
            ":SOURce:OUTPut:STATe OFF", ":STOP", ":TRIGger:STATus?", ":CLEar",
        ])
        self.assertEqual(fake.afg_output, "0")
        self.assertNotIn(":RUN", fake.commands)
        self.assertNotIn("*RST", fake.commands)
        self.assertIn(":SYSTem:ERRor:NEXT?", fake.commands)
        self.assertEqual(MODULE.parser().parse_args(["clear"]).command, "clear")

    def test_capture_requires_confirmation(self):
        with self.assertRaises(SystemExit):
            MODULE.require_confirmation("yes")
        fake = FakeInstrument()
        with self.assertRaises(SystemExit):
            MODULE.capture_point(MODULE.Rigol(fake), Path("unused"), 0.2, "yes")
        self.assertEqual(fake.commands, [])

    def test_capture_turns_afg_off_after_trigger(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        with tempfile.TemporaryDirectory() as directory:
            MODULE.capture_point(scope, Path(directory), 0.2, "VERIFIED")
        self.assertLess(fake.commands.index(":CLEar"), fake.commands.index(":SINGle"))
        on = fake.commands.index(":SOURce:OUTPut:STATe ON")
        self.assertIn(":SOURce:OUTPut:STATe OFF", fake.commands[on + 1 :])

    def test_capture_turns_afg_off_on_timeout(self):
        fake = FakeInstrument()
        fake.statuses = ["STOP", "WAIT"] + ["RUN"] * 20
        scope = MODULE.Rigol(fake)
        with self.assertRaises(TimeoutError):
            MODULE.capture_point(scope, Path("unused"), 0.01, "VERIFIED")
        self.assertEqual(fake.commands[-1], ":SOURce:OUTPut:STATe OFF")

    def test_readback_includes_acquisition_state(self):
        state = MODULE.readback(MODULE.Rigol(FakeInstrument()))
        self.assertIn("acquisition", state)
        self.assertIn("sample_rate_sa_per_s", state["acquisition"])

    def test_measurement_rejects_unknown_item(self):
        with self.assertRaises(SystemExit):
            MODULE.query_measurement(MODULE.Rigol(FakeInstrument()), "BOGUS", "CHAN1")

    def test_annotate_capture_adds_measurements_without_running(self):
        fake = FakeInstrument()
        fake.statuses = ["STOP"]
        screen = MODULE.annotate_capture(MODULE.Rigol(fake), ["VTOP:CHAN3", "VBASE:CHAN4"])
        self.assertEqual(screen, b"PNG")
        self.assertIn(":MEASure:ITEM VTOP,CHANnel3", fake.commands)
        self.assertIn(":MEASure:ITEM VBASE,CHANnel4", fake.commands)
        self.assertNotIn(":RUN", fake.commands)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_restore_never_enables_afg(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        state = MODULE.readback(scope)
        MODULE.apply_state(scope, state)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)
        self.assertEqual(fake.commands[-1], ":SOURce:OUTPut:STATe OFF")

    def test_restore_rejects_untracked_trigger_mode_before_writing(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        state = MODULE.readback(scope)
        state["trigger"]["mode"] = "SLOP"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(state))
            before = len(fake.commands)
            with self.assertRaisesRegex(ValueError, "EDGE or PULSE"):
                MODULE.restore_state(scope, path)
        self.assertNotIn(":TRIGger:MODE SLOP", fake.commands[before:])

    def test_channel_configuration_keeps_afg_off_and_reads_back(self):
        fake = FakeInstrument()
        MODULE.configure_channel(MODULE.Rigol(fake), 3, scale=0.2, bandwidth="20M")
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)
        self.assertIn(":CHANnel3:SCALe 0.2", fake.commands)
        self.assertIn(":CHANnel3:BWLimit 20M", fake.commands)

    def test_probe_ratio_uses_discrete_scpi_value(self):
        fake = FakeInstrument()
        MODULE.configure_channel(MODULE.Rigol(fake), 1, probe_ratio=10)
        self.assertIn(":CHANnel1:PROBe 10", fake.commands)

    def test_timed_afg_always_turns_off(self):
        fake = FakeInstrument()
        MODULE.timed_afg(MODULE.Rigol(fake), 0.05, "VERIFIED")
        on = fake.commands.index(":SOURce:OUTPut:STATe ON")
        self.assertIn(":SOURce:OUTPut:STATe OFF", fake.commands[on + 1:])

    def test_timed_capture_arms_before_afg_and_collects_after_shutdown(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        with tempfile.TemporaryDirectory() as directory:
            MODULE.timed_capture(scope, Path(directory), 0.05, 0.2, "VERIFIED")
        single = fake.commands.index(":SINGle")
        self.assertLess(fake.commands.index(":CLEar"), single)
        on = fake.commands.index(":SOURce:OUTPut:STATe ON")
        off = fake.commands.index(":SOURce:OUTPut:STATe OFF", on + 1)
        screenshot = fake.commands.index(":DISPlay:DATA? PNG")
        self.assertLess(single, on)
        self.assertLess(on, off)
        self.assertLess(off, screenshot)

    def test_observe_for_freezes_before_screenshot(self):
        fake = FakeInstrument()
        scope = MODULE.Rigol(fake)
        self.assertEqual(MODULE.observe_for(scope, 0.05), b"PNG")
        run = fake.commands.index(":RUN")
        self.assertLess(fake.commands.index(":CLEar"), run)
        stop = fake.commands.index(":STOP", run + 1)
        screen = fake.commands.index(":DISPlay:DATA? PNG")
        self.assertLess(run, stop)
        self.assertLess(stop, screen)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_settled_capture_stops_acquisition_before_afg_and_screenshot(self):
        fake = FakeInstrument()
        fake.statuses = ["STOP", "WAIT", "TD", "STOP"]
        scope = MODULE.Rigol(fake)
        self.assertEqual(MODULE.settled_capture(scope, 0.05, 0.2, "VERIFIED"), b"PNG")
        run = fake.commands.index(":RUN")
        self.assertLess(fake.commands.index(":CLEar"), run)
        on = fake.commands.index(":SOURce:OUTPut:STATe ON")
        on_readback = fake.commands.index(":SOURce:OUTPut:STATe?", on + 1)
        trigger_readback = fake.commands.index(":TRIGger:STATus?", on + 1)
        stop = fake.commands.index(":STOP", on + 1)
        off = fake.commands.index(":SOURce:OUTPut:STATe OFF", on + 1)
        screen = fake.commands.index(":DISPlay:DATA? PNG")
        self.assertLess(run, on)
        self.assertLess(on, on_readback)
        self.assertLess(on_readback, trigger_readback)
        self.assertLess(trigger_readback, stop)
        self.assertLess(on, stop)
        self.assertLess(stop, off)
        self.assertLess(off, screen)

    def test_settled_capture_rejects_missing_trigger_and_turns_afg_off(self):
        fake = FakeInstrument()
        fake.statuses = ["STOP"] + ["WAIT"] * 100
        with self.assertRaisesRegex(RuntimeError, "did not acquire a trigger"):
            MODULE.settled_capture(MODULE.Rigol(fake), 0.05, 0.06, "VERIFIED")
        self.assertEqual(fake.afg_output, "0")
        self.assertEqual(fake.commands[-1], ":STOP")


if __name__ == "__main__":
    unittest.main()
