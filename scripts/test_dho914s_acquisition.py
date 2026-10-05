"""Offline command and safety checks for the DHO914S domain controls."""

import importlib.util
import pathlib
import unittest
from unittest.mock import patch


path = pathlib.Path(__file__).with_name("dho914s_acquisition.py")
spec = importlib.util.spec_from_file_location("dho914s_acquisition", path)
api = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = api
spec.loader.exec_module(api)


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.commands = []
        self.state = {
            ":BODeplot:STARt": "100", ":BODeplot:STOP": "1000000",
            ":BODeplot:ENABle": "0", ":BODeplot:RUNStop": "0",
        }
        for channel in range(1, 5):
            self.state[f":CHANnel{channel}:SCALe"] = "0.1"
        for bus in range(1, 5):
            self.state[f":BUS{bus}:PARallel:WIDTh"] = "4"
        self.error_queue = ['0,"No error"']

    def afg_off(self):
        self.commands.append(":SOURce:OUTPut:STATe OFF")

    def write(self, command):
        self.commands.append(command)
        if " " in command:
            key, value = command.split(" ", 1)
            if key == ":BODeplot:VOLTage":
                band, value = value.split(",")
                key += " " + band
            elif ":THReshold" in key:
                value, source = value.split(",")
                key += " " + source
            self.state[key] = value

    def query(self, command):
        self.commands.append(command)
        if command.endswith("?"):
            return self.state.get(command[:-1], "0")
        if ":THReshold? " in command:
            key, source = command.split("? ")
            return self.state.get(key + " " + source, "0")
        if ":VOLTage? " in command:
            key, band = command.split("? ")
            return self.state.get(key + " " + band, "0")
        return "0"

    def errors(self):
        return self.error_queue


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()

    def test_acquire(self):
        for action, command in (("clear", ":CLEar"), ("run", ":RUN"),
                                ("stop", ":STOP"), ("single", ":SINGle"),
                                ("force", ":TFORce")):
            api.acquire(self.scope, action)
            self.assertIn(command, self.scope.commands)
        with self.assertRaises(ValueError):
            api.acquire(self.scope, ":SOURCE:OUTPUT:STATE ON")
        self.assertNotIn(":SOURCE:OUTPUT:STATE ON", self.scope.commands)

    def test_autoset(self):
        settings = {key: key != "lock" for key in api.AUTOSET}
        result = api.configure_settings(self.scope, "AUToset", settings)
        self.assertEqual(result, {key: "OFF" if key == "lock" else "ON" for key in settings})
        self.assertEqual(api.read_settings(self.scope, "AUToset"), result)
        api.autoset(self.scope)
        self.assertIn(":AUToset", self.scope.commands)

    def test_acquisition(self):
        result = api.configure_settings(self.scope, "ACQuire", {
            "averages": 128, "memory_depth": "1M", "type": "AVERages",
            "ultra_mode": "WATerfall", "ultra_timeout": 0.001,
            "ultra_max_frames": 100,
        })
        self.assertEqual(result["averages"], "128")
        self.assertIn(":ACQuire:SRATe?", self._read_acquisition())
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "ACQuire", {"averages": 9})
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "ACQuire", {"memory_depth": "100M"})
        self.scope.state.update({f":CHANnel{n}:DISPlay": "1" for n in range(1, 5)})
        before = len(self.scope.commands)
        with self.assertRaisesRegex(ValueError, "memory depth exceeds"):
            api.configure_settings(self.scope, "ACQuire", {"memory_depth": "25M"})
        self.assertNotIn(":ACQuire:MDEPth 25M", self.scope.commands[before:])

    def _read_acquisition(self):
        before = len(self.scope.commands)
        api.acquisition_state(self.scope)
        return self.scope.commands[before:]

    def test_channel(self):
        settings = {"bandwidth": "20M", "coupling": "DC", "display": True,
                    "invert": False, "offset": 0.5, "time_calibration": 1e-9,
                    "scale": 0.1, "probe": "10", "label_show": True,
                    "label": "INPUT", "units": "VOLTage", "vernier": False,
                    "position": 0.5}
        result = api.configure_settings(self.scope, "CHANnel", settings, 2)
        self.assertEqual(set(result), set(settings))
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "CHANnel", {"offset": 9}, 2)
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "CHANnel", {"label": "X;:RUN"}, 2)
        with self.assertRaises(ValueError):
            api.read_settings(self.scope, "CHANnel", index=5)

    def test_bus(self):
        settings = {key: (True if field.kind == "bool" else field.allowed[0] if field.kind == "enum" else
                          1 if field.kind == "int" else 0.001)
                    for key, field in api.BUS.items()}
        settings["parallel_bit"] = 0
        settings["position"] = 0
        settings["rs232_data_bits"] = 8
        settings["spi_data_bits"] = 8
        settings["rs232_baud"] = 9600
        settings["can_baud"] = 1_000_000
        settings["can_sample_point"] = 50
        result = api.configure_settings(self.scope, "BUS", settings, 1)
        self.assertEqual(set(result), set(settings))
        self.assertIn(":BUS1:DATA?", self._read_bus())
        self.assertEqual(api.bus_threshold(self.scope, 1, "CH1", 1.2), "1.2")
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "BUS", {"parallel_bit": 4}, 1)
        with self.assertRaises(ValueError):
            api.configure_settings(self.scope, "BUS", {"mode": "CAN;:RUN"}, 1)

    def _read_bus(self):
        before = len(self.scope.commands)
        api.bus_data(self.scope, 1)
        return self.scope.commands[before:]

    def test_bode(self):
        with self.assertRaises(ValueError):
            api.run_bode(self.scope, seconds=0.1, confirmation="")
        self.assertNotIn(":BODeplot:RUNStop ON", self.scope.commands)
        api.configure_settings(self.scope, "BODeplot", {"start_hz": 2_000_000, "stop_hz": 5_000_000,
                                                       "points": 30, "sweep_type": "LOG",
                                                       "input": "CHANnel1", "output": "CHANnel2"})
        self.assertLess(self.scope.commands.index(":BODeplot:STOP 5000000"),
                        self.scope.commands.index(":BODeplot:STARt 2000000"))
        with patch.object(api.time, "sleep"):
            state = api.run_bode(self.scope, seconds=0.1, confirmation="VERIFIED")
        self.assertEqual(state["running"], "ON")
        self.assertEqual(self.scope.commands[-3:], [":BODeplot:RUNStop OFF", ":BODeplot:ENABle OFF",
                                                     ":SOURce:OUTPut:STATe OFF"])
        self.assertEqual(api.bode_voltage(self.scope, "1K", 0.3), "0.3")
        with patch.object(api.time, "sleep", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                api.run_bode(self.scope, seconds=0.1, confirmation="VERIFIED")
        self.assertEqual(self.scope.commands[-1], ":SOURce:OUTPut:STATe OFF")
        self.scope.state[":BODeplot:STARt"] = "10000"
        self.scope.state[":BODeplot:STOP"] = "100000"
        before = len(self.scope.commands)
        api.configure_settings(self.scope, "BODeplot", {"stop_hz": 5000, "start_hz": 1000})
        writes = self.scope.commands[before:]
        self.assertLess(writes.index(":BODeplot:STARt 1000"), writes.index(":BODeplot:STOP 5000"))

    def test_counter(self):
        api.configure_settings(self.scope, "COUNter", {"source": "D15", "mode": "FREQuency",
                                                      "digits": 6, "statistics": True, "enabled": True})
        api.counter_current(self.scope)
        api.clear_counter(self.scope)
        self.assertIn(":COUNter:TOTalize:CLEar", self.scope.commands)
        self.assertIn(":COUNter:CURRent?", self.scope.commands)

    def test_rejected_command(self):
        self.scope.error_queue = ['-222,"Data out of range"', '0,"No error"']
        with self.assertRaises(RuntimeError):
            api.configure_settings(self.scope, "ACQuire", {"averages": 2})


if __name__ == "__main__":
    unittest.main()
