"""Guide-derived model capability and shared-layer checks."""

import unittest

from dho800900 import DHO800900
from dho800900_models import (GUIDE_PUBLICATION, GUIDE_SOFTWARE, MODELS,
                              parse_identity, profile_for, profile_for_identity)
from dho914s_acquisition import configure_settings
from dho914s_afg import DHO914SAFG
from dho914s_channels import read_channel
from dho914s_measurements import Request, StatisticSettings, configure_statistics
from dho914s_recording import Reference
from dho914s_search import SearchSettings, configure_search
from dho914s_timing import LogicAnalyzer
from dho914s_waveforms import DHO800900Waveforms, WaveformRequest
from rigol_dho900 import readback, require_afg_off


class Instrument:
    def __init__(self):
        self.commands = []

    def write(self, command):
        self.commands.append(command)

    def query(self, command):
        self.commands.append(command)
        if command.startswith(":CHANnel") and command.endswith(":DISPlay?"):
            return "1" if command.startswith(":CHANnel1") else "0"
        return '0,"No error"' if command == ":SYSTem:ERRor:NEXT?" else "0"


class ProfileTests(unittest.TestCase):
    def test_identity_reports_guide_alignment_without_guessing_firmware_support(self):
        self.assertEqual(GUIDE_PUBLICATION, "PGA39106-1110")
        self.assertEqual(GUIDE_SOFTWARE, "00.01.03")
        for firmware, expected in (("00.01.03.00.02", "matched"),
                                   ("00.01.05.00.02", "different"),
                                   ("unknown", "unknown")):
            with self.subTest(firmware=firmware):
                result = parse_identity(f"RIGOL TECHNOLOGIES,DHO812,SERIAL,{firmware}")
                self.assertEqual(result.model, "DHO812")
                self.assertEqual(result.guide_status, expected)
        with self.assertRaisesRegex(ValueError, "no model profile"):
            profile_for(object())

    def test_all_eight_guide_models_and_identity(self):
        self.assertEqual(len(MODELS), 8)
        for name, profile in MODELS.items():
            self.assertIs(profile_for_identity(f"RIGOL TECHNOLOGIES,{name},SERIAL,00.01.03"), profile)
            self.assertEqual(profile.analog_channels, 2 if name in {"DHO802", "DHO812"} else 4)
            self.assertEqual(profile.digital_channels, 16 if name.startswith("DHO9") else 0)
            self.assertEqual(profile.afg, name in {"DHO914S", "DHO924S"})
            self.assertEqual(profile.bode, profile.afg)
            self.assertEqual(profile.external_trigger, name in {"DHO802", "DHO812"})
            self.assertEqual(profile.histogram, name.startswith("DHO9"))
            self.assertEqual(profile.lin, name.startswith("DHO9"))
            self.assertEqual(profile.spi_cs, name.startswith("DHO9") or profile.analog_channels == 4)
        with self.assertRaises(ValueError):
            profile_for_identity("RIGOL TECHNOLOGIES,DHO999,TEST,00.01.03")

    def test_sources_and_memory_follow_profile(self):
        two = MODELS["DHO812"]
        self.assertEqual(two.source("CHANnel2"), "CHAN2")
        self.assertEqual(two.source("EXT", external=True), "EXT")
        for source in ("CHAN3", "D0"):
            with self.assertRaises(ValueError):
                two.source(source, digital=True)
        self.assertEqual(two.max_memory_points(1), 25_000_000)
        self.assertEqual(two.max_memory_points(2), 10_000_000)
        self.assertEqual(MODELS["DHO914S"].max_memory_points(4), 10_000_000)
        with self.assertRaises(NotImplementedError):
            two.require("afg")

    def test_shared_transport_and_domain_boundaries(self):
        instrument = Instrument()
        scope = DHO800900(instrument, model="DHO812")
        require_afg_off(scope)
        self.assertEqual(instrument.commands, [])
        for command in (":SOURce:OUTPut:STATe ON", ":BODeplot:RUNStop ON",
                        ":LA:ENABle ON", ":HISTogram:ENABle ON",
                        ":BUS1:LIN:STANdard V2X", ":BUS1:MODE LIN",
                        ":BUS1:SPI:MODE CS", ":BUS1:SPI:SS:SOURce CHANnel2",
                        ":TRIGger:SPI:CS CHANnel2", ":CHANnel3:SCALe 1",
                        ":MEASure:ITEM? FREQuency,D0"):
            with self.subTest(command=command), self.assertRaises((ValueError, NotImplementedError)):
                scope.write(command)
        self.assertEqual(instrument.commands, [])
        scope.write(':CHANnel1:LABel:CONTent "D0 CHAN4 EXT"')
        self.assertEqual(instrument.commands, [':CHANnel1:LABel:CONTent "D0 CHAN4 EXT"'])
        instrument.commands.clear()
        with self.assertRaises(NotImplementedError):
            DHO914SAFG(scope)
        with self.assertRaises(NotImplementedError):
            LogicAnalyzer(scope)
        with self.assertRaises(ValueError):
            DHO800900Waveforms(scope).metadata(WaveformRequest("CHAN3"))
        with self.assertRaises(ValueError):
            DHO800900Waveforms(scope).metadata(WaveformRequest("D0"))
        with self.assertRaises(ValueError):
            read_channel(scope, 3)
        with self.assertRaises(ValueError):
            configure_settings(scope, "CHANnel", {"display": True}, 3)
        with self.assertRaises(NotImplementedError):
            configure_settings(scope, "BODeplot", {"points": 20})
        with self.assertRaises(ValueError):
            configure_statistics(scope, StatisticSettings(10, True),
                                 (Request("FREQUENCY", "D0"),))
        with self.assertRaises(ValueError):
            configure_settings(scope, "ACQuire", {"memory_depth": "50M"})
        with self.assertRaises(ValueError):
            configure_search(scope, SearchSettings(edge_source="CHAN3"))
        with self.assertRaises(ValueError):
            Reference(scope, 1).set_source("D0")
        self.assertEqual(instrument.commands,
                         [":CHANnel1:DISPlay?", ":CHANnel2:DISPlay?"])
        instrument.commands.clear()
        state = readback(scope)
        self.assertEqual(set(state["channels"]), {"rigol_ch1", "rigol_ch2"})
        self.assertNotIn("afg_output", state)
        self.assertFalse(any(":CHANnel3" in command or ":SOURce:" in command
                             for command in instrument.commands))


if __name__ == "__main__":
    unittest.main()
