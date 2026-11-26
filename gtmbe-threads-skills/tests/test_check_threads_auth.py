import io
import json
import sys
from pathlib import Path
import unittest
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_threads_auth import check_auth, get_profile, AuthCheckError, PROFILE_URL


class CheckThreadsAuthTests(unittest.TestCase):
    def test_empty_token_blocks_network(self):
        self.assertEqual(check_auth("", "gtmberu", fetcher=lambda token: self.fail("network used"))["status"],
                         "MISSING_THREADS_ACCESS_TOKEN")

    def test_empty_username_blocks_network(self):
        self.assertEqual(check_auth("test_secret", "", fetcher=lambda token: self.fail("network used"))["status"],
                         "MISSING_THREADS_USERNAME")

    def test_account_matches_but_does_not_imply_publish_permission(self):
        result = check_auth("test_secret", "@gtmberu", fetcher=lambda token: {"id": "789", "username": "gtmberu"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["posting_enabled"])
        self.assertFalse(result["publish_scope_verified"])
        self.assertEqual(result["status"], "IDENTITY_VERIFIED_PUBLISH_SCOPE_UNCHECKED")
        self.assertNotIn("test_secret", json.dumps(result))

    def test_account_mismatch_blocks_auth(self):
        result = check_auth("test_secret", "gtmberu", fetcher=lambda token: {"id": "789", "username": "someone_else"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "THREADS_WRONG_ACCOUNT")

    def test_id_mismatch_blocks_auth(self):
        result = check_auth("test_secret", "gtmberu", "456", fetcher=lambda token: {"id": "789", "username": "gtmberu"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "THREADS_WRONG_USER_ID")

    def test_invalid_account_id_blocks_auth(self):
        result = check_auth("test_secret", "gtmberu", fetcher=lambda token: {"id": "bad", "username": "gtmberu"})
        self.assertEqual(result["status"], "THREADS_INCOMPLETE_PROFILE")

    def test_token_uses_header_not_url_and_get_only(self):
        def opener(req, timeout):
            self.assertEqual(req.full_url, PROFILE_URL)
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), "Bearer test_secret")
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self, *args): return b'{"id":"789","username":"gtmberu"}'
            return Response()
        self.assertEqual(get_profile("test_secret", opener=opener)["id"], "789")

    def test_http_error_reports_no_credential(self):
        def opener(req, timeout):
            raise HTTPError(req.full_url, 401, "invalid secret test_secret", {}, io.BytesIO(
                b'{"error":{"code":190,"message":"secret test_secret"}}'))
        with self.assertRaises(AuthCheckError) as cm:
            get_profile("test_secret", opener=opener)
        self.assertEqual(cm.exception.meta_code, 190)
        self.assertNotIn("test_secret", str(cm.exception))

    def test_network_error_is_sanitized(self):
        def opener(req, timeout):
            raise URLError("test_secret appears in internal error")
        with self.assertRaises(AuthCheckError) as cm:
            get_profile("test_secret", opener=opener)
        self.assertEqual(str(cm.exception), "THREADS_NETWORK_ERROR")

    def test_invalid_json_is_sanitized(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return b'invalid json'
        with self.assertRaises(AuthCheckError) as cm:
            get_profile("test_secret", opener=lambda *args, **kwargs: Response())
        self.assertEqual(cm.exception.status, "THREADS_INVALID_RESPONSE")


if __name__ == "__main__":
    unittest.main()
