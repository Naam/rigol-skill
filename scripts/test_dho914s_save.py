import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import dho914s_save as save
from rigol_dho900 import Rigol


class FakeInstrument:
    def __init__(self):
        self.commands = []
        self.values = {
            ":SOURce:OUTPut:STATe?": "0",
            ":TRIGger:STATus?": "STOP",
            ":MASK:OPERate?": "STOP",
            ":MASK:OUTPut:ENABle?": "0",
            ":MASK:ENABle?": "0",
            ":SAVE:IMAGe:INVert?": "0",
            ":SAVE:IMAGe:COLor?": "COL",
            ":SAVE:IMAGe:FORMat?": "PNG",
            ":SAVE:IMAGe:HEADer?": "0",
            ":SAVE:OVERlap?": "0",
            ":SAVE:PREFix?": "Rigol",
            ":SAVE:STATus?": "1",
            ":SAVe:SMB:SERVerpath?": r"\\192.168.0.2\Share",
            ":SAVe:SMB:USERname?": "user",
            ":SAVe:SMB:PASSword?": "secret",
            ":SAVe:SMB:AUToconnect?": "0",
            ":SAVe:SMB:CONState?": "0",
            ":QUICk:OPERation?": "SIM",
            "*OPC?": "1",
            ":SYSTem:ERRor:NEXT?": '0,"No error"',
        }
        self.payload = b"\x89PNGdata"
        self.complete_saves = True
        self.timeout = 5000
        self.load_timeout = None

    @staticmethod
    def _plain(value):
        if len(value) >= 2 and value[0] == value[-1] == '"':
            return value[1:-1].replace('""', '"')
        return value

    def write(self, command):
        self.commands.append(command)
        key, separator, value = command.partition(" ")
        if not separator:
            if command == ":SAVe:SMB:CONNect":
                self.values[":SAVe:SMB:CONState?"] = "1"
            elif command == ":SAVe:SMB:DISConnect":
                self.values[":SAVe:SMB:CONState?"] = "0"
            elif command == ":STOP":
                self.values[":TRIGger:STATus?"] = "STOP"
            return
        value = self._plain(value)
        if key == ":SOURce:OUTPut:STATe":
            self.values[key + "?"] = "1" if value.upper() == "ON" else "0"
        elif key == ":SAVE:IMAGe:COLor" and value.upper() == "COLOR":
            self.values[key + "?"] = "COL"
        elif key == ":QUICk:OPERation":
            aliases = {"SIMAGE": "SIM", "SWAVE": "SWAV", "SSETUP": "SSET",
                       "AMEASURE": "AME", "SRESET": "SRES", "RECORD": "REC",
                       "SSAVE": "SSAV"}
            self.values[key + "?"] = aliases[value.upper()]
        elif key == ":SAVE:IMAGe:INVert" or key == ":SAVE:IMAGe:HEADer" or \
                key == ":SAVE:OVERlap" or key == ":SAVe:SMB:AUToconnect":
            self.values[key + "?"] = "1" if value.upper() in {"ON", "1"} else "0"
        elif key == ":LOAD:SETup":
            self.load_timeout = self.timeout
            self.values[":SOURce:OUTPut:STATe?"] = "1"
            self.values[":TRIGger:STATus?"] = "RUN"
            self.values[":MASK:OPERate?"] = "RUN"
            self.values[":MASK:OUTPut:ENABle?"] = "1"
            self.values[":MASK:ENABle?"] = "1"
        elif key == ":MASK:OPERate":
            self.values[key + "?"] = value
        elif key in {":MASK:OUTPut:ENABle", ":MASK:ENABle"}:
            self.values[key + "?"] = "1" if value.upper() in {"ON", "1"} else "0"
        else:
            self.values[key + "?"] = value
            if key in {":SAVE:IMAGe", ":SAVE:SETup", ":SAVE:WAVeform",
                       ":SAVE:MEMory:WAVeform"} and not self.complete_saves:
                self.values[":SAVE:STATus?"] = "0"

    def query(self, command):
        self.commands.append(command)
        if command not in self.values:
            raise AssertionError(f"unexpected query: {command}")
        return self.values[command]

    def query_binary_values(self, command, **_kwargs):
        self.commands.append(command)
        return self.payload


