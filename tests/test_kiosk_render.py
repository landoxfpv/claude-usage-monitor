import unittest

from _load import load_kiosk

K = load_kiosk()


class TestFonts(unittest.TestCase):
    def test_load_font_returns_usable_font(self):
        f = K.load_font(20, weight=800)
        self.assertGreater(f.getbbox("42%")[2], 0)

    def test_load_font_is_cached(self):
        self.assertIs(K.load_font(20, 800), K.load_font(20, 800))

    def test_mono_font_differs_from_sans(self):
        self.assertIsNot(K.load_font(12, 600, mono=True),
                         K.load_font(12, 600, mono=False))


if __name__ == "__main__":
    unittest.main()
