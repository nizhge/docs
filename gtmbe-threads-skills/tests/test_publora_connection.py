import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from meta_connection import read_settings
from publora_connection import list_connections, save_connection, verify_connection


class PubloraConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = Path(self.temp.name) / "connection.env"
        self.metadata = Path(self.temp.name) / "publora.json"
        self.env.write_text("THREADS_USERNAME=gtmberu\nOPENAI_API_KEY=existing_model_key\nENABLE_LIVE_THREADS=1\n")
        self.channel = {"platformId": "threads-123", "username": "@gtmberu",
                        "connectionStatus": "active", "tokenStatus": "valid",
                        "profileUrl": "https://www.threads.com/@gtmberu"}

    def tearDown(self):
        self.temp.cleanup()

    def test_read_only_request_uses_header_and_rejects_bad_response(self):
        def opener(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertNotIn("test_key", request.full_url)
            self.assertEqual(request.get_header("X-publora-key"), "test_key")
            return io.BytesIO(json.dumps({"success": True, "connections": [self.channel]}).encode())
        self.assertEqual(list_connections("test_key", opener), [self.channel])
        with self.assertRaises(ValueError):
            list_connections("test_key", lambda *a, **k: io.BytesIO(b'{"success": false}'))

    def test_connect_saves_exact_channel_privately_with_live_off(self):
        result = save_connection("private_test_key", "gtmberu", self.env, self.metadata,
                                 reader=lambda key: [self.channel])
        settings = read_settings(self.env)
        self.assertEqual(settings["PUBLISH_PROVIDER"], "publora")
        self.assertEqual(settings["THREADS_PLATFORM_ID"], "threads-123")
        self.assertEqual(settings["OPENAI_API_KEY"], "existing_model_key")
        self.assertEqual(settings["ENABLE_LIVE_THREADS"], "0")
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.metadata.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("private_test_key", json.dumps(result))
        self.assertFalse(result["publishing_permissions_verified"])

    def test_wrong_account_or_other_platform_never_replaces_settings(self):
        original = self.env.read_text()
        for change in [{"username": "wrong"}, {"platformId": "instagram-123"},
                       {"profileUrl": "https://www.threads.com/@wrong"}]:
            with self.assertRaises(ValueError):
                save_connection("private_test_key", "gtmberu", self.env, self.metadata,
                                reader=lambda key: [dict(self.channel, **change)])
            self.assertEqual(self.env.read_text(), original)
            self.assertFalse(self.metadata.exists())

    def test_inactive_expired_or_ambiguous_connection_is_rejected(self):
        for channels in [[dict(self.channel, connectionStatus="reconnect_required")],
                         [dict(self.channel, tokenStatus="expired")],
                         [self.channel, dict(self.channel, platformId="threads-456")], []]:
            with self.assertRaises(ValueError):
                verify_connection("private_test_key", "gtmberu", reader=lambda key: channels)

    def test_existing_platform_binding_is_preserved(self):
        self.env.write_text(self.env.read_text() + "THREADS_PLATFORM_ID=threads-999\n")
        original = self.env.read_text()
        with self.assertRaises(ValueError):
            save_connection("private_test_key", "gtmberu", self.env, self.metadata,
                            reader=lambda key: [self.channel])
        with self.assertRaises(ValueError):
            save_connection("private_test_key", "gtmberu", self.env, self.metadata,
                            platform_id="threads-123", reader=lambda key: [self.channel])
        self.assertEqual(self.env.read_text(), original)

    def test_partial_configuration_and_newline_key_rejected(self):
        for name in ["", "gtmberu extra"]:
            with self.assertRaises(ValueError):
                verify_connection("private_test_key", name, reader=lambda key: [self.channel])
        with self.assertRaises(ValueError):
            save_connection("private_test_key\nENABLE_LIVE_THREADS=1", "gtmberu", self.env, self.metadata)


if __name__ == "__main__":
    unittest.main()
