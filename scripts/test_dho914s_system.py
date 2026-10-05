import unittest

from dho914s_system import (
    LanSettings, clear_status, configure_lan, configure_system, identity,
    operation_complete, read_lan, read_setup, read_status, recall_register,
    restore_setup, save_register, self_test, set_status_enable, status_registers,
    visa_address, reset, wait_complete, error_queue, _quiesce_outputs,
    exercise_aux_output,
)


class FakeInstrument:
    def __init__(self):
        self.timeout = 5000
        self.writes = []
        self.raw_writes = []
        self.values = {
            "*IDN?": "RIGOL TECHNOLOGIES,DHO914S,ABC123,00.01.03",
            ":SYSTem:AOUTput?": "TOUT", ":SYSTem:BEEPer?": "0",
            ":SYSTem:PON?": "DEF", ":SYSTem:PSTatus?": "OPEN",
            ":SYSTem:LOCKed?": "0", ":SYSTem:AUToscale?": "1",
            ":SYSTem:RAMount?": "4", ":SYSTem:MODules?": "1,0,0,0,0",
            ":SYSTem:GAMount?": "10", ":SYSTem:VERSion?": "3.0",
            ":SYSTem:DGSTatus?": "0", ":SYSTem:KEYBOARDCheck?": "true",
            ":LAN:DHCP?": "1", ":LAN:AUToip?": "0", ":LAN:MANual?": "0",
            ":LAN:IPADdress?": "192.168.1.10", ":LAN:SMASk?": "255.255.255.0",
            ":LAN:GATeway?": "192.168.1.1", ":LAN:DNS?": "8.8.8.8",
            ":LAN:MDNS?": "0", ":LAN:HOST:NAME?": "scope",
            ":LAN:DESCription?": "bench", ":LAN:MAC?": "00:19:AF:00:11:22",
            ":LAN:DSERver?": "192.168.1.1", ":LAN:STATus?": "CONNECTED",
            ":LAN:VISA?": "TCPIP::192.168.1.10::INSTR",
            ":LAN:VISA? LXI": "TCPIP::192.168.1.10::INSTR",
            ":LAN:VISA? USB": "USB0::0x1AB1::0x04CE::ABC123::INSTR",
            ":LAN:VISA? SOCKet": "TCPIP::192.168.1.10::4000::SOCKET",
            "*ESE?": "0", "*ESR?": "0", "*SRE?": "0", "*STB?": "0",
            "*OPC?": "1", "*TST?": "0", ":SYSTem:ERRor:NEXT?": '0,"No error"',
            ":SYSTem:ERRor?": '0,"No error"',
            ":SOURce:OUTPut:STATe?": "0",
            ":MASK:OPERate?": "STOP", ":MASK:OUTPut:ENABle?": "0",
            ":TRIGger:STATus?": "STOP",
        }
        self.payload = b"TEST"
        self.fail_command = None
        self.ignore_command = None
        self.failed_once = False
        self.pending_error = False
        self.fail_raw = False

    def write(self, command):
        self.writes.append(command)
        if command == self.ignore_command:
            return
        if command == ":STOP":
            self.values[":TRIGger:STATus?"] = "STOP"
        if command == ":RUN":
            self.values[":TRIGger:STATus?"] = "RUN"
        parts = command.split(" ", 1)
        if len(parts) == 2:
            key, value = parts
            if key in {":LAN:HOST:NAME", ":LAN:DESCription"}:
                value = value.strip('"')
            if key == ":SYSTem:AOUTput" and value == "PFAil":
                value = "PFA"
            self.values[key + "?"] = value
            if key == ":SOURce:OUTPut:STATe":
                self.values[key + "?"] = "1" if value == "ON" else "0"
            if key == ":MASK:OPERate":
                self.values[key + "?"] = value
            if key == ":MASK:OUTPut:ENABle":
                self.values[key + "?"] = "1" if value == "ON" else "0"
        if command == "*RCL":
            self.values[":SOURce:OUTPut:STATe?"] = "1"
        if command == "*RST":
            self.values[":SOURce:OUTPut:STATe?"] = "1"
        if command == ":SYSTem:RESet":
            self.values[":SOURce:OUTPut:STATe?"] = "1"
        if self.fail_command == command and not self.failed_once:
            self.failed_once = True
            self.pending_error = True

    def query(self, command):
        if command not in self.values:
            raise AssertionError(f"Unexpected query: {command}")
        return self.values[command]

    def query_binary_values(self, *args, **kwargs):
        return self.payload

    def write_raw(self, data):
        self.values[":SOURce:OUTPut:STATe?"] = "1"
        self.values[":MASK:OUTPut:ENABle?"] = "1"
        self.values[":MASK:OPERate?"] = "RUN"
        self.values[":TRIGger:STATus?"] = "RUN"
        if self.fail_raw:
            raise OSError("simulated transfer failure")
        self.raw_writes.append(data)


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.instrument = FakeInstrument()

    def write(self, command):
        self.instrument.write(command)

    def query(self, command):
        return self.instrument.query(command)

    def errors(self):
        if self.instrument.pending_error:
            self.instrument.pending_error = False
            return ['-200,"Execution error"', '0,"No error"']
        return ['0,"No error"']


class SystemApiTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()

    def test_identity_and_status_are_typed(self):
        self.assertEqual(identity(self.scope).firmware, "00.01.03")
        status = read_status(self.scope)
        self.assertEqual(status.analog_channels, 4)
        self.assertEqual(status.modules, (1, 0, 0, 0, 0))
        self.assertTrue(status.autoscale)

    def test_system_settings_verify_and_gate_aux(self):
        initial_commands = list(self.scope.instrument.writes)
        with self.assertRaises(PermissionError):
            configure_system(self.scope, aux_output="PFAil")
        with self.assertRaisesRegex(ValueError, "separately"):
            configure_system(self.scope, beeper=True, locked=True,
                             aux_output="PFAil", confirm_aux=True, aux_duration_s=0.001)
        self.assertEqual(self.scope.instrument.writes, initial_commands)
        state = configure_system(self.scope, beeper=True, locked=True)
        self.assertTrue(state.beeper)
        self.assertEqual(state.aux_output, "TOUT")
        self.assertNotIn(":SYSTem:AOUTput PFAil", self.scope.instrument.writes)
        self.assertIn(":SYSTem:LOCKed ON", self.scope.instrument.writes)

    def test_safe_system_preferences_and_error_queue_forms(self):
        state = configure_system(self.scope, beeper=True, power_on="LATEST",
                                 power_status="DEFAULT", locked=True, autoscale=False)
        self.assertEqual((state.power_on, state.power_status, state.autoscale),
                         ("LAT", "DEF", False))
        for command in (":SYSTem:BEEPer ON", ":SYSTem:PON LAT",
                        ":SYSTem:PSTatus DEF", ":SYSTem:LOCKed ON",
                        ":SYSTem:AUToscale OFF"):
            self.assertIn(command, self.scope.instrument.writes)
        self.assertEqual(error_queue(self.scope), ())
        self.assertEqual(error_queue(self.scope, short_form=True), ())
        wait_complete(self.scope)
        self.assertIn("*WAI", self.scope.instrument.writes)

    def test_status_register_commands_and_mask_validation(self):
        state = set_status_enable(self.scope, event_mask=4, service_mask=16)
        self.assertEqual(state["ese"], 4)
        self.assertEqual(state["sre"], 16)
        self.assertTrue(operation_complete(self.scope))
        operation_complete(self.scope, query=False)
        self.assertIn("*OPC", self.scope.instrument.writes)
        with self.assertRaises(ValueError):
            set_status_enable(self.scope, event_mask=256)
        self.assertEqual(status_registers(self.scope)["esr"], 0)

    def test_lan_read_and_safe_config_apply(self):
        settings, details = read_lan(self.scope)
        self.assertTrue(settings.dhcp)
        self.assertEqual(details["mac"], "00:19:AF:00:11:22")
        self.assertEqual(visa_address(self.scope, "socket"), "TCPIP::192.168.1.10::4000::SOCKET")
        with self.assertRaises(ValueError):
            visa_address(self.scope, "ethernet")
        with self.assertRaises(PermissionError):
            configure_lan(self.scope, LanSettings(False, False, True, "192.168.1.30", "255.255.255.0", "192.168.1.1", "8.8.8.8"))
        configure_lan(self.scope, LanSettings(False, False, True, "192.168.1.30", "255.255.255.0", "192.168.1.1", "8.8.8.8"), confirm=True)
        self.assertIn(":LAN:MANual ON", self.scope.instrument.writes)
        self.assertIn(":LAN:DHCP OFF", self.scope.instrument.writes)
        self.assertEqual(self.scope.instrument.writes[-1], ":LAN:APPLy")

    def test_lan_rejects_invalid_values_before_io(self):
        with self.assertRaises(ValueError):
            configure_lan(self.scope, LanSettings(False, False, True, "127.0.0.1"), confirm=True)
        with self.assertRaises(ValueError):
            configure_lan(self.scope, LanSettings(False, False, False), confirm=True)
        with self.assertRaises(ValueError):
            configure_lan(self.scope, LanSettings(True, False, True, "192.168.1.30"), confirm=True)
        self.assertEqual(self.scope.instrument.writes, [])

    def test_lan_readback_mismatch_restores_prior_settings(self):
        instrument = self.scope.instrument
        original_query = instrument.query
        def stale_address(command):
            if command == ":LAN:IPADdress?" and ":LAN:APPLy" in instrument.writes:
                return "192.168.1.99"
            return original_query(command)
        instrument.query = stale_address
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            configure_lan(self.scope, LanSettings(False, False, True,
                          "192.168.1.30", "255.255.255.0", "192.168.1.1", "8.8.8.8"),
                          confirm=True)
        self.assertEqual(instrument.writes.count(":LAN:APPLy"), 2)
        self.assertIn(":LAN:IPADdress 192.168.1.10", instrument.writes)

    def test_lan_rejects_truthy_non_boolean_at_construction(self):
        with self.assertRaises(TypeError):
            LanSettings(1, False, True)
        with self.assertRaises(TypeError):
            LanSettings(False, False, True, mdns=1)

    def test_lan_optional_settings_and_visa_variants(self):
        configure_lan(self.scope, LanSettings(False, True, False, mdns=True,
                      host_name="scope-2", description="lab bench"), confirm=True)
        for command in (":LAN:AUToip ON", ":LAN:MDNS ON",
                        ':LAN:HOST:NAME "scope-2"', ':LAN:DESCription "lab bench"',
                        ":LAN:APPLy"):
            self.assertIn(command, self.scope.instrument.writes)
        for kind in (None, "LXI", "USB", "SOCKET"):
            self.assertTrue(visa_address(self.scope, kind))

    def test_lan_partial_failure_attempts_full_rollback(self):
        self.scope.instrument.fail_command = ":LAN:IPADdress 192.168.1.30"
        with self.assertRaisesRegex(RuntimeError, "Rigol rejected"):
            configure_lan(
                self.scope,
                LanSettings(False, False, True, "192.168.1.30", "255.255.255.0", "192.168.1.1", "8.8.8.8"),
                confirm=True,
            )
        self.assertEqual(self.scope.instrument.values[":LAN:IPADdress?"], "192.168.1.10")
        self.assertEqual(self.scope.instrument.values[":LAN:DHCP?"], "ON")
        self.assertIn(":LAN:APPLy", self.scope.instrument.writes)

    def test_setup_read_and_confirmed_bounded_restore(self):
        blob = read_setup(self.scope)
        self.assertEqual(blob, b"#14TEST")
        with self.assertRaises(PermissionError):
            restore_setup(self.scope, blob, confirm_no_dut=False)
        restore_setup(self.scope, blob, confirm_no_dut=True)
        self.assertEqual(self.scope.instrument.raw_writes, [b":SYSTem:SETup #14TEST"])
        self.assertEqual(self.scope.instrument.values[":SOURce:OUTPut:STATe?"], "0")
        self.assertEqual(self.scope.instrument.values[":MASK:OUTPut:ENABle?"], "0")
        self.assertEqual(self.scope.instrument.values[":MASK:OPERate?"], "STOP")
        self.assertEqual(self.scope.instrument.values[":TRIGger:STATus?"], "STOP")
        with self.assertRaises(ValueError):
            restore_setup(self.scope, b"#15TEST", confirm_no_dut=True)

    def test_setup_restore_requires_finite_timeout_and_shuts_down_on_failure(self):
        self.scope.instrument.timeout = 0
        with self.assertRaises(ValueError):
            restore_setup(self.scope, b"#14TEST", confirm_no_dut=True)
        self.assertEqual(self.scope.instrument.raw_writes, [])
        self.scope.instrument.timeout = 5000
        self.scope.instrument.fail_raw = True
        with self.assertRaises(OSError):
            restore_setup(self.scope, b"#14TEST", confirm_no_dut=True)
        self.assertEqual(self.scope.instrument.values[":SOURce:OUTPut:STATe?"], "0")
        self.assertEqual(self.scope.instrument.values[":MASK:OUTPut:ENABle?"], "0")
        self.scope.instrument.fail_raw = False
        oversized = b"#71000000" + b"X" * 1_000_000
        with self.assertRaises(ValueError):
            restore_setup(self.scope, oversized, confirm_no_dut=True)

    def test_destructive_common_commands_require_confirmation(self):
        for action in (lambda: recall_register(self.scope), lambda: clear_status(self.scope)):
            with self.assertRaises(PermissionError):
                action()
        save_register(self.scope, 3)
        with self.assertRaises(PermissionError):
            recall_register(self.scope, confirm_no_dut=False)
        recall_register(self.scope, confirm_no_dut=True)
        clear_status(self.scope, confirm=True)
        self.assertIn("*SAV 3", self.scope.instrument.writes)
        self.assertIn("*RCL", self.scope.instrument.writes)
        self.assertIn("*CLS", self.scope.instrument.writes)

    def test_factory_reset_is_confirmed_and_quiesced(self):
        with self.assertRaises(PermissionError):
            reset(self.scope)
        with self.assertRaises(PermissionError):
            reset(self.scope, system=True)
        reset(self.scope, confirm_no_dut=True)
        self.assertIn("*RST", self.scope.instrument.writes)
        self.assertEqual(self.scope.instrument.values[":SOURce:OUTPut:STATe?"], "0")
        self.assertEqual(self.scope.instrument.values[":TRIGger:STATus?"], "STOP")
        reset(self.scope, confirm_no_dut=True, system=True)
        self.assertIn(":SYSTem:RESet", self.scope.instrument.writes)
        self.assertEqual(self.scope.instrument.values[":SOURce:OUTPut:STATe?"], "0")

    def test_recall_and_reset_failures_still_quiesce_outputs(self):
        for command, action in (
            ("*RCL", lambda scope: recall_register(scope, confirm_no_dut=True)),
            ("*RST", lambda scope: reset(scope, confirm_no_dut=True)),
            (":SYSTem:RESet", lambda scope: reset(scope, confirm_no_dut=True, system=True)),
        ):
            scope = FakeScope()
            scope.instrument.fail_command = command
            scope.instrument.values[":TRIGger:STATus?"] = "RUN"
            with self.assertRaises(RuntimeError):
                action(scope)
            self.assertEqual(scope.instrument.values[":SOURce:OUTPut:STATe?"], "0")
            self.assertEqual(scope.instrument.values[":TRIGger:STATus?"], "STOP")

    def test_quiesce_rejects_ignored_shutdown_writes(self):
        active_state = {
            ":TRIGger:STATus?": "RUN",
            ":MASK:OPERate?": "RUN",
            ":MASK:OUTPut:ENABle?": "1",
        }
        for command, response in (
            (":STOP", ":TRIGger:STATus?"),
            (":MASK:OPERate STOP", ":MASK:OPERate?"),
            (":MASK:OUTPut:ENABle OFF", ":MASK:OUTPut:ENABle?"),
        ):
            scope = FakeScope()
            scope.instrument.values.update(active_state)
            scope.instrument.ignore_command = command
            with self.subTest(command=command), self.assertRaisesRegex(
                    RuntimeError, "could not verify output quiescence"):
                _quiesce_outputs(scope)
            self.assertEqual(scope.instrument.values[response],
                             active_state[response])
            self.assertIn(":SOURce:OUTPut:STATe OFF", scope.instrument.writes)

    def test_aux_mode_is_bounded_and_restored(self):
        before = list(self.scope.instrument.writes)
        with self.assertRaises(ValueError):
            configure_system(self.scope, aux_output="TOUT", confirm_aux=True)
        self.assertEqual(self.scope.instrument.writes, before)
        self.assertEqual(exercise_aux_output(self.scope, "PFAil", duration_s=0.001,
                                             confirm_no_dut=True), "PFA")
        self.assertEqual(self.scope.instrument.values[":SYSTem:AOUTput?"], "TOUT")
        self.assertIn(":SYSTem:AOUTput PFAil", self.scope.instrument.writes)
        self.assertIn(":MASK:OPERate RUN", self.scope.instrument.writes)
        writes = self.scope.instrument.writes
        restore = writes.index(":SYSTem:AOUTput TOUT")
        self.assertIn(":MASK:OPERate STOP", writes[writes.index(":MASK:OPERate RUN"):restore])
        self.assertEqual(self.scope.instrument.values[":MASK:OPERate?"], "STOP")
        self.assertEqual(self.scope.instrument.values[":MASK:OUTPut:ENABle?"], "0")
        self.assertEqual(configure_system(self.scope, aux_output="PFAil",
                                          confirm_aux=True, aux_duration_s=0.001).aux_output,
                         "TOUT")
        self.assertEqual(exercise_aux_output(self.scope, "TOUT", duration_s=0.001,
                                             confirm_no_dut=True), "TOUT")
        self.assertIn(":RUN", self.scope.instrument.writes)
        self.assertEqual(self.scope.instrument.values[":TRIGger:STATus?"], "STOP")
        with self.assertRaises(ValueError):
            exercise_aux_output(self.scope, "PFAil", duration_s=6,
                                confirm_no_dut=True)
        scope = FakeScope()
        scope.instrument.ignore_command = ":SYSTem:AOUTput PFAil"
        with self.assertRaisesRegex(RuntimeError, "read back"):
            exercise_aux_output(scope, "PFAil", duration_s=0.001,
                                confirm_no_dut=True)
        self.assertEqual(scope.instrument.values[":SYSTem:AOUTput?"], "TOUT")
        self.assertEqual(scope.instrument.values[":TRIGger:STATus?"], "STOP")
        scope = FakeScope()
        scope.instrument.fail_command = ":MASK:OPERate RUN"
        with self.assertRaises(RuntimeError):
            exercise_aux_output(scope, "PFAil", duration_s=0.001,
                                confirm_no_dut=True)
        self.assertEqual(scope.instrument.values[":SYSTem:AOUTput?"], "TOUT")
        self.assertEqual(scope.instrument.values[":MASK:OPERate?"], "STOP")
        self.assertEqual(scope.instrument.values[":MASK:OUTPut:ENABle?"], "0")

    def test_self_test(self):
        self.assertEqual(self_test(self.scope), (True, ()))


if __name__ == "__main__":
    unittest.main()
