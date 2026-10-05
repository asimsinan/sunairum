import unittest

from layout_geometry import bounds, parse_transform, text_width_px


class LayoutGeometryTests(unittest.TestCase):
    def test_transform_bounds_include_nonuniform_scale(self):
        result = bounds(10, 20, 100, 50, parse_transform("translate(5 6) scale(2 3)"))
        self.assertEqual({"x": 25.0, "y": 66.0, "width": 200.0, "height": 150.0}, result)

    def test_text_width_is_positive(self):
        self.assertGreater(text_width_px("Readable text", 16), 0)


if __name__ == "__main__":
    unittest.main()
