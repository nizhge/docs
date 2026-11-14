import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline import (connect, store_sources, add_draft, approve, send, reconcile,
                      digest, load_voice, browser_attempt, browser_readback)
from engine import draft_prompt, threads_length
from publish_threads import publish


class EditorialPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "queue.sqlite3"
        self.db = connect(self.path)
        self.item = {"id": "source1", "source": "kyrillic", "category": "telegram",
                     "url": "https://t.me/kyrillic/123", "title": "Основатель и продажи",
                     "summary": "Ранние продажи помогают основателю изучить рынок.",
                     "body_text": "Ранние продажи помогают основателю изучить рынок.", "published_at": "2026-11-14"}
        self.text = "У kyrillic мысль про первые продажи. Я бы сначала проверил, чему учит каждый отказ, а уже потом строил отдел продаж. Что думаете?"
        store_sources(self.db, [self.item])
        self.draft = add_draft(self.db, self.item, {"text": self.text})

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def approve(self):
        approve(self.db, self.draft["id"], digest(self.text), "founder", "Opinion; source credited, original implication and voice reviewed", 85)

    def send(self, sender):
        return send(self.db, self.draft["id"], "founder", "token", sender=sender,
                    verifier=lambda *args: {"id": "123", "username": "founder"},
                    finder=lambda *args: None, receipts_path=Path(self.tmp.name) / "receipts.json")

    def test_owner_voice_is_used_for_external_commentary(self):
        prompt = draft_prompt(self.item, "Owner writes conversationally")
        self.assertIn("Owner writes conversationally", prompt[1]["content"])
        self.assertIn("never imitate the source", prompt[0]["content"])

    def test_approval_binds_exact_text_and_account(self):
        with self.assertRaisesRegex(ValueError, "hash"):
            approve(self.db, self.draft["id"], "wrong", "founder", "review", 85)
        self.approve()
        with self.assertRaisesRegex(ValueError, "account"):
            send(self.db, self.draft["id"], "someone_else", "token")
        self.db.execute("UPDATE drafts SET text='tampered'")
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.send(lambda *args: self.fail("should not send"))

    def test_failure_survives_restart_and_blocks_retry(self):
        self.approve()
        def fail(*args):
            other = connect(self.path)
            self.assertEqual(other.execute("SELECT status FROM drafts").fetchone()[0], "ATTEMPT_STARTED")
            other.close()
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            self.send(fail)
        self.db.close()
        self.db = connect(self.path)
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "UNKNOWN_REQUIRES_RECONCILIATION")
        with self.assertRaises(ValueError):
            self.send(lambda *args: self.fail("never retry an uncertain send"))
        receipt = reconcile(self.db, self.draft["id"], "token",
                            finder=lambda *args: {"id": "456"},
                            reader=lambda *args: {"id": "456", "text": self.text,
                                                 "permalink": "https://www.threads.com/@founder/post/abc"})
        self.assertEqual(receipt["status"], "PUBLISHED_VERIFIED")

    def test_confirmed_receipt_and_repeated_send(self):
        self.approve()
        receipt = self.send(lambda *args: {"status": "PUBLISHED_VERIFIED", "post_id": "456",
                                         "permalink": "https://www.threads.com/@founder/post/abc"})
        self.assertEqual(receipt["status"], "PUBLISHED_VERIFIED")
        with self.assertRaises(ValueError):
            self.send(lambda *args: self.fail("duplicate send"))

    def test_source_history_and_semantic_queue_duplicates(self):
        other = dict(self.item, id="source2", url="https://t.me/kyrillic/124")
        with self.assertRaisesRegex(ValueError, "duplicates"):
            add_draft(self.db, other, {"text": self.text + "!"})
        self.db.execute("INSERT INTO history VALUES(?,?)", (other["url"], "prior Notion draft"))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "history"):
            add_draft(self.db, other, {"text": "kyrillic обсуждает продажи. Мне интересно, что покупатель делает сразу после первой встречи. Как считаете?"})

    def test_missing_source_credit_and_copied_passage_rejected(self):
        other = dict(self.item, id="source2", url="https://t.me/kyrillic/124")
        with self.assertRaisesRegex(ValueError, "credit"):
            add_draft(self.db, other, {"text": "Перед тем как масштабировать продажи, проверьте, понимает ли команда процесс покупки. Расскажите про ваш подход."})
        other["body_text"] = "один два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать"
        with self.assertRaisesRegex(ValueError, "copies"):
            add_draft(self.db, other, {"text": "kyrillic: один два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать. Что думаете?"})

    def test_emoji_count_and_missing_readback_text(self):
        self.assertEqual(threads_length("Я😀"), 5)
        ids = iter(["11", "22"])
        result = publish({"id": "x", "text": self.text}, Path(self.tmp.name) / "readback.json", "123", "token",
                         poster=lambda *args: {"id": next(ids)},
                         reader=lambda *args: {"id": "22", "permalink": "https://www.threads.com/@founder/post/abc"})
        self.assertEqual(result["status"], "API_CONFIRMED_LINK_UNVERIFIED")

    def test_voice_requires_curated_owner_samples(self):
        path = Path(self.tmp.name) / "voice.json"
        path.write_text(json.dumps({"status": "CORPUS_REVIEWED", "sample_urls": ["https://t.me/kyrillic/1"] * 8}))
        with self.assertRaisesRegex(ValueError, "owner"):
            load_voice(path)

    def test_browser_attempt_is_durable_and_prevents_double_send(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "profile"):
            browser_attempt(self.db, self.draft["id"], "founder", "https://www.threads.com/@wrong")
        result = browser_attempt(self.db, self.draft["id"], "founder", "https://www.threads.com/@founder")
        self.assertEqual(result["text"], self.text)
        self.db.close()
        self.db = connect(self.path)
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "BROWSER_ATTEMPT_STARTED")
        with self.assertRaisesRegex(ValueError, "unused approval"):
            browser_attempt(self.db, self.draft["id"], "founder", "https://www.threads.com/@founder")
        with self.assertRaises(ValueError):
            self.send(lambda *args: self.fail("browser attempt cannot be resent through API"))

    def test_browser_confirmation_requires_exact_text_and_account(self):
        self.approve()
        browser_attempt(self.db, self.draft["id"], "founder", "https://www.threads.com/@founder")
        for readback in [
            {"text": self.text, "permalink": "https://www.threads.com/@wrong/post/abc"},
            {"text": self.text + " changed", "permalink": "https://www.threads.com/@founder/post/abc"},
            {"text": self.text, "permalink": "http://www.threads.com/@founder/post/abc"},
        ]:
            with self.assertRaises(ValueError):
                browser_readback(self.db, self.draft["id"], readback)
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "BROWSER_ATTEMPT_STARTED")
        receipt = browser_readback(self.db, self.draft["id"], {"text": self.text,
                                    "permalink": "https://www.threads.com/@founder/post/Abc_123?x=1"})
        self.assertEqual(receipt["provider"], "threads_browser")
        self.assertEqual(receipt["permalink"], "https://www.threads.com/@founder/post/Abc_123")
        with self.assertRaises(ValueError):
            browser_readback(self.db, self.draft["id"], {"text": self.text, "permalink":receipt["permalink"]})


if __name__ == "__main__":
    unittest.main()
