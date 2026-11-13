import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from auto_publish_owner import (
    select_eligible, do_run, load_state, verify_identity, text_digest
)


def make_html(posts):
    result = []
    for post_id, text, timestamp, forwarded in posts:
        forwarded_tag = '<div class="tgme_widget_message_forwarded_from">From another channel</div>' if forwarded else ""
        result.append(
            f'<div class="tgme_widget_message" data-post="gtmbe/{post_id}">'
            f'{forwarded_tag}'
            f'<div class="tgme_widget_message_text js-message_text">{text}</div>'
            f'<time datetime="{timestamp}">today</time></div>'
        )
    return "".join(result)


class AutoOwnerTests(unittest.TestCase):
    def setUp(self):
        self.today = datetime(2026, 11, 13, tzinfo=timezone.utc)
        self.owned_text = (
            "У продукта часто нет проблемы с маркетингом как таковым. "
            "Есть проблема в том, что непонятно, кто именно готов платить. "
            "Сначала разговариваешь с клиентами, проверяешь цену, "
            "а уже потом льёшь трафик. Иначе быстро покупаешь себе иллюзию спроса."
        )
        self.html = make_html([
            (300, self.owned_text, "2026-11-12T10:00:00+00:00", False),
            (301, "Поддержите запуск нашей платформы и заходите на Product Hunt! "
                  "Сегодня мы запустились, ваша поддержка очень нужна нашей команде.",
             "2026-11-12T09:00:00+00:00", False),
            (302, self.owned_text, "2026-11-11T10:00:00+00:00", True),
            (303, "Очень коротко.", "2026-11-11T11:00:00+00:00", False),
        ])

    def test_selection_excludes_promos_forwards_short(self):
        selected = select_eligible(self.html, today=self.today)
        self.assertEqual([x["source_post_id"] for x in selected], ["300"])
        self.assertEqual(selected[0]["text"], self.owned_text)
        self.assertEqual(selected[0]["text_sha256"], text_digest(self.owned_text))

    def test_preview_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            result = do_run(self.html, path, False, today=self.today)
            self.assertEqual(result["status"], "PREVIEW_ONLY")
            self.assertEqual(result["posted"], 0)
            self.assertFalse(path.exists())

    def test_wrong_account_fails_before_publishing(self):
        fake_getter = lambda url, token: {"id": "999", "username": "wrong"}
        with self.assertRaisesRegex(ValueError, "different user"):
            verify_identity("test", "123", "right", getter=fake_getter)

    def test_live_persists_attempt_before_sending_and_dedupes(self):
        events = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"GTMBE_AUTO_PUBLISH": "true"}):
            path = Path(tmp) / "state.json"
            def getter(url, token):
                if "me?fields=" in url:
                    return {"id": "123", "username": "gtmbe_actual"}
                if "me/threads?" in url:
                    return {"data": []}
                raise ValueError("Unexpected URL")
            def committer(path):
                events.append(("persist", load_state(path)["entries"]["https://t.me/gtmbe/300"]["status"]))
            def sender(post, receipts, uid, token):
                events.append(("sent", post["text"]))
                return {"status": "PUBLISHED_VERIFIED", "post_id": "12345",
                        "permalink": "https://www.threads.com/@gtmbe_actual/post/C_test"}
            output = do_run(self.html, path, True, token="token", user_id="123",
                            username="@gtmbe_actual", getter=getter,
                            sender=sender, committer=committer, today=self.today)
            self.assertEqual(output["status"], "PUBLISHED_VERIFIED")
            self.assertEqual(output["posted"], 1)
            self.assertEqual(events[0], ("persist", "ATTEMPT_STARTED"))
            self.assertEqual(events[1], ("sent", self.owned_text))
            self.assertEqual(events[2], ("persist", "PUBLISHED_VERIFIED"))
            output2 = do_run(self.html, path, True, token="token", user_id="123",
                             username="@gtmbe_actual", getter=getter,
                             sender=sender, committer=committer, today=self.today)
            self.assertEqual(output2["posted"], 0)
            self.assertEqual(output2["status"], "NO_ELIGIBLE_POST")

    def test_error_leaves_durable_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"GTMBE_AUTO_PUBLISH": "true"}):
            path = Path(tmp) / "state.json"
            def getter(url, token):
                if "me?fields=" in url:
                    return {"id": "123", "username": "gtmbe_actual"}
                return {"data": []}
            def sender(*args):
                raise TimeoutError("post could have been sent")
            with self.assertRaises(TimeoutError):
                do_run(self.html, path, True, token="token", user_id="123",
                       username="gtmbe_actual", getter=getter, sender=sender,
                       committer=lambda path: None, today=self.today)
            self.assertEqual(load_state(path)["entries"]["https://t.me/gtmbe/300"]["status"],
                             "ATTEMPT_STARTED")


if __name__ == "__main__":
    unittest.main()
