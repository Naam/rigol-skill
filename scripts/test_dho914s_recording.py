import unittest

from dho914s_recording import Recording, Reference, enable_reference_labels, reference_labels_enabled


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.commands = []
        self.queries = []
        self.fail_play_state = False
        self.fail_record_state = False
        self.fail_record_on_run = False
        self.recording = "STOP"
        self.playing = "STOP"
        self.record = {"enabled": "1", "frames": "100", "max": "500",
                       "interval": "1.0E-2", "prompt": "0"}
        self.play = {"current": "4", "time": "2025-01-01 00:00:00", "start": "1",
                     "end": "10", "max": "20", "interval": "1.0E-1",
                     "mode": "SING", "direction": "FORW"}
        self.reference = {"source": "CHAN1", "scale": "2.0E-1", "offset": "0.0",
                          "color": "GRE", "label": "REF"}
        self.labels = "0"

    def write(self, command):
        self.commands.append(command)
        if command.endswith("FRAMes:MAX"):
            self.record["frames"] = self.record["max"]
        for key, head in (("frames", ":RECord:WRECord:FRAMes "),
                          ("frames", ":RECord:FRAMes "),
                          ("interval", ":RECord:WRECord:FINTerval "),
                          ("prompt", ":RECord:WRECord:PROMpt ")):
            if command.startswith(head):
                self.record[key] = command[len(head):]
        for key, head in (("enabled", ":RECord:WRECord:ENABle "),
                          ("enabled", ":RECord:ENABle ")):
            if command.startswith(head):
                self.record[key] = "1" if command.endswith("ON") else "0"
        if command.endswith("OPERate RUN") or command == ":RECord:STARt ON":
            if "WREPlay" in command or command == ":RECord:PLAY ON":
                self.playing = "RUN"
            else:
                self.recording = "RUN"
                if self.fail_record_on_run:
                    self.fail_record_state = True
        if command.endswith("OPERate STOP") or command == ":RECord:STARt OFF":
            if "WREPlay" in command:
                self.playing = "STOP"
            else:
                self.recording = "STOP"
        if command in {":RECord:PLAY ON", ":RECord:PLAY OFF"}:
            self.playing = "RUN" if command.endswith("ON") else "STOP"
        for key, head in (("start", ":RECord:WREPlay:FSTart "),
                          ("end", ":RECord:WREPlay:FEND "),
                          ("interval", ":RECord:WREPlay:FINTerval ")):
            if command.startswith(head):
                self.play[key] = command[len(head):]
        if command.startswith(":RECord:WREPlay:MODE "):
            self.play["mode"] = "REP" if command.endswith("REP") else "SING"
        if command.startswith(":RECord:WREPlay:DIRection "):
            self.play["direction"] = "BACK" if command.endswith("BACK") else "FORW"
        if command.startswith(":RECord:WREPlay:FCURrent ") or command.startswith(":RECord:CURRent "):
            self.play["current"] = command.rsplit(" ", 1)[1]
        if command.startswith(":RECord:WREPlay:PLAY "):
            self.play["current"] = self.play["start"] if command.endswith("FFIRst") else self.play["end"]
        if command.startswith(":REFerence:SOURce 1,"):
            self.reference["source"] = command.split(",", 1)[1].replace("CHANnel", "CHAN")
        if command.startswith(":REFerence:VSCale 1,"):
            self.reference["scale"] = command.split(",", 1)[1]
        if command.startswith(":REFerence:VOFFset 1,"):
            self.reference["offset"] = command.split(",", 1)[1]
        if command.startswith(":REFerence:COLor 1,"):
            self.reference["color"] = {"GREen": "GRE", "ORANge": "ORAN"}.get(command.split(",", 1)[1], command.split(",", 1)[1])
        if command.startswith(":REFerence:LABel:CONTent 1,"):
            self.reference["label"] = command.split(",", 1)[1][1:-1].replace('""', '"')
        if command.startswith(":REFerence:LABel:ENABle "):
            self.labels = "1" if command.endswith("ON") else "0"

    def query(self, command):
        self.queries.append(command)
        if self.fail_record_state and command == ":RECord:WRECord:OPERate?":
            raise OSError("record transport failed")
        if self.fail_play_state and command == ":RECord:WREPlay:OPERate?":
            raise OSError("playback transport failed")
        record_queries = {
            ":RECord:WRECord:ENABle?": self.record["enabled"],
            ":RECord:ENABle?": self.record["enabled"],
            ":RECord:WRECord:OPERate?": "STOP",
            ":RECord:STARt?": "0",
            ":RECord:WRECord:FRAMes?": self.record["frames"],
            ":RECord:FRAMes?": self.record["frames"],
            ":RECord:WRECord:FMAX?": self.record["max"],
            ":RECord:WRECord:FINTerval?": self.record["interval"],
            ":RECord:WRECord:PROMpt?": self.record["prompt"],
        }
        play_queries = {
            ":RECord:WREPlay:OPERate?": "STOP",
            ":RECord:PLAY?": "0",
            ":RECord:WREPlay:FCURrent?": self.play["current"],
            ":RECord:CURRent?": self.play["current"],
            ":RECord:WREPlay:FCURrent:TIME?": self.play["time"],
            ":RECord:WREPlay:FSTart?": self.play["start"],
            ":RECord:WREPlay:FEND?": self.play["end"],
            ":RECord:WREPlay:FMAX?": self.play["max"],
            ":RECord:WREPlay:FINTerval?": self.play["interval"],
            ":RECord:WREPlay:MODE?": self.play["mode"],
            ":RECord:WREPlay:DIRection?": self.play["direction"],
        }
        for key, value in record_queries.items() | play_queries.items():
            if command == key:
                return value
        if command.startswith(":REFerence:"):
            key = command.split("?", 1)[0].split(":")[-1].upper()
            return {"SOURCE": self.reference["source"], "VSCALE": self.reference["scale"],
                    "VOFFSET": self.reference["offset"], "COLOR": self.reference["color"],
                    "CONTENT": self.reference["label"]}.get(key, "") if "? 1" in command else self.labels
        raise KeyError(command)

    def errors(self):
        return ['0,"No error"']


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()
        self.recorder = Recording(self.scope)

    def test_recording_all_setters_queries_and_legacy_forms(self):
        state = self.recorder.settings()
        self.assertEqual((state.enabled, state.frame_count, state.max_frames), (True, 100, 500))
        state = self.recorder.configure(frames=200, interval_s=0.02, enabled=False, completion_beep=True)
        self.assertEqual((state.frame_count, state.frame_interval_s, state.enabled, state.completion_beep),
                         (200, 0.02, False, True))
        self.recorder.configure(frames=250, enabled=True, legacy_commands=True)
        self.assertIn(":RECord:FRAMes 250", self.scope.commands)
        self.assertIn(":RECord:ENABle ON", self.scope.commands)
        self.recorder.set_maximum_frames()
        self.assertIn(":RECord:WRECord:FRAMes:MAX", self.scope.commands)
        self.assertEqual(self.scope.record["frames"], "500")
        with self.assertRaises(ValueError):
            self.recorder.configure(frames=501)

    def test_start_stop_canonical_and_legacy_with_confirmation_and_guaranteed_stop(self):
        with self.assertRaises(ValueError):
            self.recorder.start()
        self.recorder.start(confirm=True)
        self.assertIn(":RECord:WRECord:OPERate RUN", self.scope.commands)
        self.assertIn(":RECord:WRECord:OPERate STOP", self.scope.commands)
        self.recorder.start(confirm=True, legacy_command=True)
        self.assertIn(":RECord:STARt ON", self.scope.commands)
        self.assertIn(":RECord:STARt OFF", self.scope.commands)
        self.recorder.stop()
        self.assertEqual(self.scope.commands[-1], ":RECord:WRECord:OPERate STOP")

    def test_record_timeout_reports_incomplete_run_and_stops(self):
        original_query = self.scope.query
        def never_complete(command):
            if command == ":RECord:WRECord:OPERate?":
                return "RUN"
            return original_query(command)
        self.scope.query = never_complete
        with self.assertRaises(TimeoutError):
            self.recorder.start(confirm=True, timeout_s=0.05)
        self.assertEqual(self.scope.commands[-1], ":RECord:WRECord:OPERate STOP")
        self.scope.query = original_query
        self.scope.fail_record_on_run = True
        with self.assertRaises(OSError):
            self.recorder.start(confirm=True, timeout_s=0.05)
        self.assertEqual(self.scope.commands[-1], ":RECord:WRECord:OPERate STOP")

    def test_playback_configuration_readback_legacy_navigation_and_safety(self):
        state = self.recorder.playback_settings()
        self.assertEqual((state.current_frame, state.start_frame, state.end_frame, state.max_frames), (4, 1, 10, 20))
        self.assertTrue(state.current_frame_time.startswith("2025-"))
        with self.assertRaises(ValueError):
            self.recorder.play(start=1, end=21, confirm=True)
        with self.assertRaises(ValueError):
            self.recorder.play(start=1, end=2)
        self.recorder.play(start=2, end=8, interval_s=0.2, mode="REPEAT", direction="BACKWARD",
                           confirm=True, timeout_s=0.05)
        for command in (":RECord:WREPlay:FSTart 2", ":RECord:WREPlay:FEND 8",
                        ":RECord:WREPlay:FINTerval 0.2", ":RECord:WREPlay:MODE REP",
                        ":RECord:WREPlay:DIRection BACK", ":RECord:WREPlay:OPERate RUN",
                        ":RECord:WREPlay:OPERate STOP"):
            self.assertIn(command, self.scope.commands)
        self.recorder.play(start=1, end=10, confirm=True, legacy_command=True, timeout_s=0.05)
        self.assertIn(":RECord:PLAY ON", self.scope.commands)
        self.assertIn(":RECord:PLAY OFF", self.scope.commands)
        self.recorder.set_current_frame(7, confirm=True)
        self.assertEqual(self.recorder.current_frame(), 7)
        self.recorder.set_current_frame(5, confirm=True, legacy_command=True)
        self.assertEqual(self.recorder.current_frame(legacy_command=True), 5)
        self.assertIn(":RECord:CURRent 5", self.scope.commands)
        self.recorder.step("BACK", confirm=True)
        self.recorder.step("NEXT", confirm=True)
        self.assertIn(":RECord:WREPlay:BACK", self.scope.commands)
        self.assertIn(":RECord:WREPlay:NEXT", self.scope.commands)
        self.recorder.play_from("FIRST", confirm=True)
        self.recorder.play_from("END", confirm=True)
        self.assertIn(":RECord:WREPlay:PLAY FFIRst", self.scope.commands)
        self.assertIn(":RECord:WREPlay:PLAY FEND", self.scope.commands)
        self.recorder.stop_playback()
        self.assertEqual(self.scope.commands[-1], ":RECord:WREPlay:OPERate STOP")
        self.scope.fail_play_state = True
        with self.assertRaises(OSError):
            self.recorder.play(start=2, end=8, confirm=True, timeout_s=0.05)
        self.assertEqual(self.scope.commands[-1], ":RECord:WREPlay:OPERate STOP")

    def test_reference_all_sources_settings_and_actions(self):
        ref = Reference(self.scope, 1)
        self.assertEqual(ref.settings().source, "CHAN1")
        for source in ("CHANnel2", "D15", "MATH4"):
            ref.set_source(source)
        self.assertIn(":REFerence:SOURce 1,CHANnel2", self.scope.commands)
        self.assertIn(":REFerence:SOURce 1,D15", self.scope.commands)
        self.assertIn(":REFerence:SOURce 1,MATH4", self.scope.commands)
        ref.set_scale(0.5, probe_ratio=10)
        ref.set_offset(1.0)
        self.assertIn(":REFerence:VSCale 1,0.5", self.scope.commands)
        self.assertIn(":REFerence:VOFFset 1,1", self.scope.commands)
        for color in ("GRAY", "GREEN", "BLUE", "RED", "ORANGE"):
            ref.set_color(color)
        ref.set_label('scope "A"')
        self.assertEqual(ref.settings().label, 'scope "A"')
        with self.assertRaises(ValueError):
            ref.save()
        ref.save(confirm=True)
        with self.assertRaises(ValueError):
            ref.reset_vertical()
        ref.reset_vertical(confirm=True)
        ref.select()
        self.assertIn(":REFerence:SAVE 1", self.scope.commands)
        self.assertIn(":REFerence:RESet 1", self.scope.commands)
        self.assertIn(":REFerence:CURRent 1", self.scope.commands)
        self.assertTrue(enable_reference_labels(self.scope, True))
        self.assertTrue(reference_labels_enabled(self.scope))
        self.assertIn(":REFerence:LABel:ENABle ON", self.scope.commands)
        with self.assertRaises(ValueError):
            Reference(self.scope, 11)
        with self.assertRaises(ValueError):
            ref.set_source("SCPI;*RST")


if __name__ == "__main__":
    unittest.main()
