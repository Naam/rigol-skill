import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dho914s_trigger_protocol as protocol
from dho800900_models import MODELS


DEFAULTS = {
    protocol.RS232Config: {"source": "CHAN1", "level_v": "0", "polarity": "POS", "when": "STAR", "data": "0", "baud": "9600", "width": "8", "stop": "1", "parity": "NONE"},
    protocol.IICConfig: {"scl": "CHAN1", "clock_level_v": "0", "sda": "CHAN2", "data_level_v": "0", "when": "STAR", "address_width": "7", "address": "0", "direction": "WRIT", "data_bytes": "1", "data": "0", "current_bit": "0", "code": "255"},
    protocol.SPIConfig: {"clk": "CHAN1", "scl": "CHAN1", "scl_level_v": "0", "slope": "POS", "miso": "CHAN2", "sda": "CHAN2", "data_level_v": "0", "when": "CS", "cs": "CHAN3", "cs_level_v": "0", "mode": "LOW", "timeout_s": "1E-6", "width": "8", "data": "0", "current_bit": "0", "code": "255"},
    protocol.CANConfig: {"baud": "1000000", "source": "CHAN1", "signal_type": "H", "when": "SOF", "sample_point": "50", "extended_id": "0", "define": "DATA", "data_width": "1", "data": "0", "current_bit": "0", "code": "255", "level_v": "0"},
    protocol.LINConfig: {"source": "CHAN1", "level_v": "0", "standard": "BOTH", "baud": "9600", "sample_point": "50", "when": "SYNC", "error": "SYNC", "identifier": "0", "data": "0", "current_bit": "0", "code": "255"},
}


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.states = {kind: dict(values) for kind, values in DEFAULTS.items()}
        self.mode = "EDGE"
        self.writes = []
        self.queries = []
        self.errors_pending = []
        self.fail_once = None
        self.ignore_once = None
        self.fail_mode_once = False
        self.ignore_mode_once = False

    def afg_off(self):
        self.writes.append(":SOURce:OUTPut:STATe OFF")

    def write(self, command):
        self.writes.append(command)
        if command.startswith(":TRIGger:MODE "):
            if self.fail_mode_once:
                self.fail_mode_once = False
                self.errors_pending.append('-200,"simulated mode failure"')
                return
            if self.ignore_mode_once:
                self.ignore_mode_once = False
                return
            token = command.rsplit(" ", 1)[1].upper()
            self.mode = {
                "PULSE": "PULS", "SLOPE": "SLOP", "VIDEO": "VID", "PATTERN": "PATT",
                "DURATION": "DUR", "TIMEOUT": "TIM", "WINDOW": "WIND", "DELAY": "DEL",
                "SETUP": "SET", "NTHEDGE": "NEDG", "NEDGE": "NEDG",
            }.get(token, token)
            return
        for kind, fields in protocol._SPECS.items():
            for name in fields:
                path = protocol._path(kind, name)
                if command.startswith(path + " "):
                    if self.fail_once == path:
                        self.fail_once = None
                        self.errors_pending.append('-200,"simulated failure"')
                        return
                    if self.ignore_once == path:
                        self.ignore_once = None
                        return
                    value = command[len(path) + 1:]
                    if value == "None":
                        self.errors_pending.append('-222,"invalid null"')
                        return
                    self.states[kind][name] = value
                    return

    def query(self, command):
        self.queries.append(command)
        if command == ":TRIGger:MODE?":
            return self.mode
        if command == ":SOURce:OUTPut:STATe?":
            return "OFF"
        if command.startswith(":CHANnel") and command.endswith(":SCALe?"):
            return "1"
        if command.startswith(":CHANnel") and command.endswith(":OFFSet?"):
            return "0"
        for kind, fields in protocol._SPECS.items():
            for name in fields:
                if command == protocol._path(kind, name) + "?":
                    return self.states[kind][name]
        raise AssertionError(f"unexpected query: {command}")

    def errors(self):
        if self.errors_pending:
            result, self.errors_pending = self.errors_pending, []
            return result + ['+0,"No error"']
        return ['+0,"No error"']


