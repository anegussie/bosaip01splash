import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dev.tests import fixture_files
from dev.tools import gguf_metadata


class GgufMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gguf = Path(self.temp.name) / "model.gguf"
        fixture_files.write_gguf(
            self.gguf,
            {
                "general.architecture": "qwen4exp",
                "qwen4exp.attention.indexer.top_k": 2048,
                "qwen4exp.attention.indexer.head_count": 4,
                "qwen4exp.block_count": 48,
                "qwen4exp.attention.compress_ratios": [0, 0, 0, 4],
                "qwen4exp.rope.theta": 1000000.0,
            },
            tensors=(("model.gguf", (2, 2), 6, bytes(range(16))),),
        )
        self.before = self.gguf.read_bytes()

    def table(self):
        with self.gguf.open("rb") as stream:
            _, _, count = gguf_metadata.header(stream)
            return gguf_metadata.entries(stream, count)

    def test_setting_a_scalar_rewrites_only_its_value(self):
        offset = next(
            entry[2]
            for entry in self.table()
            if entry[0] == "qwen4exp.attention.indexer.top_k"
        )
        self.assertEqual(
            gguf_metadata.set_scalar(
                self.gguf, "qwen4exp.attention.indexer.top_k", 4096
            ),
            2048,
        )
        after = self.gguf.read_bytes()
        self.assertEqual(len(after), len(self.before))
        self.assertEqual(after[:offset], self.before[:offset])
        self.assertEqual(after[offset + 4 :], self.before[offset + 4 :])
        values = {name: value for name, _, _, value in self.table()}
        self.assertEqual(values["qwen4exp.attention.indexer.top_k"], 4096)
        self.assertEqual(values["qwen4exp.block_count"], 48)
        self.assertEqual(values["qwen4exp.rope.theta"], 1000000.0)

    def test_the_command_line_reads_a_key_and_writes_one(self):
        self.assertEqual(
            gguf_metadata.main([str(self.gguf), "qwen4exp.block_count"]), 0
        )
        gguf_metadata.main([str(self.gguf), "qwen4exp.attention.indexer.top_k", "4096"])
        self.assertEqual(
            {name: value for name, _, _, value in self.table()}[
                "qwen4exp.attention.indexer.top_k"
            ],
            4096,
        )
        self.assertEqual(gguf_metadata.main([str(self.gguf)]), 0)

    def test_an_array_or_an_absent_key_is_refused(self):
        with self.assertRaises(ValueError):
            gguf_metadata.set_scalar(self.gguf, "qwen4exp.attention.compress_ratios", 4)
        with self.assertRaises(KeyError):
            gguf_metadata.set_scalar(self.gguf, "qwen4exp.attention.indexer.missing", 4)
        self.assertEqual(self.gguf.read_bytes(), self.before)
