"""Hằng số dùng chung: địa chỉ cổng, endpoint, header và giá trị mặc định.

Mọi thay đổi về giao diện cổng Dịch vụ công nên bắt đầu từ file này.
Các đường dẫn là tương đối so với :data:`BASE`.
"""

from __future__ import annotations

ORIGIN = "https://dichvucong.gdt.gov.vn"
BASE = f"{ORIGIN}/tthc"

# --- Trang Thuế điện tử cũ (một số tờ khai cũ chỉ còn ở đây) ---
LEGACY_ETAX_ORIGIN = "https://thuedientu.gdt.gov.vn"
LEGACY_ETAX_BASE = f"{LEGACY_ETAX_ORIGIN}/etaxnnt"

# --- Đăng nhập ---
LOGIN_PAGE = "/login"
LOGIN_ENDPOINT = "/loginLDAP"
LOGIN_CAPTCHA = "/login/getCaptcha"

# --- Trang hồ sơ và CAPTCHA tra cứu ---
LANDING = "/tchs"
SEARCH_CAPTCHA = "/getCaptcha"

# --- Nguồn Thuế điện tử (tờ khai nộp trước 01/07/2025) ---
ETAX_SEARCH = "/tchs/thuedientu"
ETAX_DOWNLOAD = "/tchs/downloadhoso-tdt"

# --- Nguồn Dịch vụ công (hồ sơ nộp từ 01/07/2025) ---
DVC_SEARCH = "/ho-so/search"
DVC_VALIDATE = "/tchs/validateIdTkhai"
DVC_DOWNLOAD = "/tchs/downloadhoso"
DVC_DOWNLOAD_FORM = "/downloadhoso"

# --- Dùng chung ---
CASE_DETAIL = "/tchs/files/detail/{case_id}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153 Safari/537.36"
    ),
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

SOURCE_ETAX = "ETAX"
SOURCE_DVC = "DVC"
#: Trang Thuế điện tử cũ — nguồn chính mặc định trước cutoff.
SOURCE_ETAX_LEGACY = "ETAX_LEGACY"
SOURCES = (SOURCE_DVC, SOURCE_ETAX)
#: Mọi nguồn có thể xuất hiện trong metadata.
ALL_SOURCES = (SOURCE_DVC, SOURCE_ETAX, SOURCE_ETAX_LEGACY)

METADATA_CSV = "danh_sach_ho_so.csv"
METADATA_JSON = "danh_sach_ho_so.json"
METADATA_XLSX = "danh_sach_to_khai.xlsx"
