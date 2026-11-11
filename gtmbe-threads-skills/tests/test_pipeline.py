import json
import sys
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from engine import (parse_rss, parse_telegram, candidates_from_sources, canonical_url,
                    validate_draft, item_id, load_sources, clean_text, is_owned_telegram, draft_prompt)
from publish_threads import fetch_approved, publish


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.rss = (ROOT / "tests/fixtures/sample_feed.xml").read_text(encoding="utf-8")
        self.item = parse_rss(self.rss, "fixture")[0]

    def test_feed_extracts_title_url_description(self):
        items = parse_rss(self.rss, "fixture")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Founder-led sales tests and pricing experiments")
        self.assertTrue(items[0]["url"].startswith("https://example.com"))
        self.assertEqual(len(items[0]["id"]), 16)

    def test_telegram_public_html_extraction(self):
        html = '<div class="tgme_widget_message" data-post="mychannel/12"><div class="tgme_widget_message_text js-message_text">Новый B2B продукт и маркетинг. Как продать?</div></div>'
        items = parse_telegram(html, "Demo")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://t.me/mychannel/12")
        self.assertIn("маркетинг", items[0]["summary"])

    def test_relevance_ranks_candidates(self):
        items, errors = candidates_from_sources([{"name": "fixture", "type": "rss", "url": "https://example.com/feed"}],
            fetcher=lambda url: self.rss, now=datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertEqual(len(items), 2)
        self.assertFalse(errors)
        self.assertGreater(items[0]["relevance_score"], 30)

    def test_canonical_url_dedupes_tracking(self):
        self.assertEqual(canonical_url("https://Example.com/news/?utm_source=threads"), "https://example.com/news")
        self.assertEqual(item_id("https://a/b"), item_id("https://a/b"))

    def test_rejects_unverified_quantitative_claim(self):
        post = "В B2B SaaS рост 900% из ниоткуда. Что думаете?"
        self.assertIn("Numeric claim", validate_draft(post, self.item))

    def test_requires_soft_cta(self):
        self.assertIn("CTA", validate_draft("Сначала проверяйте спрос, потом масштабируйте маркетинг и продажи.", self.item))
        self.assertIsNone(validate_draft("Вместо долгих GTM-презентаций я бы начинал с разговоров с покупателями. А вы как считаете?", self.item))

    def test_owner_telegram_keeps_original_wording(self):
        original = "У стартапа может быть красивый продукт, но без понятного покупателя GTM не полетит. Как считаете?"
        base = {"category": "telegram", "title": original[:120], "summary": original, "url": "https://t.me/example/123"}
        owned = dict(base, source="owner Telegram (operator supplied)")
        external = dict(base, source="external channel")
        self.assertTrue(is_owned_telegram(owned))
        self.assertIsNone(validate_draft(original, owned))
        self.assertIn("Too close", validate_draft(original, external))
        self.assertIn("light-touch", draft_prompt(owned)[0]["content"])
        self.assertIn("third-party", draft_prompt(external)[0]["content"])

    def test_source_registry_telegram_first(self):
        sources = load_sources(ROOT / "config/research_sources.json")
        self.assertTrue(sources)
        self.assertTrue(all(src["type"] == "telegram" for src in sources))

    def test_source_registry_has_only_https(self):
        sources = load_sources(ROOT / "config/research_sources.json")
        self.assertGreaterEqual(len(sources), 6)
        self.assertTrue(all(s["url"].startswith("https://") for s in sources))


class PublisherTests(unittest.TestCase):
    def test_exact_sha_approval_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            post = "Сначала проверяйте спрос, потом пишите стратегию. А вы как считаете?"
            digest = sha256(post.encode()).hexdigest()
            drafts = [{"id": "draft_one", "text": post, "text_sha256": digest, "status": "REVIEW_REQUIRED"}]
            (root / "drafts.json").write_text(json.dumps(drafts), encoding="utf-8")
            (root / "approval.json").write_text(json.dumps({"draft_one": "wrong"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                fetch_approved(root / "drafts.json", root / "approval.json", "draft_one")
            (root / "approval.json").write_text(json.dumps({"draft_one": digest}), encoding="utf-8")
            self.assertEqual(fetch_approved(root / "drafts.json", root / "approval.json", "draft_one")["id"], "draft_one")

    def test_live_publisher_rejects_duplicate_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            post = {"id": "draft_one", "text": "Valid source-backed post with a gentle CTA. What do you think?"}
            calls = []
            def fake_post(url, form, token):
                calls.append(url)
                return {"id": "12345" if len(calls) == 1 else "67890"}
            receipts = Path(tmp) / "receipts.json"
            res = publish(post, receipts, "123", "test", poster=fake_post)
            self.assertEqual(res["status"], "API_CONFIRMED")
            self.assertEqual(len(calls), 2)
            with self.assertRaises(ValueError):
                publish(post, receipts, "123", "test", poster=fake_post)
            self.assertEqual(len(calls), 2)

    def test_uncertain_publish_is_blocked_on_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipts = Path(tmp) / "receipts.json"
            post = {"id": "draft_unknown", "text": "Some post"}
            def fail(url, form, token):
                raise TimeoutError("network disconnected")
            with self.assertRaises(TimeoutError):
                publish(post, receipts, "123", "test", poster=fail)
            self.assertIn("UNKNOWN", receipts.read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                publish(post, receipts, "123", "test", poster=fail)


if __name__ == "__main__":
    unittest.main()
