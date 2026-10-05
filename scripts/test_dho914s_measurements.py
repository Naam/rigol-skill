import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dho914s_measurements import (
    MeasurementSetup, Request, StatisticRequest, StatisticSettings,
    clear_measurements, configure_measurement_setup, configure_statistics,
    read_counter, read_dvm, read_frozen, read_measurement_counter,
    read_measurement_setup, reset_measurement_thresholds,
)
from rigol_dho900 import MEASUREMENT_TYPES


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self, responses=None, *, afg="0", trigger="STOP"):
        self.responses = {
            ":MEASure:SOURce?": "CHAN1", ":MEASure:AMSource?": "OFF",
            ":MEASure:SETup:MAX?": "90", ":MEASure:SETup:MID?": "60",
            ":MEASure:SETup:MIN?": "30", ":MEASure:SETup:PSA?": "CHAN1",
            ":MEASure:SETup:PSB?": "CHAN1", ":MEASure:SETup:DSA?": "CHAN1",
            ":MEASure:SETup:DSB?": "CHAN1", ":MEASure:THReshold:SOURce?": "CHAN1",
            ":MEASure:THReshold:TYPE?": "PERC", ":MEASure:AREA?": "MAIN",
            ":MEASure:INDicator?": "0", ":MEASure:COUNter:ENABle?": "0",
            ":MEASure:COUNter:SOURce?": "CHAN1", ":MEASure:AMP:TYPE?": "MAN",
            ":MEASure:AMP:MANual:TOP?": "HIST", ":MEASure:AMP:MANual:BASE?": "HIST",
            ":MEASure:CATegory?": "0", ":TIMebase:DELay:ENABle?": "0",
        }
        self.responses.update(responses or {})
        self.afg = afg
        self.trigger = trigger
        self.commands = []
        self.error_queue = []
        self.count = "100"
        self.enabled = "1"

    def query(self, command):
        self.commands.append(command)
        if command == ":SOURce:OUTPut:STATe?":
            return self.afg
        if command == ":TRIGger:STATus?":
            return self.trigger
        if command == ":MEASure:STATistic:COUNt?":
            return self.count
        if command == ":MEASure:STATistic:DISPlay?":
            return self.enabled
        return self.responses[command]

    def write(self, command):
        self.commands.append(command)
        if command.startswith(":MEASure:STATistic:COUNt "):
            self.count = command.split()[-1]
        if command.startswith(":MEASure:STATistic:DISPlay "):
            self.enabled = str(int(command.endswith("ON")))

    def errors(self):
        return self.error_queue or ["0,No error"]


