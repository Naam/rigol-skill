import unittest

from dho800900_models import MODELS

from dho914s_trigger_analog import (
    Delay,
    Duration,
    Edge,
    NthEdge,
    Pattern,
    Pulse,
    Runt,
    SetupHold,
    Slope,
    Timeout,
    TriggerState,
    Video,
    Windows,
    _validate,
    configure_trigger,
    read_trigger,
    restore_trigger,
)


class FakeRigol:
    profile = MODELS["DHO914S"]
    def __init__(self, mode="EDGE"):
        self.mode = mode
        self.writes = []
        self.queries = []
        self.fail_on = None
        self.pending_errors = []
        self.parameter_levels = {}
        self.values = {
            ":TRIGger:MODE?": mode,
            ":TRIGger:SWEep?": "AUTO",
            ":TRIGger:HOLDoff?": "1.000000E-6",
            ":TRIGger:NREJect?": "0",
            ":TRIGger:STATus?": "STOP",
            ":TRIGger:POSition?": "0",
            ":TRIGger:EDGE:SOURce?": "CHAN1",
            ":TRIGger:EDGE:SLOPe?": "POS",
            ":TRIGger:EDGE:LEVel?": "0.0",
            ":TRIGger:COUPling?": "DC",
            ":TRIGger:SLOPe:SOURce?": "CHAN1",
            ":TRIGger:SLOPe:POLarity?": "POS",
            ":TRIGger:SLOPe:WHEN?": "GRE",
            ":TRIGger:SLOPe:TLOWer?": "1e-6",
            ":TRIGger:SLOPe:TUPPer?": "2e-6",
            ":TRIGger:SLOPe:WINDow?": "TA",
            ":TRIGger:SLOPe:ALEVel?": "0.5",
            ":TRIGger:SLOPe:BLEVel?": "-0.5",
            ":TRIGger:VIDeo:SOURce?": "CHAN1",
            ":TRIGger:VIDeo:POLarity?": "POS",
            ":TRIGger:VIDeo:MODE?": "ALIN",
            ":TRIGger:VIDeo:LINE?": "1",
            ":TRIGger:VIDeo:STANdard?": "NTSC",
            ":TRIGger:VIDeo:LEVel?": "0",
            ":TRIGger:PULSe:SOURce?": "CHAN2",
            ":TRIGger:PULSe:POLarity?": "NEG",
            ":TRIGger:PULSe:WHEN?": "LESS",
            ":TRIGger:PULSe:UWIDth?": "2e-6",
            ":TRIGger:PULSe:LEVel?": "0.1",
            ":CHANnel1:SCALe?": "1",
            ":CHANnel1:OFFSet?": "0",
            ":CHANnel2:SCALe?": "0.1",
            ":CHANnel2:OFFSet?": "0",
            ":CHANnel3:SCALe?": "1",
            ":CHANnel3:OFFSet?": "0",
            ":CHANnel4:SCALe?": "1",
            ":CHANnel4:OFFSet?": "0",
        }

    def afg_off(self):
        self.write(":SOURce:OUTPut:STATe OFF")

    def write(self, command):
        self.writes.append(command)
        if self.fail_on and command.startswith(self.fail_on):
            self.pending_errors.append("-222,Data out of range")
            self.fail_on = None
            return
        if command.startswith(":TRIGger:MODE "):
            mode = command.rsplit(" ", 1)[1]
            self.values[":TRIGger:MODE?"] = {
                "PULSe": "PULS", "SLOPe": "SLOP", "VIDeo": "VID", "PATTern": "PATT",
                "DURation": "DUR", "TIMeout": "TIM", "WINDows": "WIND", "DELay": "DEL",
                "SHOLd": "SET", "NEDGe": "NEDG",
            }.get(mode, mode)
        if command.startswith((":TRIGger:PATTern:LEVel ", ":TRIGger:DURation:LEVel ")):
            prefix, arguments = command.split(" ", 1)
            source, value = arguments.split(",", 1)
            normalized = {"CHANnel1": "CHAN1", "CHANnel2": "CHAN2", "CHANnel3": "CHAN3", "CHANnel4": "CHAN4"}.get(source, source)
            self.parameter_levels[(prefix + "?", normalized)] = value
        for prefix, query in {
            ":TRIGger:SWEep ": ":TRIGger:SWEep?",
            ":TRIGger:HOLDoff ": ":TRIGger:HOLDoff?",
            ":TRIGger:NREJect ": ":TRIGger:NREJect?",
            ":TRIGger:EDGE:SOURce ": ":TRIGger:EDGE:SOURce?",
            ":TRIGger:EDGE:SLOPe ": ":TRIGger:EDGE:SLOPe?",
            ":TRIGger:EDGE:LEVel ": ":TRIGger:EDGE:LEVel?",
            ":TRIGger:COUPling ": ":TRIGger:COUPling?",
            ":TRIGger:PULSe:SOURce ": ":TRIGger:PULSe:SOURce?",
            ":TRIGger:PULSe:POLarity ": ":TRIGger:PULSe:POLarity?",
            ":TRIGger:PULSe:WHEN ": ":TRIGger:PULSe:WHEN?",
            ":TRIGger:PULSe:LWIDth ": ":TRIGger:PULSe:LWIDth?",
            ":TRIGger:PULSe:UWIDth ": ":TRIGger:PULSe:UWIDth?",
            ":TRIGger:PULSe:LEVel ": ":TRIGger:PULSe:LEVel?",
            ":TRIGger:SLOPe:SOURce ": ":TRIGger:SLOPe:SOURce?",
            ":TRIGger:SLOPe:POLarity ": ":TRIGger:SLOPe:POLarity?",
            ":TRIGger:SLOPe:WHEN ": ":TRIGger:SLOPe:WHEN?",
            ":TRIGger:SLOPe:TLOWer ": ":TRIGger:SLOPe:TLOWer?",
            ":TRIGger:SLOPe:TUPPer ": ":TRIGger:SLOPe:TUPPer?",
            ":TRIGger:SLOPe:WINDow ": ":TRIGger:SLOPe:WINDow?",
            ":TRIGger:SLOPe:ALEVel ": ":TRIGger:SLOPe:ALEVel?",
            ":TRIGger:SLOPe:BLEVel ": ":TRIGger:SLOPe:BLEVel?",
            ":TRIGger:VIDeo:SOURce ": ":TRIGger:VIDeo:SOURce?",
            ":TRIGger:VIDeo:POLarity ": ":TRIGger:VIDeo:POLarity?",
            ":TRIGger:VIDeo:MODE ": ":TRIGger:VIDeo:MODE?",
            ":TRIGger:VIDeo:LINE ": ":TRIGger:VIDeo:LINE?",
            ":TRIGger:VIDeo:STANdard ": ":TRIGger:VIDeo:STANdard?",
            ":TRIGger:VIDeo:LEVel ": ":TRIGger:VIDeo:LEVel?",
            ":TRIGger:PATTern:PATTern ": ":TRIGger:PATTern:PATTern?",
            ":TRIGger:PATTern:SOURce ": ":TRIGger:PATTern:SOURce?",
            ":TRIGger:DURation:SOURce ": ":TRIGger:DURation:SOURce?",
            ":TRIGger:DURation:TYPE ": ":TRIGger:DURation:TYPE?",
            ":TRIGger:DURation:WHEN ": ":TRIGger:DURation:WHEN?",
            ":TRIGger:DURation:TLOWer ": ":TRIGger:DURation:TLOWer?",
            ":TRIGger:DURation:TUPPer ": ":TRIGger:DURation:TUPPer?",
            ":TRIGger:TIMeout:SOURce ": ":TRIGger:TIMeout:SOURce?",
            ":TRIGger:TIMeout:SLOPe ": ":TRIGger:TIMeout:SLOPe?",
            ":TRIGger:TIMeout:TIME ": ":TRIGger:TIMeout:TIME?",
            ":TRIGger:TIMeout:LEVel ": ":TRIGger:TIMeout:LEVel?",
            ":TRIGger:RUNT:SOURce ": ":TRIGger:RUNT:SOURce?",
            ":TRIGger:RUNT:POLarity ": ":TRIGger:RUNT:POLarity?",
            ":TRIGger:RUNT:WHEN ": ":TRIGger:RUNT:WHEN?",
            ":TRIGger:RUNT:WLOWer ": ":TRIGger:RUNT:WLOWer?",
            ":TRIGger:RUNT:WUPPer ": ":TRIGger:RUNT:WUPPer?",
            ":TRIGger:RUNT:BLEVel ": ":TRIGger:RUNT:BLEVel?",
            ":TRIGger:RUNT:ALEVel ": ":TRIGger:RUNT:ALEVel?",
            ":TRIGger:WINDows:SOURce ": ":TRIGger:WINDows:SOURce?",
            ":TRIGger:WINDows:SLOPe ": ":TRIGger:WINDows:SLOPe?",
            ":TRIGger:WINDows:POSition ": ":TRIGger:WINDows:POSition?",
            ":TRIGger:WINDows:TIME ": ":TRIGger:WINDows:TIME?",
            ":TRIGger:WINDows:BLEVel ": ":TRIGger:WINDows:BLEVel?",
            ":TRIGger:WINDows:ALEVel ": ":TRIGger:WINDows:ALEVel?",
            ":TRIGger:DELay:SA ": ":TRIGger:DELay:SA?",
            ":TRIGger:DELay:ASLop ": ":TRIGger:DELay:ASLop?",
            ":TRIGger:DELay:SB ": ":TRIGger:DELay:SB?",
            ":TRIGger:DELay:BSLop ": ":TRIGger:DELay:BSLop?",
            ":TRIGger:DELay:TYPE ": ":TRIGger:DELay:TYPE?",
            ":TRIGger:DELay:TLOWer ": ":TRIGger:DELay:TLOWer?",
            ":TRIGger:DELay:TUPPer ": ":TRIGger:DELay:TUPPer?",
            ":TRIGger:DELay:ALEVel ": ":TRIGger:DELay:ALEVel?",
            ":TRIGger:DELay:BLEVel ": ":TRIGger:DELay:BLEVel?",
            ":TRIGger:SHOLd:DSRC ": ":TRIGger:SHOLd:DSRC?",
            ":TRIGger:SHOLd:CSRC ": ":TRIGger:SHOLd:CSRC?",
            ":TRIGger:SHOLd:SLOPe ": ":TRIGger:SHOLd:SLOPe?",
            ":TRIGger:SHOLd:PATTern ": ":TRIGger:SHOLd:PATTern?",
            ":TRIGger:SHOLd:TYPE ": ":TRIGger:SHOLd:TYPE?",
            ":TRIGger:SHOLd:STIMe ": ":TRIGger:SHOLd:STIMe?",
            ":TRIGger:SHOLd:HTIMe ": ":TRIGger:SHOLd:HTIMe?",
            ":TRIGger:SHOLd:DLEVel ": ":TRIGger:SHOLd:DLEVel?",
            ":TRIGger:SHOLd:CLEVel ": ":TRIGger:SHOLd:CLEVel?",
            ":TRIGger:NEDGe:SOURce ": ":TRIGger:NEDGe:SOURce?",
            ":TRIGger:NEDGe:SLOPe ": ":TRIGger:NEDGe:SLOPe?",
            ":TRIGger:NEDGe:IDLE ": ":TRIGger:NEDGe:IDLE?",
            ":TRIGger:NEDGe:EDGE ": ":TRIGger:NEDGe:EDGE?",
            ":TRIGger:NEDGe:LEVel ": ":TRIGger:NEDGe:LEVel?",
        }.items():
            if command.startswith(prefix):
                value = command[len(prefix):]
                self.values[query] = {f"CHANnel{i}": f"CHAN{i}" for i in range(1, 5)}.get(value, value)

    def query(self, command):
        self.queries.append(command)
        if command.startswith(":TRIGger:PATTern:LEVel? ") or command.startswith(":TRIGger:DURation:LEVel? "):
            prefix, source = command.split("? ", 1)
            normalized = {"CHANnel1": "CHAN1", "CHANnel2": "CHAN2", "CHANnel3": "CHAN3", "CHANnel4": "CHAN4"}.get(source, source)
            return self.parameter_levels.get((prefix + "?", normalized), "0")
        values = {
            **self.values,
            ":SOURce:OUTPut:STATe?": "0",
        }
        return values[command]

    def errors(self):
        result = [*self.pending_errors, "0,No error"]
        self.pending_errors.clear()
        return result


