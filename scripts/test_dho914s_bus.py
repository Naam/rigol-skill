import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dho914s_bus as bus
from dho800900_models import MODELS


DEFAULT_PROTOCOLS = {
    bus.ParallelConfig: {"source": "CHAN1", "clock_source": "OFF", "slope": "POS", "width": "1", "bit": "0", "bit_source": "CHAN1", "endian": "MSB", "polarity": "POS"},
    bus.RS232Config: {"tx": "CHAN1", "rx": "OFF", "polarity": "NEG", "parity": "NONE", "endian": "LSB", "baud": "9600", "data_bits": "8", "stop_bits": "1"},
    bus.IICConfig: {"clock_source": "CHAN1", "data_source": "CHAN2", "exchange": "0", "address_format": "NORM"},
    bus.SPIConfig: {"clock_source": "CHAN1", "clock_slope": "POS", "miso_source": "CHAN2", "mosi_source": "OFF", "polarity": "HIGH", "miso_polarity": "HIGH", "mosi_polarity": "HIGH", "data_bits": "8", "endian": "MSB", "mode": "TIM", "timeout_s": "1E-6", "select_source": "CHAN3", "select_polarity": "LOW"},
    bus.CANConfig: {"source": "CHAN1", "signal_type": "CANL", "baud": "1000000", "sample_point": "50"},
    bus.LINConfig: {"parity": "0", "source": "CHAN1", "standard": "MIX"},
}


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.common = {n: {"MODE": "PAR", "DISPlay": "1", "FORMat": "HEX", "EVENt": "0", "LABel": "1", "POSition": "0"} for n in range(1, 5)}
        self.protocols = {n: {kind: dict(values) for kind, values in DEFAULT_PROTOCOLS.items()} for n in range(1, 5)}
        self.thresholds = {(n, name): "0" for n in range(1, 5) for name in ("PAL", "TX", "RX", "SCL", "SDA", "CS", "CLK", "MISO", "MOSI", "LIN", "CAN", "PALCLK", "CH1", "CH2", "CH3", "CH4")}
        self.writes = []
        self.queries = []
        self.errors_pending = []
        self.fail_once = None
        self.ignore_once = None
        self.raw = self.block(b"PARALLEL\nTime,Data,\n-2.47us,0,\n1.554us,1,\n")
        self.instrument = self

    @staticmethod
    def block(payload):
        return b"#9" + f"{len(payload):09d}".encode() + payload + b"\n"

    def afg_off(self):
        self.writes.append(":SOURce:OUTPut:STATe OFF")

    def write(self, command):
        self.writes.append(command)
        if command.startswith(":BUS") and ":THReshold " in command:
            prefix, params = command.split(" ", 1)
            value, kind = params.split(",", 1)
            number = int(prefix[4])
            if self.fail_once == prefix:
                self.fail_once = None
                self.errors_pending.append('-200,"simulated failure"')
                return
            self.thresholds[(number, kind)] = value
            return
        for number in range(1, 5):
            for key, leaf in {"mode":"MODE", "display":"DISPlay", "data_format":"FORMat", "event_table":"EVENt", "label":"LABel", "position":"POSition"}.items():
                path = f":BUS{number}:{leaf}"
                if command.startswith(path + " "):
                    if self.fail_once == path:
                        self.fail_once = None
                        self.errors_pending.append('-200,"simulated failure"')
                        return
                    if self.ignore_once == path:
                        self.ignore_once = None
                        return
                    self.common[number][leaf] = command[len(path) + 1:]
                    return
            for config_type, (_, _, specs) in bus._PROTOCOLS.items():
                for field in specs:
                    path = bus._path(number, config_type, field)
                    if command.startswith(path + " "):
                        if self.fail_once == path:
                            self.fail_once = None
                            self.errors_pending.append('-200,"simulated failure"')
                            return
                        if self.ignore_once == path:
                            self.ignore_once = None
                            return
                        self.protocols[number][config_type][field] = command[len(path) + 1:]
                        return
            path = f":BUS{number}:EEXPort"
            if command.startswith(path + " "):
                return
        raise AssertionError(f"unexpected write: {command}")

    def query(self, command):
        self.queries.append(command)
        if command == ":TRIGger:STATus?":
            return "STOP"
        if command.startswith(":CHANnel") and command.endswith(":SCALe?"):
            return "1"
        if command.startswith(":CHANnel") and command.endswith(":OFFSet?"):
            return "0"
        threshold = __import__("re").fullmatch(r":BUS([1-4]):THReshold\? ([A-Z0-9]+)", command)
        if threshold:
            return self.thresholds[(int(threshold.group(1)), threshold.group(2))]
        for number in range(1, 5):
            for leaf, value in self.common[number].items():
                if command == f":BUS{number}:{leaf}?":
                    return value
            for config_type, (_, _, specs) in bus._PROTOCOLS.items():
                for field in specs:
                    if command == bus._path(number, config_type, field) + "?":
                        return self.protocols[number][config_type][field]
        if self.errors_pending:
            return ""
        raise AssertionError(f"unexpected query: {command}")

    def query_raw(self, command):
        self.queries.append(command)
        return self.raw

    def errors(self):
        if self.errors_pending:
            result, self.errors_pending = self.errors_pending, []
            return result + ['+0,"No error"']
        return ['+0,"No error"']


