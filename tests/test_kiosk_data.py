import unittest

from _load import load_kiosk

K = load_kiosk()
NOW = 1_751_800_000.0

SNAP_OK = {
    "received_at": NOW - 20,
    "payload": {
        "session_id": "abc12345",
        "model": {"display_name": "Fable 5"},
        "workspace": {"current_dir": "/Users/fra/Documents/WORK/claude-usage-monitor"},
        "cost": {"total_cost_usd": 1.234, "total_lines_added": 12,
                 "total_lines_removed": 3, "total_duration_ms": 3_840_000},
        "rate_limits": {
            "five_hour": {"used_percentage": 42, "resets_at": NOW + 7200},
            "seven_day": {"used_percentage": 71.5, "resets_at": NOW + 90000},
        },
    },
    "sessions": [],
}
SNAP_OK["sessions"] = [{"received_at": SNAP_OK["received_at"],
                        "payload": SNAP_OK["payload"]}]


class TestParseState(unittest.TestCase):
    def test_none_snapshot_is_no_server(self):
        self.assertEqual(K.parse_state(None, NOW)["status"], "no-server")

    def test_empty_payload_is_no_data(self):
        snap = {"received_at": None, "payload": None, "sessions": []}
        self.assertEqual(K.parse_state(snap, NOW)["status"], "no-data")

    def test_ok_state_windows_in_preferred_order(self):
        st = K.parse_state(SNAP_OK, NOW)
        self.assertEqual(st["status"], "ok")
        self.assertEqual([w["key"] for w in st["windows"]],
                         ["five_hour", "seven_day"])
        self.assertEqual(st["windows"][0]["label"], "SESSIONE · 5H")
        self.assertEqual(st["windows"][0]["pct"], 42.0)
        self.assertEqual(st["model"], "Fable 5")

    def test_unknown_windows_get_generated_label_max_two(self):
        snap = {"received_at": NOW, "sessions": [],
                "payload": {"rate_limits": {
                    "monthly": {"used_percentage": 5},
                    "five_hour": {"used_percentage": 1},
                    "yearly": {"used_percentage": 9}}}}
        st = K.parse_state(snap, NOW)
        self.assertEqual(len(st["windows"]), 2)
        self.assertEqual(st["windows"][0]["key"], "five_hour")
        self.assertEqual(st["windows"][1]["label"], "MONTHLY")

    def test_session_view(self):
        st = K.parse_state(SNAP_OK, NOW)
        self.assertEqual(st["sessions"][0]["name"], "claude-usage-monitor")
        self.assertEqual(st["sessions"][0]["meta"],
                         "Fable 5 · $1.23 · +12/-3 · 1h 04m")


class TestFormats(unittest.TestCase):
    def test_countdown_days(self):
        self.assertEqual(K.format_countdown(NOW + 2 * 86400 + 5 * 3600, NOW),
                         "2g 05h")

    def test_countdown_hours(self):
        self.assertEqual(K.format_countdown(NOW + 4 * 3600 + 32 * 60, NOW),
                         "4h 32m")

    def test_countdown_minutes(self):
        self.assertEqual(K.format_countdown(NOW + 12 * 60 + 30, NOW), "12m 30s")

    def test_countdown_past_and_missing(self):
        self.assertEqual(K.format_countdown(NOW - 5, NOW), "ora")
        self.assertEqual(K.format_countdown(None, NOW), "—")

    def test_duration(self):
        self.assertEqual(K.format_duration(3_840_000), "1h 04m")
        self.assertEqual(K.format_duration(300_000), "5m")


class TestResetsAtNormalization(unittest.TestCase):
    def test_iso_string_with_z_suffix(self):
        # NOW + 7200s == 2025-07-06T13:06:40Z
        snap = {"received_at": NOW, "sessions": [], "payload": {"rate_limits": {
            "five_hour": {"used_percentage": 1,
                          "resets_at": "2025-07-06T13:06:40Z"}}}}
        st = K.parse_state(snap, NOW)
        self.assertAlmostEqual(st["windows"][0]["resets_at"], NOW + 7200, places=0)

    def test_millisecond_epoch(self):
        ms = (NOW + 3600) * 1000
        snap = {"received_at": NOW, "sessions": [], "payload": {"rate_limits": {
            "five_hour": {"used_percentage": 1, "resets_at": ms}}}}
        st = K.parse_state(snap, NOW)
        self.assertAlmostEqual(st["windows"][0]["resets_at"], NOW + 3600, places=3)

    def test_unparsable_string_is_none(self):
        snap = {"received_at": NOW, "sessions": [], "payload": {"rate_limits": {
            "five_hour": {"used_percentage": 1, "resets_at": "not-a-date"}}}}
        st = K.parse_state(snap, NOW)
        self.assertIsNone(st["windows"][0]["resets_at"])
        self.assertEqual(K.format_countdown(None, NOW), "—")

    def test_percentage_alias_utilization(self):
        snap = {"received_at": NOW, "sessions": [], "payload": {"rate_limits": {
            "five_hour": {"utilization": 33.5}}}}
        st = K.parse_state(snap, NOW)
        self.assertEqual(st["windows"][0]["pct"], 33.5)


class TestNonDictPayload(unittest.TestCase):
    def test_string_payload_is_no_data(self):
        snap = {"received_at": NOW, "payload": "oops", "sessions": []}
        self.assertEqual(K.parse_state(snap, NOW)["status"], "no-data")

    def test_list_payload_is_no_data(self):
        snap = {"received_at": NOW, "payload": [1, 2, 3], "sessions": []}
        self.assertEqual(K.parse_state(snap, NOW)["status"], "no-data")

    def test_session_entry_with_string_payload_falls_back(self):
        entry = {"received_at": NOW, "payload": "oops"}
        view = K._session_view(entry)
        self.assertEqual(view["name"], "sessione")
        self.assertEqual(view["meta"], "")


if __name__ == "__main__":
    unittest.main()