class AnalogTriggerTests(unittest.TestCase):
    def test_two_channel_profile_rejects_missing_sources_before_writes(self):
        scope = FakeRigol()
        scope.profile = MODELS["DHO812"]
        for source in ("CHAN3", "D0"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                _validate(scope, Edge(source=source))
        self.assertEqual(scope.writes, [])

    def test_rejects_edge_level_outside_selected_channel_range(self):
        scope = FakeRigol()
        with self.assertRaisesRegex(ValueError, "edge level"):
            _validate(scope, Edge(source="CHAN2", level_v=0.6))
        self.assertEqual(scope.writes, [])

    def test_edge_digital_source_uses_digital_level_range_without_analog_only_queries(self):
        scope = FakeRigol()
        scope.values[":TRIGger:EDGE:SOURce?"] = "D12"
        state = read_trigger(scope)
        self.assertEqual(state.config.source, "D12")
        self.assertIsNone(state.config.coupling)
        self.assertIsNone(state.noise_reject)
        self.assertNotIn(":TRIGger:COUPling?", scope.queries)
        self.assertNotIn(":TRIGger:NREJect?", scope.queries)

    def test_rejects_malformed_noise_reject_readback(self):
        scope = FakeRigol()
        scope.values[":TRIGger:NREJect?"] = "MAYBE"
        with self.assertRaisesRegex(RuntimeError, "invalid boolean"):
            read_trigger(scope)

    def test_checks_scpi_error_queue_after_readback(self):
        scope = FakeRigol()
        scope.pending_errors.append("-113,Undefined header")
        with self.assertRaisesRegex(RuntimeError, "rejected a command"):
            read_trigger(scope)

    def test_restore_requires_holdoff_for_non_video_modes_before_writing(self):
        scope = FakeRigol()
        state = TriggerState(Edge(), "AUTO", None, False, "STOP", 0.0)
        with self.assertRaisesRegex(ValueError, "holdoff is required"):
            restore_trigger(scope, state)
        self.assertEqual(scope.writes, [])

    def test_restores_complete_edge_snapshot_and_reads_back(self):
        scope = FakeRigol()
        state = TriggerState(Edge(source="CHAN1", slope="NEG", level_v=0.25), "NORM", 2e-6, True, "STOP", 0.0)
        restored = restore_trigger(scope, state)
        self.assertEqual(restored.config, state.config)
        self.assertIn(":TRIGger:EDGE:SLOPe NEG", scope.writes)
        self.assertIn(":TRIGger:EDGE:LEVel 0.25", scope.writes)
        self.assertEqual(scope.writes[0], ":SOURce:OUTPut:STATe OFF")

    def test_configure_trigger_returns_instrument_readback(self):
        scope = FakeRigol()
        state = configure_trigger(scope, Edge(slope="NEG", level_v=0.25), sweep="NORM")
        self.assertEqual(state.config, Edge(slope="NEG", level_v=0.25))
        self.assertEqual(state.sweep, "NORM")

    def test_queries_only_width_forms_valid_for_pulse_condition(self):
        scope = FakeRigol(mode="PULS")
        state = read_trigger(scope)
        self.assertIsInstance(state.config, Pulse)
        self.assertIsNone(state.config.lower_width_s)
        self.assertEqual(state.config.upper_width_s, 2e-6)
        self.assertNotIn(":TRIGger:PULSe:LWIDth?", scope.queries)

    def test_pulse_digital_source_uses_plus_minus_20_volt_limits(self):
        scope = FakeRigol(mode="PULS")
        scope.values[":TRIGger:PULSe:SOURce?"] = "D15"
        scope.values[":TRIGger:PULSe:LEVel?"] = "20"
        state = read_trigger(scope)
        self.assertEqual(state.config.source, "D15")
        self.assertIsNone(state.noise_reject)
        scope.values[":TRIGger:PULSe:LEVel?"] = "20.1"
        with self.assertRaisesRegex(ValueError, "pulse level"):
            read_trigger(scope)

    def test_slope_configuration_round_trips(self):
        scope = FakeRigol()
        config = Slope(when="GLES", lower_time_s=1e-6, upper_time_s=3e-6,
                       window="TAB", upper_level_v=0.4, lower_level_v=-0.3)
        state = configure_trigger(scope, config)
        self.assertEqual(state.config, config)
        self.assertEqual(state.mode, "SLOPE")

    def test_video_configuration_round_trips_without_holdoff(self):
        scope = FakeRigol()
        config = Video(source="CHAN3", polarity="NEG", sync="LINE", line=100,
                       standard="720P60", level_v=0.1)
        state = configure_trigger(scope, config)
        self.assertEqual(state.config, config)
        self.assertIsNone(state.holdoff_s)
        self.assertNotIn(":TRIGger:HOLDoff ", scope.writes)

    def test_remaining_nonprotocol_mode_command_matrix(self):
        cases = (
            (Edge("CHAN1", "RFAL", 0.1, "LFREJECT"), (
                (":TRIGger:EDGE:SOURce ", ":TRIGger:EDGE:SOURce?"),
                (":TRIGger:EDGE:SLOPe ", ":TRIGger:EDGE:SLOPe?"),
                (":TRIGger:EDGE:LEVel ", ":TRIGger:EDGE:LEVel?"),
                (":TRIGger:COUPling ", ":TRIGger:COUPling?"))),
            (Pulse("CHAN2", "NEG", "GLES", 1e-6, 2e-6, 0.1), (
                (":TRIGger:PULSe:SOURce ", ":TRIGger:PULSe:SOURce?"),
                (":TRIGger:PULSe:POLarity ", ":TRIGger:PULSe:POLarity?"),
                (":TRIGger:PULSe:WHEN ", ":TRIGger:PULSe:WHEN?"),
                (":TRIGger:PULSe:LWIDth ", ":TRIGger:PULSe:LWIDth?"),
                (":TRIGger:PULSe:UWIDth ", ":TRIGger:PULSe:UWIDth?"),
                (":TRIGger:PULSe:LEVel ", ":TRIGger:PULSe:LEVel?"))),
            (Slope("CHAN3", "NEG", "GLES", 1e-6, 2e-6, "TAB", 0.2, -0.2), (
                (":TRIGger:SLOPe:SOURce ", ":TRIGger:SLOPe:SOURce?"),
                (":TRIGger:SLOPe:POLarity ", ":TRIGger:SLOPe:POLarity?"),
                (":TRIGger:SLOPe:WHEN ", ":TRIGger:SLOPe:WHEN?"),
                (":TRIGger:SLOPe:TUPPer ", ":TRIGger:SLOPe:TUPPer?"),
                (":TRIGger:SLOPe:TLOWer ", ":TRIGger:SLOPe:TLOWer?"),
                (":TRIGger:SLOPe:WINDow ", ":TRIGger:SLOPe:WINDow?"),
                (":TRIGger:SLOPe:ALEVel ", ":TRIGger:SLOPe:ALEVel?"),
                (":TRIGger:SLOPe:BLEVel ", ":TRIGger:SLOPe:BLEVel?"))),
            (Video("CHAN4", "NEG", "LINE", 100, "PALSecam", 0.1), (
                (":TRIGger:VIDeo:SOURce ", ":TRIGger:VIDeo:SOURce?"),
                (":TRIGger:VIDeo:POLarity ", ":TRIGger:VIDeo:POLarity?"),
                (":TRIGger:VIDeo:MODE ", ":TRIGger:VIDeo:MODE?"),
                (":TRIGger:VIDeo:LINE ", ":TRIGger:VIDeo:LINE?"),
                (":TRIGger:VIDeo:STANdard ", ":TRIGger:VIDeo:STANdard?"),
                (":TRIGger:VIDeo:LEVel ", ":TRIGger:VIDeo:LEVel?"))),
            (Pattern(("H", "R", "L", "X"), "D2", (("CHAN1", 0.2),)), (
                (":TRIGger:PATTern:PATTern ", ":TRIGger:PATTern:PATTern?"),
                (":TRIGger:PATTern:SOURce ", ":TRIGger:PATTern:SOURce?"),
                (":TRIGger:PATTern:LEVel ", ":TRIGger:PATTern:LEVel? "))),
            (Duration("D3", ("H", "L", "X", "H"), "UNGL", 1e-6, 3e-6, (("CHAN1", 0.2),)), (
                (":TRIGger:DURation:SOURce ", ":TRIGger:DURation:SOURce?"),
                (":TRIGger:DURation:TYPE ", ":TRIGger:DURation:TYPE?"),
                (":TRIGger:DURation:WHEN ", ":TRIGger:DURation:WHEN?"),
                (":TRIGger:DURation:TUPPer ", ":TRIGger:DURation:TUPPer?"),
                (":TRIGger:DURation:TLOWer ", ":TRIGger:DURation:TLOWer?"),
                (":TRIGger:DURation:LEVel ", ":TRIGger:DURation:LEVel? "))),
            (Timeout("D4", "RFAL", 3e-6, -12), (
                (":TRIGger:TIMeout:SOURce ", ":TRIGger:TIMeout:SOURce?"),
                (":TRIGger:TIMeout:SLOPe ", ":TRIGger:TIMeout:SLOPe?"),
                (":TRIGger:TIMeout:TIME ", ":TRIGger:TIMeout:TIME?"),
                (":TRIGger:TIMeout:LEVel ", ":TRIGger:TIMeout:LEVel?"))),
            (Runt("CHAN4", "NEG", "GLES", 1e-6, 2e-6, -0.1, 0.2), (
                (":TRIGger:RUNT:SOURce ", ":TRIGger:RUNT:SOURce?"),
                (":TRIGger:RUNT:POLarity ", ":TRIGger:RUNT:POLarity?"),
                (":TRIGger:RUNT:WHEN ", ":TRIGger:RUNT:WHEN?"),
                (":TRIGger:RUNT:WUPPer ", ":TRIGger:RUNT:WUPPer?"),
                (":TRIGger:RUNT:WLOWer ", ":TRIGger:RUNT:WLOWer?"),
                (":TRIGger:RUNT:ALEVel ", ":TRIGger:RUNT:ALEVel?"),
                (":TRIGger:RUNT:BLEVel ", ":TRIGger:RUNT:BLEVel?"))),
            (Windows("CHAN2", "RFAL", "TIME", 4e-6, -0.2, 0.3), (
                (":TRIGger:WINDows:SOURce ", ":TRIGger:WINDows:SOURce?"),
                (":TRIGger:WINDows:SLOPe ", ":TRIGger:WINDows:SLOPe?"),
                (":TRIGger:WINDows:POSition ", ":TRIGger:WINDows:POSition?"),
                (":TRIGger:WINDows:TIME ", ":TRIGger:WINDows:TIME?"),
                (":TRIGger:WINDows:ALEVel ", ":TRIGger:WINDows:ALEVel?"),
                (":TRIGger:WINDows:BLEVel ", ":TRIGger:WINDows:BLEVel?"))),
            (Delay("D1", "NEG", "CHAN4", "POS", "GOUT", 1e-6, 2e-6, -10, 0.1), (
                (":TRIGger:DELay:SA ", ":TRIGger:DELay:SA?"),
                (":TRIGger:DELay:ASLop ", ":TRIGger:DELay:ASLop?"),
                (":TRIGger:DELay:SB ", ":TRIGger:DELay:SB?"),
                (":TRIGger:DELay:BSLop ", ":TRIGger:DELay:BSLop?"),
                (":TRIGger:DELay:TYPE ", ":TRIGger:DELay:TYPE?"),
                (":TRIGger:DELay:TUPPer ", ":TRIGger:DELay:TUPPer?"),
                (":TRIGger:DELay:TLOWer ", ":TRIGger:DELay:TLOWer?"),
                (":TRIGger:DELay:ALEVel ", ":TRIGger:DELay:ALEVel?"),
                (":TRIGger:DELay:BLEVel ", ":TRIGger:DELay:BLEVel?"))),
            (SetupHold("D1", "CHAN2", "NEG", "L", "SETH", 2e-6, 3e-6, -5, 0.1), (
                (":TRIGger:SHOLd:DSRC ", ":TRIGger:SHOLd:DSRC?"),
                (":TRIGger:SHOLd:CSRC ", ":TRIGger:SHOLd:CSRC?"),
                (":TRIGger:SHOLd:SLOPe ", ":TRIGger:SHOLd:SLOPe?"),
                (":TRIGger:SHOLd:PATTern ", ":TRIGger:SHOLd:PATTern?"),
                (":TRIGger:SHOLd:TYPE ", ":TRIGger:SHOLd:TYPE?"),
                (":TRIGger:SHOLd:STIMe ", ":TRIGger:SHOLd:STIMe?"),
                (":TRIGger:SHOLd:HTIMe ", ":TRIGger:SHOLd:HTIMe?"),
                (":TRIGger:SHOLd:DLEVel ", ":TRIGger:SHOLd:DLEVel?"),
                (":TRIGger:SHOLd:CLEVel ", ":TRIGger:SHOLd:CLEVel?"))),
            (NthEdge("D0", "NEG", 16e-9, 65535, 20), (
                (":TRIGger:NEDGe:SOURce ", ":TRIGger:NEDGe:SOURce?"),
                (":TRIGger:NEDGe:SLOPe ", ":TRIGger:NEDGe:SLOPe?"),
                (":TRIGger:NEDGe:IDLE ", ":TRIGger:NEDGe:IDLE?"),
                (":TRIGger:NEDGe:EDGE ", ":TRIGger:NEDGe:EDGE?"),
                (":TRIGger:NEDGe:LEVel ", ":TRIGger:NEDGe:LEVel?"))),
        )
        for config, forms in cases:
            with self.subTest(mode=type(config).__name__):
                scope = FakeRigol()
                state = configure_trigger(scope, config)
                self.assertIsInstance(state.config, type(config))
                if isinstance(config, (Pattern, Duration)):
                    self.assertEqual(state.config.pattern, config.pattern)
                    self.assertEqual(state.config.source, config.source)
                    actual_levels = dict(state.config.levels)
                    for source, level in config.levels:
                        self.assertEqual(actual_levels[source], level)
                else:
                    self.assertEqual(state.config, config)
                self.assertTrue(any(command.startswith(":TRIGger:MODE ") for command in scope.writes))
                for common_query in (":TRIGger:MODE?", ":TRIGger:SWEep?", ":TRIGger:STATus?", ":TRIGger:POSition?"):
                    self.assertIn(common_query, scope.queries)
                self.assertTrue(any(command.startswith(":TRIGger:SWEep ") for command in scope.writes))
                if type(config).__name__ not in {"Video", "Timeout", "SetupHold", "NthEdge"}:
                    self.assertTrue(any(command.startswith(":TRIGger:HOLDoff ") for command in scope.writes))
                    self.assertIn(":TRIGger:HOLDoff?", scope.queries)
                if state.noise_reject is not None:
                    self.assertTrue(any(command.startswith(":TRIGger:NREJect ") for command in scope.writes))
                    self.assertIn(":TRIGger:NREJect?", scope.queries)
                for setter, query in forms:
                    self.assertTrue(any(command.startswith(setter) for command in scope.writes), setter)
                    self.assertTrue(any(command.startswith(query) for command in scope.queries), query)
                restored = restore_trigger(scope, state)
                self.assertEqual(restored, state)

    def test_pattern_rejects_multiple_edges_before_writing(self):
        scope = FakeRigol()
        with self.assertRaisesRegex(ValueError, "at most one"):
            configure_trigger(scope, Pattern(("R", "F", "X", "X")))
        self.assertEqual(scope.writes, [])

    def test_failed_scpi_write_rolls_back_previous_trigger_state(self):
        scope = FakeRigol()
        scope.fail_on = ":TRIGger:EDGE:LEVel "
        with self.assertRaisesRegex(RuntimeError, "rejected a command"):
            configure_trigger(scope, Edge(slope="NEG", level_v=0.25))
        state = read_trigger(scope)
        self.assertEqual(state.config, Edge())
        self.assertGreaterEqual(scope.writes.count(":TRIGger:EDGE:SLOPe POS"), 1)

    def test_transition_from_no_holdoff_mode_sets_mode_before_holdoff(self):
        scope = FakeRigol()
        configure_trigger(scope, Timeout())
        start = len(scope.writes)
        restored = restore_trigger(scope, TriggerState(Edge(), "AUTO", 8e-9, False, "STOP", 0.0))
        writes = scope.writes[start:]
        self.assertEqual(restored.mode, "EDGE")
        self.assertLess(next(i for i, cmd in enumerate(writes) if cmd.startswith(":TRIGger:MODE EDGE")),
                        next(i for i, cmd in enumerate(writes) if cmd.startswith(":TRIGger:HOLDoff ")))

    def test_unknown_mode_rejected_without_writes(self):
        scope = FakeRigol(mode="RS232")
        with self.assertRaisesRegex(ValueError, "outside this module"):
            read_trigger(scope)
        self.assertEqual(scope.writes, [])

    def test_incomplete_snapshot_rejected_before_writes(self):
        scope = FakeRigol()
        state = TriggerState(None, "AUTO", None, False, "STOP", 0.0)
        with self.assertRaisesRegex(ValueError, "complete supported"):
            restore_trigger(scope, state)
        self.assertEqual(scope.writes, [])


if __name__ == "__main__":
    unittest.main()
