"""Offline checks against section 3.6 channel forms and dependencies."""

import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dho914s_channels import ChannelChanges, configure_channel, read_channel


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.commands = []
        self.values = {":SOURce:OUTPut:STATe": "0", ":TIMebase:MAIN:SCALe": "1e-6"}
        defaults = {"BWLimit": "OFF", "COUPling": "DC", "DISPlay": "1",
                    "INVert": "0", "OFFSet": "0", "TCALibrate": "0",
                    "SCALe": "0.1", "PROBe": "1", "LABel:SHOW": "0",
                    "LABel:CONTent": "CH1", "UNITs": "VOLT", "VERNier": "0",
                    "POSition": "0"}
        for channel in range(1, 5):
            for command, value in defaults.items():
                self.values[f":CHANnel{channel}:{command}"] = value
        self.error_queue = ['0,"No error"']

    def afg_off(self):
        self.commands.append(":SOURce:OUTPut:STATe OFF")
        self.values[":SOURce:OUTPut:STATe"] = "0"

    def write(self, command):
        self.commands.append(command)
        if " " in command:
            key, value = command.split(" ", 1)
            if key.endswith(":LABel:CONTent") and value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('""', '"')
            self.values[key] = {"ON": "1", "OFF": "0", "VOLTage": "VOLT",
                                "AMPere": "AMP", "UNKNown": "UNKN"}.get(value, value)

    def query(self, command):
        self.commands.append(command)
        value = self.values[command[:-1]]
        if command.endswith(":LABel:CONTent?") and '"' in value:
            return '"' + value.replace('"', '""') + '"'
        return value

    def errors(self):
        return self.error_queue


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()

    def test_all_thirteen_read_and_write_forms(self):
        changes = ChannelChanges(bandwidth="20M", coupling="AC", display=False,
                                 inverted=True, offset_v=0.5,
                                 time_calibration_s=20e-9, scale_v_div=0.1,
                                 probe_ratio=10, label_visible=True,
                                 label="INPUT_1", units="AMPere", vernier=True,
                                 position_v=-0.5)
        state = configure_channel(self.scope, 2, changes)
        self.assertEqual(state.units, "AMPere")
        self.assertEqual(state.probe_ratio, 10)
        self.assertEqual(state.label, "INPUT_1")
        for name in ("BWLimit", "COUPling", "DISPlay", "INVert", "OFFSet",
                     "TCALibrate", "SCALe", "PROBe", "LABel:SHOW",
                     "LABel:CONTent", "UNITs", "VERNier", "POSition"):
            self.assertTrue(any(cmd.startswith(f":CHANnel2:{name} ") for cmd in self.scope.commands), name)
            self.assertIn(f":CHANnel2:{name}?", self.scope.commands)
        self.assertLess(self.scope.commands.index(":CHANnel2:PROBe 10"),
                        self.scope.commands.index(":CHANnel2:SCALe 0.1"))
        self.assertEqual(read_channel(self.scope, 2), state)

    def test_rejects_dependent_ranges_before_writes(self):
        for changes in (ChannelChanges(probe_ratio=0.001, scale_v_div=0.1),
                        ChannelChanges(scale_v_div=0.01, offset_v=2),
                        ChannelChanges(position_v=101),
                        ChannelChanges(time_calibration_s=101e-9),
                        ChannelChanges(label="X;:RUN"),
                        ChannelChanges(display=1)):
            before = len(self.scope.commands)
            with self.assertRaises(ValueError):
                configure_channel(self.scope, 1, changes)
            self.assertFalse(any(c.startswith(":CHANnel1:") and " " in c
                                 for c in self.scope.commands[before:]))
        self.scope.values[":TIMebase:MAIN:SCALe"] = "20e-6"
        with self.assertRaisesRegex(ValueError, "timebase"):
            configure_channel(self.scope, 1, ChannelChanges(time_calibration_s=1e-9))

    def test_scale_transition_and_probe_only(self):
        self.scope.values[":CHANnel1:OFFSet"] = "2"
        configure_channel(self.scope, 1, ChannelChanges(scale_v_div=0.01, offset_v=0.5))
        self.assertLess(self.scope.commands.index(":CHANnel1:OFFSet 0.5"),
                        self.scope.commands.index(":CHANnel1:SCALe 0.01"))
        self.scope.values[":CHANnel1:SCALe"] = "0.1"
        self.assertEqual(configure_channel(self.scope, 1, ChannelChanges(probe_ratio=0.001)).probe_ratio,
                         0.001)

    def test_guide_channel_label_example_set_and_query(self):
        state = configure_channel(self.scope, 1, ChannelChanges(label="ch1"))
        self.assertEqual(state.label, "ch1")
        self.assertIn(':CHANnel1:LABel:CONTent "ch1"', self.scope.commands)
        self.assertIn(":CHANnel1:LABel:CONTent?", self.scope.commands)
        state = configure_channel(self.scope, 1, ChannelChanges(label='INPUT "A"'))
        self.assertEqual(state.label, 'INPUT "A"')
        self.assertIn(':CHANnel1:LABel:CONTent "INPUT ""A"""', self.scope.commands)
        for label in ("", "X;:RUN", "line\nbreak", "μV"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                configure_channel(self.scope, 1, ChannelChanges(label=label))

    def test_output_and_instrument_errors(self):
        self.scope.error_queue = ['-222,"Data out of range"', '0,"No error"']
        with self.assertRaises(RuntimeError):
            configure_channel(self.scope, 1, ChannelChanges(coupling="AC"))
        self.scope = FakeScope()
        self.scope.values[":SOURce:OUTPut:STATe"] = "1"
        self.scope.afg_off = lambda: self.scope.commands.append(":SOURce:OUTPut:STATe OFF")
        with self.assertRaisesRegex(RuntimeError, "AFG"):
            configure_channel(self.scope, 1, ChannelChanges(coupling="AC"))
        self.assertNotIn(":CHANnel1:COUPling AC", self.scope.commands)


if __name__ == "__main__":
    unittest.main()
