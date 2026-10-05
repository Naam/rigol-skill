import csv
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import dho914s_waveforms as waveforms
import rigol_dho900 as base


class FakeInstrument:
    def __init__(self, *, status="STOP", data=None, preamble=None):
        self.commands = []
        self.status = status
        self.afg = "0"
        self.data = data if data is not None else [128]
        self.preamble = preamble or "0,0,4,1,1e-6,0,0,0.01,0,128"
        self.state = {
            "SOURce": "CHAN1", "MODE": "NORM", "FORMat": "BYTE",
            "POINts": "1000", "STARt": "1", "STOP": "1000",
        }
        self.start = 1
        self.stop = 1000

    def write(self, command):
        self.commands.append(command)
        if command == ":SOURce:OUTPut:STATe OFF":
            self.afg = "0"
        elif command.startswith(":WAVeform:") and " " in command:
            field, value = command[len(":WAVeform:"):].split(" ", 1)
            if field == "STARt":
                self.start = int(value)
            elif field == "STOP":
                self.stop = int(value)
            self.state[field] = value

    def query(self, command):
        self.commands.append(command)
        if command == ":SOURce:OUTPut:STATe?":
            return self.afg
        if command == ":SYSTem:ERRor:NEXT?":
            return '0,"No error"'
        if command == ":TRIGger:STATus?":
            return self.status
        if command == ":WAVeform:PREamble?":
            return self.preamble
        if command == ":WAVeform:DATA?":
            return ",".join(map(str, self.data[self.start - 1:self.stop]))
        if command.startswith(":WAVeform:") and command.endswith("?"):
            return self.state.get(command[len(":WAVeform:"):-1], "0")
        raise AssertionError(command)

    def query_binary_values(self, command, **_kwargs):
        self.commands.append(command)
        return self.data[self.start - 1:self.stop]


class WaveformsTest(unittest.TestCase):
    def test_word_analog_scale_and_prior_state_restore(self):
        fake = FakeInstrument(
            data=[33000, 32768, 32000, 32769],
            preamble="1,0,4,1,2e-6,-1e-6,0,0.001,0,32768",
        )
        reader = waveforms.DHO914SWaveforms(base.Rigol(fake), chunk_points=2)
        capture = reader.read(waveforms.WaveformRequest("CHANNEL2", "NORMAL", "WORD", 4))
        self.assertEqual(capture.metadata.source, "CHAN2")
        self.assertEqual(list(capture.values), [0.232, 0.0, -0.768, 0.001])
        self.assertEqual([t for t, _ in capture.samples()], [-1e-6, 1e-6, 3e-6, 5e-6])
        self.assertIn(":WAVeform:FORMat WORD", fake.commands)
        self.assertEqual(fake.state["MODE"], "NORM")
        self.assertEqual(fake.state["SOURce"], "CHAN1")

    def test_digital_ascii_and_math_source_validation(self):
        fake = FakeInstrument(data=["0.0", "1.0", "0.5", "-1e-3"])
        reader = waveforms.DHO914SWaveforms(base.Rigol(fake))
        request = waveforms.WaveformRequest("D15", "MAX", "ASCII", 4)
        fake.preamble = "2,1,4,1,1e-6,0,0,1,0,0"
        self.assertEqual(list(reader.read(request).values), [0.0, 1.0, 0.5, -0.001])
        with self.assertRaisesRegex(ValueError, "NORMAL mode only"):
            waveforms.WaveformRequest("MATH1", "RAW", "BYTE", 10)
        with self.assertRaisesRegex(ValueError, "NORMAL mode"):
            waveforms.WaveformRequest("CHAN1", "NORMAL", "BYTE", 1001)

    def test_raw_requires_stop_before_any_waveform_writes(self):
        fake = FakeInstrument(status="WAIT")
        reader = waveforms.DHO914SWaveforms(base.Rigol(fake))
        with self.assertRaisesRegex(RuntimeError, "stopped acquisition"):
            reader.read(waveforms.WaveformRequest("CHAN1", "RAW", "BYTE", 4))
        self.assertFalse(any(command.startswith(":WAVeform:") for command in fake.commands))

    def test_export_csv_streams_chunks_and_supports_50m_request(self):
        fake = FakeInstrument(data=[128] * 5,
                              preamble="0,2,5,1,1e-9,0,0,0.01,0,128")
        reader = waveforms.DHO914SWaveforms(base.Rigol(fake), chunk_points=2)
        request = waveforms.WaveformRequest("CHAN4", "RAW", "BYTE", 5)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "raw.csv"
            metadata = reader.export_csv(request, output)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(metadata.points, 5)
        self.assertEqual(len(rows), 6)
        self.assertEqual(fake.commands.count(":WAVeform:DATA?"), 3)
        self.assertNotIn(":SOURce:OUTPut:STATe ON", fake.commands)

    def test_request_validation_precedes_instrument_io(self):
        self.assertEqual(waveforms.WaveformRequest("CHAN1", "RAW", "WORD", 50_000_000).points,
                         50_000_000)
        with self.assertRaises(ValueError):
            waveforms.WaveformRequest("D16")
        with self.assertRaises(ValueError):
            waveforms.WaveformRequest("CHAN1", points=True)
        fake = FakeInstrument()
        with self.assertRaises(ValueError):
            waveforms.DHO914SWaveforms(base.Rigol(fake), chunk_points=250001)
        self.assertEqual(fake.commands, [])

    def test_metadata_uses_preamble_without_fetching_samples(self):
        fake = FakeInstrument(preamble="0,0,1000,8,1e-6,-2e-6,0,0.01,0,128")
        metadata = waveforms.DHO914SWaveforms(base.Rigol(fake)).metadata(
            waveforms.WaveformRequest("MATH2", points=4)
        )
        self.assertEqual((metadata.source, metadata.averages, metadata.points), ("MATH2", 8, 1000))
        self.assertIn(":WAVeform:PREamble?", fake.commands)
        self.assertNotIn(":WAVeform:DATA?", fake.commands)

    def test_restore_resets_raw_window_before_entering_normal_mode(self):
        class BoundedFake(FakeInstrument):
            def __init__(self):
                super().__init__(preamble="0,0,4,1,1e-6,0,0,0.01,0,128")
                self.state.update({"MODE": "RAW", "POINts": "50000000",
                                   "STARt": "40000000", "STOP": "50000000"})
                self.start = 40_000_000
                self.stop = 50_000_000

            def write(self, command):
                if command == ":WAVeform:MODE NORMal" and (
                        int(self.state["STARt"]) > 1000 or
                        int(self.state["STOP"]) > 1000 or
                        int(self.state["POINts"]) > 1000):
                    raise RuntimeError("normal-mode window exceeds 1000-point limit")
                super().write(command)

        fake = BoundedFake()
        waveforms.DHO914SWaveforms(base.Rigol(fake)).metadata(
            waveforms.WaveformRequest("CHAN1", "NORMAL", "BYTE", 4)
        )
        mode_index = fake.commands.index(":WAVeform:MODE NORMal", fake.commands.index(":WAVeform:PREamble?") + 1)
        self.assertLess(fake.commands.index(":WAVeform:STARt 1", fake.commands.index(":WAVeform:PREamble?") + 1), mode_index)
        self.assertEqual(fake.state["MODE"], "RAW")
        self.assertEqual(fake.state["STARt"], "40000000")
        self.assertEqual(fake.state["STOP"], "50000000")


if __name__ == "__main__":
    unittest.main()
