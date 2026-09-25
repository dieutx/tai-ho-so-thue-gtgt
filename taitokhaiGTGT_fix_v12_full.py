# -*- coding: utf-8 -*-
"""Tìm kiếm và tải hồ sơ từ Cổng Dịch vụ công Thuế."""

import base64
import csv
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import cv2
import easyocr
import numpy as np
import requests
from bs4 import BeautifulSoup


BASE = "https://dichvucong.gdt.gov.vn/tthc"
USERNAME = os.getenv("GDT_USERNAME", "").strip()
PASSWORD = os.getenv("GDT_PASSWORD", "")
FROM_DATE = os.getenv("GDT_FROM_DATE", "01/09/2026")
TO_DATE = os.getenv("GDT_TO_DATE", "25/09/2026")
DOWNLOAD_DIR = Path(os.getenv("GDT_DOWNLOAD_DIR", "download"))
CASE_ID = os.getenv("GDT_CASE_ID", "").strip()

ETAX_CUTOFF = date(2025, 7, 1)
MAX_DAYS_PER_SEARCH = 31
PAGE_SIZE = 10
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


@dataclass
class CaseRecord:
    ma_ho_so: str
    nguon: str
    ten_tthc: str = ""
    to_khai: str = ""
    ky_tinh_thue: str = ""
    loai_to_khai: str = ""
    lan_nop: str = ""
    lan_bo_sung: str = ""
    ngay_nop: str = ""
    noi_nop: str = ""
    trang_thai: str = ""
    tep_zip: str = ""


def parse_date(value):
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as error:
        raise ValueError(f"Ngày không hợp lệ: {value}. Định dạng đúng là dd/mm/yyyy") from error


def format_date(value):
    return value.strftime("%d/%m/%Y")


def iter_search_periods(from_date, to_date):
    """Chia khoảng ngày thành các đoạn tối đa 31 ngày và đúng nguồn dữ liệu."""
    start = parse_date(from_date) if isinstance(from_date, str) else from_date
    end = parse_date(to_date) if isinstance(to_date, str) else to_date
    if start > end:
        raise ValueError("GDT_FROM_DATE phải nhỏ hơn hoặc bằng GDT_TO_DATE")

    while start <= end:
        source = "ETAX" if start < ETAX_CUTOFF else "DVC"
        source_end = ETAX_CUTOFF - timedelta(days=1) if source == "ETAX" else end
        chunk_end = min(end, source_end, start + timedelta(days=MAX_DAYS_PER_SEARCH - 1))
        yield start, chunk_end, source
        start = chunk_end + timedelta(days=1)


def get_reader():
    global reader
    if reader is None:
        print("Đang nạp EasyOCR...")
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
        print(f"Máy chủ giới hạn tần suất; chờ {delay} giây...")
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
        print("Lỗi CAPTCHA:", response.status_code, content_type)
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
        print("OCR không tìm được kết quả gồm 5 ký tự")
        return ""

    counts = Counter(text for _, text in candidates)
    best_confidence = {}
    for confidence, text in candidates:
        best_confidence[text] = max(confidence, best_confidence.get(text, 0.0))
    best_text = max(counts, key=lambda text: (counts[text], best_confidence[text]))
    candidates.sort(reverse=True)
    print("OCR:", candidates[:3], "chọn:", best_text)
    return best_text


def login():
    for attempt in range(1, LOGIN_ATTEMPTS + 1):
        print(f"ĐĂNG NHẬP {attempt}/{LOGIN_ATTEMPTS}")
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
                print("ĐĂNG NHẬP THÀNH CÔNG")
                return True
        except (ValueError, AttributeError):
            pass
        time.sleep(4)
    return False


def direct_cells(row):
    return [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]


def parse_records(html, source):
    soup = BeautifulSoup(html, "lxml")
    records = []
    seen = set()
    for row in soup.select("tbody tr"):
        cells = direct_cells(row)
        marker = row.find(attrs={"data-ma-ho-so": True})
        case_id = marker.get("data-ma-ho-so", "").strip() if marker else ""

        if source == "ETAX":
            if not case_id and len(cells) > 1:
                case_id = cells[1]
            if not case_id or len(cells) < 10:
                continue
            record = CaseRecord(
                ma_ho_so=case_id,
                nguon="ETAX",
                to_khai=cells[2],
                ky_tinh_thue=cells[3],
                loai_to_khai=cells[4],
                lan_nop=cells[5],
                lan_bo_sung=cells[6],
                ngay_nop=cells[7],
                noi_nop=cells[8],
                trang_thai=cells[9],
            )
        else:
            if not case_id and len(cells) > 2:
                case_id = cells[2]
            if not case_id or len(cells) < 12:
                continue
            record = CaseRecord(
                ma_ho_so=case_id,
                nguon="DVC",
                ten_tthc=cells[3],
                to_khai=cells[4],
                ky_tinh_thue=cells[5],
                loai_to_khai=cells[6],
                lan_bo_sung=cells[7],
                lan_nop=cells[8],
                noi_nop=cells[9],
                ngay_nop=cells[10],
                trang_thai=cells[11],
            )

        if record.ma_ho_so not in seen:
            seen.add(record.ma_ho_so)
            records.append(record)
    return records


