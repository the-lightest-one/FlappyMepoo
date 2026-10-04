from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import bot  # noqa: E402
import storage  # noqa: E402


class PlayKeyboardTests(unittest.TestCase):
    def test_https_gives_web_app_button(self):
        with mock.patch.object(bot, "GAME_URL", "https://example.com/game"):
            button = bot.play_keyboard(42)["inline_keyboard"][0][0]

        self.assertIn("web_app", button)
        self.assertEqual(button["web_app"]["url"], "https://example.com/game/?user=42")

    def test_local_http_uses_link_button(self):
        with mock.patch.object(bot, "GAME_URL", "http://localhost:8080"):
            button = bot.play_keyboard(7)["inline_keyboard"][0][0]


        self.assertNotIn("web_app", button)
        self.assertEqual(button["url"], "http://localhost:8080/?user=7")

    def test_game_url_carries_user_id(self):
        with mock.patch.object(bot, "GAME_URL", "https://x.ru"):
            self.assertEqual(bot.game_url_for(555), "https://x.ru/?user=555")


class FormatTopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmpdir.name) / "scores.json"
        self.addCleanup(lambda: setattr(storage, "DATA_FILE", self.original))

    def test_empty_leaderboard_message(self):
        self.assertIn("/play", bot.format_top())

    def test_rows_are_escaped_and_ordered(self):
        storage.save_score("<b>хакер</b>", 2)
        storage.save_score("норм", 15)

        text = bot.format_top()

        self.assertLess(text.index("норм"), text.index("хакер"))
        self.assertNotIn("<b>хакер</b>", text)         
        self.assertIn("&lt;b&gt;хакер&lt;/b&gt;", text)

    def test_respects_limit(self):
        for index in range(5):
            storage.save_score(f"user{index}", index)
        self.assertEqual(bot.format_top(limit=3).count("попыток"), 3)


if __name__ == "__main__":
    unittest.main()
