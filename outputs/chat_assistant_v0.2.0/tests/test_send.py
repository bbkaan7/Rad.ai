"""Submission paths tested with all keyboard/mouse actions mocked."""

import unittest
from unittest.mock import patch
from contextlib import ExitStack
from assistant.core import Observation

try:
    from assistant.desktop import Desktop
except (ImportError, OSError, AttributeError):
    Desktop = None


@unittest.skipIf(Desktop is None, "Windows desktop dependencies required")
class SendTests(unittest.TestCase):
    def run_send(self, method, observations):
        driver = object.__new__(Desktop)
        driver.profile = {"send_method": method}
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "observe", side_effect=observations))
            stack.enter_context(patch.object(driver, "check"))
            click = stack.enter_context(patch.object(driver, "click"))
            write = stack.enter_context(patch("assistant.desktop.pyautogui.write"))
            press = stack.enter_context(patch("assistant.desktop.pyautogui.press"))
            try:
                result = driver.send(Observation("chat", "Hi"), "Hello")
                error = None
            except ValueError as exc:
                result, error = None, exc
        return result, error, click, write, press

    def test_enter_submits_once_and_requires_manual_verification_without_bubbles(self):
        observed = Observation("chat", "Hi")
        result, error, click, write, press = self.run_send("enter", [observed, observed])
        self.assertFalse(result)
        self.assertIsNone(error)
        click.assert_called_once_with("empty_textbox")
        press.assert_called_once_with("enter")
        self.assertEqual(write.call_count, 5)

    def test_button_submission_does_not_press_enter(self):
        observed = Observation("chat", "Hi")
        _, error, click, _, press = self.run_send("button", [observed, observed])
        self.assertIsNone(error)
        self.assertEqual([call.args[0] for call in click.call_args_list], ["empty_textbox", "send"])
        press.assert_not_called()

    def test_incoming_change_after_typing_blocks_submission(self):
        _, error, click, _, press = self.run_send("enter", [Observation("chat", "Hi"), Observation("chat", "Wait")])
        self.assertIn("during typing", str(error))
        click.assert_called_once_with("empty_textbox")
        press.assert_not_called()

    def test_changed_recipient_blocks_all_input(self):
        _, error, click, write, press = self.run_send("enter", [Observation("other", "Hi")])
        self.assertIsNotNone(error)
        click.assert_not_called()
        write.assert_not_called()
        press.assert_not_called()

    def test_pending_recovery_rejects_mismatched_text_without_typing(self):
        import numpy as np
        driver = object.__new__(Desktop)
        driver.scale = 1
        driver.profile = {"draft_from_anchor": {"x": 10, "top": -10, "width": 80, "height": 20}}
        expected = Observation("chat", "Hi")
        with patch.object(driver, "observe", return_value=expected), \
             patch.object(driver, "capture", return_value=(np.zeros((100,100,3), dtype=np.uint8), {})), \
             patch.object(driver, "find", return_value=(5,50)), \
             patch.object(driver, "ocr", return_value="Different draft"), \
             patch.object(driver, "submit_and_verify") as submit, \
             patch("assistant.desktop.pyautogui.write") as write:
            with self.assertRaisesRegex(ValueError, "does not exactly match"):
                driver.finish_pending(expected, "Hello")
        submit.assert_not_called()
        write.assert_not_called()

    def test_pending_recovery_checks_exact_draft_and_rechecks_conversation(self):
        import numpy as np
        driver = object.__new__(Desktop)
        driver.scale = 1
        driver.profile = {"draft_from_anchor": {"x": 10, "top": -10, "width": 80, "height": 20}}
        expected = Observation("chat", "Hi")
        with patch.object(driver, "observe", side_effect=[expected, expected]) as observe, \
             patch.object(driver, "capture", return_value=(np.zeros((100,100,3), dtype=np.uint8), {})), \
             patch.object(driver, "find", return_value=(5,50)), \
             patch.object(driver, "ocr", return_value="Hello\n"), \
             patch.object(driver, "submit_and_verify", return_value=True) as submit, \
             patch("assistant.desktop.pyautogui.write") as write:
            self.assertTrue(driver.finish_pending(expected, "Hello"))
        self.assertEqual(observe.call_count, 2)
        submit.assert_called_once_with(expected, "Hello")
        write.assert_not_called()
