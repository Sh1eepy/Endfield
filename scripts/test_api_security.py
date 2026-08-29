"""Offline API security regressions. No CDN, private network or LLM calls."""
import asyncio
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("HF_HUB_OFFLINE", "1")
from scripts import api_server, api_security


class CountingStream(httpx.SyncByteStream):
    def __init__(self, chunks=64, size=64 * 1024):
        self.chunks, self.size = chunks, size
        self.read = 0
        self.closed = False

    def __iter__(self):
        for _ in range(self.chunks):
            self.read += self.size
            yield b"a" * self.size

    def close(self):
        self.closed = True


class MediaSecurityTests(unittest.TestCase):
    URL = "https://bbs.hycdn.cn/image/test.png"

    def setUp(self):
        self.guard = threading.BoundedSemaphore(1)
        patcher = patch.object(api_server, "_MEDIA_SEMAPHORE", self.guard)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, response, expected_status=None):
        requests = []
        source_stream = response.stream

        def handler(request):
            requests.append(request)
            return response

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with patch("httpx.stream", side_effect=client.stream):
                if expected_status:
                    with self.assertRaises(HTTPException) as caught:
                        api_server.media_proxy(self.URL)
                    self.assertEqual(caught.exception.status_code, expected_status)
                else:
                    result = api_server.media_proxy(self.URL)
                    self.assertEqual(result.body, b"a" * source_stream.read)
                    self.assertIn("max-age=86400", result.headers["cache-control"])
                    self.assertFalse(self.guard.acquire(blocking=False), "slot held until response sent")

                    async def noop(*args):
                        pass

                    asyncio.run(result({"type": "http"}, noop, noop))
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers["accept-encoding"], "identity")
        self.assertTrue(source_stream.closed)
        self.assertTrue(self.guard.acquire(blocking=False), "all exits must release media slot")
        self.guard.release()

    def test_redirects_never_fetch_location(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                stream = CountingStream()
                self.fetch(httpx.Response(status, headers={
                    "location": "http://127.0.0.1:9/mock-only"}, stream=stream), 502)
                self.assertEqual(stream.read, 0)

    def test_url_validation_before_network(self):
        for url in (
            "http://bbs.hycdn.cn/image/a", "https://example.com/image/a",
            "https://bbs.hycdn.cn.evil.test/image/a", "https://bbs.hycdn.cn:8080/image/a",
            "https://bbs.hycdn.cn:bad/image/a", "https://user@bbs.hycdn.cn/image/a",
            "https://bbs.hycdn.cn/other/a", "https://[broken/image/a",
        ):
            with self.subTest(url=url), patch("httpx.stream") as stream:
                with self.assertRaises(HTTPException) as caught:
                    api_server.media_proxy(url)
                self.assertEqual(caught.exception.status_code, 400)
                stream.assert_not_called()

    def test_declared_oversize_rejected_before_read(self):
        stream = CountingStream()
        self.fetch(httpx.Response(200, headers={"content-type": "image/png",
            "content-length": str(api_server.MEDIA_MAX_BYTES + 1)}, stream=stream), 413)
        self.assertEqual(stream.read, 0)

    def test_missing_or_dishonest_length_cannot_bypass_stream_limit(self):
        for length in (None, "1"):
            with self.subTest(length=length):
                headers = {"content-type": "audio/mpeg"}
                if length is not None:
                    headers["content-length"] = length
                stream = CountingStream(chunks=1000)
                with patch.object(api_server, "MEDIA_MAX_BYTES", 128 * 1024):
                    self.fetch(httpx.Response(200, headers=headers, stream=stream), 413)
                self.assertEqual(stream.read, 3 * 64 * 1024)

    def test_media_at_exact_limit_is_accepted(self):
        stream = CountingStream(chunks=2)
        with patch.object(api_server, "MEDIA_MAX_BYTES", 128 * 1024):
            self.fetch(httpx.Response(200, headers={"content-type": "image/png"}, stream=stream))

    def test_bad_type_encoding_length_and_status_rejected_without_read(self):
        cases = (
            (200, {"content-type": "text/html"}, 415),
            (200, {"content-type": "image/png", "content-encoding": "gzip"}, 502),
            (200, {"content-type": "image/png", "content-length": "invalid"}, 502),
            (200, {"content-type": "image/png", "content-length": "-1"}, 502),
            (404, {}, 502),
        )
        for status, headers, expected in cases:
            with self.subTest(headers=headers, status=status):
                stream = CountingStream()
                self.fetch(httpx.Response(status, headers=headers, stream=stream), expected)
                self.assertEqual(stream.read, 0)

    def test_full_concurrency_rejected_without_download(self):
        self.guard.acquire()
        try:
            with patch("httpx.stream") as stream, patch.object(self.guard, "acquire", return_value=False):
                with self.assertRaises(HTTPException) as caught:
                    api_server.media_proxy(self.URL)
                self.assertEqual(caught.exception.status_code, 429)
                stream.assert_not_called()
        finally:
            self.guard.release()

    def test_upstream_timeout_releases_slot(self):
        with patch("httpx.stream", side_effect=httpx.ReadTimeout("mock only")):
            with self.assertRaises(HTTPException) as caught:
                api_server.media_proxy(self.URL)
            self.assertEqual(caught.exception.status_code, 502)
        self.assertTrue(self.guard.acquire(blocking=False))
        self.guard.release()

    def test_client_disconnect_releases_slot_and_buffer(self):
        self.guard.acquire()
        response = api_server._MediaResponse(b"test", slot=self.guard)

        async def disconnected(*args):
            raise OSError("mock client disconnected")

        with self.assertRaises(OSError):
            asyncio.run(response({"type": "http"}, disconnected, disconnected))
        self.assertEqual(response.body, b"")
        self.assertTrue(self.guard.acquire(blocking=False))
        self.guard.release()


class AskBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="endfield-security-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "budget.sqlite3"

    def test_minute_limit_persists_across_instances(self):
        api_security.AskBudget(self.path, per_minute=1).consume("a", now=120)
        with self.assertRaises(HTTPException) as caught:
            api_security.AskBudget(self.path, per_minute=1).consume("a", now=121)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.headers["Retry-After"], "59")
        api_security.AskBudget(self.path, per_minute=1).consume("a", now=180)

    def test_daily_ip_limit_and_utc_day_reset(self):
        budget = api_security.AskBudget(self.path, per_ip_day=1)
        budget.consume("a", now=120)
        with self.assertRaises(HTTPException):
            budget.consume("a", now=240)
        budget.consume("b", now=240)
        budget.consume("a", now=86400)

    def test_global_limit_applies_across_client_ips(self):
        budget = api_security.AskBudget(self.path, per_day=1)
        budget.consume("a", now=120)
        with self.assertRaises(HTTPException) as caught:
            budget.consume("b", now=121)
        self.assertIn("本站", caught.exception.detail)

    def test_concurrent_instances_cannot_overspend(self):
        def admit(index):
            try:
                api_security.AskBudget(self.path, per_day=3).consume(str(index), now=120)
                return 200
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(admit, range(20)))
        self.assertEqual(statuses.count(200), 3)
        self.assertEqual(statuses.count(429), 17)

    def test_store_errors_fail_closed(self):
        with self.assertRaises(HTTPException) as caught:
            api_security.AskBudget(Path(self.tmp.name)).consume("a")
        self.assertEqual(caught.exception.status_code, 503)


class HttpAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="endfield-http-security-")
        self.addCleanup(self.tmp.cleanup)
        self.budget = api_security.AskBudget(Path(self.tmp.name) / "usage.sqlite3", per_minute=2)
        for patcher in (
            patch.object(api_security, "ASK_BUDGET", self.budget),
            patch.object(api_security, "FEEDBACK_BUDGET", api_security.AskBudget(
                Path(self.tmp.name) / "usage.sqlite3", per_minute=2, namespace="feedback")),
            patch.object(api_security, "API_ACCESS_TOKEN", ""),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_anonymous_calls_are_limited_before_llm(self):
        with TestClient(api_server.app) as client, patch("rag_ask.ask", return_value={"ok": True}) as ask:
            responses = [client.post("/api/ask", json={"query": "test", "gen_answer": False}) for _ in range(3)]
        self.assertEqual([r.status_code for r in responses], [200, 200, 429])
        self.assertEqual(ask.call_count, 2)
        self.assertIn("Retry-After", responses[-1].headers)

    def test_bearer_token_is_required_when_configured(self):
        with patch.object(api_security, "API_ACCESS_TOKEN", "test-secret"), TestClient(api_server.app) as client:
            with patch("rag_ask.ask", return_value={"ok": True}) as ask:
                for header in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic test-secret"}):
                    response = client.post("/api/ask", json={"query": "test"}, headers=header)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers["www-authenticate"], "Bearer")
                ask.assert_not_called()
                for _ in range(2):
                    self.assertEqual(client.post("/api/ask", json={"query": "test"}, headers={
                        "Authorization": "Bearer test-secret"}).status_code, 200)
                self.assertEqual(ask.call_count, 2, "bad tokens must not consume daily quota")

    def test_feedback_uses_token_and_independent_rate_limit(self):
        payload = {"trace_id": "a" * 32, "query": "test", "vote": "useful",
                   "observed_answer": "answer", "client_type": "web"}
        with patch.object(api_security, "API_ACCESS_TOKEN", "test-secret"), \
                patch("scripts.rag_trace.trace_store.submit_feedback",
                      return_value={"feedback_id": "f", "status": "pending_review"}) as submit, \
                TestClient(api_server.app) as client:
            self.assertEqual(client.post("/api/feedback", json=payload).status_code, 401)
            headers = {"Authorization": "Bearer test-secret"}
            statuses = [client.post("/api/feedback", json=payload, headers=headers).status_code
                        for _ in range(3)]
        self.assertEqual(statuses, [201, 201, 429])
        self.assertEqual(submit.call_count, 2)

    def test_forwarding_headers_cannot_reset_ip_limit(self):
        with TestClient(api_server.app) as client, patch("rag_ask.ask", return_value={"ok": True}):
            statuses = [client.post("/api/ask", json={"query": "test"}, headers={
                "X-Forwarded-For": f"192.0.2.{i}", "X-Real-IP": f"192.0.2.{i}"
            }).status_code for i in range(3)]
        self.assertEqual(statuses, [200, 200, 429])

    def test_store_failure_never_calls_llm(self):
        with patch.object(self.budget, "path", Path(self.tmp.name)), TestClient(api_server.app) as client:
            with patch("rag_ask.ask") as ask:
                self.assertEqual(client.post("/api/ask", json={"query": "test"}).status_code, 503)
                ask.assert_not_called()

    def test_admin_routes_reject_remote_and_spoofed_headers(self):
        with TestClient(api_server.app) as client:
            for path in ("/api/health/deep", "/api/metrics"):
                self.assertEqual(client.get(path, headers={"X-Forwarded-For": "127.0.0.1"}).status_code, 403)
            self.assertEqual(client.get("/api/health").status_code, 200)

    def test_admin_allows_loopback_or_token(self):
        with TestClient(api_server.app, client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/metrics").status_code, 200)
        with patch.object(api_security, "API_ACCESS_TOKEN", "test-secret"), TestClient(api_server.app) as client:
            self.assertEqual(client.get("/api/metrics", headers={"Authorization": "Bearer test-secret"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
