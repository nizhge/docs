import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from publish_publora import PubloraClient, idempotency_key, post_report
from pipeline import (connect, store_sources, add_draft, approve, digest, send_publora,
                      reconcile_publora, send, browser_attempt, browser_readback)

GROUP = "507f1f77bcf86cd799439011"
PLATFORM = "threads-123"
TEXT = "У kyrillic мысль про первые продажи. Я бы проверил, чему учит каждый отказ, а уже потом строил отдел продаж. Что думаете?"
LINK = "https://www.threads.com/@gtmberu/post/Abc123"


def report(status="published", **post_changes):
    post = {"platform": "threads", "platformId": "123", "content": TEXT,
            "status": status, "postedId": "456" if status == "published" else None,
            "permalink": LINK if status == "published" else None, "isThread": False}
    post.update(post_changes)
    return {"success": True, "postGroupId": GROUP, "platforms": [PLATFORM],
            "posts": [post], "media": [], "firstComments": []}


class FakeClient:
    def __init__(self, existing=None, result=None, before_create=None):
        self.calls = []
        self.existing = existing
        self.result = result or report()
        self.before_create = before_create

    def find_duplicate(self, text, platform):
        self.calls.append("find")
        return self.existing

    def create_post(self, text, platform, key):
        self.calls.append("create")
        if self.before_create:
            self.before_create()
        return GROUP

    def get_post(self, group):
        self.calls.append("get")
        return self.result


