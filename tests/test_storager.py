from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storager.scanner import human_size, dir_size, scan_immediate_children
from storager.classifier import classify
from storager.inspector import inspect_path
from storager.cli import parse_size, parse_parallel
from storager.interactive import parse_selection
from storager.profiles import get_profile, PROFILES
from storager.diagnose import Problem
from storager.cli import _health_score, _disk_bar
from storager.present import age_str, summarize_report
from storager.scanner import DiskEntry


class TestHumanSize(unittest.TestCase):
    def test_units(self):
        self.assertEqual(human_size(0), "0.0 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(1024 ** 2), "1.0 MB")
        self.assertEqual(human_size(1024 ** 3), "1.0 GB")
        self.assertEqual(human_size(1024 ** 4), "1.0 TB")

    def test_fractional(self):
        self.assertEqual(human_size(1536), "1.5 KB")


class TestParseSize(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_size("5G"), 5 * 1024 ** 3)
        self.assertEqual(parse_size("500M"), 500 * 1024 ** 2)
        self.assertEqual(parse_size("2T"), 2 * 1024 ** 4)
        self.assertEqual(parse_size("1024"), 1024)

    def test_invalid(self):
        self.assertIsNone(parse_size(""))
        self.assertIsNone(parse_size("abc"))
        self.assertIsNone(parse_size("5X"))


class TestParseParallel(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(parse_parallel("auto"), "auto")
        self.assertEqual(parse_parallel("sequential"), "sequential")
        self.assertEqual(parse_parallel("4"), "4")
        self.assertEqual(parse_parallel("999"), "32")
        self.assertEqual(parse_parallel("garbage"), "auto")


class TestParseSelection(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_selection("3", 10), [3])

    def test_range(self):
        self.assertEqual(parse_selection("1-4", 10), [1, 2, 3, 4])

    def test_mixed(self):
        self.assertEqual(parse_selection("1,3-5,8", 10), [1, 3, 4, 5, 8])

    def test_out_of_bounds_ignored(self):
        self.assertEqual(parse_selection("1,99", 10), [1])

    def test_garbage_ignored(self):
        self.assertEqual(parse_selection("abc", 10), [])


class TestDirSize(unittest.TestCase):
    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            total, count, err = dir_size(Path(d))
            self.assertEqual(total, 0)
            self.assertEqual(count, 0)

    def test_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.bin").write_bytes(b"x" * 100)
            (p / "b.bin").write_bytes(b"y" * 200)
            total, count, err = dir_size(p)
            self.assertEqual(total, 300)
            self.assertEqual(count, 2)

    def test_nested(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "sub").mkdir()
            (p / "sub" / "c.bin").write_bytes(b"z" * 50)
            total, count, _ = dir_size(p)
            self.assertEqual(total, 50)
            self.assertEqual(count, 1)


class TestScan(unittest.TestCase):
    def test_finds_entries(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.bin").write_bytes(b"x" * 10)
            (p / "sub").mkdir()
            (p / "sub" / "b.bin").write_bytes(b"y" * 100)
            entries = scan_immediate_children(p)
            names = {e.path.name for e in entries}
            self.assertEqual(names, {"a.bin", "sub"})

    def test_sorted_desc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "small.bin").write_bytes(b"x" * 10)
            (p / "big.bin").write_bytes(b"y" * 1000)
            entries = scan_immediate_children(p)
            self.assertEqual(entries[0].path.name, "big.bin")


class TestClassifier(unittest.TestCase):
    def _entry(self, name, is_dir=False):
        return DiskEntry(path=Path("/tmp") / name, size=1000, is_dir=is_dir)

    def test_cache(self):
        ce = classify(self._entry("Caches", is_dir=True))
        self.assertEqual(ce.category, "cache")
        self.assertEqual(ce.risk, "safe")

    def test_node_modules(self):
        ce = classify(self._entry("node_modules", is_dir=True))
        self.assertEqual(ce.category, "build")

    def test_media(self):
        ce = classify(self._entry("photo.jpg"))
        self.assertEqual(ce.category, "media")
        self.assertEqual(ce.risk, "risky")

    def test_trash(self):
        ce = classify(self._entry(".Trash", is_dir=True))
        self.assertEqual(ce.category, "trash")

    def test_unknown(self):
        ce = classify(self._entry("random.xyz"))
        self.assertEqual(ce.risk, "unknown")


class TestProfiles(unittest.TestCase):
    def test_known_profiles(self):
        for name in ("developer", "designer", "casual", "minimal"):
            self.assertIn(name, PROFILES)
            self.assertIsNotNone(get_profile(name))

    def test_unknown_profile(self):
        self.assertIsNone(get_profile("nope"))

    def test_developer_rules(self):
        p = get_profile("developer")
        self.assertTrue(any("node_modules" in str(r[2]).lower() or "virtualenv" in r[2].lower() for r in p.extra_rules))


class TestInspector(unittest.TestCase):
    def test_counts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.txt").write_text("hi")
            (p / "b.txt").write_text("there")
            (p / "sub").mkdir()
            (p / "sub" / "c.log").write_text("x")
            rep = inspect_path(p)
            self.assertEqual(rep.files, 3)
            self.assertEqual(rep.dirs, 1)
            self.assertEqual(rep.by_ext.get("txt"), 2)
            self.assertEqual(rep.by_ext.get("log"), 1)


class TestHealthScore(unittest.TestCase):
    def test_healthy(self):
        self.assertGreaterEqual(_health_score(50, []), 80)

    def test_critical(self):
        probs = [Problem("critical", None, "x")] * 3
        self.assertLess(_health_score(95, probs), 50)

    def test_floored(self):
        self.assertGreaterEqual(_health_score(99, [Problem("critical", None, "x")] * 20), 0)


class TestAgeStr(unittest.TestCase):
    def test_today(self):
        self.assertEqual(age_str(0.1), "today")

    def test_days(self):
        self.assertEqual(age_str(5), "5 days")

    def test_months(self):
        self.assertEqual(age_str(60), "2 months")

    def test_years(self):
        self.assertEqual(age_str(800), "2.2 years")


class TestSummarize(unittest.TestCase):
    def test_empty(self):
        from storager.inspector import ItemReport
        self.assertEqual(summarize_report(ItemReport(path="/tmp")), "")

    def test_with_data(self):
        from storager.inspector import ItemReport
        rep = ItemReport(path="/tmp", files=10, dirs=2, by_ext={"txt": 10}, newest=0)
        s = summarize_report(rep)
        self.assertIn("10 files", s)
        self.assertIn(".txt", s)


if __name__ == "__main__":
    unittest.main()
