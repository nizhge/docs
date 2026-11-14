#!/usr/bin/env python3
"""Narrow Publora transport for one approved, text-only Threads destination.

The caller must journal before create_post. No request is retried here.
Provider content is stored content; it is never presented as live text readback.
Contracts: https://docs.publora.com/endpoints/{create-post,get-post,list-posts}
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

from engine import threads_length
from meta_connection import validate_secret

API_BASE = "https://api.publora.com/api/v1"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the API key to a redirect target.
        return None


class PubloraClient:
    def __init__(self, key, opener=None):
        self._key = validate_secret(key)
        self._open = opener or build_opener(NoRedirect()).open

    def request(self, path, body=None, idempotency_key=None):
        if not re.fullmatch(r"(?:create-post|get-post/[a-fA-F0-9]{24}|list-posts\?page=\d+&limit=100&platform=threads)", path):
            raise ValueError("Unsupported Publora operation")
        headers = {"x-publora-key": self._key, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if not idempotency_key or not re.fullmatch(r"gtmbe-[a-f0-9]{64}", idempotency_key):
                raise ValueError("Publication requires a stable idempotency key")
            headers["Idempotency-Key"] = idempotency_key
        request = Request(API_BASE + "/" + path, data=data, headers=headers,
                          method="POST" if data is not None else "GET")
        try:
            with self._open(request, timeout=25) as response:
                raw = response.read(2_000_001)
        except HTTPError as exc:
            raise ValueError("Publora request failed with HTTP " + str(exc.code)) from None
        except Exception:
            raise ValueError("Publora response unavailable; do not repeat a publication") from None
        if len(raw) > 2_000_000:
            raise ValueError("Publora response is too large")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("success") is not True:
            raise ValueError("Publora did not confirm the request")
        return result

    def create_post(self, text, platform_id, idempotency_key):
        if not re.fullmatch(r"threads-\d+", platform_id) or not text.strip() or threads_length(text) > 500:
            raise ValueError("One valid Threads destination and a single text post are required")
        result = self.request("create-post", {"content": text, "platforms": [platform_id],
                                             "publishNow": True, "firstComments": []}, idempotency_key)
        group_id = result.get("postGroupId")
        if not isinstance(group_id, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", group_id):
            raise ValueError("Publora did not return a valid post group ID")
        return group_id

    def get_post(self, group_id):
        if not re.fullmatch(r"[a-fA-F0-9]{24}", group_id):
            raise ValueError("A valid stored Publora post group ID is required")
        return self.request("get-post/" + group_id)

    def find_duplicate(self, text, platform_id):
        """Read all bounded provider history; does not see posts made outside Publora."""
        matches = set()
        for page in range(1, 11):
            result = self.request("list-posts?" + urlencode({"page": page, "limit": 100, "platform": "threads"}))
            posts, pagination = result.get("posts"), result.get("pagination")
            if (not isinstance(posts, list) or any(not isinstance(p, dict) for p in posts)
                    or not isinstance(pagination, dict) or type(pagination.get("hasNextPage")) is not bool):
                raise ValueError("Invalid Publora history response")
            for post in posts:
                platforms = post.get("platforms")
                if not isinstance(platforms, list) or any(not isinstance(p, dict) for p in platforms):
                    raise ValueError("Invalid Publora history targets")
                if post.get("content") == text and any(p.get("platformId") == platform_id for p in platforms):
                    group_id = post.get("postGroupId")
                    if not isinstance(group_id, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", group_id):
                        raise ValueError("Invalid Publora history group ID")
                    matches.add(group_id)
            if not pagination["hasNextPage"]:
                break
        else:
            raise ValueError("Publora history exceeds the checked range; review it before publishing")
        if len(matches) > 1:
            raise ValueError("Several matching Publora posts exist; inspect them without sending")
        return next(iter(matches), None)


def idempotency_key(draft_id, text_hash, platform_id):
    return "gtmbe-" + sha256((platform_id + "\n" + draft_id + "\n" + text_hash).encode()).hexdigest()


def post_report(result, group_id, platform_id, account, text):
    """Validate the provider report without treating stored text as live readback."""
    if (result.get("success") is not True or result.get("postGroupId") != group_id
            or result.get("platforms") != [platform_id]):
        raise ValueError("Publora post group or destination mismatch")
    posts = result.get("posts")
    if not isinstance(posts, list) or len(posts) != 1 or not isinstance(posts[0], dict):
        raise ValueError("Expected exactly one Publora platform post")
    post = posts[0]
    if (post.get("platform") != "threads" or str(post.get("platformId")) != platform_id.removeprefix("threads-")
            or post.get("content") != text or post.get("isThread") is True or post.get("threadParts") not in (None, [])
            or result.get("media") != [] or result.get("firstComments") not in (None, [])
            or result.get("firstComment") not in (None, {})):
        raise ValueError("Publora stored content does not match the approved single text post")
    provider_status = post.get("status")
    states = {"draft": "PUBLORA_DRAFT_NOT_PUBLISHED", "scheduled": "PUBLORA_PENDING",
              "pending": "PUBLORA_PENDING", "processing": "PUBLORA_PENDING",
              "published": "PUBLORA_PUBLISHED_REQUIRES_READBACK", "failed": "PUBLORA_FAILED_NO_RETRY"}
    if provider_status not in states:
        raise ValueError("Unknown Publora publication status")
    permalink, post_id = post.get("permalink"), post.get("postedId")
    if permalink:
        url = urlparse(permalink)
        if (url.scheme != "https" or url.hostname not in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}
                or not re.fullmatch(r"/@" + re.escape(account) + r"/post/[A-Za-z0-9_-]+/?", url.path, re.I)):
            raise ValueError("Publora permalink does not match the intended Threads account")
        permalink = url._replace(query="", fragment="").geturl()
    if post_id is not None and not str(post_id).isdigit():
        raise ValueError("Invalid Threads post ID in Publora report")
    report = {"provider": "publora", "status": states[provider_status], "provider_status": provider_status,
              "post_group_id": group_id, "platform_id": platform_id, "account": account,
              "text_sha256": sha256(text.encode()).hexdigest(), "publication_verified": False,
              "post_id": str(post_id) if post_id is not None else None, "permalink": permalink}
    error = post.get("error")
    if isinstance(error, dict):
        code = error.get("code", "")
        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            report["error_code"] = code
        report["outcome_unknown"] = error.get("outcomeUnknown") is True
    return report
