import unittest

from gdt_tax.http import HttpClient


class StubResponse:
    def __init__(self, status_code: int, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.content = b""
        self.text = ""


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def make_client(responses, **kwargs) -> tuple[HttpClient, FakeSession]:
    session = FakeSession(responses)
    client = HttpClient(
        session=session,
        retries=kwargs.pop("retries", 3),
        min_backoff=0.0,
        default_backoff=0.0,
        **kwargs,
    )
    return client, session


class UrlJoiningTests(unittest.TestCase):
    def test_ghep_duong_dan_tuong_doi(self):
        client, _ = make_client([])
        self.assertEqual(
            client.url("/tchs/thuedientu"), "https://dichvucong.gdt.gov.vn/tthc/tchs/thuedientu"
        )

    def test_giu_nguyen_url_day_du(self):
        client, _ = make_client([])
        self.assertEqual(client.url("https://khac.example/x"), "https://khac.example/x")


class RetryTests(unittest.TestCase):
    def test_thu_lai_khi_bi_gioi_han_tan_suat(self):
        client, session = make_client(
            [
                StubResponse(429, {"Retry-After": "0"}),
                StubResponse(429, {"Retry-After": "0"}),
                StubResponse(200),
            ]
        )
        response = client.get("/tchs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(session.calls), 3)

    def test_tra_ve_429_o_lan_thu_cuoi(self):
        client, session = make_client(
            [StubResponse(429), StubResponse(429), StubResponse(429)], retries=3
        )
        response = client.get("/tchs")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(session.calls), 3)

    def test_khong_thu_lai_voi_ma_khac(self):
        client, session = make_client([StubResponse(500)])
        self.assertEqual(client.get("/tchs").status_code, 500)
        self.assertEqual(len(session.calls), 1)

    def test_retry_after_sai_dinh_dang_dung_mac_dinh(self):
        client, session = make_client(
            [StubResponse(429, {"Retry-After": "khong-phai-so"}), StubResponse(200)]
        )
        self.assertEqual(client.get("/tchs").status_code, 200)
        self.assertEqual(len(session.calls), 2)

    def test_dong_session(self):
        client, session = make_client([])
        client.close()
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