def page_count(html, source):
    soup = BeautifulSoup(html, "lxml")
    if source == "ETAX":
        goto = soup.find(id="goToPage_tdt")
        maximum = goto.get("max", "") if goto else ""
        return int(maximum) if str(maximum).isdigit() else None

    total = soup.find(id="totalPage")
    if total and total.get_text(strip=True).isdigit():
        return int(total.get_text(strip=True))
    goto = soup.find(id="gotoPageInput")
    maximum = goto.get("max", "") if goto else ""
    return int(maximum) if str(maximum).isdigit() else None


def search_page_dvc(page, start, end):
    response = request(
        "GET",
        BASE + "/ho-so/search",
        params={
            "maNghiepVu": "",
            "maTTHC": "",
            "maToKhai": "",
            "maHoSo": "",
            "tuNgay": format_date(start),
            "denNgay": format_date(end),
            "scope_tdt1": "SELF",
            "mstUyQuyen_tdt1": "",
            "captcha": solve_captcha(fetch_captcha("search") or b""),
            "page": page,
            "size": PAGE_SIZE,
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
    return response


def search_page_etax(page, start, end, csrf):
    captcha_data = fetch_captcha("search")
    captcha = solve_captcha(captcha_data) if captcha_data else ""
    return request(
        "POST",
        BASE + "/tchs/thuedientu",
        data={
            "_csrf": csrf,
            "page": page,
            "size": PAGE_SIZE,
            "maToKhai_tdt": "",
            "maGiaoDichTthc_tdt": "",
            "tuNgay_tdt": format_date(start),
            "denNgay_tdt": format_date(end),
            "scope_tdt2": "SELF",
            "mstUyQuyen_tdt2": "",
            "captcha": captcha,
            "btnSearch_tdt": "",
        },
        headers={
            **HEADERS,
            "Accept": "text/html-partial",
            "Content-Type": "application/x-www-form-urlencoded",
            "HX-Current-URL": BASE + "/tchs",
            "HX-Request": "true",
            "HX-Target": "bangKetQuaTraCuu_tdt",
            "HX-Trigger": "form_search_tdt",
            "Origin": "https://dichvucong.gdt.gov.vn",
            "Referer": BASE + "/tchs",
            "X-XSRF-TOKEN": csrf,
        },
    )


def search_page(page, start, end, source, csrf=""):
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        response = (
            search_page_etax(page, start, end, csrf)
            if source == "ETAX"
            else search_page_dvc(page, start, end)
        )
        records = parse_records(response.text, source) if response.status_code == 200 else []
        total_pages = page_count(response.text, source) if response.status_code == 200 else None
        print(
            f"SEARCH {source} {format_date(start)}-{format_date(end)} "
            f"page={page} try={attempt}: HTTP={response.status_code}, "
            f"records={len(records)}, pages={total_pages}"
        )
        if records or total_pages is not None:
            return records, total_pages
        time.sleep(4)
    raise RuntimeError(f"Không tìm được trang {page} sau {SEARCH_ATTEMPTS} lần thử")


def safe_filename_part(value, maximum=70):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return value[:maximum] or "khong-ro"


def zip_filename(record):
    parts = [
        safe_filename_part(record.ma_ho_so, 50),
        safe_filename_part(record.ky_tinh_thue, 20),
        safe_filename_part(record.loai_to_khai, 30),
        safe_filename_part(record.to_khai, 70),
    ]
    return "__".join(parts) + ".zip"


def valid_zip(data):
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return archive.testzip() is None
    except zipfile.BadZipFile:
        return False


def existing_zip(record):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    preferred = DOWNLOAD_DIR / zip_filename(record)
    candidates = [preferred, *DOWNLOAD_DIR.glob(f"*{record.ma_ho_so}*.zip")]
    checked = set()
    for candidate in candidates:
        if candidate in checked or not candidate.is_file():
            continue
        checked.add(candidate)
        try:
            if not valid_zip(candidate.read_bytes()):
                continue
            if candidate != preferred and not preferred.exists():
                candidate.rename(preferred)
                candidate = preferred
            record.tep_zip = candidate.name
            print("BỎ QUA ZIP ĐÃ CÓ:", candidate)
            return candidate
        except OSError:
            continue
    return None


def decode_download_response(response, record):
    data = response.content
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("content"):
            data = base64.b64decode(payload["content"], validate=True)
    except (ValueError, TypeError, base64.binascii.Error):
        pass

    if not valid_zip(data):
        print("LỖI TẢI: phản hồi không phải ZIP hợp lệ:", record.ma_ho_so)
        return None

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOAD_DIR / zip_filename(record)
    path.write_bytes(data)
    record.tep_zip = path.name
    print(f"ĐÃ LƯU: {path} ({len(data):,} bytes)")
    return path


def download_etax(record, detail_url, csrf):
    response = request(
        "POST",
        BASE + "/tchs/downloadhoso-tdt",
        params={"loaiTraCuu": "ETAX"},
        json={"maHoSo": record.ma_ho_so},
        headers={
            **HEADERS,
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://dichvucong.gdt.gov.vn",
            "Referer": detail_url,
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": csrf,
        },
    )
    return response


def download_dvc(record, detail_url, csrf):
    validation = request(
        "GET",
        BASE + "/tchs/validateIdTkhai",
        params={"idTKhai": record.ma_ho_so},
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
        return request(
            "POST",
            BASE + "/tchs/downloadhoso",
            json={"maHoSo": record.ma_ho_so},
            headers={
                **HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Origin": "https://dichvucong.gdt.gov.vn",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": csrf,
                "Referer": detail_url,
            },
        )

    print("Validate AJAX không khả dụng; thử form tải dự phòng:", validation.text[:100])
    return request(
        "POST",
        BASE + "/downloadhoso",
        data={"_csrf": csrf, "mahoso": record.ma_ho_so},
        headers={
            **HEADERS,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://dichvucong.gdt.gov.vn",
            "Referer": detail_url,
        },
    )


def download(record):
    found = existing_zip(record)
    if found:
        return found

    loai = "ETAX" if record.nguon == "ETAX" else ""
    detail_url = f"{BASE}/tchs/files/detail/{record.ma_ho_so}?loai={loai}"
    detail = request("GET", detail_url, headers={**HEADERS, "Referer": BASE + "/tchs"})
    csrf = token_from_form(detail.text) if detail.status_code == 200 else ""
    if not csrf:
        csrf = token_from_html(detail.text) if detail.status_code == 200 else ""
    if not csrf:
        print("LỖI TẢI: không có CSRF token:", record.ma_ho_so)
        return None

    response = (
        download_etax(record, detail_url, csrf)
        if record.nguon == "ETAX"
        else download_dvc(record, detail_url, csrf)
    )
    if response.status_code != 200:
        print("LỖI TẢI:", record.ma_ho_so, response.status_code, response.text[:500])
        return None
    return decode_download_response(response, record)


def write_metadata(records):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    rows = [asdict(records[key]) for key in sorted(records)]
    if not rows:
        return

    csv_path = DOWNLOAD_DIR / "danh_sach_ho_so.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    json_path = DOWNLOAD_DIR / "danh_sach_ho_so.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"METADATA: {csv_path} và {json_path}")


def process_period(start, end, source, csrf, records, succeeded):
    current_page = 1
    total_pages = None
    while total_pages is None or current_page <= total_pages:
        page_records, detected_pages = search_page(current_page, start, end, source, csrf)
        if detected_pages is not None:
            total_pages = detected_pages

        print(f"TRANG {current_page}: {len(page_records)} hồ sơ {source}")
        for index, record in enumerate(page_records, start=1):
            if record.ma_ho_so not in records:
                records[record.ma_ho_so] = record
            else:
                record = records[record.ma_ho_so]

            if CASE_ID and record.ma_ho_so != CASE_ID:
                continue
            print(f"TẢI trang={current_page} mục={index}/{len(page_records)}: {record.ma_ho_so}")
            if download(record):
                succeeded.add(record.ma_ho_so)
            write_metadata(records)
            time.sleep(1)

            if CASE_ID and record.ma_ho_so == CASE_ID:
                return True

        if total_pages is None and not page_records:
            break
        current_page += 1
        if total_pages is None or current_page <= total_pages:
            time.sleep(3)
    return False


def process_all_periods(landing_html):
    csrf = token_from_form(landing_html) or token_from_html(landing_html)
    records = {}
    succeeded = set()

    for start, end, source in iter_search_periods(FROM_DATE, TO_DATE):
        print(f"\n=== {source}: {format_date(start)} - {format_date(end)} ===")
        found_target = process_period(start, end, source, csrf, records, succeeded)
        if found_target:
            break

    write_metadata(records)
    expected = 1 if CASE_ID else len(records)
    return len(succeeded), expected


def main():
    if not USERNAME or not PASSWORD:
        raise SystemExit(
            "Thiếu GDT_USERNAME hoặc GDT_PASSWORD. "
            "Hãy cấu hình biến môi trường trước khi chạy."
        )

    parse_date(FROM_DATE)
    parse_date(TO_DATE)
    if not login():
        raise SystemExit("ĐĂNG NHẬP THẤT BẠI")

    landing = request("GET", BASE + "/tchs", headers=HEADERS)
    if landing.status_code != 200:
        raise SystemExit(f"Không mở được trang hồ sơ: HTTP {landing.status_code}")

    succeeded, expected = process_all_periods(landing.text)
    print(f"HOÀN TẤT: {succeeded}/{expected} hồ sơ đã tải")
    if CASE_ID and expected == 1 and succeeded == 0:
        print("Không tìm thấy hoặc không tải được GDT_CASE_ID trong khoảng ngày đã cấu hình")
    if succeeded != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