class MeasurementsTest(unittest.TestCase):
    def test_frozen_batch_and_statistics(self):
        fake = FakeScope({
            ":MEASure:ITEM? VTOP,CHANnel3": "1.25E+0",
            ":MEASure:ITEM? RRDELAY,CHANnel1,CHANnel2": "*****",
            ":MEASure:STATistic:ITEM? MAXIMUM,VTOP,CHANnel3": "1.30E+0",
        })
        result = read_frozen(
            fake, (Request("vtop", "chan3"), Request("rrdelay", "chan1", "chan2")),
            statistics=(StatisticRequest(Request("vtop", "chan3"), "maximum"),),
            statistic_settings=StatisticSettings(100, True),
        )
        self.assertEqual([(x.item, x.value, x.status, x.unit, x.statistic) for x in result], [
            ("VTOP", 1.25, "valid", "V", None),
            ("RRDELAY", None, "unavailable", "s", None),
            ("VTOP", 1.3, "valid", "V", "MAXIMUM"),
        ])
        self.assertFalse(any(c.startswith(":RUN") or c.startswith(":SING") or
                             c.startswith(":SOURce:OUTPut:STATe ON") for c in fake.commands))
        self.assertFalse(any(c.startswith(":MEASure:ITEM ") for c in fake.commands))

    def test_all_items_and_digital_restriction(self):
        self.assertEqual(len(MEASUREMENT_TYPES), 42)
        for item in MEASUREMENT_TYPES:
            source_b = "CHAN2" if item.endswith(("DELAY", "PHASE")) else None
            fake = FakeScope({f":MEASure:ITEM? {item},CHANnel1" +
                              (",CHANnel2" if source_b else ""): "1"})
            self.assertEqual(read_frozen(fake, (Request(item, "CHAN1", source_b),))[0].value, 1)
        with self.assertRaises(ValueError):
            read_frozen(FakeScope(), (Request("VTOP", "D0"),))
        with self.assertRaises(ValueError):
            read_frozen(FakeScope(), (Request("RRDELAY", "CHAN1"),))
        self.assertEqual(read_frozen(FakeScope({":MEASure:ITEM? PERIOD,D15": "2e-6"}),
                                     (Request("PERIOD", "D15"),))[0].unit, "s")

    def test_safety_and_errors(self):
        request = (Request("VPP", "CHAN1"),)
        for fake in (FakeScope(afg="1"), FakeScope(trigger="RUN")):
            with self.assertRaises(RuntimeError):
                read_frozen(fake, request)
            self.assertFalse(any(c.startswith(":MEASure:ITEM?") for c in fake.commands))
        fake = FakeScope({":MEASure:ITEM? VPP,CHANnel1": "1e38"})
        self.assertEqual(read_frozen(fake, request)[0].status, "unavailable")
        fake.error_queue = ["-100,Command error", "0,No error"]
        with self.assertRaises(RuntimeError):
            read_frozen(fake, request)
        with self.assertRaises(ValueError):
            read_frozen(FakeScope(), request,
                        statistics=(StatisticRequest(request[0], "MAXIMUM"),))

    def test_configure_statistics_explicit_and_bounded(self):
        fake = FakeScope()
        configure_statistics(fake, StatisticSettings(100, True), (Request("VPP", "CHAN2"),))
        self.assertIn(":MEASure:STATistic:ITEM VPP,CHANnel2", fake.commands)
        self.assertNotIn(":RUN", fake.commands)
        with self.assertRaises(ValueError):
            configure_statistics(FakeScope(), StatisticSettings(100, True),
                                 (Request("VPP", "CHAN2"),) * 11)
        with self.assertRaises(ValueError):
            StatisticSettings(1, True)
        with self.assertRaises(RuntimeError):
            read_frozen(FakeScope(), (), statistic_settings=StatisticSettings(10, True))

    def test_live_dvm_and_counter_have_explicit_settings(self):
        fake = FakeScope({":DVM:SOURce?": "CHAN3", ":DVM:MODE?": "DC",
                          ":DVM:ENABle?": "1", ":DVM:CURRent?": "2.5E+0",
                          ":COUNter:SOURce?": "D1", ":COUNter:MODE?": "FREQ",
                          ":COUNter:ENABle?": "1", ":COUNter:CURRent?": "2E+4"},
                         trigger="RUN")
        self.assertEqual((read_dvm(fake, source="CHAN3", mode="DC").value,
                          read_counter(fake, source="D1", mode="FREQUENCY").unit),
                         (2.5, "Hz"))
        with self.assertRaises(RuntimeError):
            read_dvm(fake, source="CHAN2", mode="DC")
        self.assertFalse(any(c.startswith(":STOP") or c.startswith(":RUN")
                             for c in fake.commands))

    def test_measurement_setup_all_setters_and_readbacks(self):
        commands = {
            ":MEASure:SOURce?": "CHAN1", ":MEASure:AMSource?": "OFF",
            ":MEASure:SETup:MAX?": "90", ":MEASure:SETup:MID?": "60",
            ":MEASure:SETup:MIN?": "30", ":MEASure:SETup:PSA?": "CHAN1",
            ":MEASure:SETup:PSB?": "CHAN1", ":MEASure:SETup:DSA?": "CHAN1",
            ":MEASure:SETup:DSB?": "CHAN1", ":MEASure:THReshold:SOURce?": "CHAN1",
            ":MEASure:THReshold:TYPE?": "PERC", ":MEASure:AREA?": "MAIN",
            ":MEASure:INDicator?": "0", ":MEASure:COUNter:ENABle?": "0",
            ":MEASure:COUNter:SOURce?": "CHAN1", ":MEASure:AMP:TYPE?": "MAN",
            ":MEASure:AMP:MANual:TOP?": "HIST", ":MEASure:AMP:MANual:BASE?": "HIST",
            ":MEASure:CATegory?": "0",
        }

        class SetupFake(FakeScope):
            def query(self, command):
                self.commands.append(command)
                if command == ":SOURce:OUTPut:STATe?":
                    return self.afg
                if command in commands:
                    return commands[command]
                return super().query(command)

            def write(self, command):
                self.commands.append(command)
                if command.startswith(":MEASure:") and " " in command:
                    setting, value = command.split(" ", 1)
                    commands[setting + "?"] = value

        fake = SetupFake()
        result = configure_measurement_setup(fake, MeasurementSetup(
            source="CHAN2", all_measurement_source="OFF",
            threshold_max=95, threshold_mid=80, threshold_min=70,
            phase_source_a="D0", phase_source_b="MATH1",
            delay_source_a="CHAN3", delay_source_b="D1",
            threshold_source="MATH3", threshold_type="PERCENT",
            area="MAIN", indicator=True, counter_enabled=True,
            counter_source="D15", amplitude_type="MANUAL",
            amplitude_top="MAXMIN", amplitude_base="HISTOGRAM", category=2,
            clear_items=True,
        ))
        self.assertEqual((result.source, result.phase_source_a, result.counter_source,
                          result.amplitude_type, result.category),
                         ("CHANnel2", "D0", "D15", "MANUAL", 2))
        for command in (
            ":MEASure:CLEar", ":MEASure:SOURce CHANnel2", ":MEASure:AMSource OFF",
            ":MEASure:SETup:MAX 95", ":MEASure:SETup:MID 80", ":MEASure:SETup:MIN 70",
            ":MEASure:SETup:PSA D0", ":MEASure:SETup:PSB MATH1",
            ":MEASure:SETup:DSA CHANnel3", ":MEASure:SETup:DSB D1",
            ":MEASure:THReshold:SOURce MATH3", ":MEASure:THReshold:TYPE PERCent",
            ":MEASure:AREA MAIN", ":MEASure:INDicator ON",
            ":MEASure:COUNter:ENABle ON", ":MEASure:COUNter:SOURce D15",
            ":MEASure:AMP:TYPE MANual", ":MEASure:AMP:MANual:TOP MAXMin",
            ":MEASure:AMP:MANual:BASE HISTogram", ":MEASure:CATegory 2",
        ):
            self.assertIn(command, fake.commands)

    def test_measurement_setup_rejects_invalid_values_before_writes(self):
        fake = FakeScope()
        with self.assertRaisesRegex(ValueError, "MIN < MID < MAX"):
            configure_measurement_setup(fake, MeasurementSetup(threshold_min=80, threshold_mid=70))
        self.assertFalse(any(not c.endswith("?") for c in fake.commands))
        fake = FakeScope()
        with self.assertRaisesRegex(ValueError, "requires delayed sweep"):
            configure_measurement_setup(fake, MeasurementSetup(area="ZOOM"))
        self.assertFalse(any(not c.endswith("?") for c in fake.commands))
        fake = FakeScope()
        with self.assertRaisesRegex(ValueError, "indicator must be bool"):
            configure_measurement_setup(fake, MeasurementSetup(indicator=1))
        self.assertFalse(any(not c.endswith("?") for c in fake.commands))

    def test_measurement_counter_value_and_reset_commands(self):
        fake = FakeScope({":MEASure:COUNter:VALue?": "9.999996E+3"})
        result = read_measurement_counter(fake)
        self.assertEqual((result.value, result.unit), (9999.996, "Hz"))
        fake = FakeScope()
        reset_measurement_thresholds(fake)
        self.assertIn(":MEASure:THReshold:DEFault", fake.commands)
        clear_measurements(fake)
        self.assertIn(":MEASure:CLEar", fake.commands)
        with self.assertRaises(RuntimeError):
            read_measurement_counter(FakeScope(trigger="RUN"))


if __name__ == "__main__":
    unittest.main()
