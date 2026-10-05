import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import dho914s_search as search
from rigol_dho900 import Rigol


def setting_writes(instrument):
    return [command for command in instrument.commands
            if "?" not in command and not command.endswith(":OUTPut:STATe OFF")]


class FakeInstrument:
    def __init__(self):
        self.commands = []
        self.values = {
            ":SOURce:OUTPut:STATe": "0",
            ":TRIGger:STATus": "STOP",
            ":CHANnel1:SCALe": "1",
            ":CHANnel1:OFFSet": "0",
            ":CHANnel2:SCALe": "2",
            ":CHANnel2:OFFSet": "0.5",
            ":SEARch:STATe": "0",
            ":SEARch:MODE": "EDGE",
            ":SEARch:EDGE:SLOPe": "POS",
            ":SEARch:EDGE:SOURce": "CHAN1",
            ":SEARch:EDGE:THReshold": "0",
            ":SEARch:PULSe:POLarity": "POS",
            ":SEARch:PULSe:QUALifier": "GRE",
            ":SEARch:PULSe:SOURce": "CHAN1",
            ":SEARch:PULSe:UWIDth": "2e-6",
            ":SEARch:PULSe:LWIDth": "1e-6",
            ":SEARch:PULSe:THReshold": "0",
            ":SEARch:COUNt": "3",
            ":SEARch:EVENt": "0",
            ":NAVigate:ENABle": "0",
            ":NAVigate:MODE": "TIME",
            ":NAVigate:TIME:SPEed": "NORM",
            ":NAVigate:TIME:PLAY": "0",
            ":NAVigate:FRAMe:DISPlay:MODE": "ADJ",
            ":NAVigate:FRAMe:STARt:FRAMe": "1",
            ":NAVigate:FRAMe:END:FRAMe": "10",
            ":NAVigate:FRAMe:PLAY": "0",
            ":ACQuire:ULTRa:MAXFrame": "100",
            ":ACQuire:TYPE": "ULTR",
            ":TIMebase:MODE": "MAIN",
        }
        self.search_value = "1.25e-3"
        self.error = '0,"No error"'

    def write(self, command):
        self.commands.append(command)
        key, _, value = command.partition(" ")
        if key in self.values and value:
            self.values[key] = value.upper().replace("ON", "1").replace("OFF", "0")
            aliases = {"POSITIVE": "POS", "NEGATIVE": "NEG", "EITHER": "EITH",
                       "GREATER": "GRE", "GLESS": "GLES", "PULSE": "PULS",
                       "SEARCH": "SEAR", "FRAME": "FRAM", "NORMAL": "NORM",
                       "ADJACENT": "ADJ", "OVERLAY": "OVER", "WATERFALL": "WAT",
                       "PERSPECTIVE": "PERS", "MOSAIC": "MOS"}
            self.values[key] = aliases.get(self.values[key], self.values[key])
            self.values[key] = self.values[key].replace("CHANNEL", "CHAN")
        if command.startswith(":SEARch:EVENt "):
            selected = int(command.rsplit(" ", 1)[1])
            self.values[":SEARch:EVENt"] = str(selected or 1)

    def query(self, command):
        self.commands.append(command)
        if command == ":SYSTem:ERRor:NEXT?":
            return self.error
        if command.startswith(":SEARch:VALue? "):
            return self.search_value
        return self.values.get(command[:-1], "0")


