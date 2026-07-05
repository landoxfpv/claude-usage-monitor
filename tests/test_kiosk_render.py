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


NOW = 1_751_800_000.0
STATE_OK = {
    "status": "ok", "updated_at": NOW - 20, "model": "Fable 5",
    "windows": [
        {"key": "five_hour", "label": "SESSIONE · 5H", "pct": 42.0,
         "resets_at": NOW + 7200},
        {"key": "seven_day", "label": "SETTIMANA · 7G", "pct": 91.0,
         "resets_at": NOW + 90000},
    ],
    "sessions": [{"name": "claude-usage-monitor",
                  "meta": "Fable 5 · $1.23 · +12/-3 · 1h 04m"},
                 {"name": "altra-repo", "meta": "Fable 5 · $0.10"}],
}


class TestRenderFrame(unittest.TestCase):
    def test_size_and_mode(self):
        img = K.render_frame(STATE_OK, (480, 320), 0, NOW)
        self.assertEqual((img.size, img.mode), ((480, 320), "RGB"))

    def test_not_blank(self):
        img = K.render_frame(STATE_OK, (480, 320), 0, NOW)
        lo, hi = img.convert("L").getextrema()
        self.assertGreater(hi - lo, 100)

    def test_states_render_differently(self):
        a = K.render_frame({"status": "no-server"}, (480, 320), 0, NOW)
        b = K.render_frame({"status": "no-data"}, (480, 320), 0, NOW)
        c = K.render_frame(STATE_OK, (480, 320), 0, NOW)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        self.assertNotEqual(b.tobytes(), c.tobytes())

    def test_carousel_changes_frame(self):
        a = K.render_frame(STATE_OK, (480, 320), 0, NOW)
        b = K.render_frame(STATE_OK, (480, 320), 1, NOW)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_bar_color_thresholds(self):
        self.assertEqual(K.bar_color(50), K.PAL["violet"])
        self.assertEqual(K.bar_color(75), K.PAL["warning"])
        self.assertEqual(K.bar_color(95), K.PAL["danger"])

    def test_scales_to_other_sizes(self):
        img = K.render_frame(STATE_OK, (320, 240), 0, NOW)
        self.assertEqual(img.size, (320, 240))


if __name__ == "__main__":
    unittest.main()
