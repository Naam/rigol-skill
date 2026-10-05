import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dho914s_mask import DHO914SMask, MaskConfig, MaskMetrics


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.values = {
            ":MASK:ENABle": "0", ":MASK:SOURce": "CHAN1", ":MASK:OPERate": "STOP",
            ":MASK:X": "0.24", ":MASK:Y": "0.48", ":MASK:OUTPut:ENABle": "0",
            ":MASK:OUTPut:EVENt": "FAIL", ":MASK:OUTPut:TIME": "1e-6",
            ":MASK:FAILed": "2", ":MASK:PASSed": "8", ":MASK:TOTal": "10",
        }
        self.writes = []
        self.queries = []
        self.error_list = []
        self.fail_on = None

    def query(self, command):
        self.queries.append(command)
        key = command[:-1] if command.endswith("?") else command
        try:
            return self.values[key]
        except KeyError as exc:
            raise AssertionError(f"unhandled query {command}") from exc

    def write(self, command):
        self.writes.append(command)
        if command == self.fail_on:
            raise RuntimeError("simulated instrument failure")
        if command == ":MASK:RESet":
            self.values.update({":MASK:FAILed": "0", ":MASK:PASSed": "0", ":MASK:TOTal": "0"})
            return
        if " " in command:
            key, value = command.split(" ", 1)
            if key == ":MASK:SOURce":
                value = value.replace("CHANnel", "CHAN")
            self.values[key] = value

    def errors(self):
        return self.error_list or ["0,No error"]


class MaskTest(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()
        self.mask = DHO914SMask(self.scope)

    def test_typed_configuration_and_all_leaf_commands(self):
        config = MaskConfig(4, 2, 0.04, "pass", 10e-3)
        result = self.mask.configure(config)
        self.assertEqual(result, config)
        self.assertEqual(self.scope.values[":MASK:ENABle"], "OFF")
        self.assertEqual(self.scope.values[":MASK:OUTPut:ENABle"], "OFF")
        self.assertNotIn(":MASK:OUTPut:ENABle ON", self.scope.writes)
        self.mask.read_state()
        self.mask.read_metrics()
        self.mask.reset_metrics()
        writes = {cmd.split(" ", 1)[0] for cmd in self.scope.writes}
        for command in (":MASK:ENABle", ":MASK:SOURce", ":MASK:OPERate", ":MASK:X",
                        ":MASK:Y", ":MASK:CREate", ":MASK:RESet",
                        ":MASK:OUTPut:ENABle", ":MASK:OUTPut:EVENt", ":MASK:OUTPut:TIME"):
            self.assertIn(command, writes)
        for command in (":MASK:FAILed?", ":MASK:PASSed?", ":MASK:TOTal?"):
            self.assertIn(command, self.scope.queries)

    def test_limits_rejected_before_instrument_writes(self):
        for values in ({"source_channel": 5}, {"horizontal_div": 2.01},
                       {"vertical_div": 0.039}, {"output_event": "OTHER"},
                       {"output_pulse_s": 11e-3}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.mask.configure(MaskConfig(**values))
        with self.assertRaises(ValueError):
            self.mask.run(seconds=0.049, confirmation="VERIFIED")
        with self.assertRaises((ValueError, SystemExit)):
            self.mask.run(seconds=0.2, confirmation="NO")
        self.assertEqual(self.scope.writes, [])

    def test_bounded_aux_run_and_metrics(self):
        with patch("dho914s_mask.time.sleep") as sleep:
            metrics = self.mask.run(seconds=0.05, confirmation="VERIFIED",
                                    config=MaskConfig(output_event="PASS"))
        sleep.assert_called_once_with(0.05)
        self.assertEqual(metrics, MaskMetrics(8, 2, 10))
        self.assertIn(":MASK:OUTPut:ENABle ON", self.scope.writes)
        self.assertIn(":MASK:OPERate RUN", self.scope.writes)
        self.assertEqual(self.scope.values[":MASK:OUTPut:ENABle"], "OFF")
        self.assertEqual(self.scope.values[":MASK:OPERate"], "STOP")
        self.assertEqual(self.scope.values[":MASK:ENABle"], "OFF")

    def test_failure_after_aux_on_attempts_all_shutdown_commands(self):
        self.scope.fail_on = ":MASK:OPERate RUN"
        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with patch("dho914s_mask.time.sleep"):
                self.mask.run(seconds=0.05, confirmation="VERIFIED")
        self.assertEqual(self.scope.values[":MASK:OUTPut:ENABle"], "OFF")
        self.assertEqual(self.scope.values[":MASK:OPERate"], "STOP")
        self.assertEqual(self.scope.values[":MASK:ENABle"], "OFF")
        self.assertEqual(self.scope.writes[-3:], [":MASK:OPERate STOP",
                                                 ":MASK:OUTPut:ENABle OFF",
                                                 ":MASK:ENABle OFF"])

    def test_non_aux_run_and_metric_consistency(self):
        with patch("dho914s_mask.time.sleep"):
            self.mask.run(seconds=0.1, confirmation="VERIFIED", aux_output=False)
        self.assertNotIn(":MASK:OUTPut:ENABle ON", self.scope.writes)
        self.scope.values[":MASK:PASSed"] = "9"
        with self.assertRaisesRegex(RuntimeError, "exceed"):
            self.mask.read_metrics()


if __name__ == "__main__":
    unittest.main()