class TriggerProtocolTests(unittest.TestCase):
    def test_family_profile_blocks_lin_and_two_channel_spi_cs(self):
        scope = FakeScope()
        scope.profile = MODELS["DHO812"]
        with self.assertRaises(NotImplementedError):
            protocol.configure_trigger_mode(scope, "LIN")
        with self.assertRaises(NotImplementedError):
            protocol.configure_trigger(scope, protocol.LINConfig(source="CHAN1"))
        self.assertEqual(scope.writes, [])
        with self.assertRaises(ValueError):
            protocol.configure_trigger(scope, protocol.RS232Config(source="D0"))
        scope.states[protocol.SPIConfig]["cs"] = "CHAN2"
        with self.assertRaises(NotImplementedError):
            protocol.configure_trigger(scope, protocol.SPIConfig(when="CS"))
        self.assertEqual(scope.writes, [])

    def test_common_mode_can_activate_each_serial_protocol(self):
        for name in ("RS232", "IIC", "SPI", "CAN", "LIN"):
            with self.subTest(mode=name):
                scope = FakeScope()
                state = protocol.configure_trigger_mode(scope, name)
                self.assertEqual(state, protocol.TriggerModeState(name))
                self.assertEqual(protocol.read_trigger_mode(scope).mode, name)
                self.assertIn(f":TRIGger:MODE {name}", scope.writes)

    def test_protocol_configuration_activates_its_trigger_mode(self):
        scope = FakeScope()
        protocol.configure_trigger(scope, protocol.RS232Config(baud=19200))
        self.assertEqual(protocol.read_trigger_mode(scope).mode, "RS232")

    def test_common_mode_failure_restores_previous_mode(self):
        for raw_mode, expected in (("EDGE", "EDGE"), ("SET", "SETUPHOLD"), ("WIND", "WINDOWS"), ("NEDG", "NTHEDGE")):
            with self.subTest(previous=raw_mode):
                scope = FakeScope()
                scope.mode = raw_mode
                scope.fail_mode_once = True
                with self.assertRaisesRegex(RuntimeError, "simulated mode failure"):
                    protocol.configure_trigger_mode(scope, "CAN")
                self.assertEqual(protocol.read_trigger_mode(scope).mode, expected)
                self.assertEqual(scope.writes[-1], f":TRIGger:MODE {protocol._TRIGGER_MODE_TOKENS[expected]}")

    def test_ignored_common_mode_write_is_detected_and_rolled_back(self):
        scope = FakeScope()
        scope.ignore_mode_once = True
        with self.assertRaisesRegex(RuntimeError, "did not apply trigger mode"):
            protocol.configure_trigger_mode(scope, "LIN")
        self.assertEqual(protocol.read_trigger_mode(scope).mode, "EDGE")

    def test_each_protocol_reads_typed_full_state(self):
        scope = FakeScope()
        for kind in protocol._SPECS:
            state = protocol.read_trigger(scope, kind)
            self.assertIsInstance(state, kind)
            self.assertIsNotNone(getattr(state, "when"))

    def test_protocol_specific_err_alias_decoding(self):
        scope = FakeScope()
        scope.states[protocol.LINConfig]["when"] = "ERR"
        scope.states[protocol.CANConfig]["when"] = "ERR"
        self.assertEqual(protocol.read_trigger(scope, protocol.LINConfig).when, "ERRor")
        self.assertEqual(protocol.read_trigger(scope, protocol.CANConfig).when, "ERRandom")

    @staticmethod
    def _profile(scope, config_type, field):
        states = scope.states[config_type]
        if config_type is protocol.RS232Config and field in {"data", "width"}:
            states["when"] = "DATA"
        elif config_type is protocol.IICConfig:
            states["when"] = "ADAT"
            states["address_width"] = "7"
            states["direction"] = "WRIT"
        elif config_type is protocol.SPIConfig:
            states["when"] = "TIM" if field == "timeout_s" else "CS"
        elif config_type is protocol.CANConfig:
            if field == "extended_id":
                states["when"] = "IDFR"
            elif field in {"define", "data_width", "data"}:
                states["when"] = "IDD"
        elif config_type is protocol.LINConfig:
            if field == "error":
                states["when"] = "ERR"
            elif field == "identifier":
                states["when"] = "IDD"
            elif field == "data":
                states["when"] = "DATA"

    @staticmethod
    def _candidate(config_type, field, before):
        leaf, kind, bounds = protocol._SPECS[config_type][field]
        current = getattr(before, field)
        if kind == "source":
            return "CHAN4" if current != "CHAN4" else "D15"
        if kind == "bool":
            return not current
        if kind == "int":
            if field == "baud":
                return 115200
            next_value = max(bounds[0], (current or bounds[0]) + 1)
            return next_value if bounds[1] is None else min(bounds[1], next_value)
        if kind == "real":
            return 0.002 if field == "timeout_s" else 0.25
        choices = bounds
        return next(choice for choice in choices if choice != current)

    def test_every_documented_protocol_field_has_setter_and_query_readback(self):
        total = 0
        for config_type, specs in protocol._SPECS.items():
            for field in specs:
                scope = FakeScope()
                self._profile(scope, config_type, field)
                before = protocol.read_trigger(scope, config_type)
                self.assertIsNotNone(getattr(before, field), (config_type.__name__, field))
                path = protocol._path(config_type, field)
                value = self._candidate(config_type, field, before)
                result = protocol.configure_trigger(scope, config_type(**{field: value}))
                self.assertIn(path + "?", scope.queries, (config_type.__name__, field))
                self.assertTrue(any(write.startswith(path + " ") for write in scope.writes), (config_type.__name__, field))
                expected = protocol._canonical(specs[field][1], value, specs[field][2], field)
                self.assertEqual(getattr(result, field), expected, (config_type.__name__, field))
                total += 1
        self.assertEqual(total, 60)

    def test_requested_write_mismatch_is_rejected_and_rolled_back(self):
        scope = FakeScope()
        before = protocol.read_trigger(scope, protocol.RS232Config)
        scope.ignore_once = ":TRIGger:RS232:BAUD"
        with self.assertRaisesRegex(RuntimeError, "did not apply"):
            protocol.configure_trigger(scope, protocol.RS232Config(baud=19200))
        self.assertEqual(protocol.read_trigger(scope, protocol.RS232Config), before)

    def test_spi_timeout_order_and_readback(self):
        scope = FakeScope()
        protocol.configure_trigger(scope, protocol.SPIConfig(when="TIMeout"))
        state = protocol.configure_trigger(scope, protocol.SPIConfig(timeout_s=0.002, width=12, data=0xABC))
        changed = [line for line in scope.writes if line.startswith(":TRIGger:SPI:")]
        self.assertEqual(changed, [":TRIGger:SPI:WHEN TIMeout", ":TRIGger:SPI:WIDTh 12", ":TRIGger:SPI:TIMeout 0.002", ":TRIGger:SPI:DATA 2748"])
        self.assertEqual(state.when, "TIMeout")
        self.assertEqual(state.timeout_s, 0.002)

    def test_rejects_conditional_or_dynamic_values_before_writing(self):
        scope = FakeScope()
        cases = (
            (protocol.SPIConfig(timeout_s=0.1), "timeout"),
            (protocol.IICConfig(when="ADDRess", address_width=8, direction="READ"), "direction"),
            (protocol.IICConfig(when="ADDRess", address_width=7, address=128), "address"),
            (protocol.RS232Config(width=5, data=32), "data"),
            (protocol.LINConfig(when="ID", data=1), "data"),
            (protocol.RS232Config(source="CHAN1", level_v=5), "level"),
        )
        for config, message in cases:
            scope.writes.clear()
            with self.assertRaisesRegex(ValueError, message):
                protocol.configure_trigger(scope, config)
            self.assertEqual(scope.writes, [])

    def test_selector_then_conditional_write_is_two_phase(self):
        cases = (
            (protocol.RS232Config, protocol.RS232Config(when="DATA", width=7), protocol.RS232Config(when="DATA"), protocol.RS232Config(width=7)),
            (protocol.IICConfig, protocol.IICConfig(when="ADDRess", address_width=10), protocol.IICConfig(when="ADDRess"), protocol.IICConfig(address_width=10)),
            (protocol.SPIConfig, protocol.SPIConfig(when="TIMeout", timeout_s=0.1), protocol.SPIConfig(when="TIMeout"), protocol.SPIConfig(timeout_s=0.1)),
            (protocol.CANConfig, protocol.CANConfig(when="IDFRame", extended_id=True), protocol.CANConfig(when="IDFRame"), protocol.CANConfig(extended_id=True)),
            (protocol.LINConfig, protocol.LINConfig(when="ERRor", error="CHECk"), protocol.LINConfig(when="ERRor"), protocol.LINConfig(error="CHECk")),
        )
        for _, unsafe, select, configure in cases:
            scope = FakeScope()
            with self.assertRaisesRegex(ValueError, "unavailable"):
                protocol.configure_trigger(scope, unsafe)
            self.assertEqual(scope.writes, [])
            protocol.configure_trigger(scope, select)
            result = protocol.configure_trigger(scope, configure)
            self.assertIsNotNone(result.when)

    def test_iic_width_eight_skips_unavailable_direction(self):
        scope = FakeScope()
        scope.states[protocol.IICConfig]["when"] = "ADDR"
        scope.states[protocol.IICConfig]["address_width"] = "8"
        state = protocol.read_trigger(scope, protocol.IICConfig)
        self.assertIsNone(state.direction)
        self.assertNotIn(":TRIGger:IIC:DIRection?", scope.queries)

    def test_write_error_restores_entire_snapshot(self):
        scope = FakeScope()
        before = protocol.read_trigger(scope, protocol.RS232Config)
        scope.fail_once = ":TRIGger:RS232:BAUD"
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            protocol.configure_trigger(scope, protocol.RS232Config(baud=19200, polarity="NEGative"))
        self.assertEqual(protocol.read_trigger(scope, protocol.RS232Config), before)
        self.assertIn(":TRIGger:RS232:POLarity NEGative", scope.writes)
        self.assertIn(":TRIGger:RS232:BAUD 9600", scope.writes)

    def test_late_failure_restores_active_conditional_values_for_each_protocol(self):
        cases = (
            (protocol.RS232Config, protocol.RS232Config(when="DATA"), protocol.RS232Config(width=7, data=100), ":TRIGger:RS232:DATA"),
            (protocol.IICConfig, protocol.IICConfig(when="DATA"), protocol.IICConfig(data_bytes=2, data=300), ":TRIGger:IIC:DATA"),
            (protocol.SPIConfig, protocol.SPIConfig(), protocol.SPIConfig(mode="HIGH", cs_level_v=1), ":TRIGger:SPI:SLEVel"),
            (protocol.CANConfig, protocol.CANConfig(when="IDData"), protocol.CANConfig(data_width=2, data=300), ":TRIGger:CAN:DATA"),
            (protocol.LINConfig, protocol.LINConfig(when="ERRor"), protocol.LINConfig(sample_point=60, error="CHECk"), ":TRIGger:LIN:ERRor"),
        )
        for kind, seed, update, failing_path in cases:
            scope = FakeScope()
            protocol.configure_trigger(scope, seed)
            before = protocol.read_trigger(scope, kind)
            scope.fail_once = failing_path
            with self.assertRaises(RuntimeError):
                protocol.configure_trigger(scope, update)
            self.assertEqual(protocol.read_trigger(scope, kind), before, kind.__name__)


if __name__ == "__main__":
    unittest.main()