class SearchNavigationTest(unittest.TestCase):
    def setUp(self):
        self.instrument = FakeInstrument()
        self.scope = Rigol(self.instrument)

    def test_search_configuration_readback_and_threshold_limits(self):
        settings = search.SearchSettings(
            mode="PULSE", enabled=True, edge_slope="EITHER", edge_source="CHANnel2",
            edge_threshold_v=8.5, pulse_polarity="NEGATIVE", pulse_qualifier="GLESS",
            pulse_source="CHANnel2", pulse_lower_s=2e-6, pulse_upper_s=8e-6,
            pulse_threshold_v=9.5)
        state = search.configure_search(self.scope, settings)
        self.assertEqual(state.settings, settings)
        self.assertEqual(self.instrument.values[":SEARch:MODE"], "PULS")
        writes_before = setting_writes(self.instrument)
        with self.assertRaises(ValueError):
            search.configure_search(self.scope, search.SearchSettings(edge_threshold_v=5))
        writes_after = setting_writes(self.instrument)
        self.assertEqual(writes_after, writes_before)

    def test_rejects_bad_greater_less_width_order_before_io(self):
        writes_before = setting_writes(self.instrument)
        with self.assertRaises(ValueError):
            search.configure_search(self.scope, search.SearchSettings(
                pulse_qualifier="GLESS", pulse_lower_s=3e-6, pulse_upper_s=2e-6))
        writes_after = setting_writes(self.instrument)
        self.assertEqual(writes_after, writes_before)

    def test_configuration_requires_afg_off(self):
        self.instrument.values[":SOURce:OUTPut:STATe"] = "1"
        search.configure_search(self.scope, search.SearchSettings())
        self.assertEqual(self.instrument.values[":SOURce:OUTPut:STATe"], "0")
        self.assertIn(":SOURce:OUTPut:STATe OFF", self.instrument.commands)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", self.instrument.commands)

    def test_select_search_event_checks_count_and_returns_seconds(self):
        self.instrument.values[":SEARch:STATe"] = "1"
        self.assertEqual(search.select_search_event(self.scope, 0), 1.25e-3)
        self.assertIn(":SEARch:EVENt 0", self.instrument.commands)
        self.assertIn(":SEARch:VALue? 1", self.instrument.commands)
        self.assertEqual(search.select_search_event(self.scope, 2), 1.25e-3)
        self.assertIn(":SEARch:VALue? 2", self.instrument.commands)
        writes_before = setting_writes(self.instrument)
        with self.assertRaises(ValueError):
            search.select_search_event(self.scope, 4)
        writes_after = setting_writes(self.instrument)
        self.assertEqual(writes_after, writes_before)

    def test_navigation_checks_modes_and_frame_limits(self):
        self.instrument.values[":NAVigate:MODE"] = "FRAM"
        settings = search.NavigationSettings(mode="FRAME", enabled=True,
                                             frame_start=20, frame_end=25)
        state = search.configure_navigation(self.scope, settings)
        self.assertEqual((state.frame_start, state.frame_end), (20, 25))
        self.assertEqual(state.settings.mode, "FRAME")
        writes = [c for c in self.instrument.commands if c.startswith(":NAVigate:FRAMe:") and " " in c]
        self.assertLess(writes.index(":NAVigate:FRAMe:END:FRAMe 25"),
                        writes.index(":NAVigate:FRAMe:STARt:FRAMe 20"))
        writes_before = setting_writes(self.instrument)
        with self.assertRaises(ValueError):
            search.configure_navigation(self.scope, search.NavigationSettings(
                mode="FRAME", frame_start=101, frame_end=101))
        writes_after = setting_writes(self.instrument)
        self.assertEqual(writes_after, writes_before)

    def test_navigation_dependencies_and_playback_actions(self):
        self.instrument.values[":NAVigate:MODE"] = "SEAR"
        self.instrument.values[":NAVigate:ENABle"] = "1"
        with self.assertRaises(RuntimeError):
            search.navigate(self.scope, "NEXT")
        self.instrument.values[":SEARch:STATe"] = "1"
        search.navigate(self.scope, "NEXT")
        self.assertIn(":NAVigate:SEARch:NEXT", self.instrument.commands)
        self.instrument.values[":NAVigate:MODE"] = "TIME"
        self.assertTrue(search.set_navigation_play(self.scope, True))
        self.assertEqual(self.instrument.values[":NAVigate:TIME:PLAY"], "1")

    def test_all_navigation_actions(self):
        for mode, commands in search._ACTIONS.items():
            self.instrument.values[":NAVigate:MODE"] = {"TIME": "TIME", "SEARCH": "SEAR",
                                                            "FRAME": "FRAM"}[mode]
            self.instrument.values[":NAVigate:ENABle"] = "1"
            self.instrument.values[":SEARch:STATe"] = "1"
            self.instrument.values[":ACQuire:TYPE"] = "ULTR"
            for action, command in commands.items():
                search.navigate(self.scope, action)
                self.assertIn(command, self.instrument.commands)

    def test_navigation_mode_speed_and_both_play_controls(self):
        state = search.configure_navigation(self.scope,
                                            search.NavigationSettings(mode="TIME", speed="HIGH"))
        self.assertEqual(state.settings.mode, "TIME")
        self.assertEqual(state.settings.speed, "HIGH")
        self.assertIn(":NAVigate:MODE TIME", self.instrument.commands)
        self.assertIn(":NAVigate:TIME:SPEed HIGH", self.instrument.commands)
        self.assertTrue(search.set_navigation_play(self.scope, True, mode="TIME"))
        self.assertFalse(search.set_navigation_play(self.scope, False, mode="TIME"))
        self.instrument.values[":ACQuire:TYPE"] = "ULTR"
        self.instrument.values[":NAVigate:MODE"] = "FRAM"
        self.instrument.values[":NAVigate:ENABle"] = "1"
        self.assertTrue(search.set_navigation_play(self.scope, True, mode="FRAME"))
        self.assertIn(":NAVigate:FRAMe:PLAY ON", self.instrument.commands)
        self.assertFalse(search.set_navigation_play(self.scope, False, mode="FRAME"))
        self.assertIn(":NAVigate:FRAMe:PLAY OFF", self.instrument.commands)

    def test_nonstopped_navigation_is_rejected(self):
        self.instrument.values[":TRIGger:STATus"] = "RUN"
        with self.assertRaises(RuntimeError):
            search.configure_navigation(self.scope, search.NavigationSettings())


if __name__ == "__main__":
    unittest.main()