class BusTests(unittest.TestCase):
    @staticmethod
    def _candidate(config_type, field, current):
        _, kind, bounds = bus._PROTOCOLS[config_type][2][field]
        if kind in {"source", "source_off"}:
            return "CHAN4"
        if kind == "bool":
            return not current
        if kind == "int":
            if field == "baud":
                return 115200
            next_value = max(bounds[0], current + 1)
            return next_value if bounds[1] is None else min(bounds[1], next_value)
        if kind == "real":
            return 0.002 if field == "timeout_s" else 0.25
        return next(value for value in bounds if value != current)

    @staticmethod
    def _profile(scope, config_type, field):
        if config_type is bus.ParallelConfig and field in {"width", "bit", "bit_source"}:
            scope.protocols[1][config_type]["source"] = "USER"
            scope.protocols[1][config_type]["width"] = "4"
        if config_type is bus.SPIConfig:
            scope.protocols[1][config_type]["mode"] = "TIM" if field == "timeout_s" else "CS"

    def test_common_setter_and_query_forms(self):
        scope = FakeScope()
        before = bus.read_settings(scope, 1)
        self.assertEqual(before.mode, "PARallel")
        self.assertEqual(bus.configure_settings(scope, 1, bus.BusSettings(mode="CAN")).mode, "CAN")
        self.assertFalse(bus.configure_settings(scope, 1, bus.BusSettings(display=False)).display)
        self.assertTrue(bus.configure_settings(scope, 1, bus.BusSettings(display=True)).display)
        settings = bus.configure_settings(scope, 1, bus.BusSettings(data_format="BIN", event_table=True, label=False, position=-100))
        self.assertEqual((settings.data_format, settings.event_table, settings.label, settings.position), ("BIN", True, False, -100))
        for path in (":BUS1:MODE?", ":BUS1:DISPlay?", ":BUS1:FORMat?", ":BUS1:EVENt?", ":BUS1:LABel?", ":BUS1:POSition?"):
            self.assertIn(path, scope.queries)

    def test_all_protocol_leaf_setter_and_query_forms(self):
        total = 0
        for config_type, (_, mode, specs) in bus._PROTOCOLS.items():
            for field in specs:
                scope = FakeScope()
                scope.common[1]["MODE"] = "RS232" if mode == "RS232" else mode.upper()[:3]
                self._profile(scope, config_type, field)
                state = bus.read_protocol(scope, 1, config_type)
                self.assertIsNotNone(getattr(state, field), (config_type.__name__, field))
                value = self._candidate(config_type, field, getattr(state, field))
                result = bus.configure_protocol(scope, 1, config_type(**{field: value}))
                path = bus._path(1, config_type, field)
                self.assertIn(path + "?", scope.queries, (config_type.__name__, field))
                self.assertTrue(any(command.startswith(path + " ") for command in scope.writes), (config_type.__name__, field))
                expected = bus._validate(specs[field][1], value, specs[field][2], field)
                self.assertEqual(getattr(result, field), expected, (config_type.__name__, field))
                total += 1
        self.assertEqual(total, 40)

    def test_parallel_user_and_spi_mode_conditional_two_phase_setup(self):
        scope = FakeScope()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            bus.configure_protocol(scope, 1, bus.ParallelConfig(source="USER", width=4))
        bus.configure_protocol(scope, 1, bus.ParallelConfig(source="USER"))
        self.assertEqual(bus.configure_protocol(scope, 1, bus.ParallelConfig(width=4, bit=2, bit_source="CHANnel3")).bit, 2)
        scope.writes.clear()
        with self.assertRaisesRegex(ValueError, "shrinking width"):
            bus.configure_protocol(scope, 1, bus.ParallelConfig(width=2))
        self.assertEqual(scope.writes, [])
        scope = FakeScope()
        scope.common[1]["MODE"] = "SPI"
        with self.assertRaisesRegex(ValueError, "unavailable"):
            bus.configure_protocol(scope, 1, bus.SPIConfig(mode="CS", select_source="CHANnel2"))
        bus.configure_protocol(scope, 1, bus.SPIConfig(mode="CS"))
        self.assertEqual(bus.configure_protocol(scope, 1, bus.SPIConfig(select_source="CHANnel2")).select_source, "CHANnel2")

    def test_all_threshold_source_forms_validate_and_read_back(self):
        cases = {
            "PAL": (bus.ParallelConfig, "PARallel", {"source": "CHAN2"}),
            "PALCLK": (bus.ParallelConfig, "PARallel", {"source": "CHAN2", "clock_source": "CHAN3"}),
            "TX": (bus.RS232Config, "RS232", {"tx": "CHAN1", "rx": "CHAN2"}),
            "RX": (bus.RS232Config, "RS232", {"tx": "CHAN1", "rx": "CHAN2"}),
            "SCL": (bus.IICConfig, "IIC", {"clock_source": "CHAN1"}),
            "SDA": (bus.IICConfig, "IIC", {"data_source": "CHAN2"}),
            "CS": (bus.SPIConfig, "SPI", {"mode": "CS", "select_source": "CHAN3"}),
            "CLK": (bus.SPIConfig, "SPI", {"clock_source": "CHAN1"}),
            "MISO": (bus.SPIConfig, "SPI", {"miso_source": "CHAN2"}),
            "MOSI": (bus.SPIConfig, "SPI", {"mosi_source": "CHAN3"}),
            "LIN": (bus.LINConfig, "LIN", {"source": "CHAN1"}),
            "CAN": (bus.CANConfig, "CAN", {"source": "CHAN1"}),
        }
        for kind in ("CH1", "CH2", "CH3", "CH4"):
            scope = FakeScope()
            self.assertEqual(bus.configure_thresholds(scope, 1, {kind: 0.5})[kind], 0.5)
        for name, (config_type, mode, changes) in cases.items():
            scope = FakeScope()
            scope.common[1]["MODE"] = "RS232" if mode == "RS232" else mode.upper()[:3]
            for field, value in changes.items():
                scope.protocols[1][config_type][field] = value
            result = bus.configure_thresholds(scope, 1, {name: 0.5})
            self.assertEqual(result[name], 0.5, name)
            self.assertIn(f":BUS1:THReshold? {name}", scope.queries)
        self.assertEqual(len(cases) + 4, 16)
        with self.assertRaisesRegex(ValueError, "threshold"):
            bus.configure_thresholds(FakeScope(), 1, {"CH1": 5.1})

    def test_binary_event_data_parse_and_truncation(self):
        scope = FakeScope()
        capture = bus.read_events(scope, 1)
        self.assertEqual((capture.protocol, capture.columns), ("PARALLEL", ("Time", "Data")))
        self.assertEqual([event.timestamp_s for event in capture.events], [-2.47e-6, 1.554e-6])
        scope.raw = b"#9000000007SHORT"
        with self.assertRaisesRegex(ValueError, "truncated"):
            bus.read_events(scope, 1)

    def test_file_export_requires_explicit_overwrite_and_stopped_event_table(self):
        scope = FakeScope()
        with self.assertRaisesRegex(ValueError, "allow_overwrite"):
            bus.export_events(scope, 1, "D:/events.csv")
        bus.configure_settings(scope, 1, bus.BusSettings(event_table=True))
        bus.export_events(scope, 1, "D:/events.csv", allow_overwrite=True)
        self.assertIn(':BUS1:EEXPort "D:/events.csv"', scope.writes)
        with self.assertRaisesRegex(ValueError, "quotes"):
            bus.export_events(scope, 1, 'D:/bad"name.csv', allow_overwrite=True)

    def test_failed_common_and_protocol_writes_restore_snapshot(self):
        scope = FakeScope()
        before = bus.read_settings(scope, 1)
        scope.fail_once = ":BUS1:LABel"
        with self.assertRaises(RuntimeError):
            bus.configure_settings(scope, 1, bus.BusSettings(data_format="BIN", label=False))
        self.assertEqual(bus.read_settings(scope, 1), before)
        scope.common[1]["MODE"] = "SPI"
        before_spi = bus.read_protocol(scope, 1, bus.SPIConfig)
        scope.fail_once = ":BUS1:SPI:DBITs"
        with self.assertRaises(RuntimeError):
            bus.configure_protocol(scope, 1, bus.SPIConfig(data_bits=12, endian="LSB"))
        self.assertEqual(bus.read_protocol(scope, 1, bus.SPIConfig), before_spi)

    def test_family_profile_rejects_unsupported_decode_modes(self):
        scope = FakeScope()
        scope.profile = MODELS["DHO812"]
        with self.assertRaises(NotImplementedError):
            bus.configure_settings(scope, 1, bus.BusSettings(mode="LIN"))
        self.assertEqual(scope.writes, [])
        scope.common[1]["MODE"] = "SPI"
        scope.protocols[1][bus.SPIConfig]["mode"] = "CS"
        with self.assertRaises(NotImplementedError):
            bus.read_protocol(scope, 1, bus.SPIConfig)
        scope.profile = MODELS["DHO814"]
        self.assertEqual(bus.read_protocol(scope, 1, bus.SPIConfig).mode, "CS")


if __name__ == "__main__":
    unittest.main()