class PubloraTransportTests(unittest.TestCase):
    def test_submit_exact_text_one_target_publish_now_key_in_header(self):
        def opener(request, timeout):
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.full_url, "https://api.publora.com/api/v1/create-post")
            self.assertEqual(request.get_header("X-publora-key"), "private_test_key")
            self.assertEqual(request.get_header("Idempotency-key"), stable)
            self.assertEqual(json.loads(request.data), {"content": TEXT, "platforms": [PLATFORM],
                                                       "publishNow": True, "firstComments": []})
            return io.BytesIO(json.dumps({"success": True, "postGroupId": GROUP}).encode())
        stable = idempotency_key("draft1", digest(TEXT), PLATFORM)
        self.assertEqual(stable, idempotency_key("draft1", digest(TEXT), PLATFORM))
        self.assertNotEqual(stable, idempotency_key("draft1", digest(TEXT), "threads-999"))
        self.assertEqual(PubloraClient("private_test_key", opener).create_post(TEXT, PLATFORM, stable), GROUP)

    def test_group_lookup_is_read_only_and_rejects_untrusted_id(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.get_method())
            self.assertIsNone(request.data)
            return io.BytesIO(json.dumps(report()).encode())
        client = PubloraClient("private_test_key", opener)
        self.assertEqual(client.get_post(GROUP)["postGroupId"], GROUP)
        for bad in ["../create-post", GROUP + "?key=secret"]:
            with self.assertRaises(ValueError):
                client.get_post(bad)
        self.assertEqual(calls, ["GET"])

    def test_provider_status_never_becomes_verified_publication(self):
        for state, expected in [("draft", "PUBLORA_DRAFT_NOT_PUBLISHED"),
                                ("scheduled", "PUBLORA_PENDING"), ("published", "PUBLORA_PUBLISHED_REQUIRES_READBACK"),
                                ("failed", "PUBLORA_FAILED_NO_RETRY")]:
            receipt = post_report(report(state), GROUP, PLATFORM, "gtmberu", TEXT)
            self.assertEqual(receipt["status"], expected)
            self.assertFalse(receipt["publication_verified"])
        for changes in [{"platformId": "999"}, {"platform": "instagram"}, {"content": TEXT + "!"},
                        {"isThread": True}, {"permalink": LINK.replace("gtmberu", "wrong")}]:
            with self.assertRaises(ValueError):
                post_report(report(**changes), GROUP, PLATFORM, "gtmberu", TEXT)
        payload = report()
        payload["media"] = [{"mediaId": "unapproved"}]
        with self.assertRaises(ValueError):
            post_report(payload, GROUP, PLATFORM, "gtmberu", TEXT)

    def test_duplicate_scan_checks_pages_and_exact_target(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            page2 = "page=2" in request.full_url
            body = {"success": True, "posts": [{"postGroupId": GROUP, "content": TEXT,
                    "platforms": [{"platformId": PLATFORM if page2 else "threads-999"}]}],
                    "pagination": {"hasNextPage": not page2}}
            return io.BytesIO(json.dumps(body).encode())
        self.assertEqual(PubloraClient("private_test_key", opener).find_duplicate(TEXT, PLATFORM), GROUP)
        self.assertEqual(len(calls), 2)


class PubloraQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "queue.sqlite3"
        self.db = connect(self.path)
        item = {"id": "publora_source", "source": "kyrillic", "category": "telegram",
                "url": "https://t.me/kyrillic/123", "title": "Основатель и продажи",
                "summary": "Первые продажи помогают основателю изучить рынок."}
        store_sources(self.db, [item])
        self.draft = add_draft(self.db, item, {"text": TEXT})
        self.verifier = lambda *args: {"username": "gtmberu", "platform_id": PLATFORM}

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def approve(self):
        approve(self.db, self.draft["id"], digest(TEXT), "gtmberu", "Source and owner voice reviewed", 85)

    def submit(self, client, **kwargs):
        return send_publora(self.db, self.draft["id"], "gtmberu", "private_test_key", PLATFORM,
                            client=client, verifier=kwargs.get("verifier", self.verifier))

    def reconcile(self, client):
        return reconcile_publora(self.db, self.draft["id"], "private_test_key", "gtmberu", PLATFORM, client)

    def test_exact_approval_and_channel_required_before_write(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            self.submit(client)
        self.approve()
        with self.assertRaises(ValueError):
            self.submit(client, verifier=lambda *a: {"username": "wrong", "platform_id": PLATFORM})
        self.db.execute("UPDATE drafts SET text=text || '!'")
        self.db.commit()
        with self.assertRaises(ValueError):
            self.submit(client)
        self.assertEqual(client.calls, [])

    def test_attempt_is_durable_before_create_and_blocks_all_send_routes(self):
        self.approve()
        def check_marker():
            other = connect(self.path)
            row = other.execute("SELECT status,receipt FROM drafts").fetchone()
            other.close()
            self.assertEqual(row["status"], "PUBLORA_ATTEMPT_STARTED")
            self.assertEqual(json.loads(row["receipt"])["platform_id"], PLATFORM)
        client = FakeClient(before_create=check_marker)
        receipt = self.submit(client)
        self.assertEqual(receipt["status"], "PUBLORA_PENDING")
        self.assertFalse(receipt["publication_verified"])
        self.db.close()
        self.db = connect(self.path)
        with self.assertRaises(ValueError):
            self.submit(client)
        with self.assertRaises(ValueError):
            send(self.db, self.draft["id"], "gtmberu", "unused")
        with self.assertRaises(ValueError):
            browser_attempt(self.db, self.draft["id"], "gtmberu", "https://www.threads.com/@gtmberu")
        self.assertEqual(client.calls.count("create"), 1)

    def test_uncertain_submit_is_recovered_only_by_reads(self):
        self.approve()
        def timeout():
            raise TimeoutError("secret must not be logged")
        failed = FakeClient(before_create=timeout)
        with self.assertRaisesRegex(ValueError, "uncertain") as caught:
            self.submit(failed)
        self.assertNotIn("secret", str(caught.exception))
        self.db.close()
        self.db = connect(self.path)
        with self.assertRaises(ValueError):
            self.submit(failed)
        class UnavailableRead(FakeClient):
            def get_post(self, group):
                raise TimeoutError("Read temporarily unavailable")
        with self.assertRaises(TimeoutError):
            self.reconcile(UnavailableRead(existing=GROUP))
        saved = json.loads(self.db.execute("SELECT receipt FROM drafts").fetchone()[0])
        self.assertEqual(saved["post_group_id"], GROUP)
        lookup = FakeClient(existing=GROUP)
        receipt = self.reconcile(lookup)
        self.assertEqual(lookup.calls, ["get"])
        self.assertEqual(receipt["status"], "PUBLORA_PUBLISHED_REQUIRES_READBACK")
        self.assertFalse(receipt["publication_verified"])
        with self.assertRaises(ValueError):
            browser_readback(self.db, self.draft["id"], {"text": TEXT + "!", "permalink": LINK})
        with self.assertRaises(ValueError):
            browser_readback(self.db, self.draft["id"], {"text": TEXT, "permalink": LINK + "Other"})
        verified = browser_readback(self.db, self.draft["id"], {"text": TEXT, "permalink": LINK})
        self.assertEqual(verified["status"], "PUBLISHED_VERIFIED")
        self.assertEqual(verified["post_group_id"], GROUP)
        self.assertEqual(verified["post_id"], "456")

    def test_existing_provider_draft_is_not_sent_again(self):
        self.approve()
        client = FakeClient(existing=GROUP, result=report("draft"))
        self.assertEqual(self.submit(client)["status"], "PUBLORA_EXISTING_REQUIRES_RECONCILIATION")
        receipt = self.reconcile(client)
        self.assertEqual(receipt["status"], "PUBLORA_DRAFT_NOT_PUBLISHED")
        self.assertNotIn("create", client.calls)
        with self.assertRaises(ValueError):
            self.submit(client)

    def test_failed_report_does_not_enable_retry_and_bad_readback_preserves_receipt(self):
        self.approve()
        client = FakeClient(result=report("failed"))
        self.submit(client)
        receipt = self.reconcile(client)
        self.assertEqual(receipt["status"], "PUBLORA_FAILED_NO_RETRY")
        client.result = report(content="wrong")
        with self.assertRaises(ValueError):
            self.reconcile(client)
        self.assertEqual(self.db.execute("SELECT status FROM drafts").fetchone()[0], "PUBLORA_FAILED_NO_RETRY")
        with self.assertRaises(ValueError):
            self.submit(client)
        self.assertEqual(client.calls.count("create"), 1)


if __name__ == "__main__":
    unittest.main()
