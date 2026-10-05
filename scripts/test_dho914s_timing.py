import unittest

from dho914s_timing import LogicAnalyzer, Timebase


from dho800900_models import MODELS


class FakeScope:
    profile = MODELS["DHO914S"]
    def __init__(self):
        self.commands = []
        self.queries = []
        self.la = {"enabled": "0", "active": "D0", "sort": "D15D0", "size": "MED"}
        self.channels = {f"D{i}": {"enabled": "0", "label": f"D{i}"} for i in range(16)}
        self.pods = {1: {"display": "0", "threshold": "1.4"},
                     2: {"display": "0", "threshold": "1.4"}}
        self.tb = {"delay_enabled": "0", "delay_offset": "0", "delay_scale": "0.2",
                   "main_offset": "0", "main_scale": "1", "mode": "MAIN",
                   "href_mode": "CENT", "href_pos": "0", "vernier": "0",
                   "roll": "1", "xy_enabled": "0", "x": "CHAN1", "y": "CHAN2",
                   "z": "NONE", "grid": "FULL"}
        self.trigger_status = "RUN"

    def write(self, command):
        self.commands.append(command)
        if command.startswith(":LA:ENABle "):
            self.la["enabled"] = "1" if command.endswith("ON") else "0"
        elif command.startswith(":LA:ACTive "):
            self.la["active"] = command.split(" ", 1)[1]
        elif command.startswith(":LA:AUTosort "):
            self.la["sort"] = command.split(" ", 1)[1]
        elif command.startswith(":LA:DIGital:ENABle "):
            channel, state = command.split(" ", 1)[1].split(",")
            self.channels[channel]["enabled"] = "1" if state == "ON" else "0"
        elif command.startswith(":LA:DIGital:LABel "):
            channel, label = command.split(" ", 1)[1].split(",", 1)
            self.channels[channel]["label"] = label[1:-1].replace('""', '"')
        elif command.startswith(":LA:POD"):
            pod = int(command[len(":LA:POD")])
            if ":DISPlay " in command:
                self.pods[pod]["display"] = "1" if command.endswith("ON") else "0"
            elif ":THReshold " in command:
                self.pods[pod]["threshold"] = command.rsplit(" ", 1)[1]
        elif command.startswith(":LA:SIZE "):
            self.la["size"] = {"SMALl": "SMAL", "MEDium": "MED", "LARGe": "LARG"}[command.split(" ", 1)[1]]
        elif command.startswith(":TIMebase"):
            head, value = command.split(" ", 1)
            key = {
                ":TIMebase:DELay:ENABle": "delay_enabled", ":TIMebase:DELay:OFFSet": "delay_offset",
                ":TIMebase:DELay:SCALe": "delay_scale", ":TIMebase:MAIN:OFFSet": "main_offset",
                ":TIMebase:MAIN:SCALe": "main_scale", ":TIMebase:OFFSet": "main_offset",
                ":TIMebase:SCALe": "main_scale", ":TIMebase": "main_offset",
                ":TIMebase:MAIN": "main_offset", ":TIMebase:MODE": "mode",
                ":TIMebase:HREFerence:MODE": "href_mode", ":TIMebase:HREFerence:POSition": "href_pos",
                ":TIMebase:VERNier": "vernier", ":TIMebase:ROLL": "roll",
                ":TIMebase:XY:ENABle": "xy_enabled", ":TIMebase:XY:X": "x",
                ":TIMebase:XY:Y": "y", ":TIMebase:XY:Z": "z", ":TIMebase:XY:GRID": "grid",
            }.get(head)
            if key:
                if key in {"delay_enabled", "vernier", "xy_enabled"}:
                    value = "1" if value == "ON" else "0"
                self.tb[key] = value
                if key == "mode" and value == "XY":
                    self.tb["mode"] = "MAIN"
                    self.tb["xy_enabled"] = "1"
                if key == "mode" and value == "MAIN":
                    self.tb["xy_enabled"] = "0"

    def query(self, command):
        self.queries.append(command)
        if command == ":TRIGger:STATus?":
            return self.trigger_status
        if command == ":LA:ENABle?":
            return self.la["enabled"]
        if command == ":LA:ACTive?":
            return self.la["active"]
        if command == ":LA:AUTosort?":
            return self.la["sort"]
        if command == ":LA:SIZE?":
            return self.la["size"]
        if command.startswith(":LA:DIGital:ENABle? "):
            return self.channels[command.rsplit(" ", 1)[1]]["enabled"]
        if command.startswith(":LA:DIGital:LABel? "):
            return self.channels[command.rsplit(" ", 1)[1]]["label"]
        if command.startswith(":LA:POD"):
            pod = int(command[len(":LA:POD")])
            return self.pods[pod]["display" if ":DISPlay?" in command else "threshold"]
        mapping = {
            ":TIMebase:DELay:ENABle?": "delay_enabled", ":TIMebase:DELay:OFFSet?": "delay_offset",
            ":TIMebase:DELay:SCALe?": "delay_scale", ":TIMebase:MAIN:OFFSet?": "main_offset",
            ":TIMebase:MAIN:SCALe?": "main_scale", ":TIMebase:OFFSet?": "main_offset",
            ":TIMebase:SCALe?": "main_scale", ":TIMebase?": "main_offset",
            ":TIMebase:MAIN?": "main_offset", ":TIMebase:MODE?": "mode",
            ":TIMebase:HREFerence:MODE?": "href_mode", ":TIMebase:HREFerence:POSition?": "href_pos",
            ":TIMebase:VERNier?": "vernier", ":TIMebase:ROLL?": "roll",
            ":TIMebase:XY:ENABle?": "xy_enabled", ":TIMebase:XY:X?": "x",
            ":TIMebase:XY:Y?": "y", ":TIMebase:XY:Z?": "z", ":TIMebase:XY:GRID?": "grid",
        }
        if command in mapping:
            return self.tb[mapping[command]]
        raise KeyError(command)

    def errors(self):
        return ['0,"No error"']


class LogicAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()
        self.la = LogicAnalyzer(self.scope)

    def test_settings_enable_channel_sort_label_and_active_queries(self):
        state = self.la.settings()
        expected = {":LA:ENABle?", ":LA:ACTive?", ":LA:AUTosort?", ":LA:SIZE?"}
        expected.update(f":LA:DIGital:{field}? D{i}" for i in range(16)
                        for field in ("ENABle", "LABel"))
        expected.update(f":LA:POD{pod}:{field}?" for pod in (1, 2)
                        for field in ("DISPlay", "THReshold"))
        self.assertEqual(set(self.scope.queries), expected)
        self.assertEqual(len(state.channels), 16)
        self.assertEqual(state.channels[15].name, "D15")
        self.assertFalse(self.la.enable(True) is False)
        self.la.set_channel_enabled("D3", True)
        self.assertEqual(self.la.set_active("D3"), "D3")
        self.assertEqual(self.la.set_auto_sort("D0D15"), "D0D15")
        self.assertEqual(self.la.set_label("D3", "CLK"), "CLK")
        self.la.set_active(None)
        self.assertIn(":LA:ENABle ON", self.scope.commands)
        self.assertIn(":LA:DIGital:ENABle D3,ON", self.scope.commands)
        self.assertIn(":LA:ACTive D3", self.scope.commands)
        self.assertIn(":LA:AUTosort D0D15", self.scope.commands)
        self.assertIn(":LA:DIGital:LABel D3,\"CLK\"", self.scope.commands)
        with self.assertRaises(ValueError):
            self.la.set_active("D4")

    def test_pods_size_and_group_action_use_documented_limits(self):
        for pod_index in (1, 2):
            pod = self.la.set_pod(pod_index, displayed=True, threshold_v=20 - pod_index)
            self.assertEqual((pod.index, pod.displayed, pod.threshold_v),
                             (pod_index, True, float(20 - pod_index)))
        with self.assertRaises(ValueError):
            self.la.set_pod(1, threshold_v=20.1)
        for size in ("SMALL", "MEDIUM", "LARGE"):
            self.la.set_waveform_size(size)
        for i in range(16):
            self.la.set_channel_enabled(f"D{i}", True)
            self.la.set_channel_enabled(f"D{i}", False)
        for i in range(9):
            self.la.set_channel_enabled(f"D{i}", True)
        with self.assertRaises(ValueError):
            self.la.set_waveform_size("LARGE")
        for group in (1, 2, 3, 4):
            self.la.delete_group(group)
        for pod_index in (1, 2):
            self.assertIn(f":LA:POD{pod_index}:DISPlay ON", self.scope.commands)
            self.assertIn(f":LA:POD{pod_index}:THReshold {20 - pod_index}", self.scope.commands)
        for size_command in (":LA:SIZE SMALl", ":LA:SIZE MEDium", ":LA:SIZE LARGe"):
            self.assertIn(size_command, self.scope.commands)
        for channel in (f"D{i}" for i in range(16)):
            self.assertIn(f":LA:DIGital:ENABle {channel},ON", self.scope.commands)
            self.assertIn(f":LA:DIGital:ENABle {channel},OFF", self.scope.commands)
        for group in (1, 2, 3, 4):
            self.assertIn(f":LA:DELete GROup{group}", self.scope.commands)
        self.assertIn(":LA:SIZE LARGe", self.scope.commands)
        with self.assertRaises(ValueError):
            self.la.delete_group(5)


