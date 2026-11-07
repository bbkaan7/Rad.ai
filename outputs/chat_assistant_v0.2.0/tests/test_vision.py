"""Synthetic images only; these tests never capture or control the desktop."""

import unittest
from unittest.mock import patch
import threading

try:
    import numpy as np
    from assistant.desktop import locate, Desktop, crop
except (ImportError, OSError, AttributeError):
    np = None


@unittest.skipIf(np is None, "Requires the Windows desktop environment and CV dependencies")
class VisionTests(unittest.TestCase):
    def setUp(self):
        self.template = np.random.default_rng(7).integers(0, 256, (20, 30), dtype=np.uint8)
        self.frame = np.zeros((120, 200, 3), dtype=np.uint8)
        self.frame[30:50, 40:70] = self.template[:, :, None]

    def test_template_center(self):
        self.assertEqual(locate(self.frame, self.template), (55, 40))

    def test_ambiguous_matches_are_rejected(self):
        self.frame[70:90, 120:150] = self.template[:, :, None]
        with self.assertRaisesRegex(ValueError, "Multiple"):
            locate(self.frame, self.template)

    def test_missing_match_stops(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            locate(np.zeros_like(self.frame), self.template)

    def test_invalid_crop_is_rejected(self):
        with self.assertRaises(ValueError):
            crop(self.frame, [190, 10, 30, 20])

    def test_cancel_does_not_touch_mouse(self):
        driver = object.__new__(Desktop)
        driver.cancelled = threading.Event()
        driver.cancelled.set()
        with patch("assistant.desktop.pyautogui.failSafeCheck") as mouse:
            with self.assertRaises(InterruptedError):
                driver.check()
            mouse.assert_not_called()

    def test_regions_scale_from_reference_dpi(self):
        driver = object.__new__(Desktop)
        driver.scale = 1.25
        driver.profile = {"regions": {"chat": [8, 40, 240, 320]}}
        self.assertEqual(driver.region("chat"), [10, 50, 300, 400])

    def test_click_offsets_allow_negative_monitor_coordinates(self):
        driver = object.__new__(Desktop)
        box = {"left": -1920, "top": 80, "width": 200, "height": 120}
        with patch.object(driver, "capture", return_value=(self.frame, box)), \
             patch.object(driver, "template", return_value=self.template), \
             patch.object(driver, "check"), patch("assistant.desktop.bounds", return_value=box), \
             patch("assistant.desktop.time.sleep"), patch("assistant.desktop.pyautogui.click") as click:
            driver.handle = 1
            driver.click("send")
        click.assert_called_once_with(-1865, 120)

    def test_moving_window_blocks_click(self):
        driver = object.__new__(Desktop)
        box = {"left": 100, "top": 80, "width": 200, "height": 120}
        moved = dict(box, left=300)
        with patch.object(driver, "capture", return_value=(self.frame, box)), \
             patch.object(driver, "template", return_value=self.template), \
             patch.object(driver, "check"), patch("assistant.desktop.bounds", return_value=moved), \
             patch("assistant.desktop.pyautogui.click") as click:
            driver.handle = 1
            with self.assertRaisesRegex(ValueError, "Window moved"):
                driver.click("send")
        click.assert_not_called()

    def test_message_pane_follows_input_when_friend_chat_expands(self):
        driver = object.__new__(Desktop)
        driver.scale = 1.25
        driver.content_offset_x = 282
        driver.profile = {"regions": {"chat": [7,92,386,408]}, "chat_bottom_from_anchor": 18}
        with patch.object(driver, "find", return_value=(320, 853)):
            region = driver.message_region(self.frame)
        self.assertEqual(region, [291,115,482,716])


if __name__ == "__main__":
    unittest.main()
