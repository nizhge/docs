import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from engine import candidates_from_sources, parse_telegram, exclusion_reason
from pipeline import (connect, approve, digest, generation_candidates, source_gate,
                      store_sources, send_publora, reconcile_publora, browser_readback)
from run_flow import run_flow

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
TEXT = "У kyrillic обсуждают первые продажи. Я бы проверял не только число встреч, но и то, какую задачу покупатель готов оплатить сейчас. Что думаете?"
GROUP = "507f1f77bcf86cd799439011"
LINK = "https://www.threads.com/@gtmberu/post/Abc123"


class NewsFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = connect(self.root / "queue.sqlite3")
        self.sources = self.root / "sources.json"
        self.sources.write_text(json.dumps([{"name": "kyrillic", "type": "telegram", "url": "https://t.me/s/kyrillic"}]))
        self.voice = self.root / "voice.json"
        self.voice.write_text(json.dumps({"status": "CORPUS_REVIEWED", "instructions": ["Specific owner voice."],
                                         "sample_urls": ["https://t.me/gtmbe/" + str(i) for i in range(8)]}))
        self.html = ('<div class="tgme_widget_message" data-post="kyrillic/3000">'
                     '<div class="tgme_widget_message_text">Первые продажи позволяют основателю изучить, '
                     'как покупатель выбирает продукт и какие возражения возникают. Важно понять процесс '
                     'принятия решения, прежде чем масштабировать команду.</div>'
                     '<time datetime="2026-11-16T09:00:00+00:00"></time></div>')
        self.settings = {"PUBLISH_PROVIDER": "publora", "THREADS_USERNAME": "gtmberu", "ENABLE_LIVE_THREADS": "0"}

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def collect(self, sources, **options):
        return candidates_from_sources(sources, fetcher=lambda url: self.html, **options)

    def draft(self, item, key, model, voice):
        self.assertIn("Specific owner voice", voice)
        return {"text": TEXT, "angle": "Buyer demand", "verification_notes": "Opinion; source credited."}

    def run_cycle(self, **options):
        return run_flow(self.db, self.sources, self.voice, self.root, self.settings,
                        now=NOW, collector=self.collect, drafter=self.draft, **options)

    def test_live_parser_to_prompt_packet_without_model_never_fakes_a_draft(self):
        report = self.run_cycle()
        self.assertEqual(report["collection"]["items"], 1)
        self.assertIn("AUTOMATIC_GENERATION_MODEL_NOT_CONNECTED", report["blockers"])
        self.assertIn("PUBLORA_CHANNEL_NOT_CONNECTED", report["blockers"])
        self.assertEqual(report["created"], [])
        request = json.loads((self.root / "generation_requests.json").read_text())[0]
        self.assertIn("Specific owner voice", request["messages"][1]["content"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM drafts").fetchone()[0], 0)
        self.assertEqual((self.root / "generation_requests.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("secret", (self.root / "flow_report.json").read_text())

    def test_collection_to_voice_draft_and_review_is_deduplicated_on_next_run(self):
        self.settings["OPENAI_API_KEY"] = "private_test_model_key"
        first = self.run_cycle()
        second = self.run_cycle()
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(second["created"], [])
        self.assertEqual(second["queue"], {"REVIEW_REQUIRED": 1})
        record = json.loads((self.root / "review.json").read_text())[0]
        self.assertTrue(record["source_sha256"])
        self.assertEqual(record["text_sha256"], digest(TEXT))
        self.assertIn(TEXT, (self.root / "review.html").read_text())
        self.assertNotIn("private_test_model_key", (self.root / "review.html").read_text())
        self.assertEqual(first["verified_publications_total"], 0)

    def test_old_unknown_and_future_dates_never_enter_news_generation(self):
        item = parse_telegram(self.html, "kyrillic")[0]
        item["relevance_score"] = 66
        for date, reason in [("2026-10-01T00:00:00+00:00", "source_too_old"),
                             (None, "source_date_missing"), ("invalid", "source_date_invalid"),
                             ("2027-01-01T00:00:00+00:00", "source_date_in_future")]:
            self.assertEqual(source_gate(dict(item, published_at=date), now=NOW), reason)
        store_sources(self.db, [dict(item, published_at="2026-10-01T00:00:00+00:00")])
        items, excluded = generation_candidates(self.db, now=NOW)
        self.assertEqual(items, [])
        self.assertEqual(excluded, {"source_too_old": 1})

    def test_cached_source_not_fetched_this_run_is_not_sent_or_generated(self):
        item = parse_telegram(self.html, "kyrillic")[0]
        item["relevance_score"] = 66
        store_sources(self.db, [item])
        report = run_flow(self.db, self.sources, self.voice, self.root, self.settings, now=NOW,
                          collector=lambda *a, **k: ([], [{"source": "kyrillic", "error": "private error detail"}]))
        self.assertEqual(report["eligible_sources"], 0)
        self.assertEqual(report["excluded"], {"not_fetched_this_run": 1})
        self.assertNotIn("private error detail", json.dumps(report))

    def test_complete_cycle_only_submits_approved_then_reads_without_resend(self):
        self.settings.update(OPENAI_API_KEY="private_test_model_key", PUBLORA_API_KEY="private_test_key",
                             THREADS_PLATFORM_ID="threads-123", ENABLE_LIVE_THREADS="1")
        report = self.run_cycle()
        draft_id = report["created"][0]
        self.assertEqual(report["submitted"], [])
        approve(self.db, draft_id, digest(TEXT), "gtmberu", "Facts, attribution and voice reviewed", 85)
        calls = []
        class Client:
            def find_duplicate(self, text, platform):
                calls.append("find")
                return None
            def create_post(self, text, platform, key):
                calls.append("POST")
                return GROUP
            def get_post(self, group):
                calls.append("GET")
                return {"success": True, "postGroupId": GROUP, "platforms": ["threads-123"], "media": [],
                        "posts": [{"platform": "threads", "platformId": "123", "content": TEXT,
                                   "status": "published", "postedId": "456", "permalink": LINK}]}
        client = Client()
        def submit(db, ident, settings):
            return send_publora(db, ident, "gtmberu", "private_test_key", "threads-123", client,
                                lambda *a: {"username": "gtmberu", "platform_id": "threads-123"})
        def read(db, ident, settings):
            return reconcile_publora(db, ident, "private_test_key", "gtmberu", "threads-123", client)
        sent = self.run_cycle(publish_approved=True, submitter=submit, reconciler=read)
        again = self.run_cycle(publish_approved=True, submitter=submit, reconciler=read)
        self.assertEqual(calls.count("POST"), 1)
        self.assertEqual(calls.count("GET"), 2)
        self.assertEqual(sent["verified_publications_total"], 0)
        self.assertIn("PRIOR_ATTEMPT_REQUIRES_READBACK", again["blockers"])
        browser_readback(self.db, draft_id, {"text": TEXT, "permalink": LINK})
        final = self.run_cycle(publish_approved=True, submitter=submit, reconciler=read)
        self.assertEqual(final["verified_publications_total"], 1)
        self.assertEqual(calls.count("POST"), 1)

    def test_live_off_and_changed_source_preserve_approval_without_send(self):
        self.settings.update(OPENAI_API_KEY="private_test_model_key", PUBLORA_API_KEY="private_test_key",
                             THREADS_PLATFORM_ID="threads-123")
        draft_id = self.run_cycle()["created"][0]
        approve(self.db, draft_id, digest(TEXT), "gtmberu", "Reviewed", 85)
        reject = lambda *a: self.fail("must not submit")
        disabled = self.run_cycle(publish_approved=True, submitter=reject)
        self.assertIn("LIVE_PUBLISHING_NOT_ENABLED", disabled["blockers"])
        self.settings["ENABLE_LIVE_THREADS"] = "1"
        self.html = self.html.replace("возражения", "новые возражения")
        changed = self.run_cycle(publish_approved=True, submitter=reject)
        self.assertEqual(changed["errors"][0]["reason"], "source_changed_requires_review")
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "APPROVED")

    def test_interrupted_run_replaces_old_report_and_records_terminal_event(self):
        self.run_cycle()
        def fail(*args, **kwargs):
            raise TimeoutError("credential must not be logged")
        with self.assertRaises(TimeoutError):
            run_flow(self.db, self.sources, self.voice, self.root, self.settings, collector=fail)
        report = json.loads((self.root / "flow_report.json").read_text())
        self.assertEqual(report["status"], "INTERRUPTED")
        self.assertNotIn("credential", json.dumps(report))
        self.assertEqual(self.db.execute("SELECT kind FROM events ORDER BY seq DESC LIMIT 1").fetchone()[0], "FLOW_INTERRUPTED")

    def test_timeout_in_full_cycle_never_resubmits_after_restart(self):
        self.settings.update(OPENAI_API_KEY="private_test_model_key", PUBLORA_API_KEY="private_test_key",
                             THREADS_PLATFORM_ID="threads-123", ENABLE_LIVE_THREADS="1")
        draft_id = self.run_cycle()["created"][0]
        approve(self.db, draft_id, digest(TEXT), "gtmberu", "Reviewed", 85)
        calls = []
        class Client:
            def find_duplicate(self, text, platform):
                calls.append("GET_HISTORY")
                return None
            def create_post(self, text, platform, key):
                calls.append("POST")
                raise TimeoutError("Never log credentials")
        client = Client()
        def submit(db, ident, settings):
            return send_publora(db, ident, "gtmberu", "private_test_key", "threads-123", client,
                                lambda *a: {"username": "gtmberu", "platform_id": "threads-123"})
        def read(db, ident, settings):
            return reconcile_publora(db, ident, "private_test_key", "gtmberu", "threads-123", client)
        first = self.run_cycle(publish_approved=True, submitter=submit, reconciler=read)
        self.assertEqual(first["errors"][0]["stage"], "publish")
        self.db.close()
        self.db = connect(self.root / "queue.sqlite3")
        second = self.run_cycle(publish_approved=True, submitter=submit, reconciler=read)
        self.assertEqual(calls.count("POST"), 1)
        self.assertIn("PRIOR_ATTEMPT_REQUIRES_READBACK", second["blockers"])
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "UNKNOWN_REQUIRES_RECONCILIATION")

    def test_approved_news_cannot_age_into_a_later_publication(self):
        self.settings.update(OPENAI_API_KEY="private_test_model_key", PUBLORA_API_KEY="private_test_key",
                             THREADS_PLATFORM_ID="threads-123", ENABLE_LIVE_THREADS="1")
        draft_id = self.run_cycle()["created"][0]
        approve(self.db, draft_id, digest(TEXT), "gtmberu", "Reviewed", 85)
        report = run_flow(self.db, self.sources, self.voice, self.root, self.settings,
                          now=datetime(2026, 11, 24, 12, tzinfo=timezone.utc), collector=self.collect,
                          drafter=self.draft, publish_approved=True,
                          submitter=lambda *a: self.fail("must not send stale news"))
        self.assertEqual(report["errors"][0]["reason"], "source_too_old")
        self.assertEqual(report["submitted"], [])

    def test_event_registration_folder_promotions_and_story_boost_are_excluded(self):
        item = parse_telegram(self.html, "kyrillic")[0]
        for ending in ["Регистрация: @VenturePortBot", "Пройти быструю регистрацию здесь.",
                       "Подписаться можно тут", "Помогите разблокировать сторис"]:
            self.assertEqual(exclusion_reason(dict(item, body_text=item["body_text"] + ending)), "promotion_event_or_job_listing")


if __name__ == "__main__":
    unittest.main()
