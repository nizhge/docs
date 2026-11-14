import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from meta_connection import save_connection, read_settings, secret_input


class MetaConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = Path(self.temp.name) / "connection.env"
        self.meta = Path(self.temp.name) / "meta.json"
        self.env.write_text("THREADS_USERNAME=gtmberu\nOPENAI_API_KEY=preserved_model_key\nENABLE_LIVE_THREADS=1\n")
        self.verify = lambda token, uid, name: {"id": "123", "username": "gtmberu"}

    def tearDown(self):
        self.temp.cleanup()

    def test_connect_saves_privately_only_after_identity_check(self):
        result = save_connection("test_token_value", "gtmberu", self.env, self.meta, verifier=self.verify)
        settings = read_settings(self.env)
        self.assertEqual(settings["THREADS_ACCESS_TOKEN"], "test_token_value")
        self.assertEqual(settings["OPENAI_API_KEY"], "preserved_model_key")
        self.assertEqual(settings["ENABLE_LIVE_THREADS"], "0")
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.meta.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("test_token_value", json.dumps(result))
        self.assertFalse(result["publishing_permissions_verified"])

    def test_failed_identity_preserves_existing_connection(self):
        original = self.env.read_text()
        def wrong(*args):
            raise ValueError("Threads username does not match")
        with self.assertRaises(ValueError):
            save_connection("test_token_value", "gtmberu", self.env, self.meta, verifier=wrong)
        self.assertEqual(self.env.read_text(), original)
        self.assertFalse(self.meta.exists())

    def test_exchange_rechecks_replacement_identity(self):
        tokens = []
        def verify(token, uid, name):
            tokens.append(token)
            return self.verify(token, uid, name)
        result = save_connection("short_test_token", "gtmberu", self.env, self.meta,
                                 exchange=True, app_secret="test_app_secret", verifier=verify,
                                 requester=lambda *args: {"access_token": "long_test_token", "expires_in": 5184000})
        self.assertEqual(tokens, ["short_test_token", "long_test_token"])
        self.assertEqual(read_settings(self.env)["THREADS_ACCESS_TOKEN"], "long_test_token")
        self.assertEqual(result["token_kind"], "long_lived")
        self.assertIsNotNone(result["expires_at"])

    def test_failed_exchange_never_overwrites_current_token(self):
        original = self.env.read_text()
        with self.assertRaises(ValueError):
            save_connection("short_test_token", "gtmberu", self.env, self.meta,
                            exchange=True, app_secret="test_app_secret", verifier=self.verify,
                            requester=lambda *args: {"access_token": "long_test_token"})
        self.assertEqual(self.env.read_text(), original)

    def test_refresh_keeps_existing_live_choice(self):
        save_connection("long_test_token", "gtmberu", self.env, self.meta, verifier=self.verify,
                        requester=lambda *args: {"access_token": "refreshed_test_token", "expires_in": 5184000}, refresh=True)
        self.assertEqual(read_settings(self.env)["ENABLE_LIVE_THREADS"], "1")

    def test_secret_file_must_be_private_and_cannot_inject_env(self):
        path = Path(self.temp.name) / "token.txt"
        path.write_text("test_token_value")
        os.chmod(path, 0o644)
        with self.assertRaises(ValueError):
            secret_input(path, "unused")
        os.chmod(path, 0o600)
        self.assertEqual(secret_input(path, "unused"), "test_token_value")
        path.write_text("a_test_token\nENABLE_LIVE_THREADS=1")
        with self.assertRaises(ValueError):
            secret_input(path, "unused")


if __name__ == "__main__":
    unittest.main()
