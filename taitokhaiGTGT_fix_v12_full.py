# -*- coding: utf-8 -*-
"""Đăng nhập DVC Thuế, tìm hồ sơ và tải ZIP trong khoảng ngày cấu hình."""

import base64
import os
import re
import sys
import time
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path

import cv2
import easyocr
import numpy as np
import requests
from bs4 import BeautifulSoup


BASE = "https://dichvucong.gdt.gov.vn/tthc"
USERNAME = os.getenv("GDT_USERNAME", "0101234567-QL").strip()
PASSWORD = os.getenv("GDT_PASSWORD", "REDACTED")
FROM_DATE = os.getenv("GDT_FROM_DATE", "01/08/2026")
TO_DATE = os.getenv("GDT_TO_DATE", "31/08/2026")
DOWNLOAD_DIR = Path(os.getenv("GDT_DOWNLOAD_DIR", "download"))
CASE_ID = os.getenv("GDT_CASE_ID", "").strip()

LOGIN_ATTEMPTS = 10
SEARCH_ATTEMPTS = 6
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153 Safari/537.36"
    ),
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

session = requests.Session()
reader = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_reader():
    global reader
    if reader is None:
        print("Loading EasyOCR...")
        reader = easyocr.Reader(["en"], gpu=False)
    return reader


def token_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", attrs={"name": "csrf-token"})
    return tag.get("content", "") if tag else ""


def token_from_form(html):
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("input", attrs={"name": "_csrf"})
    return field.get("value", "") if field else ""


