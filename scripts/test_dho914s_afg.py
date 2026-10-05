import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dho914s_afg import CarrierConfig, DHO914SAFG, ModulationConfig


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.values = {
            ":SOURce:OUTPut:STATe": "0", ":SOURce:MOD:STATe": "0",
            ":SOURce:FUNCtion": "SIN", ":SOURce:FREQuency": "1000",
            ":SOURce:VOLTage:AMPLitude": "6", ":SOURce:VOLTage:OFFSet": "0",
            ":SOURce:PHASe": "0", ":SOURce:FUNCtion:RAMP:SYMMetry": "50",
            ":SOURce:FUNCtion:SQUare:DUTY": "50", ":SOURce:MOD:TYPe": "AM",
        }
        self.writes = []
        self.errors_list = []
        self.fail_on = None

    def query(self, command):
        if command.endswith("?"):
            command = command[:-1]
        if command.startswith(":SOURce:MOD:") and command.count(":") >= 4:
            pass
        if command not in self.values:
            raise AssertionError(f"unhandled query {command}?")
        return self.values[command]

    def write(self, command):
        self.writes.append(command)
        if command == self.fail_on:
            raise RuntimeError("simulated transport failure")
        if " " not in command:
            return
        head, value = command.split(" ", 1)
        self.values[head] = value
        if head == ":SOURce:FUNCtion":
            functions = {"SINusoid": "SIN", "SQUare": "SQU", "RAMP": "RAMP",
                         "DC": "DC", "NOISe": "NOIS", "ARB": "ARB",
                         "SIN": "SIN", "SQU": "SQU"}
            self.values[head] = functions[value]
        if ":MOD:" in head and head.endswith(":FUNCtion"):
            self.values[head] = {"SINusoid": "SIN", "SQUare": "SQU", "TRIangle": "TRI",
                                 "UPRamp": "UPR", "DNRamp": "DNR", "NOISe": "NOIS"}[value]
        if ":MOD:" in head and head.endswith(":TYPe"):
            self.values[head] = value

    def errors(self):
        return self.errors_list or ["0,No error"]


