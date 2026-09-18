"""Unit tests for the core modules (no GUI required)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import achievements, cache, secrets, settings, steam_paths
from core.paths import APP_DIR


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        return {}

    def close(self):  # noqa: D401 - mimics requests.Response
        pass


class ParseAppIdsTest(unittest.TestCase):
    def test_parse(self):
        from ui.helpers import parse_appids

        self.assertEqual(parse_appids("111,222 333"), ["111", "222", "333"])
        self.assertEqual(parse_appids("1;2,1"), ["1", "2"])
        self.assertEqual(parse_appids(""), [])


class AchievementsTest(unittest.TestCase):
    def test_sanitize_game_name(self):
        self.assertEqual(
            achievements.sanitize_game_name("Counter-Strike: Source"), "CounterStrike_Source"
        )
        self.assertEqual(achievements.sanitize_game_name("Ação & Aventura! 2"), "Acao_Aventura_2")
        self.assertEqual(achievements.sanitize_game_name("   "), "unknown")

    def test_convert_to_gse_format(self):
        playerstats = {
            "achievements": [
                {"apiname": "A", "achieved": 1, "unlocktime": 10},
                {"apiname": "B", "achieved": 0, "unlocktime": 0},
                {"apiname": "", "achieved": 1},
            ]
        }
        self.assertEqual(
            achievements.convert_to_gse_format(playerstats),
            {"A": {"earned": True, "earned_time": 10}, "B": {"earned": False, "earned_time": 0}},
        )

    def test_write_and_rotate_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"APPDATA": tmp}):
                for i in range(7):
                    achievements.write_achievements_file(
                        "42", {"A": {"earned": True, "earned_time": i}}
                    )
                target = Path(tmp) / "GSE Saves" / "42" / "achievements.json"
                self.assertTrue(target.exists())
                backups = list(target.parent.glob("achievements.json.*.bak"))
                self.assertEqual(len(backups), achievements.MAX_BACKUPS)
                self.assertEqual(
                    json.loads(target.read_text(encoding="utf-8")),
                    {"A": {"earned": True, "earned_time": 6}},
                )

    def test_read_achievements_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"APPDATA": tmp}):
                self.assertIsNone(achievements.read_achievements_file("99"))
                data = {"A": {"earned": True, "earned_time": 1}}
                achievements.write_achievements_file("99", data)
                self.assertEqual(achievements.read_achievements_file("99"), data)

    def test_diff_achievements(self):
        old = {"A": {"earned": True}, "B": {"earned": False}, "C": {"earned": True}}
        new = {"A": {"earned": True}, "B": {"earned": True}, "D": {"earned": True}}
        gained, lost = achievements.diff_achievements(old, new)
        self.assertEqual(sorted(gained), ["B", "D"])
        self.assertEqual(lost, ["C"])
        self.assertEqual(
            achievements.diff_achievements(None, {"X": {"earned": True}}), (["X"], [])
        )


class SettingsTest(unittest.TestCase):
    def test_secret_roundtrip(self):
        token = secrets.protect("secret-key")
        self.assertTrue(token.startswith("dpapi:"))
        self.assertEqual(secrets.unprotect(token), "secret-key")
        self.assertEqual(secrets.unprotect("plain"), "plain")

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            with mock.patch.object(settings, "CONFIG_FILE", config):
                settings.save_settings(
                    {"api_key": "k", "steam_id": "1", "save_data": True, "create_name_file": True}
                )
                raw = json.loads(config.read_text(encoding="utf-8"))
                self.assertTrue(raw["api_key"].startswith("dpapi:"))
                loaded = settings.load_settings()
                self.assertEqual(loaded["api_key"], "k")
                self.assertTrue(loaded["create_name_file"])

    def test_does_not_persist_when_save_data_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            with mock.patch.object(settings, "CONFIG_FILE", config):
                settings.save_settings({"api_key": "k", "steam_id": "1", "save_data": False})
                loaded = settings.load_settings()
                self.assertEqual(loaded["api_key"], "")
                self.assertEqual(loaded["steam_id"], "")


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        patches = [
            mock.patch.object(cache, "CACHE_DIR", base),
            mock.patch.object(cache, "COVERS_DIR", base / "covers"),
            mock.patch.object(cache, "INFO_DIR", base / "info"),
            mock.patch.object(cache, "ACHIEVEMENTS_DIR", base / "achievements"),
            mock.patch.object(cache, "NO_COVER_FILE", base / "no_cover.json"),
            mock.patch.object(cache, "COVER_META_FILE", base / "covers_meta.json"),
            mock.patch.object(cache, "_no_cover_cache", None),
            mock.patch.object(cache, "_meta_cache", None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_looks_like_image(self):
        self.assertTrue(cache._looks_like_image(b"\xff\xd8\xff\xe0xx"))
        self.assertTrue(cache._looks_like_image(b"\x89PNG\r\n\x1a\nxx"))
        self.assertFalse(cache._looks_like_image(b"<html>"))
        self.assertFalse(cache._looks_like_image(b""))

    def test_invalid_response_marks_no_cover(self):
        fake = FakeResponse(200, b"<html>", {"Content-Type": "text/html"})
        with mock.patch.object(cache.requests, "get", return_value=fake):
            self.assertIsNone(cache.download_cover("1"))
        self.assertTrue(cache.is_no_cover("1"))

    def test_valid_response_saved(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        fake = FakeResponse(200, png, {"Content-Type": "image/png", "ETag": '"abc"'})
        with mock.patch.object(cache.requests, "get", return_value=fake):
            path = cache.download_cover("2")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_304_reuses_cached(self):
        path = cache.get_cover_path("3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff" + b"0" * 10)
        cache._set_meta("3", '"etag"')
        cache._load_meta()["3"]["checked"] = 0
        with mock.patch.object(cache.requests, "get", return_value=FakeResponse(304)):
            self.assertEqual(cache.download_cover("3"), path)


class AchievementsCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        patches = [
            mock.patch.object(cache, "CACHE_DIR", base),
            mock.patch.object(cache, "ACHIEVEMENTS_DIR", base / "achievements"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_save_and_load_within_ttl(self):
        cache.save_playerstats_cache("10", {"achievements": [{"apiname": "A"}]})
        self.assertIsNotNone(cache.load_playerstats_cache("10", 60))

    def test_expired_returns_none_and_removes_file(self):
        path = cache.save_playerstats_cache("11", {"achievements": []})
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["cached_at"] = 0
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertIsNone(cache.load_playerstats_cache("11", 60))
        self.assertFalse(path.exists())
        self.assertIsNone(cache.load_playerstats_cache("11", 0))  # disabled

    def test_purge_expired(self):
        fresh = cache.save_playerstats_cache("20", {})
        stale = cache.save_playerstats_cache("21", {})
        payload = json.loads(stale.read_text(encoding="utf-8"))
        payload["cached_at"] = 0
        stale.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(cache.purge_expired_achievements_cache(60), 1)
        self.assertTrue(fresh.exists())
        self.assertFalse(stale.exists())
        self.assertEqual(cache.purge_expired_achievements_cache(0), 0)  # disabled

    def test_clear(self):
        cache.save_playerstats_cache("12", {})
        cache.save_playerstats_cache("13", {})
        self.assertEqual(cache.clear_achievements_cache(), 2)
        self.assertIsNone(cache.load_playerstats_cache("12", 60))


class SteamPathsTest(unittest.TestCase):
    def test_parse_vdf(self):
        text = (
            '"libraryfolders"\n{\n "0"\n {\n "path" "C:\\\\Games"\n '
            '"apps"\n {\n "10" "x"\n }\n }\n}'
        )
        parsed = steam_paths._parse_vdf(text)
        self.assertEqual(parsed["0"]["apps"]["10"], "x")


class PathsTest(unittest.TestCase):
    def test_app_dir_exists(self):
        self.assertTrue(APP_DIR.exists())


if __name__ == "__main__":
    unittest.main()
