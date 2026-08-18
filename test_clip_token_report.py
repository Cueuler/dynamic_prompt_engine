"""Tests for CLIP token report helpers and node."""

import unittest
from unittest.mock import MagicMock

from dynamic_prompt_engine.clip_token_report import (
    CLIPTokenReport,
    CLIP_INVALID_MESSAGE,
    content_from_chunk,
    content_token_count,
    encoder_tokenizer,
    format_clip_token_report,
    reconstruct_content,
)


BOS = 49406
EOS = 49407
PAD_L = EOS
PAD_G = 0


class FakeClipTokenizer:
    max_length = 77
    start_token = BOS
    end_token = EOS

    def __init__(self, inv_vocab=None):
        self.inv_vocab = inv_vocab or {
            BOS: "<start>",
            EOS: "<end>",
            100: "hello",
            101: "world",
            102: "more",
            103: "tokens",
        }

    def decode(self, token_ids, skip_special_tokens=True):
        return " ".join(self.inv_vocab.get(token_id, f"t{token_id}") for token_id in token_ids)


class FakeSDXLTokenizer:
    def __init__(self):
        self.clip_l = FakeClipTokenizer()
        self.clip_g = FakeClipTokenizer(
            inv_vocab={
                BOS: "<start>",
                EOS: "<end>",
                100: "hello",
                101: "world",
                102: "more",
                103: "tokens",
                0: "<pad>",
            }
        )
        self.clip_g.pad_token = PAD_G


def make_chunk(content_ids, pad_token=PAD_L, pad_count=72):
    chunk = [(BOS, 1.0)]
    chunk.extend((token_id, 1.0) for token_id in content_ids)
    chunk.append((EOS, 1.0))
    chunk.extend((pad_token, 1.0) for _ in range(pad_count))
    return chunk


class TestContentFromChunk(unittest.TestCase):
    def test_extracts_content_between_bos_and_eos(self):
        chunk = [(BOS, 1.0), (100, 1.0), (101, 1.0), (EOS, 1.0), (PAD_L, 1.0)]
        content = content_from_chunk(chunk, BOS, EOS)
        self.assertEqual([pair[0] for pair in content], [100, 101])

    def test_clip_g_padding_after_eos_is_excluded(self):
        chunk = [(BOS, 1.0), (100, 1.0), (EOS, 1.0), (PAD_G, 1.0), (PAD_G, 1.0)]
        content = content_from_chunk(chunk, BOS, EOS)
        self.assertEqual(content_token_count(content), 1)

    def test_empty_chunk_returns_empty_content(self):
        self.assertEqual(content_from_chunk([], BOS, EOS), [])


class TestReconstructContent(unittest.TestCase):
    def test_decodes_integer_tokens(self):
        tokenizer = FakeClipTokenizer()
        content = [(100, 1.0), (101, 1.0)]
        self.assertEqual(reconstruct_content(content, tokenizer), "hello world")

    def test_embedding_placeholder(self):
        tokenizer = FakeClipTokenizer()
        embedding = object()
        content = [(100, 1.0), (embedding, 1.0), (101, 1.0)]
        self.assertEqual(reconstruct_content(content, tokenizer), "hello [embedding] world")

    def test_inv_vocab_fallback(self):
        class VocabOnlyTokenizer:
            inv_vocab = {100: "hel</w>", 101: "lo"}

        content = [(100, 1.0), (101, 1.0)]
        self.assertEqual(reconstruct_content(content, VocabOnlyTokenizer()), "hel lo")


class TestFormatClipTokenReport(unittest.TestCase):
    def test_single_chunk_no_overflow(self):
        chunks = {"l": [make_chunk([100, 101], pad_count=73)]}
        report = format_clip_token_report(chunks, FakeClipTokenizer())
        self.assertIn("CLIP-L  window 77, content capacity 75", report)
        self.assertIn("chunks: 1    content tokens: 2    overflow: no", report)
        self.assertIn("[chunk 1/1]  2/75", report)
        self.assertIn("hello world", report)

    def test_two_chunk_overflow(self):
        content_ids = list(range(100, 180))
        inv = {BOS: "<start>", EOS: "<end>", **{i: f"t{i}" for i in content_ids}}
        tokenizer = FakeClipTokenizer(inv_vocab=inv)
        chunk1 = make_chunk(content_ids[:75], pad_count=0)
        chunk2 = make_chunk(content_ids[75:], pad_count=70)
        report = format_clip_token_report({"l": [chunk1, chunk2]}, tokenizer)
        self.assertIn("chunks: 2    content tokens: 80    overflow: yes", report)
        self.assertIn("[chunk 1/2]  75/75", report)
        self.assertIn("[chunk 2/2]  5/75", report)

    def test_dual_l_and_g_sections(self):
        chunk = make_chunk([100, 101], pad_count=73)
        root = FakeSDXLTokenizer()
        report = format_clip_token_report({"l": [chunk], "g": [chunk]}, root)
        self.assertIn("CLIP-L  window 77, content capacity 75", report)
        self.assertIn("CLIP-G  window 77, content capacity 75", report)
        self.assertLess(report.index("CLIP-L"), report.index("CLIP-G"))

    def test_empty_prompt(self):
        chunks = {"l": [make_chunk([], pad_count=75)]}
        report = format_clip_token_report(chunks, FakeClipTokenizer())
        self.assertIn("content tokens: 0    overflow: no", report)
        self.assertIn("[chunk 1/1]  0/75", report)

    def test_unlimited_tokenizer_uses_token_count(self):
        class T5Tokenizer:
            max_length = 999999
            start_token = None
            end_token = None

        chunk = [(100, 1.0), (101, 1.0), (102, 1.0)]
        root = MagicMock()
        root.clip_t5xxl = T5Tokenizer()
        report = format_clip_token_report({"t5xxl": [chunk]}, root)
        self.assertIn("T5-XXL", report)
        self.assertIn("tokens: 3", report)
        self.assertNotIn("window 77", report)


class TestEncoderTokenizer(unittest.TestCase):
    def test_sdxl_sub_tokenizers(self):
        root = FakeSDXLTokenizer()
        self.assertIs(encoder_tokenizer(root, "l"), root.clip_l)
        self.assertIs(encoder_tokenizer(root, "g"), root.clip_g)

    def test_sd1_clip_attr(self):
        root = MagicMock()
        root.clip_l = FakeClipTokenizer()
        self.assertIs(encoder_tokenizer(root, "l"), root.clip_l)


class TestCLIPTokenReportNode(unittest.TestCase):
    def setUp(self):
        self.node = CLIPTokenReport()

    def test_inspect_calls_tokenize_and_returns_ui(self):
        clip = MagicMock()
        clip.tokenizer = FakeClipTokenizer()
        clip.tokenize.return_value = {"l": [make_chunk([100, 101], pad_count=73)]}

        result = self.node.inspect(clip, "hello world")

        clip.tokenize.assert_called_once_with("hello world")
        self.assertIn("ui", result)
        self.assertIn("result", result)
        self.assertEqual(result["ui"]["text"][0], result["result"][0])
        self.assertIn("CLIP-L", result["result"][0])

    def test_none_clip_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.node.inspect(None, "test")
        self.assertIn(CLIP_INVALID_MESSAGE, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
