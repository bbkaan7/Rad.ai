"""Calibration must not erase working references when DPI or the dock changes."""

import unittest
from assistant.layout import calibration_profile, content_offset, reference_region


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"size": [438, 742], "reference_dpi": 96,
                        "left_dock_width": 226, "regions": {"chat": [7, 92, 386, 408]},
                        "templates": {"next": "next.png"}, "template_dpi": {"next": 120},
                        "incoming_color": [255, 255, 255], "read_mode": "bubbles"}

    def test_dpi_change_preserves_calibration(self):
        updated, offset, changed = calibration_profile(self.profile, [548, 928], 120)
        self.assertFalse(changed)
        self.assertEqual(offset, 0)
        self.assertEqual(updated, self.profile)

    def test_optional_dock_preserves_regions_and_templates(self):
        updated, offset, changed = calibration_profile(self.profile, [830, 928], 120)
        self.assertFalse(changed)
        self.assertEqual(offset, 282)
        self.assertEqual(updated, self.profile)
        self.assertEqual(reference_region([292, 115, 480, 510], offset, 120, 96),
                         [8, 92, 384, 408])

    def test_advertisement_selection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "advertisement"):
            reference_region([100, 115, 480, 510], 282, 120, 96)

    def test_real_resize_resets_incompatible_calibration_only_in_copy(self):
        updated, offset, changed = calibration_profile(self.profile, [900, 950], 120)
        self.assertTrue(changed)
        self.assertEqual(updated["regions"], {})
        self.assertEqual(updated["templates"], {})
        self.assertNotIn("template_dpi", updated)
        self.assertNotIn("left_dock_width", updated)
        self.assertEqual(self.profile["templates"], {"next": "next.png"})

    def test_unknown_width_is_not_treated_as_a_dock(self):
        self.assertIsNone(content_offset(self.profile, [700, 928], 120))

    def test_template_dpi_kept_independent_of_region_dpi(self):
        updated, _, _ = calibration_profile(self.profile, [548, 928], 120)
        self.assertEqual(updated["reference_dpi"], 96)
        self.assertEqual(updated["template_dpi"]["next"], 120)


if __name__ == "__main__":
    unittest.main()
