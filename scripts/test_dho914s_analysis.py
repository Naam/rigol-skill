import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dho914s_analysis import (
    HistogramSettings,
    MathSettings,
    configure_histogram,
    configure_math,
    read_fft_search_results,
    read_histogram_statistics,
)
from rigol_dho900 import Rigol


class FakeInstrument:
    def __init__(self):
        self.writes = []
        self.queries = []
        self.output = "0"
        self.ignore_writes = False
        self.responses = {
            ":MATH1:OPERator?": "ADD",
            ":MATH1:FFT:FREQuency:STARt?": "1",
            ":MATH1:FFT:FREQuency:END?": "10000000",
            ":MATH1:FFT:UNIT?": "DB",
            ":MATH1:FFT:SCALe?": "2",
            ":MATH1:FILTer:TYPE?": "LPAS",
            ":MATH1:FILTer:W1?": "1000000",
            ":MATH1:FILTer:W2?": "2000000",
            ":TIMebase:MAIN:SCALe?": "1e-5",
            ":HISTogram:RANGe:LEFT?": "-2e-5",
            ":HISTogram:RANGe:RIGHt?": "2e-5",
            ":HISTogram:RANGe:TOP?": "8",
            ":HISTogram:RANGe:BOTTom?": "-8",
            ":HISTogram:SOURce?": "CHAN1",
            ":HISTogram:TYPE?": "VERT",
            ":HISTogram:HEIGht?": "2",
            ":CHANnel1:SCALe?": "1",
            ":CHANnel1:OFFSet?": "0",
            ":CHANnel2:SCALe?": "1",
            ":CHANnel2:OFFSet?": "0",
            ":CHANnel3:SCALe?": "1",
            ":CHANnel3:OFFSet?": "0",
            ":CHANnel4:SCALe?": "1",
            ":CHANnel4:OFFSet?": "0",
            ":SYSTem:ERRor:NEXT?": "+0,No error",
            ":MATH1:FFT:SEARch:RES?": "1,2.50000MHz,-24.98dBV\n2,3.5kHz,-27.84dBV",
            ":HISTogram:STATistics:RESult?": "[Sum:5hits,Peaks:2hits,Max:3us,Min:-1us,Pk_Pk:4us,Mean:1us,Median:1us,Mode:1us,Bin width:20ns,Sigma:2us]",
        }

    def write(self, command):
        self.writes.append(command)
        if command == ":SOURce:OUTPut:STATe OFF":
            self.output = "0"
        elif not self.ignore_writes and command.startswith((":MATH", ":HISTogram:")) and " " in command:
            setting, value = command.split(" ", 1)
            self.responses[setting + "?"] = value

    def query(self, command):
        self.queries.append(command)
        if command == ":SOURce:OUTPut:STATe?":
            return self.output
        return self.responses.get(command, "0")


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeInstrument()
        self.scope = Rigol(self.fake)

    def test_math_contextual_setting_and_readback(self):
        state = configure_math(self.scope, 1, MathSettings(operator="FFT", fft_source=2, fft_window="HANNING", fft_search_count=8))
        self.assertEqual(state.index, 1)
        self.assertIn(":MATH1:OPERator FFT", self.fake.writes)
        self.assertIn(":MATH1:FFT:SOURce CHANnel2", self.fake.writes)
        self.assertIn(":MATH1:FFT:WINDow HANNing", self.fake.writes)
        self.assertIn(":MATH1:FFT:SEARch:NUM 8", self.fake.writes)
        self.assertIn(":MATH1:WINDow:TITLe?", self.fake.queries)
        self.assertNotIn(":MATH1:SOURce2?", self.fake.queries)

    def test_each_math_setter_has_a_fake_instrument_path(self):
        cases = [
            ("ADD", MathSettings(display=True), ":MATH1:DISPlay ON"),
            ("ADD", MathSettings(operator="DIFF"), ":MATH1:OPERator DIFF"),
            ("ADD", MathSettings(source1="CHAN2"), ":MATH1:SOURce1 CHANnel2"),
            ("ADD", MathSettings(source2="CHAN2"), ":MATH1:SOURce2 CHANnel2"),
            ("AND", MathSettings(logic_source1="D3"), ":MATH1:LSOurce1 D3"),
            ("AND", MathSettings(logic_source2="D4"), ":MATH1:LSOurce2 D4"),
            ("ADD", MathSettings(scale=0.5), ":MATH1:SCALe 0.5"),
            ("ADD", MathSettings(offset=2), ":MATH1:OFFSet 2"),
            ("ADD", MathSettings(invert=True), ":MATH1:INVert ON"),
            ("ADD", MathSettings(reset=True), ":MATH1:RESet"),
            ("ADD", MathSettings(grid="HALF"), ":MATH1:GRID HALF"),
            ("ADD", MathSettings(expand="CENTER"), ":MATH1:EXPand CENTER"),
            ("ADD", MathSettings(waveform_type="MAIN"), ":MATH1:WAVetype MAIN"),
            ("FFT", MathSettings(fft_source=3), ":MATH1:FFT:SOURce CHANnel3"),
            ("FFT", MathSettings(fft_window="BLACKMAN"), ":MATH1:FFT:WINDow BLACkman"),
            ("FFT", MathSettings(fft_unit="DB"), ":MATH1:FFT:UNIT DB"),
            ("FFT", MathSettings(fft_scale=1.5), ":MATH1:FFT:SCALe 1.5"),
            ("FFT", MathSettings(fft_offset=0.5), ":MATH1:FFT:OFFSet 0.5"),
            ("FFT", MathSettings(fft_hscale_hz=1000), ":MATH1:FFT:HSCale 1000"),
            ("FFT", MathSettings(fft_center_hz=1000), ":MATH1:FFT:HCENter 1000"),
            ("FFT", MathSettings(fft_start_hz=10), ":MATH1:FFT:FREQuency:STARt 10"),
            ("FFT", MathSettings(fft_end_hz=100000), ":MATH1:FFT:FREQuency:END 100000"),
            ("FFT", MathSettings(fft_search_enabled=True), ":MATH1:FFT:SEARch:ENABle ON"),
            ("FFT", MathSettings(fft_search_count=4), ":MATH1:FFT:SEARch:NUM 4"),
            ("FFT", MathSettings(fft_search_threshold=0.5), ":MATH1:FFT:SEARch:THReshold 0.5"),
            ("FFT", MathSettings(fft_search_excursion=1), ":MATH1:FFT:SEARch:EXCursion 1"),
            ("FFT", MathSettings(fft_search_order="FREQORDER"), ":MATH1:FFT:SEARch:ORDer FREQorder"),
            ("LPAS", MathSettings(filter_type="HPASS"), ":MATH1:FILTer:TYPE HPASs"),
            ("LPAS", MathSettings(filter_w1_hz=500000), ":MATH1:FILTer:W1 500000"),
            ("BPAS", MathSettings(filter_w2_hz=500000), ":MATH1:FILTer:W2 500000"),
            ("AND", MathSettings(logic_sensitivity_div=0.5), ":MATH1:SENSitivity 0.5"),
            ("DIFF", MathSettings(differential_distance=5), ":MATH1:DISTance 5"),
            ("AND", MathSettings(threshold1_v=0.1), ":MATH1:THReshold1 0.1"),
            ("AND", MathSettings(threshold2_v=0.1), ":MATH1:THReshold2 0.1"),
            ("AND", MathSettings(threshold3_v=0.1), ":MATH1:THReshold3 0.1"),
            ("AND", MathSettings(threshold4_v=0.1), ":MATH1:THReshold4 0.1"),
            ("ADD", MathSettings(label_show=True), ":MATH1:LABel:SHOW ON"),
        ]
        for operator, settings, expected_command in cases:
            with self.subTest(command=expected_command):
                fake = FakeInstrument()
                fake.responses[":MATH1:OPERator?"] = operator
                if operator == "BPAS":
                    fake.responses[":MATH1:FILTer:TYPE?"] = "BPAS"
                    fake.responses[":MATH1:FILTer:W1?"] = "100000"
                    fake.responses[":MATH1:FILTer:W2?"] = "200000"
                configure_math(Rigol(fake), 1, settings)
                self.assertIn(expected_command, fake.writes)

    def test_rejects_math_dependency_before_writes(self):
        with self.assertRaisesRegex(ValueError, "source2"):
            configure_math(self.scope, 1, MathSettings(operator="NOT", source2="CHAN2"))
        self.assertEqual(self.fake.writes, [])

    def test_invalid_boolean_and_fft_limits_fail_before_writes(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            configure_math(self.scope, 1, MathSettings(operator="FFT", display="yes"))
        with self.assertRaisesRegex(ValueError, "fft_center_hz"):
            configure_math(self.scope, 1, MathSettings(operator="FFT", fft_center_hz=4))
        with self.assertRaisesRegex(ValueError, "fft_offset"):
            configure_math(self.scope, 1, MathSettings(operator="FFT", fft_offset=1e10))
        self.assertEqual(self.fake.writes, [])

    def test_zoom_math_requires_zoom_enabled(self):
        with self.assertRaisesRegex(ValueError, "requires delayed sweep"):
            configure_math(self.scope, 1, MathSettings(waveform_type="ZOOM"))
        self.fake.responses[":TIMebase:DELay:ENABle?"] = "1"
        state = configure_math(self.scope, 1, MathSettings(waveform_type="ZOOM"))
        self.assertEqual(state.values["waveform_type"], "ZOOM")

    def test_math_readback_mismatch_is_reported(self):
        self.fake.ignore_writes = True
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            configure_math(self.scope, 1, MathSettings(display=True))

    def test_fft_threshold_uses_unit_scale_and_offset(self):
        with self.assertRaisesRegex(ValueError, "vertical range"):
            configure_math(self.scope, 1, MathSettings(operator="FFT", fft_search_threshold=9))
        with self.assertRaisesRegex(ValueError, "explicit FFT scale and offset"):
            configure_math(self.scope, 1, MathSettings(operator="FFT", fft_unit="VRMS", fft_search_threshold=0.5))
        self.assertEqual(self.fake.writes, [])

    def test_filter_range_uses_live_timebase(self):
        with self.assertRaisesRegex(ValueError, "timebase-derived"):
            configure_math(self.scope, 1, MathSettings(operator="LPAS", filter_w1_hz=1234567))
        self.assertEqual(self.fake.writes, [])

    def test_histogram_range_order_and_parameter_bounds(self):
        with self.assertRaisesRegex(ValueError, "left < right"):
            configure_histogram(self.scope, HistogramSettings(left=2e-5))
        self.assertEqual(self.fake.writes, [])
        configure_histogram(self.scope, HistogramSettings(source=2, height_div=4, enabled=True))
        self.assertIn(":HISTogram:SOURce CHANnel2", self.fake.writes)
        self.assertIn(":HISTogram:HEIGht 4", self.fake.writes)
        self.assertIn(":HISTogram:ENABle ON", self.fake.writes)

    def test_histogram_bound_pair_is_written_without_crossing(self):
        configure_histogram(self.scope, HistogramSettings(left=3e-5, right=4e-5))
        self.assertLess(self.fake.writes.index(":HISTogram:RANGe:RIGHt 4e-05"), self.fake.writes.index(":HISTogram:RANGe:LEFT 3e-05"))

    def test_each_histogram_setter_has_a_fake_instrument_path(self):
        configure_histogram(self.scope, HistogramSettings(
            enabled=True, histogram_type="HORIZONTAL", source=2, height_div=4,
            left=-1e-5, right=1e-5, top=3, bottom=-3,
        ))
        for command in (
            ":HISTogram:ENABle ON", ":HISTogram:TYPE HORizontal",
            ":HISTogram:SOURce CHANnel2", ":HISTogram:HEIGht 4",
            ":HISTogram:RANGe:LEFT -1e-05", ":HISTogram:RANGe:RIGHt 1e-05",
            ":HISTogram:RANGe:TOP 3.0", ":HISTogram:RANGe:BOTTom -3.0",
        ):
            self.assertIn(command, self.fake.writes)

    def test_histogram_readback_rejects_bad_enum_and_mismatch(self):
        from dho914s_analysis import read_histogram
        self.fake.responses[":HISTogram:TYPE?"] = "SIDE"
        with self.assertRaisesRegex(ValueError, "invalid histogram type"):
            read_histogram(self.scope)
        self.fake.responses[":HISTogram:TYPE?"] = "VERTical"
        self.fake.responses[":HISTogram:ENABle?"] = "MAYBE"
        with self.assertRaisesRegex(ValueError, "enabled state"):
            read_histogram(self.scope)
        self.fake.responses[":HISTogram:ENABle?"] = "0"
        self.fake.responses[":HISTogram:HEIGht?"] = "5"
        with self.assertRaisesRegex(ValueError, "out-of-range"):
            read_histogram(self.scope)
        self.fake.responses[":HISTogram:HEIGht?"] = "2"
        self.fake.ignore_writes = True
        with self.assertRaisesRegex(RuntimeError, "histogram readback mismatch"):
            configure_histogram(self.scope, HistogramSettings(height_div=3))

    def test_analysis_results_are_useful_data(self):
        peaks = read_fft_search_results(self.scope, 1)
        self.assertEqual(peaks[0].frequency_hz, 2.5e6)
        self.assertEqual(peaks[0].amplitude_unit, "dBV")
        self.assertEqual(peaks[1].frequency_hz, 3500)
        stats = read_histogram_statistics(self.scope)
        self.assertEqual(stats.fields["Sum"], "5hits")
        self.assertEqual(stats.fields["Bin width"], "20ns")


if __name__ == "__main__":
    unittest.main()
