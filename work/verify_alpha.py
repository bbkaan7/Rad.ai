"""Side-effect-free checks with desktop, network and OCR mocks."""
import importlib.util
import sys
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1] / "outputs" / "sohbet_alpha"
sys.path.insert(0, str(ROOT))
stubs = {name: MagicMock() for name in (
    "ctypes", "cv2", "keyboard", "mss", "pyautogui", "pytesseract", "requests"
)}
stubs["pyautogui"].FailSafeException = type("FailSafeException", (Exception,), {})
with patch.dict(sys.modules, stubs):
    spec = importlib.util.spec_from_file_location("alpha", ROOT / "main.py")
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)


class AlphaTests(unittest.TestCase):
    def setUp(self):
        bot.stop_event.clear()
        bot.trigger_event.clear()
        if bot.busy_lock.locked():
            bot.busy_lock.release()
        for stub in stubs.values():
            stub.reset_mock()

    def test_multiline_message(self):
        self.assertEqual(bot.clean_message("  Hello\n how are you?\x0c "), "Hello how are you?")

    def test_api_contract_and_empty_response(self):
        bot.requests.post.return_value.json.return_value = {"response": "Fine\n thanks"}
        self.assertEqual(bot.generate_reply("Hi"), "Fine thanks")
        self.assertFalse(bot.requests.post.call_args.kwargs["json"]["stream"])
        bot.requests.post.return_value.json.return_value = {"response": " "}
        with self.assertRaises(ValueError):
            bot.generate_reply("Hi")

    def test_api_error_is_reported_in_english(self):
        bot.requests.post.return_value.json.return_value = {"error": "model not found"}
        with self.assertRaisesRegex(ValueError, "Ollama error: model not found"):
            bot.generate_reply("Hi")

    def test_version_matches_release_file(self):
        self.assertEqual(bot.VERSION, (ROOT / "VERSION").read_text().strip())
        with patch.object(sys, "argv", ["main.py", "--version"]), \
             patch.object(bot, "run_cycle") as cycle:
            with self.assertRaises(SystemExit) as exit_result:
                bot.main()
            self.assertEqual(exit_result.exception.code, 0)
            cycle.assert_not_called()

    def test_missing_template_does_not_click(self):
        self.assertFalse(bot.find_and_click(ROOT / "missing.png"))
        bot.pyautogui.click.assert_not_called()

    def test_failed_textbox_stops_before_typing(self):
        with patch.object(bot, "capture_screen", return_value=(None, None)), \
             patch.object(bot, "read_text", return_value="Hi"), \
             patch.object(bot, "generate_reply", return_value="Hello"), \
             patch.object(bot, "find_and_click", return_value=False), \
             patch.object(bot, "type_reply") as write:
            bot.run_cycle()
            write.assert_not_called()

    def test_unicode_and_ascii(self):
        with patch.object(bot.time, "sleep"):
            bot.type_reply("aé")
        bot.pyautogui.write.assert_called_once_with("a", interval=0.05)
        bot.keyboard.write.assert_called_once_with("é", exact=True)

    def test_stop_prevents_typing(self):
        bot.stop_event.set()
        with self.assertRaises(InterruptedError):
            bot.type_reply("a")
        bot.pyautogui.write.assert_not_called()

    def test_busy_trigger_not_queued(self):
        bot.trigger_cycle()
        self.assertTrue(bot.trigger_event.is_set())
        bot.trigger_event.clear()
        bot.trigger_cycle()
        self.assertFalse(bot.trigger_event.is_set())

    def test_key_diagnostic_never_runs_chat(self):
        with patch.object(sys, "argv", ["main.py", "--key-test"]), \
             patch.object(bot.os, "name", "posix"), \
             patch.object(bot.threading, "Event") as event, \
             patch.object(bot, "run_cycle") as chat:
            event.return_value.wait.side_effect = KeyboardInterrupt
            bot.main()
            chat.assert_not_called()
            bot.keyboard.unhook.assert_called_once()

    def test_alternative_hotkey_registered(self):
        with patch.object(sys, "argv", ["main.py"]), \
             patch.object(bot.os, "name", "posix"), \
             patch.object(bot.trigger_event, "wait", side_effect=KeyboardInterrupt):
            bot.main()
        keys = [call.args[0] for call in bot.keyboard.add_hotkey.call_args_list]
        self.assertEqual(keys, ["f9", "ctrl+alt+9", "f10"])
        callbacks = [call.args[1] for call in bot.keyboard.add_hotkey.call_args_list]
        self.assertEqual(len(set(callbacks)), 3)
        self.assertEqual(bot.keyboard.remove_hotkey.call_count, 3)

    def poll_frames(self, frames, test=False):
        with patch.object(bot, "windows_key_reader", return_value=MagicMock(side_effect=frames)), \
             patch.object(bot.stop_event, "wait", side_effect=[False] * len(frames) + [True]), \
             patch.object(bot, "trigger_cycle") as trigger:
            bot.windows_key_listener(test=test)
            return trigger.call_count

    def test_windows_held_key_fires_once_on_release(self):
        self.assertEqual(self.poll_frames([set(), {"f9"}, {"f9"}, set(), set()]), 1)

    def test_windows_combo_waits_for_all_releases(self):
        self.assertEqual(self.poll_frames([{"ctrl", "alt", "9"}, {"ctrl", "alt"}]), 0)
        self.assertEqual(self.poll_frames([{"ctrl", "alt", "9"}, {"ctrl"}, set()]), 1)

    def test_windows_diagnostic_does_not_trigger(self):
        self.assertEqual(self.poll_frames([{"f9"}, set()], test=True), 0)

    def test_windows_busy_press_is_discarded(self):
        bot.busy_lock.acquire()
        self.assertEqual(self.poll_frames([{"f9"}, set()]), 0)

    def test_windows_f10_has_priority(self):
        self.assertEqual(self.poll_frames([{"f9"}, {"f10"}]), 0)
        self.assertTrue(bot.stop_event.is_set())

    def test_windows_main_does_not_install_keyboard_hooks(self):
        with patch.object(sys, "argv", ["main.py"]), \
             patch.object(bot.os, "name", "nt"), \
             patch.object(bot.threading, "Thread") as thread, \
             patch.object(bot.trigger_event, "wait", side_effect=KeyboardInterrupt):
            bot.main()
            thread.return_value.start.assert_called_once()
            thread.return_value.join.assert_called_once()
        bot.keyboard.add_hotkey.assert_not_called()
        bot.keyboard.hook.assert_not_called()

    def test_template_threshold_and_offset(self):
        import numpy as np
        template = np.array([[0, 255], [255, 0]], dtype=np.uint8)
        reference = MagicMock()
        reference.is_file.return_value = True
        bot.cv2.imdecode.return_value = template
        bot.cv2.cvtColor.return_value = np.zeros((20, 20), dtype=np.uint8)
        with patch.object(bot.np, "fromfile", return_value=template), \
             patch.object(bot, "capture_screen", return_value=(None, (100, 200))):
            bot.cv2.minMaxLoc.return_value = (0, 0.95, (0, 0), (5, 6))
            self.assertEqual(bot.find_element(reference), (106, 207))
            bot.cv2.minMaxLoc.return_value = (0, 0.5, (0, 0), (5, 6))
            self.assertIsNone(bot.find_element(reference))


if __name__ == "__main__":
    unittest.main(verbosity=2)
