import unittest

try:
    import numpy as np
    from assistant.vision import bubble_rectangles, strip_timestamp, ocr_image
except ImportError:
    np = None


@unittest.skipIf(np is None, "OpenCV and NumPy required")
class BubbleTests(unittest.TestCase):
    def test_incoming_and_outgoing_are_separated(self):
        frame = np.full((400, 400, 3), 20, dtype=np.uint8)
        frame[100:145, 12:190] = [55, 60, 70]
        frame[200:245, 210:392] = [85, 90, 100]
        self.assertEqual(bubble_rectangles(frame, [55, 60, 70], "left"), [(12, 100, 178, 45)])
        self.assertEqual(bubble_rectangles(frame, [85, 90, 100], "right"), [(210, 200, 182, 45)])

    def test_light_theme_uses_narrow_tolerance(self):
        frame = np.full((400, 400, 3), 250, dtype=np.uint8)
        frame[300:340, 10:160] = 255
        self.assertEqual(bubble_rectangles(frame, [255]*3, tolerance=2), [(10, 300, 150, 40)])

    def test_latest_bubble_is_last(self):
        frame = np.full((400, 400, 3), 20, dtype=np.uint8)
        frame[100:140, 10:160] = 55
        frame[250:290, 10:100] = 55
        self.assertEqual(bubble_rectangles(frame, [55]*3)[-1], (10, 250, 90, 40))

    def test_pane_background_is_not_a_message(self):
        frame = np.full((400, 400, 3), 55, dtype=np.uint8)
        self.assertEqual(bubble_rectangles(frame, [55]*3), [])

    def test_right_aligned_text_is_not_incoming(self):
        frame = np.full((400, 400, 3), 20, dtype=np.uint8)
        frame[250:290, 230:390] = 55
        self.assertEqual(bubble_rectangles(frame, [55]*3, "left"), [])

    def test_dark_bubble_outer_corner_is_removed_but_inner_text_is_kept(self):
        frame = np.full((40,100,3), 60, dtype=np.uint8)
        frame[:5,:5] = 255
        frame[15:25,40:50] = 255
        prepared = ocr_image(frame)
        self.assertGreater(prepared[12+6,12+6], 170)
        self.assertLess(prepared[12+60,12+135], 20)

    def test_light_background_keeps_dark_text_and_adds_white_margin(self):
        frame = np.full((40,100,3), 255, dtype=np.uint8)
        frame[15:25,40:50] = 0
        prepared = ocr_image(frame)
        self.assertEqual(prepared[0,0], 255)
        self.assertLess(prepared[12+60,12+135], 20)


if __name__ == "__main__":
    unittest.main()
