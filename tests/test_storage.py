from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import storage  # noqa: E402


class StorageTestCase(unittest.TestCase):


    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmpdir.name) / "scores.json"
        self.addCleanup(lambda: setattr(storage, "DATA_FILE", self.original))

    def read_raw(self) -> dict:
        return json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))


class SaveScoreTests(StorageTestCase):
    def test_saves_and_reports_summary(self):
        result = storage.save_score("42", 5)

        self.assertTrue(result["ok"])
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["best"], 5)
        self.assertEqual(result["rank"], 1)
        self.assertEqual(result["total"], 1)
        self.assertTrue(storage.DATA_FILE.exists())

    def test_best_keeps_maximum_and_rank_counts_better_players(self):
        storage.save_score("a", 3)
        storage.save_score("b", 10)
        result = storage.save_score("a", 7)

        self.assertEqual(result["best"], 7)      
        self.assertEqual(result["rank"], 2)      
        self.assertEqual(result["total"], 2)
        self.assertEqual(storage.best_score("a"), 7)

    def test_keeps_only_last_attempts(self):
        for value in range(storage.MAX_ATTEMPTS_PER_USER + 25):
            storage.save_score("p", value)

        self.assertEqual(len(self.read_raw()["p"]), storage.MAX_ATTEMPTS_PER_USER)
        self.assertEqual(storage.best_score("p"), storage.MAX_ATTEMPTS_PER_USER + 24)


class ValidationTests(StorageTestCase):
    def test_rejects_out_of_range_score(self):
        with self.assertRaises(ValueError):
            storage.save_score("user", -1)
        with self.assertRaises(ValueError):
            storage.save_score("user", storage.MAX_SCORE + 1)

    def test_rejects_non_numeric_score(self):
        with self.assertRaises(ValueError):
            storage.save_score("user", "много")

    def test_rejects_empty_user(self):
        with self.assertRaises(ValueError):
            storage.save_score("   ", 1)
        with self.assertRaises(ValueError):
            storage.save_score(None, 1)

    def test_zero_is_a_valid_score(self):
        self.assertEqual(storage.save_score("user", 0)["score"], 0)


class LeaderboardTests(StorageTestCase):
    def test_empty_leaderboard(self):
        self.assertEqual(storage.leaderboard(), [])
        self.assertEqual(storage.best_score("nobody"), 0)

    def test_sorted_by_best_score_descending(self):
        storage.save_score("low", 1)
        storage.save_score("high", 20)
        storage.save_score("mid", 9)

        self.assertEqual([row["user"] for row in storage.leaderboard()], ["high", "mid", "low"])
        self.assertEqual(storage.leaderboard(limit=2)[1]["user"], "mid")

    def test_broken_file_does_not_crash(self):
        storage.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        storage.DATA_FILE.write_text("{ это не json", encoding="utf-8")

        self.assertEqual(storage.leaderboard(), [])
        self.assertEqual(storage.save_score("user", 4)["best"], 4)


if __name__ == "__main__":
    unittest.main()
