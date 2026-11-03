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

# --- Cổng cá nhân: thông báo của cơ quan thuế ---
# Tài khoản cá nhân vào cổng này bằng SSO từ Dịch vụ công, không đăng nhập lại.
CANHAN_ORIGIN = "https://canhan.gdt.gov.vn"
CANHAN_BASE = f"{CANHAN_ORIGIN}/ICanhan"
CANHAN_REQUEST = f"{CANHAN_BASE}/Request"

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
#: Tải thông báo (XML) đính kèm một hồ sơ đã nộp.
DVC_NOTICE_DOWNLOAD = "/tchs/downloadthongbao"
#: SSO sang cổng cá nhân; module 10607 là "Tra cứu thông báo của CQT".
DVC_SSO_REDIRECT = "/sso/redirect-to-service"
DVC_SSO_CANHAN_MODULE = "10607"

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
#: Tờ khai của tài khoản cá nhân trên Dịch vụ công (scope SELF).
SOURCE_DVC_PERSONAL = "DVC_PERSONAL"
#: Thông báo của cơ quan thuế trên cổng canhan.gdt.gov.vn.
SOURCE_CANHAN = "CANHAN"
SOURCES = (SOURCE_DVC, SOURCE_ETAX)
#: Hai nguồn chỉ dùng khi chạy `--account-type personal`.
PERSONAL_SOURCES = (SOURCE_DVC_PERSONAL, SOURCE_CANHAN)
#: Mọi nguồn có thể xuất hiện trong metadata.
ALL_SOURCES = (SOURCE_DVC, SOURCE_ETAX, SOURCE_ETAX_LEGACY, *PERSONAL_SOURCES)

# --- Loại tài khoản ---
ACCOUNT_BUSINESS = "business"
ACCOUNT_PERSONAL = "personal"
ACCOUNT_TYPES = (ACCOUNT_BUSINESS, ACCOUNT_PERSONAL)

#: Danh mục tên người nộp thuế theo MST, lưu trong thư mục tải về.
TAXPAYER_REGISTRY_JSON = "nguoi_nop_thue.json"

METADATA_CSV = "danh_sach_ho_so.csv"
METADATA_JSON = "danh_sach_ho_so.json"
METADATA_XLSX = "danh_sach_to_khai.xlsx"