class AFGTest(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()
        self.afg = DHO914SAFG(self.scope)

    def test_carrier_commands_readback_and_dynamic_bounds(self):
        config = CarrierConfig(function="square", frequency_hz=1_000_000,
                               amplitude_vpp=8, offset_v=1, phase_deg=30,
                               square_duty_percent=0)
        state = self.afg.set_carrier(config)
        self.assertEqual(state, config)
        self.assertIn(":SOURce:FUNCtion SQUare", self.scope.writes)
        self.assertIn(":SOURce:FUNCtion:SQUare:DUTY 0", self.scope.writes)
        with self.assertRaises(ValueError):
            CarrierConfig(function="SIN", frequency_hz=11_000_000, amplitude_vpp=5.1)
        with self.assertRaises(ValueError):
            CarrierConfig(frequency_hz=11_000_000, amplitude_vpp=5, offset_v=0.01)
        with self.assertRaises(ValueError):
            CarrierConfig(function="RAMP", ramp_symmetry_percent=50,
                          square_duty_percent=50)
        self.assertEqual(CarrierConfig(function="DC", frequency_hz=None).amplitude_vpp, 6)

    def test_all_modulation_families_set_and_query(self):
        cases = (
            ModulationConfig("AM", depth_percent=120, internal_frequency_hz=1000,
                             internal_function="triangle"),
            ModulationConfig("FM", deviation_hz_or_deg=100,
                             internal_function="UPRAMP"),
            ModulationConfig("PM", deviation_hz_or_deg=360,
                             internal_function="NOISE"),
        )
        for config in cases:
            with self.subTest(kind=config.kind):
                self.afg.set_modulation(config)
                self.assertEqual(self.afg.read_modulation(), config)
                stem = f":SOURce:MOD:{config.kind}"
                self.assertTrue(any(c.startswith(stem + ":") for c in self.scope.writes))
        leaves = {c.split(" ", 1)[0] for c in self.scope.writes}
        for command in (":SOURce:MOD:AM:DEPTh", ":SOURce:MOD:AM:INTernal:FREQuency",
                        ":SOURce:MOD:AM:INTernal:FUNCtion",
                        ":SOURce:MOD:FM:DEViation", ":SOURce:MOD:FM:INTernal:FREQuency",
                        ":SOURce:MOD:FM:INTernal:FUNCtion",
                        ":SOURce:MOD:PM:DEViation", ":SOURce:MOD:PM:INTernal:FREQuency",
                        ":SOURce:MOD:PM:INTernal:FUNCtion"):
            self.assertIn(command, leaves)

    def test_rejects_invalid_modulation_and_fm_cross_bounds(self):
        with self.assertRaises(ValueError):
            ModulationConfig("AM", depth_percent=121)
        with self.assertRaises(ValueError):
            ModulationConfig("AM", depth_percent=50, deviation_hz_or_deg=2)
        with self.assertRaises(ValueError):
            ModulationConfig("FM", deviation_hz_or_deg=0.001)
        self.afg.set_carrier(CarrierConfig(frequency_hz=100))
        with self.assertRaises(ValueError):
            self.afg.set_modulation(ModulationConfig("FM", deviation_hz_or_deg=101))

    def test_carrier_changes_frequency_in_valid_intermediate_order(self):
        self.scope.values[":SOURce:FREQuency"] = "20000000"
        self.scope.values[":SOURce:VOLTage:AMPLitude"] = "4"
        self.afg.set_carrier(CarrierConfig("RAMP", 100_000, 2, 0))
        self.assertLess(self.scope.writes.index(":SOURce:FREQuency 100000"),
                        self.scope.writes.index(":SOURce:FUNCtion RAMP"))
        before = len(self.scope.writes)
        self.afg.set_carrier(CarrierConfig("SINusoid", 20_000_000, 2, 0))
        later = self.scope.writes[before:]
        self.assertLess(later.index(":SOURce:FUNCtion SINusoid"),
                        later.index(":SOURce:FREQuency 20000000"))

    def test_run_requires_verified_bounded_and_turns_both_outputs_off(self):
        carrier = CarrierConfig(function="RAMP", ramp_symmetry_percent=25)
        modulation = ModulationConfig("AM", depth_percent=50)
        for seconds, confirmation in ((0.049, "VERIFIED"), (5.01, "VERIFIED"),
                                      (0.1, "yes")):
            with self.assertRaises((ValueError, SystemExit)):
                self.afg.run(carrier, seconds=seconds, confirmation=confirmation,
                             modulation=modulation)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", self.scope.writes)
        with patch("dho914s_afg.time.sleep"):
            state = self.afg.run(carrier, seconds=0.05, confirmation="VERIFIED",
                                 modulation=modulation)
        self.assertFalse(state.output_enabled)
        self.assertFalse(state.modulation_enabled)
        self.assertIn(":SOURce:OUTPut:STATe ON", self.scope.writes)
        self.assertIn(":SOURce:MOD:STATe ON", self.scope.writes)
        self.assertEqual(self.scope.values[":SOURce:OUTPut:STATe"], "OFF")
        self.assertEqual(self.scope.values[":SOURce:MOD:STATe"], "OFF")

    def test_transport_failure_still_attempts_both_shutdowns(self):
        self.scope.fail_on = ":SOURce:MOD:STATe ON"
        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with patch("dho914s_afg.time.sleep"):
                self.afg.run(CarrierConfig(), seconds=0.05, confirmation="VERIFIED",
                             modulation=ModulationConfig("FM", deviation_hz_or_deg=10))
        self.assertEqual(self.scope.writes[-2:], [":SOURce:MOD:STATe OFF",
                                                  ":SOURce:OUTPut:STATe OFF"])
        self.assertEqual(self.scope.values[":SOURce:OUTPut:STATe"], "OFF")
        self.assertEqual(self.scope.values[":SOURce:MOD:STATe"], "OFF")

    def test_shutdown_requires_off_readback(self):
        original_write = self.scope.write
        def ignore_output_off(command):
            if command == ":SOURce:OUTPut:STATe OFF":
                self.scope.writes.append(command)
            else:
                original_write(command)
        self.scope.values[":SOURce:OUTPut:STATe"] = "ON"
        self.scope.write = ignore_output_off
        with self.assertRaisesRegex(RuntimeError, "did not confirm OFF"):
            self.afg.run(CarrierConfig(), seconds=0.05, confirmation="VERIFIED")
        self.assertNotIn(":SOURce:OUTPut:STATe ON", self.scope.writes)


if __name__ == "__main__":
    unittest.main()