class TimebaseTests(unittest.TestCase):
    def setUp(self):
        self.scope = FakeScope()
        self.tb = Timebase(self.scope)

    def test_complete_state_and_main_timebase_configuration(self):
        state = self.tb.settings()
        self.assertEqual(set(self.scope.queries), {
            ":TIMebase:DELay:ENABle?", ":TIMebase:DELay:OFFSet?", ":TIMebase:DELay:SCALe?",
            ":TIMebase:MAIN:OFFSet?", ":TIMebase:MAIN:SCALe?", ":TIMebase:MODE?",
            ":TIMebase:HREFerence:MODE?", ":TIMebase:HREFerence:POSition?",
            ":TIMebase:VERNier?", ":TIMebase:ROLL?", ":TIMebase:XY:ENABle?",
            ":TIMebase:XY:X?", ":TIMebase:XY:Y?", ":TIMebase:XY:Z?", ":TIMebase:XY:GRID?",
        })
        self.assertEqual((state.main_scale_s_per_div, state.mode, state.xy_x, state.xy_grid),
                         (1.0, "MAIN", "CHAN1", "FULL"))
        state = self.tb.configure_main(scale_s_per_div=0.1, offset_s=1.0, mode="ROLL",
                                       horizontal_reference="USER", horizontal_position=125,
                                       vernier=True, auto_roll=False)
        self.assertEqual((state.main_scale_s_per_div, state.main_offset_s, state.mode,
                          state.horizontal_reference, state.horizontal_position,
                          state.vernier, state.auto_roll),
                         (0.1, 1.0, "ROLL", "USER", 125, True, False))
        with self.assertRaises(ValueError):
            self.tb.configure_main(scale_s_per_div=0)
        with self.assertRaises(ValueError):
            self.tb.configure_main(horizontal_position=501)
        with self.assertRaises(ValueError):
            self.tb.configure_main(offset_s=11)
        self.tb.configure_main(mode="XY")
        self.assertEqual(self.tb.settings().mode, "MAIN")
        self.assertTrue(self.tb.settings().xy_enabled)
        self.assertIn(":TIMebase:MAIN:SCALe 0.1", self.scope.commands)
        self.assertIn(":TIMebase:MAIN:OFFSet 1", self.scope.commands)
        self.assertIn(":TIMebase:MODE XY", self.scope.commands)
        self.assertIn(":TIMebase:HREFerence:MODE USER", self.scope.commands)
        self.assertIn(":TIMebase:HREFerence:POSition 125", self.scope.commands)
        self.assertIn(":TIMebase:VERNier ON", self.scope.commands)
        self.assertIn(":TIMebase:ROLL 0", self.scope.commands)

    def test_optional_main_scale_and_offset_headers_for_set_and_query(self):
        for form in ("BASE", "MAIN"):
            self.scope.tb["main_scale"] = "1"
            self.assertEqual(self.tb.main_scale(form=form), 1.0)
            self.assertEqual(self.tb.main_scale(0.2, form=form), 0.2)
        for form in ("BASE", "MAIN", "OFFSET", "MAIN_OFFSET"):
            self.scope.tb["main_offset"] = "0"
            self.assertEqual(self.tb.main_offset(form=form), 0.0)
            self.assertEqual(self.tb.main_offset(0.1, form=form), 0.1)
        self.assertTrue({":TIMebase:SCALe 0.2", ":TIMebase:MAIN:SCALe 0.2"}.issubset(set(self.scope.commands)))
        self.assertTrue({":TIMebase 0.1", ":TIMebase:MAIN 0.1", ":TIMebase:OFFSet 0.1",
                         ":TIMebase:MAIN:OFFSet 0.1"}.issubset(set(self.scope.commands)))
        self.assertTrue({":TIMebase:SCALe?", ":TIMebase:MAIN:SCALe?", ":TIMebase?",
                         ":TIMebase:MAIN?", ":TIMebase:OFFSet?", ":TIMebase:MAIN:OFFSet?"}
                        .issubset(set(self.scope.queries)))

    def test_delay_xy_and_run_hotkeys(self):
        result = self.tb.configure_delay(enabled=True, scale_s_per_div=0.5, offset_s=0)
        self.assertTrue(result.delayed_enabled)
        with self.assertRaises(ValueError):
            self.tb.configure_delay(scale_s_per_div=2)
        with self.assertRaises(ValueError):
            self.tb.configure_delay(scale_s_per_div=0.3)
        with self.assertRaises(ValueError):
            self.tb.configure_delay(offset_s=5)
        result = self.tb.configure_xy(enabled=True, x="CHANnel3", y="CHAN4", z="NONE", grid="HALF")
        self.assertTrue(result.xy_enabled)
        self.assertIn(":TIMebase:XY:X CHANnel3", self.scope.commands)
        self.assertIn(":TIMebase:XY:Y CHANnel4", self.scope.commands)
        self.assertIn(":TIMebase:XY:Z NONE", self.scope.commands)
        self.assertIn(":TIMebase:XY:GRID HALF", self.scope.commands)
        self.assertIn(":TIMebase:XY:ENABle ON", self.scope.commands)
        with self.assertRaises(ValueError):
            self.tb.configure_xy(x="D0")
        with self.assertRaises(ValueError):
            self.tb.hotkey("RUN")
        self.tb.hotkey("STOP", confirm=True)
        self.tb.hotkey("RUN", confirm=True)
        self.tb.hotkey("SINGLE", confirm=True)
        self.assertIn(":TIMebase:HOTKeys STOP", self.scope.commands)
        self.assertIn(":TIMebase:HOTKeys RUN", self.scope.commands)
        self.assertIn(":TIMebase:HOTKeys SINGle", self.scope.commands)


if __name__ == "__main__":
    unittest.main()