def request(method, url, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    for attempt in range(3):
        response = session.request(method, url, **kwargs)
        if response.status_code != 429 or attempt == 2:
            return response
        retry_after = response.headers.get("Retry-After", "15")
        try:
            delay = max(5, int(retry_after))
        except ValueError:
            delay = 15
        print(f"Rate limited; waiting {delay}s...")
        time.sleep(delay)
    return response


def fetch_captcha(kind):
    path = "/login/getCaptcha" if kind == "login" else "/getCaptcha"
    referer = BASE + ("/login" if kind == "login" else "/tchs")
    response = request(
        "GET",
        BASE + path,
        params={"_": int(time.time() * 1000)},
        headers={**HEADERS, "Accept": "image/*", "Referer": referer},
    )
    content_type = response.headers.get("content-type", "").lower()
    if response.status_code != 200 or "image" not in content_type or len(response.content) < 500:
        print("CAPTCHA error:", response.status_code, content_type)
        return None
    return response.content


def solve_captcha(data):
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return ""

    enlarged = cv2.resize(image, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
    variants = [enlarged, gray]
    for threshold in (140, 170, 200):
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        variants.append(binary)

    candidates = []
    for variant in variants:
        results = get_reader().readtext(
            variant,
            detail=1,
            paragraph=False,
            allowlist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        )
        for _, raw_text, confidence in results:
            text = re.sub(r"[^A-Za-z0-9]", "", raw_text)
            if len(text) == 5:
                candidates.append((float(confidence), text))

    if not candidates:
        print("OCR: no valid 5-character result")
        return ""

    counts = Counter(text for _, text in candidates)
    best_confidence = {}
    for confidence, text in candidates:
        best_confidence[text] = max(confidence, best_confidence.get(text, 0.0))
    best_text = max(counts, key=lambda text: (counts[text], best_confidence[text]))
    candidates.sort(reverse=True)
    print("OCR candidates:", candidates[:3], "selected:", best_text)
    return best_text


def login():
    for attempt in range(1, LOGIN_ATTEMPTS + 1):
        print(f"LOGIN TRY {attempt}/{LOGIN_ATTEMPTS}")
        page = request(
            "GET",
            BASE + "/login",
            headers={**HEADERS, "Referer": "https://dichvucong.gdt.gov.vn/"},
        )
        if page.status_code != 200:
            time.sleep(3)
            continue

        csrf = token_from_html(page.text)
        captcha_data = fetch_captcha("login")
        captcha = solve_captcha(captcha_data) if captcha_data else ""
        if not csrf or not captcha:
            time.sleep(3)
            continue

        response = request(
            "POST",
            BASE + "/loginLDAP",
            data={
                "tenDN": USERNAME,
                "matKhau": base64.b64encode(PASSWORD.encode("utf-8")).decode("ascii"),
                "doiTuong": "DN",
                "captcha": captcha,
            },
            headers={
                **HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://dichvucong.gdt.gov.vn",
                "Referer": BASE + "/login",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": csrf,
            },
        )
        print("LOGIN:", response.status_code, response.text[:300])
        try:
            if str(response.json().get("status")) == "200":
                print("LOGIN SUCCESS")
                return True
        except (ValueError, AttributeError):
            pass
        time.sleep(4)

    return False


def parse_case_ids(html):
    soup = BeautifulSoup(html, "lxml")
    case_ids = []
    for tag in soup.find_all(attrs={"data-ma-ho-so": True}):
        case_id = tag.get("data-ma-ho-so", "").strip()
        if re.fullmatch(r"G\d+\.\d+-\d+-\d+", case_id):
            case_ids.append(case_id)
    if not case_ids:
        case_ids = re.findall(r"G\d+\.\d+-\d+-\d+", html)
    return list(dict.fromkeys(case_ids))


def page_count(html):
    soup = BeautifulSoup(html, "lxml")
    total = soup.find(id="totalPage")
    if total and total.get_text(strip=True).isdigit():
        return int(total.get_text(strip=True))
    goto = soup.find(id="gotoPageInput")
    maximum = goto.get("max", "") if goto else ""
    return int(maximum) if maximum.isdigit() else None


def search_page(page):
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        captcha_data = fetch_captcha("search")
        captcha = solve_captcha(captcha_data) if captcha_data else ""
        if not captcha:
            time.sleep(3)
            continue

        response = request(
            "GET",
            BASE + "/ho-so/search",
            params={
                "maNghiepVu": "",
                "maTTHC": "",
                "maToKhai": "",
                "maHoSo": "",
                "tuNgay": FROM_DATE,
                "denNgay": TO_DATE,
                "scope_tdt1": "SELF",
                "mstUyQuyen_tdt1": "",
                "captcha": captcha,
                "page": page,
                "size": 10,
            },
            headers={
                **HEADERS,
                "HX-Request": "true",
                "HX-Target": "table-container",
                "HX-Current-URL": BASE + "/tchs",
                "Accept": "text/html-partial",
                "Referer": BASE + "/tchs",
            },
        )
        ids = parse_case_ids(response.text) if response.status_code == 200 else []
        total_pages = page_count(response.text) if response.status_code == 200 else None
        print(
            f"SEARCH page={page} try={attempt}: status={response.status_code}, "
            f"records={len(ids)}, pages={total_pages}"
        )
        if ids or total_pages is not None:
            return ids, total_pages
        time.sleep(4)
    raise RuntimeError(f"Không tìm kiếm được trang {page} sau {SEARCH_ATTEMPTS} lần thử")


def search_all():
    all_ids = []
    current_page = 1
    total_pages = None
    while total_pages is None or current_page <= total_pages:
        ids, detected_pages = search_page(current_page)
        all_ids.extend(ids)
        if detected_pages is not None:
            total_pages = detected_pages
        elif not ids:
            break
        current_page += 1
        time.sleep(3)
    return list(dict.fromkeys(all_ids))


def download_by_search_page(target_case_id=""):
    """Tải ngay sau từng trang search để giữ whitelist hồ sơ của session."""
    current_page = 1
    total_pages = None
    seen = set()
    succeeded = 0

    while total_pages is None or current_page <= total_pages:
        ids, detected_pages = search_page(current_page)
        if detected_pages is not None:
            total_pages = detected_pages

        new_ids = [case_id for case_id in ids if case_id not in seen]
        seen.update(new_ids)
        print(f"PAGE {current_page}: {len(new_ids)} hồ sơ")

        if target_case_id:
            page_ids = [target_case_id] if target_case_id in new_ids else []
        else:
            page_ids = new_ids

        for index, case_id in enumerate(page_ids, start=1):
            print(f"DOWNLOAD page={current_page} item={index}/{len(page_ids)}: {case_id}")
            succeeded += int(download(case_id))
            time.sleep(1)

        if target_case_id and page_ids:
            return succeeded, 1
        if total_pages is None and not ids:
            break

        current_page += 1
        if total_pages is None or current_page <= total_pages:
            time.sleep(3)

    expected = 1 if target_case_id else len(seen)
    return succeeded, expected


def valid_zip(data):
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return archive.testzip() is None
    except zipfile.BadZipFile:
        return False


def download(case_id):
    for existing in DOWNLOAD_DIR.glob(f"*{case_id}*.zip"):
        try:
            if valid_zip(existing.read_bytes()):
                print("SKIP existing valid ZIP:", existing)
                return True
        except OSError:
            pass

    detail_url = f"{BASE}/tchs/files/detail/{case_id}?loai="
    detail = request(
        "GET",
        detail_url,
        headers={**HEADERS, "Referer": BASE + "/tchs"},
    )
    csrf = token_from_form(detail.text) if detail.status_code == 200 else ""
    if not csrf:
        csrf = token_from_html(detail.text) if detail.status_code == 200 else ""
    if not csrf:
        print("DOWNLOAD ERROR: no CSRF token for", case_id)
        return False

    validation = request(
        "GET",
        BASE + "/tchs/validateIdTkhai",
        params={"idTKhai": case_id},
        headers={
            **HEADERS,
            "Accept": "*/*",
            "Origin": "https://dichvucong.gdt.gov.vn",
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": csrf,
            "Referer": detail_url,
        },
    )
    if validation.status_code == 200 and validation.text.strip() == "200":
        response = request(
            "POST",
            BASE + "/tchs/downloadhoso",
            json={"maHoSo": case_id},
            headers={
                **HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": csrf,
                "Referer": detail_url,
            },
        )
    else:
        print(
            "AJAX validation unavailable; trying rendered download form:",
            case_id,
            validation.status_code,
            validation.text[:300],
        )
        response = request(
            "POST",
            BASE + "/downloadhoso",
            data={"_csrf": csrf, "mahoso": case_id},
            headers={
                **HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://dichvucong.gdt.gov.vn",
                "Referer": detail_url,
            },
        )

    if response.status_code != 200:
        print("DOWNLOAD ERROR:", case_id, response.status_code, response.text[:500])
        return False

    filename = f"{case_id}.zip"
    data = response.content
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("content"):
            data = base64.b64decode(payload["content"], validate=True)
            filename = Path(payload.get("fileName") or filename).name
    except (ValueError, TypeError, base64.binascii.Error):
        pass

    if not valid_zip(data):
        print("DOWNLOAD ERROR: response is not a valid ZIP for", case_id)
        return False

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOAD_DIR / filename
    path.write_bytes(data)
    print(f"SAVED: {path} ({len(data):,} bytes)")
    return True


def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit(
            "Thiếu GDT_USERNAME hoặc GDT_PASSWORD. "
            "Hãy cấu hình biến môi trường trước khi chạy."
        )

    if not login():
        raise SystemExit("LOGIN FAIL")

    landing = request("GET", BASE + "/tchs", headers=HEADERS)
    if landing.status_code != 200:
        raise SystemExit(f"Không mở được trang hồ sơ: HTTP {landing.status_code}")

    succeeded, expected = download_by_search_page(CASE_ID)
    print(f"DONE: {succeeded}/{expected} file(s) downloaded")
    if succeeded != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
