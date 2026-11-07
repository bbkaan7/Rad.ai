"""Native input and clipboard are mocked. No live applications are accessed."""

import unittest
from unittest.mock import patch

try:
    import numpy as np
    from assistant.desktop import Desktop
except (ImportError, OSError, AttributeError):
    np = None


@unittest.skipIf(np is None, "Windows desktop dependencies required")
class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((300, 300, 3), 20, dtype=np.uint8)
        self.frame[200:240, 10:200] = 60
        self.driver = object.__new__(Desktop)
        self.driver.handle = 1
        self.driver.scale = 1
        self.driver.profile = {
            "regions": {"chat": [0,30,300,250], "identity": [0,0,20,20]},
            "incoming_color": [60,60,60], "incoming_tolerance": 2,
        }

    def test_exact_text_comes_from_copy_not_ocr(self):
        with patch.object(self.driver, "check"), patch.object(self.driver, "click") as menu, \
             patch.object(self.driver, "capture", return_value=(self.frame, {})), \
             patch("assistant.desktop.bounds", return_value={"left":0,"top":0}), \
             patch("assistant.desktop.pyautogui.click") as mouse, \
             patch("assistant.desktop.time.sleep"), \
             patch("assistant.desktop.user32.GetClipboardSequenceNumber", side_effect=[10,11]), \
             patch("assistant.desktop.pyperclip.paste", return_value="here is the short message u need"):
            text = self.driver.copy_bubble(self.frame, "incoming")
        self.assertEqual(text, "here is the short message u need")
        menu.assert_called_once_with("copy_text")
        self.assertEqual(mouse.call_args.kwargs["button"], "right")

    def test_unchanged_clipboard_is_rejected(self):
        with patch.object(self.driver, "check"), patch.object(self.driver, "click"), \
             patch("assistant.desktop.bounds", return_value={"left":0,"top":0}), \
             patch("assistant.desktop.pyautogui.click"), patch("assistant.desktop.time.sleep"), \
             patch("assistant.desktop.time.monotonic", side_effect=[0,3]), \
             patch("assistant.desktop.user32.GetClipboardSequenceNumber", return_value=10), \
             patch("assistant.desktop.pyperclip.paste") as clipboard:
            with self.assertRaisesRegex(ValueError, "did not update"):
                self.driver.copy_bubble(self.frame, "incoming")
        clipboard.assert_not_called()

    def test_recipient_change_after_copy_rejects_text(self):
        changed = self.frame.copy()
        changed[0:20,0:20] = 100
        with patch.object(self.driver, "check"), patch.object(self.driver, "click"), \
             patch.object(self.driver, "capture", return_value=(changed, {})), \
             patch("assistant.desktop.bounds", return_value={"left":0,"top":0}), \
             patch("assistant.desktop.pyautogui.click"), patch("assistant.desktop.time.sleep"), \
             patch("assistant.desktop.user32.GetClipboardSequenceNumber", side_effect=[10,11]), \
             patch("assistant.desktop.pyperclip.paste", return_value="A message"):
            with self.assertRaisesRegex(ValueError, "changed while copying"):
                self.driver.copy_bubble(self.frame, "incoming")


if __name__ == "__main__":
    unittest.main()
