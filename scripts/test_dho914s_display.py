import unittest

from dho914s_display import (
    DisplaySettings,
    ManualCursorSettings,
    TrackCursorSettings,
    XyCursorSettings,
    clear_display,
    configure_cursors,
    configure_display,
    read_cursors,
    read_display,
    screenshot,
)


class FakeInstrument:
    def __init__(self):
        self.writes = []
        self.mode = "MAN"
        self.timebase = "MAIN"
        self.data = b"png"
        self.ignore_writes = set()
        self.fail_setter = None
        self.errors = ["+0,No error"]
        self.values = {
            ":CURSor:MEASure:INDicator?": "0",
            ":CURSor:MANual:TYPE?": "TIME",
            ":CURSor:MANual:SOURce?": "CHAN1",
            ":CURSor:TRACk:SOURce1?": "CHAN1",
            ":CURSor:TRACk:SOURce2?": "CHAN1",
            ":CURSor:TRACk:MODE?": "Y",
            ":DISPlay:TYPE?": "VECT",
            ":DISPlay:GRADing:TIME?": "MIN",
            ":DISPlay:WBRightness?": "50",
            ":DISPlay:GRID?": "FULL",
            ":DISPlay:GBRightness?": "50",
            ":DISPlay:RULers?": "1",
            ":DISPlay:COLor?": "0",
            ":DISPlay:WHOLd?": "0",
        }
        for prefix, names in (("MANual", ("CAX", "CAY", "CBX", "CBY")),
                              ("TRACk", ("CAX", "CAY", "CBX", "CBY")),
                              ("XY", ("AX", "AY", "BX", "BY"))):
            self.values.update({f":CURSor:{prefix}:{name}?": "0" for name in names})

    def write(self, command):
        self.writes.append(command)
        parts = command.split()
        if len(parts) < 2 or parts[0] in self.ignore_writes:
            return
        if parts[0] == self.fail_setter:
            self.errors = ["-222,Data out of range", "+0,No error"]
            self.fail_setter = None
            return
        setters = {
            ":CURSor:MODE": (":CURSor:MODE?", {"MANual": "MAN", "TRACk": "TRAC", "OFF": "OFF", "XY": "XY"}),
            ":CURSor:MEASure:INDicator": (":CURSor:MEASure:INDicator?", {}),
            ":CURSor:MANual:TYPE": (":CURSor:MANual:TYPE?", {"AMPLitude": "AMPL", "TIME": "TIME"}),
            ":CURSor:MANual:SOURce": (":CURSor:MANual:SOURce?", {}),
            ":CURSor:TRACk:SOURce1": (":CURSor:TRACk:SOURce1?", {}),
            ":CURSor:TRACk:SOURce2": (":CURSor:TRACk:SOURce2?", {}),
            ":CURSor:TRACk:MODE": (":CURSor:TRACk:MODE?", {}),
            ":DISPlay:TYPE": (":DISPlay:TYPE?", {"VECTors": "VECT"}),
            ":DISPlay:GRADing:TIME": (":DISPlay:GRADing:TIME?", {"INFinite": "INF"}),
            ":DISPlay:WBRightness": (":DISPlay:WBRightness?", {}),
            ":DISPlay:GRID": (":DISPlay:GRID?", {}),
            ":DISPlay:GBRightness": (":DISPlay:GBRightness?", {}),
            ":DISPlay:RULers": (":DISPlay:RULers?", {}),
            ":DISPlay:COLor": (":DISPlay:COLor?", {}),
            ":DISPlay:WHOLd": (":DISPlay:WHOLd?", {}),
        }
        if parts[0] in setters:
            query, aliases = setters[parts[0]]
            value = aliases.get(parts[1], parts[1])
            if query == ":CURSor:MODE?":
                self.mode = value
            elif query.endswith("INDicator?") or query.endswith(("RULers?", "COLor?", "WHOLd?")):
                self.values[query] = "1" if value.upper() in {"1", "ON"} else "0"
            else:
                self.values[query] = value
            return
        if parts[0].startswith(":CURSor:"):
            query = parts[0] + "?"
            self.values[query] = parts[1]

    def query(self, command):
        if command == ":SYSTem:ERRor:NEXT?":
            return "+0,No error"
        values = {":TIMebase:MODE?": self.timebase, ":CURSor:MODE?": self.mode, **self.values}
        if command in values:
            return values[command]
        if command.endswith("?") and any(token in command.upper() for token in ("VALUE?", "DELTA?", "CAX?", "CAY?", "CBX?", "CBY?", ":AX?", ":AY?", ":BX?", ":BY?")):
            return self.values.get(command, "1.25")
        raise AssertionError(f"unexpected query: {command}")

    def query_binary_values(self, command, **kwargs):
        self.binary_command = command
        return self.data


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.instrument = FakeInstrument()

    def write(self, command):
        self.instrument.write(command)

    def query(self, command):
        return self.instrument.query(command)

    def afg_off(self):
        self.write(":SOURce:OUTPut:STATe OFF")

    def errors(self):
        errors = self.instrument.errors
        self.instrument.errors = ["+0,No error"]
        return errors


