"""Hand-authored offline HTTP contract fixtures; no real portal requests."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import requests

from gdt_tax.errors import NetworkError
from gdt_tax.http import HttpClient
from gdt_tax.http_policy import OperationPolicy
from gdt_tax.run_hooks import RunBudget, RunCancelled, RunHooks
from tests.test_http import FakeSession, StubResponse


class StreamingResponse(StubResponse):
    def __init__(self, chunks, status=200, headers=None):
        super().__init__(status, headers)
        self.chunks = chunks
        self.closed = False
        self.read_count = 0

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            self.read_count += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed = True


class HttpPolicyTests(unittest.TestCase):
    def client(self, responses, **kwargs):
        session = FakeSession(responses)
        return HttpClient(session=session, **kwargs), session

    def test_unreviewed_urls_never_send_body(self):
        urls = ["https://outside.test/x", "//outside.test/x", "http://dichvucong.gdt.gov.vn/x",
                "https://dichvucong.gdt.gov.vn.evil.test/x",
                "https://user:password@dichvucong.gdt.gov.vn/x",
                "https://dichvucong.gdt.gov.vn:444/x"]
        for url in urls:
            with self.subTest(url=url):
                client, session = self.client([])
                with self.assertRaises(NetworkError):
                    client.post(url, data={"password": "fake-secret"})
                self.assertEqual(session.calls, [])

    def test_redirect_validated_before_sending_body_to_any_other_origin(self):
        for target in ("https://outside.test/x", "http://dichvucong.gdt.gov.vn/x",
                       "https://thuedientu.gdt.gov.vn/Request"):
            for status in (301, 302, 303, 307, 308):
                with self.subTest(target=target, status=status):
                    response = StreamingResponse([], status, {"Location": target + "?token=fake"})
                    client, session = self.client([response])
                    with self.assertRaises(NetworkError) as error:
                        client.post("/loginLDAP", data={"password": "fake-secret"})
                    self.assertNotIn("token=", str(error.exception))
                    self.assertEqual(len(session.calls), 1)
                    self.assertTrue(response.closed)
                    self.assertFalse(session.sent[0]["allow_redirects"])

    def test_internal_redirect_method_body_and_query_semantics(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                redirect = StreamingResponse([], status, {"Location": "/done"})
                final = StreamingResponse([b"ok"])
                client, session = self.client([redirect, final])
                client.post("/loginLDAP", params={"initial": "1"}, data={"password": "fake"})
                expected = "POST" if status in {307, 308} else "GET"
                self.assertEqual(session.calls[1][0], expected)
                self.assertEqual("data" in session.sent[1], expected == "POST")
                self.assertNotIn("params", session.sent[1])
                self.assertTrue(redirect.closed and final.closed)

    def test_multihop_redirect_checks_each_hop_and_stops_cycles(self):
        responses = [StreamingResponse([], 302, {"Location": "/again"}) for _ in range(6)]
        client, session = self.client(responses)
        with self.assertRaisesRegex(NetworkError, "REDIRECT_LIMIT"):
            client.get("/start")
        self.assertEqual(len(session.calls), 6)
        self.assertTrue(all(row.closed for row in responses))

    def test_stream_limit_counts_decoded_bytes_and_closes_response(self):
        response = StreamingResponse([b"abc", b"def", b"ignored"], headers={"Content-Encoding": "gzip"})
        client, _ = self.client([response])
        with self.assertRaisesRegex(NetworkError, "RESPONSE_TOO_LARGE"):
            client.get("/download", operation=OperationPolicy(max_bytes=5))
        self.assertEqual(response.read_count, 2)
        self.assertTrue(response.closed)

    def test_declared_size_never_replaces_actual_size_limit(self):
        for declared in (None, "wrong", "1", "-1"):
            response = StreamingResponse([b"abcdef"], headers={"Content-Length": declared})
            client, _ = self.client([response])
            with self.assertRaises(NetworkError):
                client.get("/download", operation=OperationPolicy(max_bytes=5))
            self.assertTrue(response.closed)
        response = StreamingResponse([b"ignored"], headers={"Content-Length": "1000"})
        client, _ = self.client([response])
        with self.assertRaises(NetworkError):
            client.get("/download", operation=OperationPolicy(max_bytes=5))
        self.assertEqual(response.read_count, 0)
        self.assertTrue(response.closed)

    def test_disconnect_is_not_retried_and_response_is_closed(self):
        response = StreamingResponse([b"part", requests.exceptions.ChunkedEncodingError("broken")])
        client, session = self.client([response])
        with self.assertRaises(NetworkError):
            client.get("/download")
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(response.closed)

    def test_post_requires_explicit_retry_safety(self):
        client, session = self.client([StreamingResponse([], 429)])
        self.assertEqual(client.post("/loginLDAP").status_code, 429)
        self.assertEqual(len(session.calls), 1)
        client, session = self.client([StreamingResponse([], 429)])
        self.assertEqual(client.get("https://thuedientu.gdt.gov.vn/etaxnnt/Request").status_code, 429)
        self.assertEqual(len(session.calls), 1)

    def test_retry_after_is_finite_bounded_and_accepts_http_date(self):
        client, _ = self.client([], min_backoff=0, default_backoff=3, max_backoff=10)
        for raw, expected in (("inf", 3), ("NaN", 3), ("-1", 3), ("999999999", 10), ("5", 5)):
            self.assertEqual(client._retry_delay(StubResponse(429, {"Retry-After": raw})), expected)
        when = datetime.now(timezone.utc) + timedelta(seconds=7)
        self.assertGreater(client._retry_delay(StubResponse(429, {"Retry-After": format_datetime(when)})), 5)

    def test_operation_policy_can_use_slower_growth_for_rate_limited_endpoint(self):
        client, _ = self.client([], min_backoff=2, default_backoff=15, max_backoff=60)
        slow = OperationPolicy('notice-download', retry_safe=True, minimum_attempts=6,
                               retry_growth=1.3)
        delays = [round(client._retry_delay(StubResponse(429), attempt, slow), 2)
                  for attempt in range(1, 6)]
        self.assertEqual(delays, [2.0, 2.6, 3.38, 4.39, 5.71])
        self.assertLess(sum(delays), 20)

    def test_operation_policy_rejects_out_of_range_growth(self):
        with self.assertRaises(ValueError):
            OperationPolicy('x', retry_safe=True, minimum_attempts=2, retry_growth=0.5)
        with self.assertRaises(ValueError):
            OperationPolicy('x', retry_safe=True, minimum_attempts=2, retry_growth=5)

    def test_no_retry_after_uses_short_exponential_backoff(self):
        client, _ = self.client([], min_backoff=2, default_backoff=15, max_backoff=60)
        self.assertEqual(client._retry_delay(StubResponse(429), 1), 2)
        self.assertEqual(client._retry_delay(StubResponse(429), 2), 4)
        self.assertEqual(client._retry_delay(StubResponse(429), 3), 8)
        self.assertEqual(client._retry_delay(StubResponse(429), 5), 32)
        self.assertEqual(client._retry_delay(StubResponse(429, {"Retry-After": "15"}), 1), 15)

    def test_budget_counts_redirects_retries_and_total_bytes(self):
        budget = RunBudget(max_requests=1)
        response = StreamingResponse([], 302, {"Location": "/again"})
        client, session = self.client([response], hooks=RunHooks(budget=budget))
        with self.assertRaisesRegex(NetworkError, "requests"):
            client.get("/start")
        self.assertEqual(len(session.calls), 1)
        response = StreamingResponse([b"abc", b"def"])
        client, _ = self.client([response], hooks=RunHooks(budget=RunBudget(max_bytes=5)))
        with self.assertRaisesRegex(NetworkError, "bytes"):
            client.get("/download")
        self.assertTrue(response.closed)
        budget = RunBudget(max_pages=1, max_auth_attempts=1)
        budget.page()
        budget.authenticate()
        with self.assertRaisesRegex(NetworkError, "pages"):
            budget.page()
        with self.assertRaisesRegex(NetworkError, "authentication"):
            budget.authenticate()

    def test_deadline_clamps_socket_timeout_and_stops_before_next_request(self):
        now = [0.0]
        budget = RunBudget(max_seconds=5, clock=lambda: now[0])
        client, session = self.client([StreamingResponse([b"ok"])], hooks=RunHooks(budget=budget))
        client.get("/start")
        self.assertEqual(session.sent[0]["timeout"], 5)
        now[0] = 6
        with self.assertRaisesRegex(NetworkError, "deadline"):
            client.get("/start")
        self.assertEqual(len(session.calls), 1)

    def test_cancellation_between_chunks_closes_response(self):
        response = StreamingResponse([b"abc", b"def"])
        hooks = RunHooks()
        client, _ = self.client([response], hooks=hooks)
        with patch.object(hooks, "check", side_effect=[None, None, None, RunCancelled()]):
            with self.assertRaises(RunCancelled):
                client.get("/download")
        self.assertTrue(response.closed)
