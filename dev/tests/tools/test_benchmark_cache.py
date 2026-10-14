import fcntl
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dev.benchmarks import benchmark_cache


class BenchmarkCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.validation = Path(self.temp.name).resolve()
        self.run = self.validation / "performance-fixture"
        self.namespace = self.run / "cache-1" / ("a" * 32)
        self.namespace.mkdir(parents=True, mode=0o700)
        (self.namespace / "lock").touch()
        (self.namespace / "state.slots").write_bytes(b"x" * 8192)
        (self.run / "replies.json").write_text("preserve me")

    def test_preview_then_prune_preserves_reports_and_other_data(self):
        production = self.validation / "production-cache"
        production.mkdir()
        (production / "state.slots").write_text("preserve me too")
        preview = benchmark_cache.clean(self.validation)
        self.assertNotIn("skipped", preview[0])
        self.assertTrue(self.namespace.exists())
        self.assertTrue(
            benchmark_cache.clean(self.validation, prune=True)[0]["removed"]
        )
        self.assertFalse(self.namespace.exists())
        self.assertEqual((self.run / "replies.json").read_text(), "preserve me")
        self.assertTrue((production / "state.slots").exists())

    def test_active_cache_is_skipped(self):
        with (self.namespace / "lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = benchmark_cache.clean(self.validation, prune=True)
            self.assertIn("skipped", result[0])
            self.assertTrue((self.namespace / "state.slots").exists())

    def test_interrupted_tuning_scratch_is_recognized(self):
        scratch = self.run / "scratch-abcd1234/cache" / ("b" * 32)
        scratch.mkdir(parents=True, mode=0o700)
        (scratch / "lock").touch()
        (scratch / "state.slots").write_bytes(b"data")
        result = benchmark_cache.clean(self.validation, prune=True)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row["removed"] for row in result))
        self.assertFalse(scratch.exists())

    def test_unexpected_file_blocks_all_deletion(self):
        (self.namespace / "notes.txt").write_text("private")
        self.assertIn("skipped", benchmark_cache.clean(self.validation, prune=True)[0])
        self.assertTrue((self.namespace / "state.slots").exists())

    def test_symlink_to_other_cache_is_never_followed(self):
        alternate = self.run / "cache-2"
        alternate.symlink_to(self.namespace.parent, target_is_directory=True)
        # A preview demonstrates that the alias is rejected before acquiring locks.
        result = benchmark_cache.clean(self.validation)
        self.assertIn("skipped", result[1])
        self.assertTrue((self.namespace / "state.slots").exists())

    def test_outside_validation_and_parent_symlinks_are_rejected(self):
        with self.assertRaises(ValueError):
            benchmark_cache.inspect_root(
                self.validation.parent / "cache-1", self.validation
            )
        linked_run = self.validation / "performance-linked"
        linked_run.symlink_to(self.run, target_is_directory=True)
        with self.assertRaises(ValueError):
            benchmark_cache.inspect_root(linked_run / "cache-1", self.validation)


if __name__ == "__main__":
    unittest.main()