class DisplayTests(unittest.TestCase):
    def test_manual_and_track_cursor_settings_and_typed_readback(self):
        scope = FakeScope()
        state = configure_cursors(
            scope, mode="manual", indicator=True,
            manual=ManualCursorSettings("AMPLitude", "CHAN2", ax=1e-6, ay=0.1, bx=2e-6, by=0.25),
        )
        self.assertEqual(state.mode, "MANual")
        self.assertEqual(state.manual_type, "AMPLitude")
        self.assertEqual(state.manual_source, "CHAN2")
        self.assertEqual(state.manual_positions[0], 1e-6)
        self.assertEqual(state.manual_positions[3], 0.25)
        self.assertEqual(state.manual.ax, 1.25)
        self.assertEqual(state.manual.inverse_delta_x, 1.25)
        self.assertIn(":CURSor:MANual:TYPE AMPLitude", scope.instrument.writes)
        self.assertIn(":CURSor:MANual:CAX 1e-06", scope.instrument.writes)
        state = configure_cursors(scope, mode="TRACk", track=TrackCursorSettings(
            "MATH1", "CHAN4", ax=1e-6, ay=0.1, bx=2e-6, by=0.25, axis="X"))
        self.assertEqual(state.track_sources, ("MATH1", "CHAN4"))
        self.assertEqual(state.track_mode, "X")
        self.assertIn(":CURSor:TRACk:SOURce1 MATH1", scope.instrument.writes)
        for prefix, fields in (("MANual", ("CAX", "CAY", "CBX", "CBY")),
                               ("TRACk", ("CAX", "CAY", "CBX", "CBY"))):
            for field in fields:
                self.assertTrue(any(write.startswith(f":CURSor:{prefix}:{field} ")
                                    for write in scope.instrument.writes))
        # Requested settings are verified even while that cursor mode is inactive.
        configure_cursors(scope, mode="OFF", manual=ManualCursorSettings(source="NONE", ax=2.5))
        self.assertEqual(scope.instrument.values[":CURSor:MANual:SOURce?"], "NONE")
        self.assertEqual(scope.instrument.values[":CURSor:MANual:CAX?"], "2.5")

    def test_xy_requires_xy_timebase_before_any_write(self):
        scope = FakeScope()
        with self.assertRaisesRegex(ValueError, "timebase mode"):
            configure_cursors(scope, xy=XyCursorSettings(ax=1))
        self.assertEqual(scope.instrument.writes, [])
        scope.instrument.timebase = "XY"
        scope.instrument.mode = "XY"
        state = configure_cursors(scope, mode="XY", xy=XyCursorSettings(ax=1.2, ay=2.3, bx=3.4, by=4.5))
        self.assertEqual(state.xy_positions, (1.2, 2.3, 3.4, 4.5))
        self.assertIsNone(state.xy.inverse_delta_x)
        for field in ("AX", "AY", "BX", "BY"):
            self.assertTrue(any(write.startswith(f":CURSor:XY:{field} ")
                                for write in scope.instrument.writes))

    def test_display_configuration_screenshot_and_clear(self):
        scope = FakeScope()
        state = read_display(scope)
        self.assertEqual(state.display_type, "VECT")
        state = configure_display(scope, DisplaySettings(
            display_type="vectors", persistence="infinite", waveform_brightness=75,
            grid="half", grid_brightness=20, rulers=True, color_grade=True, frozen=True,
        ))
        self.assertEqual(state.grid_brightness, 20)
        self.assertEqual(state.waveform_brightness, 75)
        self.assertEqual(state.grid, "HALF")
        self.assertTrue(state.rulers and state.color_grade and state.frozen)
        self.assertIn(":DISPlay:GRADing:TIME INFinite", scope.instrument.writes)
        self.assertIn(":DISPlay:TYPE VECTors", scope.instrument.writes)
        self.assertIn(":DISPlay:WHOLd 1", scope.instrument.writes)
        self.assertEqual(screenshot(scope, "jpg"), b"png")
        self.assertEqual(scope.instrument.binary_command, ":DISPlay:DATA? JPG")
        self.assertEqual(screenshot(scope), b"png")
        self.assertEqual(scope.instrument.binary_command, ":DISPlay:DATA?")
        clear_display(scope)
        self.assertEqual(scope.instrument.writes[-1], ":DISPlay:CLEar")

    def test_rejects_bad_values_without_writing(self):
        scope = FakeScope()
        with self.assertRaises(ValueError):
            configure_display(scope, DisplaySettings(grid="diagonal"))
        with self.assertRaises(ValueError):
            configure_cursors(scope, manual=ManualCursorSettings(source="EXT"))
        with self.assertRaises(ValueError):
            screenshot(scope, "GIF")
        self.assertEqual(scope.instrument.writes, [])

    def test_mismatched_readback_and_scpi_errors_fail(self):
        scope = FakeScope()
        scope.instrument.ignore_writes.add(":DISPlay:WBRightness")
        with self.assertRaisesRegex(RuntimeError, "readback.*requested"):
            configure_display(scope, DisplaySettings(waveform_brightness=75))
        scope.instrument.fail_setter = ":CURSor:MODE"
        with self.assertRaisesRegex(RuntimeError, "Rigol rejected a command"):
            configure_cursors(scope, mode="MANual")
        self.assertEqual(scope.instrument.mode, "MAN")

    def test_mid_write_scpi_error_restores_prior_display_state(self):
        scope = FakeScope()
        scope.instrument.fail_setter = ":DISPlay:GRID"
        with self.assertRaisesRegex(RuntimeError, "Rigol rejected a command"):
            configure_display(scope, DisplaySettings(waveform_brightness=75, grid="HALF"))
        self.assertEqual(scope.instrument.values[":DISPlay:WBRightness?"], "50")
        self.assertEqual(scope.instrument.values[":DISPlay:GRID?"], "FULL")


if __name__ == "__main__":
    unittest.main()