class SaveApiTests(unittest.TestCase):
    def setUp(self):
        self.instrument = FakeInstrument()
        self.scope = Rigol(self.instrument)

    def test_save_preferences_and_quick_operation_readback(self):
        state = save.configure_save_preferences(
            self.scope,
            save.SavePreferences(image_invert=True, image_color="GRAY", image_format="JPG",
                                 image_header=True, prefix="Bench_1"))
        self.assertTrue(state.image_invert)
        self.assertEqual((state.image_color, state.image_format, state.prefix),
                         ("GRAY", "JPG", "Bench_1"))
        with self.assertRaises(PermissionError):
            save.configure_save_preferences(self.scope, save.SavePreferences(overwrite=True))
        state = save.configure_save_preferences(self.scope,
                                                save.SavePreferences(overwrite=True),
                                                confirm_overwrite=True)
        self.assertTrue(state.overwrite)
        for color in ("COLOR", "GRAY"):
            self.assertEqual(save.configure_save_preferences(
                self.scope, save.SavePreferences(image_color=color)).image_color, color)
        for image_format in ("PNG", "BMP", "JPG"):
            self.assertEqual(save.configure_save_preferences(
                self.scope, save.SavePreferences(image_format=image_format)).image_format,
                image_format)
        for operation in save._QUICK_OPERATIONS:
            self.assertEqual(save.configure_quick_operation(self.scope, operation), operation)
            self.assertEqual(save.read_quick_operation(self.scope), operation)
        self.assertIn(":QUICk:OPERation SRESET", self.instrument.commands)

    def test_image_data_binary_and_save_status(self):
        self.assertEqual(save.image_data(self.scope), b"\x89PNGdata")
        self.assertTrue(save.save_status(self.scope))
        self.assertIn(":SAVE:IMAGe:DATA?", self.instrument.commands)

    def test_all_instrument_save_file_kinds_and_overlap_restore(self):
        operations = (
            (save.save_image, "C:/screen.png", ":SAVE:IMAGe"),
            (save.save_image, "C:/screen.bmp", ":SAVE:IMAGe"),
            (save.save_image, "C:/screen.jpg", ":SAVE:IMAGe"),
            (save.save_setup, "D:/bench.stp", ":SAVE:SETup"),
            (save.save_waveform, "E:/trace.bin", ":SAVE:WAVeform"),
            (save.save_waveform, "E:/trace.csv", ":SAVE:WAVeform"),
            (save.save_memory_waveform, "D:/memory.bin", ":SAVE:MEMory:WAVeform"),
            (save.save_memory_waveform, "D:/memory.csv", ":SAVE:MEMory:WAVeform"),
            (save.save_memory_waveform, "D:/memory.wfm", ":SAVE:MEMory:WAVeform"),
            (save.save_memory_waveform, "F:/external.wfm", ":SAVE:MEMory:WAVeform"),
        )
        for function, path, command in operations:
            result = function(self.scope, path)
            self.assertEqual(result.path, path)
            self.assertTrue(any(item.startswith(command + " ") for item in self.instrument.commands))
            self.assertEqual(self.instrument.values[":SAVE:OVERlap?"], "0")
        self.instrument.values[":SAVE:OVERlap?"] = "1"
        result = save.save_image(self.scope, "C:/replace.jpg", confirm_overwrite=False)
        self.assertEqual(result.kind, "image")
        self.assertEqual(self.instrument.values[":SAVE:OVERlap?"], "1")
        with self.assertRaises(ValueError):
            save.save_setup(self.scope, "C:/../unsafe.stp")

    def test_overwrite_requires_explicit_confirmation_and_restores_setting(self):
        self.instrument.values[":SAVE:OVERlap?"] = "0"
        with self.assertRaises(ValueError):
            save.save_image(self.scope, "C:/replace.png", confirm_overwrite=1)
        save.save_image(self.scope, "C:/replace.png", confirm_overwrite=True)
        self.assertEqual(self.instrument.values[":SAVE:OVERlap?"], "0")
        self.assertIn(":SAVE:OVERlap ON", self.instrument.commands)
        self.assertIn(":SAVE:OVERlap OFF", self.instrument.commands)

    def test_busy_or_timed_out_save_is_reported_and_overlap_is_restored(self):
        self.instrument.values[":SAVE:STATus?"] = "0"
        writes_before = list(self.instrument.commands)
        with self.assertRaises(RuntimeError):
            save.save_image(self.scope, "C:/busy.png")
        self.assertFalse(any(item.startswith(":SAVE:IMAGe ") for item in
                             self.instrument.commands[len(writes_before):]))
        self.instrument.values[":SAVE:STATus?"] = "1"
        self.instrument.complete_saves = False
        with self.assertRaises(TimeoutError):
            save.save_image(self.scope, "C:/slow.png", confirm_overwrite=True,
                            timeout_s=0.1)
        self.assertEqual(self.instrument.values[":SAVE:OVERlap?"], "0")
        self.assertEqual(self.instrument.values[":SOURce:OUTPut:STATe?"], "0")

    def test_smb_credentials_config_connect_disconnect_and_secret_read(self):
        state = save.configure_smb(self.scope, save.SmbSettings(
            server_path=r"\\192.168.1.4\ScopeShare", username="bench",
            password="pw!123", autoconnect=True))
        self.assertEqual(state.server_path, r"\\192.168.1.4\ScopeShare")
        self.assertTrue(state.autoconnect)
        self.assertEqual(save.read_smb_password(self.scope), "pw!123")
        self.assertTrue(save.connect_smb(self.scope).connected)
        self.assertFalse(save.disconnect_smb(self.scope).connected)
        before = len(self.instrument.commands)
        with self.assertRaises(ValueError):
            save.configure_smb(self.scope, save.SmbSettings(server_path=r"\\999.1.1.1\share"))
        self.assertEqual(len(self.instrument.commands), before)

    def test_setup_load_requires_confirmation_and_leaves_afg_off(self):
        before = len(self.instrument.commands)
        with self.assertRaises(PermissionError):
            save.load_setup(self.scope, "D:/bench.stp")
        self.assertEqual(len(self.instrument.commands), before)
        self.instrument.timeout = 12000
        self.instrument.values[":SOURce:OUTPut:STATe?"] = "1"
        self.assertEqual(save.load_setup(self.scope, "D:/bench.stp", confirm_no_dut=True),
                         "D:/bench.stp")
        self.assertEqual(self.instrument.values[":SOURce:OUTPut:STATe?"], "0")
        self.assertEqual(self.instrument.values[":TRIGger:STATus?"], "STOP")
        self.assertEqual(self.instrument.values[":MASK:OPERate?"], "STOP")
        self.assertEqual(self.instrument.values[":MASK:OUTPut:ENABle?"], "0")
        self.assertEqual(self.instrument.values[":MASK:ENABle?"], "0")
        self.assertEqual(self.instrument.timeout, 12000)
        self.assertEqual(self.instrument.load_timeout, 5000)
        self.assertIn(":LOAD:SETup \"D:/bench.stp\"", self.instrument.commands)

    def test_failed_recall_still_disables_afg_and_restores_timeout(self):
        self.instrument.values["*OPC?"] = "0"
        self.instrument.values[":SOURce:OUTPut:STATe?"] = "1"
        self.instrument.timeout = 9000
        with self.assertRaises(RuntimeError):
            save.load_setup(self.scope, "D:/bench.stp", confirm_no_dut=True)
        self.assertEqual(self.instrument.values[":SOURce:OUTPut:STATe?"], "0")
        self.assertEqual(self.instrument.values[":TRIGger:STATus?"], "STOP")
        self.assertEqual(self.instrument.values[":MASK:OPERate?"], "STOP")
        self.assertEqual(self.instrument.values[":MASK:OUTPut:ENABle?"], "0")
        self.assertEqual(self.instrument.values[":MASK:ENABle?"], "0")
        self.assertEqual(self.instrument.timeout, 9000)
        self.assertEqual(self.instrument.load_timeout, 5000)

    def test_guide_command_matrix_exercises_every_save_load_and_quick_leaf(self):
        save.configure_save_preferences(self.scope, save.SavePreferences(
            image_invert=True, image_color="GRAY", image_format="BMP", image_header=True,
            overwrite=True, prefix="Pfx"), confirm_overwrite=True)
        save.image_data(self.scope)
        save.save_image(self.scope, "C:/img.png")
        save.save_setup(self.scope, "C:/setup.stp")
        save.save_waveform(self.scope, "C:/wave.csv")
        save.save_memory_waveform(self.scope, "C:/memory.wfm")
        save.save_status(self.scope)
        save.configure_smb(self.scope, save.SmbSettings(
            server_path=r"\\192.168.1.2\Share", username="user",
            password="secret", autoconnect=True))
        save.read_smb_password(self.scope)
        save.connect_smb(self.scope)
        save.disconnect_smb(self.scope)
        save.read_smb(self.scope)
        save.load_setup(self.scope, "C:/setup.stp", confirm_no_dut=True)
        save.configure_quick_operation(self.scope, "SWAVE")
        save.read_quick_operation(self.scope)

        commands = set(self.instrument.commands)
        expected = {
            ":SAVE:IMAGe:INVert ON", ":SAVE:IMAGe:INVert?",
            ":SAVE:IMAGe:COLor GRAY", ":SAVE:IMAGe:COLor?",
            ":SAVE:IMAGe:FORMat BMP", ":SAVE:IMAGe:FORMat?",
            ":SAVE:IMAGe:HEADer ON", ":SAVE:IMAGe:HEADer?",
            ":SAVE:IMAGe:DATA?", ':SAVE:IMAGe "C:/img.png"',
            ':SAVE:SETup "C:/setup.stp"', ':SAVE:WAVeform "C:/wave.csv"',
            ':SAVE:MEMory:WAVeform "C:/memory.wfm"', ":SAVE:STATus?",
            ":SAVE:OVERlap ON", ":SAVE:OVERlap?", ':SAVE:PREFix "Pfx"',
            ":SAVE:PREFix?", ':SAVe:SMB:SERVerpath "\\\\192.168.1.2\\Share"',
            ":SAVe:SMB:SERVerpath?", ':SAVe:SMB:USERname "user"',
            ":SAVe:SMB:USERname?", ':SAVe:SMB:PASSword "secret"',
            ":SAVe:SMB:PASSword?", ":SAVe:SMB:AUToconnect ON",
            ":SAVe:SMB:AUToconnect?", ":SAVe:SMB:CONNect", ":SAVe:SMB:DISConnect",
            ":SAVe:SMB:CONState?", ':LOAD:SETup "C:/setup.stp"',
            ":QUICk:OPERation SWAVE", ":QUICk:OPERation?",
            ":STOP", ":MASK:OPERate STOP", ":MASK:OUTPut:ENABle OFF",
            ":MASK:ENABle OFF", ":SOURce:OUTPut:STATe OFF",
        }
        self.assertEqual(expected - commands, set())


if __name__ == "__main__":
    unittest.main()
