# Hướng dẫn thêm một mẫu biểu (form mapping) mới

> Dành cho người muốn "thiết kế theo form dữ liệu cần" nhưng chưa biết bắt đầu từ
> đâu. Đọc hết một lần, sau đó làm theo đúng 7 bước; mỗi bước đều có lệnh kiểm
> tra để biết mình đã đúng trước khi sang bước sau.

## 1. Bức tranh tổng thể

Công cụ tách **tải dữ liệu** khỏi **đọc dữ liệu**. Bạn đã có bước tải (ZIP tờ
khai). Phần "đọc dữ liệu" chạy offline theo luồng:

```text
ZIP đã tải
  └─► gdt-inventory   → manifest_artifact.json   (liệt kê mọi file/member + sha256)
        └─► gdt-parse → parsed_declarations.json (metadata + chỉ tiêu từng XML)
              └─► gdt-classify → phan_loai_artifact.json
                    └─► gdt-export → Tax_Return_Summary.xlsx (workbook nhiều sheet)
```

Parser **không** hard-code mẫu biểu trong code. Ý nghĩa của từng chỉ tiêu do
**một file JSON mapping** khai báo. Vì vậy thêm một mẫu mới = thêm một file JSON
+ fixture + test, **không** sửa code parser.

### Từ khóa cần nắm

| Khái niệm | Nghĩa |
|---|---|
| `form_code` | Mã mẫu trong XML, ví dụ `842` (01/GTGT), `892` (03/TNDN) |
| `form_version` | Phiên bản XML (`pbanTKhaiXML`/`PBan`), ví dụ `2.8.3` |
| `indicator_code` | Mã chỉ tiêu **chính thức** trong XML: `ct21`, `ct43`, `ctA1`, `ctB2`… |
| `canonical_name` | Tên chuẩn hóa (tiếng Anh, không dấu) dùng cho cột Excel/truy vấn |
| `display_name` | Nhãn tiếng Việt hiển thị cho người dùng |
| `datatype` | `decimal` (mặc định), `percentage`, hoặc `string` (nhãn text) |
| `xpath` | Đường dẫn đầy đủ tới chỉ tiêu, ví dụ `CTieuTKhaiChinh/ct43` |
| `detect.root` / `detect.namespace` | Thẻ gốc + namespace của XML (thông tin mô tả/kiểm chứng; việc tra mapping dùng `form_code` + `form_version`) |

### Quy tắc bất di bất dịch

1. **Không đoán.** Chỉ map khi đã đối chiếu XML thật + mẫu biểu chính thức. Chưa
   chắc thì để parser trả `NEED_MAPPING`, **không** tự gán tên.
2. **Không tính lại công thức.** Parser chỉ đọc số đã khai. Muốn `ct43` thì đọc
   `ct43`, không tự trừ/cộng từ chỉ tiêu khác.
3. **Phân biệt NULL với 0.** Ô trống ⇒ `null`; giá trị `0` ⇒ `"0"`. Không gộp hai
   thứ này.
4. **Giữ provenance.** Mỗi chỉ tiêu mang `xpath` + `raw_value` để truy vết.
5. **Chỉ map tờ khai chính.** Quét node `CTieuTKhaiChinh`; **không** đi vào bảng
   kê/phụ lục (`PLuc`, `BangKe*`, báo cáo tài chính) trừ khi có yêu cầu riêng.
6. **Một phiên bản = một file.** XML khác `form_version` thì tạo mapping riêng;
   không áp bản của version này cho version chưa kiểm chứng.

---

## 2. Chuẩn bị

```bash
# Môi trường tối thiểu để chạy parser/export (không cần OCR/mạng)
pip install beautifulsoup4 lxml openpyxl requests

# Có sẵn ZIP đã tải trong download/ (chạy gdt-tax trước nếu chưa có)
python -m unittest discover -s tests -t .     # xác nhận nền tảng đang xanh
```

Bạn cần **một XML đại diện thật** đúng `form_code` + `form_version`. Lấy từ ZIP
đã tải, hoặc từ bất kỳ nguồn hợp lệ mà bạn có quyền dùng.

> ⚠️ **Ẩn danh trước khi đưa vào repo.** Fixture phải dùng mã synthetic
> (`0000000000`, tên công ty giả, mã hồ sơ `DEMO-*`). Không commit MST, tên,
> địa chỉ, số tiền thật. Xem `SECURITY.md`.

---

## 3. Bảy bước thực hiện

### Bước 1 — Lấy XML và ẩn danh thành fixture

Đặt fixture vào `tests/fixtures/`, ví dụ `tests/fixtures/gtgt_842_v2.8.3.xml`
(tên theo quy ước `<nhóm>_<mã>_v<version>.xml`). Giữ nguyên **cấu trúc thẻ và mã
chỉ tiêu**, chỉ thay dữ liệu người nộp.

### Bước 2 — Xác định `form_code` và `form_version`

Mở XML, tìm các thẻ metadata (parser tự đọc các đường dẫn này, xem
`gdt_tax/parser/extract.py`):

| Thông tin | Thẻ thường gặp |
|---|---|
| Mã mẫu | `maTKhai` (tờ khai) hoặc `MSo` (thông báo) |
| Tên mẫu | `tenTKhai` hoặc `Ten` |
| Phiên bản | `pbanTKhaiXML` hoặc `PBan` |
| Loại kỳ | `kieuKy` (`M`/`Q`/`Y`) + `kyKKhai` |

Ghi lại cặp `(form_code, form_version)`. Đây chính là khóa tra registry.

Kiểm tra nhanh bằng dòng lệnh (parser vẫn chạy ở chế độ `NEED_MAPPING` khi chưa có
mapping, nhưng in ra được `form_code`/`form_version`):

```bash
gdt-inventory download
gdt-parse download -v          # đọc parsed_declarations.json để lấy mã/phiên bản
```

### Bước 3 — Xác định root + namespace

Xem dòng đầu của XML:

```xml
<HSoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TKhaiThue">
```

⇒ `detect.root = "HSoThueDTu"`,
`detect.namespace = "http://kekhaithue.gdt.gov.vn/TKhaiThue"`.

Có XML không namespace (ví dụ `TBao`); khi đó để `namespace` là `null` — parser tự bỏ
tiền tố `n:` khi khớp. Lưu ý: `detect` chỉ mang tính mô tả/kiểm chứng; khóa tra
mapping là cặp `(form_code, form_version)`.

### Bước 4 — Chọn và đối chiếu chỉ tiêu cần lấy

Đây là phần "thiết kế theo form dữ liệu cần". Làm như sau:

1. Mở mẫu biểu **chính thức** (PDF Công báo/Thông tư) của đúng mẫu đó.
2. Lấy danh sách chỉ tiêu bạn thực sự cần cho báo cáo (ví dụ: tổng doanh thu,
   thuế phải nộp, thuế khấu trừ…). Đừng cố map tất cả nếu chưa cần.
3. Trong XML, tìm **mã chỉ tiêu** (`ctNN`) tương ứng và xác nhận bằng cách đối
   chiếu nhãn với mẫu biểu. Ghi lại cả `xpath` đầy đủ (root bỏ qua, chỉ tính từ
   `CTieuTKhaiChinh`).
4. Chọn `datatype`: số tiền ⇒ `decimal`, thuế suất ⇒ `percentage`, nhãn text ⇒
   `string`.

> Nếu một chỉ tiêu xuất hiện ở nhiều nơi (bảng kê chi tiết), chỉ lấy bản trên
> `CTieuTKhaiChinh` để tránh nhặt nhầm số của bảng kê.

### Bước 5 — Viết file mapping JSON

Tạo `gdt_tax/form_mappings/<nhóm>_<mã>_v<version>.json` (ví dụ
`gtgt_842_v2.8.3.json`). File bắt đầu bằng `_` sẽ bị bỏ qua (dùng làm template).

```json
{
  "mapping_id": "GTGT_842_v2.8.3",
  "mapping_version": "1",
  "tax_type": "GTGT",
  "form_code": "842",
  "form_version": "2.8.3",
  "note": "Mẫu 01/GTGT. Tên chỉ tiêu đối chiếu Phụ lục trong Thông tư; XPath kiểm trên XML thật.",
  "effective_from": "2025-01-01",
  "effective_to": null,
  "detect": {
    "root": "HSoThueDTu",
    "namespace": "http://kekhaithue.gdt.gov.vn/TKhaiThue"
  },
  "fields": {
    "vat_payable": {
      "canonical_name": "vat_payable",
      "indicator_code": "ct43",
      "display_name": "Thuế GTGT phải nộp",
      "official_indicator_name": "Thuế GTGT phải nộp",
      "datatype": "decimal",
      "xpath": "CTieuTKhaiChinh/ct43"
    },
    "total_revenue": {
      "canonical_name": "total_revenue",
      "indicator_code": "ct22",
      "display_name": "Tổng doanh thu",
      "datatype": "decimal",
      "xpath": "CTieuTKhaiChinh/ct22"
    }
  }
}
```

Các trường **bắt buộc** (registry sẽ từ chối nếu thiếu): `mapping_id`,
`mapping_version`, `form_code`, `fields`. Mỗi field **bắt buộc** có
`indicator_code`.

**Chỉ tiêu nằm trong nhóm lồng nhau.** Nếu chỉ tiêu không ở ngay dưới
`CTieuTKhaiChinh` mà nằm trong một node nhóm (ví dụ
`GiaTriVaThueGTGTHHDVMuaVao/ct23`), ghi `xpath` đầy đủ:

```json
"vat_deductible_input": {
  "canonical_name": "vat_deductible_input",
  "indicator_code": "ct23",
  "display_name": "Thuế GTGT đầu vào được khấu trừ",
  "datatype": "decimal",
  "xpath": "CTieuTKhaiChinh/GiaTriVaThueGTGTHHDVMuaVao/ct23"
}
```

**Lưu ý:** nếu một `indicator_code` bị dùng cho hai `canonical_name` khác nhau,
parser chỉ lấy lần đầu tiên — đặt tên canonical rõ ràng, không map trùng mã.

### Bước 6 — Thêm fixture + test

1. Đặt XML ẩn danh vào `tests/fixtures/<form>.xml`.
2. (Tuỳ chọn nhưng nên) Tạo `tests/fixtures/<form>.golden.json` chứa các chỉ tiêu
   kỳ vọng — dùng để so sánh giá trị sau này.
3. Thêm test vào `tests/test_parser.py` theo mẫu có sẵn: nạp registry thật bằng
   `load_registry()`, gọi `extract_declaration(...)`, và khẳng định:
   - `status == "MAPPED"`;
   - `mapping_id` đúng;
   - vài chỉ tiêu quan trọng có `value` đúng (phân biệt `None` vs `"0"`);
   - `xpath` trỏ đúng chỗ.

```bash
python -m unittest tests.test_parser -v
```

### Bước 7 — Chạy end-to-end và kiểm tra

```bash
# 1) Quét ZIP đã tải để sinh manifest
gdt-inventory download --metadata download/danh_sach_ho_so.json

# 2) Parse tất cả XML; xem log MAPPED / NEED_MAPPING
gdt-parse download -v

# 3) Phân loại theo nội dung (nếu cần)
gdt-classify download

# 4) Xuất workbook Excel nhiều sheet
gdt-export download
```

Kiểm tra:

- Log `gdt-parse` báo `MAPPED` tăng lên cho mẫu của bạn.
- Mở `parsed_declarations.json`: các `indicator` có `status = "MAPPED"`,
  `canonical_name` đúng, `value` đúng.
- Mở `Tax_Return_Summary.xlsx`: sheet `01_RETURN_INDEX` và sheet nhóm
  (`02_GTGT`/`03_TNCN`/`04_TNDN`) hiển thị tờ khai của bạn; chỉ tiêu nằm trong
  `05_INDICATORS`.

Chạy `gdt-parse` lần hai: kết quả **không** nhân đôi (định danh theo
`artifact_id` + `sha256` + `parser_version`).

---

## 4. Cập nhật support matrix

Thêm một dòng vào bảng "Support matrix đã kiểm chứng" trong
[`gdt_tax/form_mappings/README.md`](../gdt_tax/form_mappings/README.md) và mô tả
rõ: nhóm thuế, mẫu, mã, phiên bản XML, vai trò, định dạng, phạm vi chỉ tiêu, và
bạn đã kiểm trên bao nhiêu XML. Không nêu "hỗ trợ" cho version chưa kiểm.

---

## 5. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cả tờ khai `status = NEED_MAPPING` | Không khớp `(form_code, form_version)` | Kiểm `form_code`/`form_version` trong XML với `mapping_id`; tạo mapping đúng version |
| `warnings: MAPPING_NOT_FOUND` | Chưa có file cho mã/phiên bản đó | Thêm file mapping đúng cặp khóa |
| Một chỉ tiêu `warnings: MISSING_IN_XML` | Mapping khai chỉ tiêu mà XML không có | Bình thường nếu bản XML đó bỏ trống; giá trị `null`. Kiểm lại `xpath` nếu đáng ra phải có |
| `warnings: PARSE_VALUE_ERROR` | Ô chứa chữ/ký tự lạ thay vì số | Kiểm `raw_value`; nếu là nhãn text thì đổi `datatype` thành `string` |
| Giá trị luôn `null` dù XML có | Sai `xpath` hoặc thiếu tiền tố nhóm | Đối chiếu `xpath` với cấu trúc XML; thêm node nhóm vào đường dẫn |
| Trùng giá trị giữa tờ khai và bảng kê | `xpath` quá ngắn nên khớp cả `PLuc` | Thêm `CTieuTKhaiChinh/...` vào `xpath` |
| Registry bỏ qua file im lặng | JSON sai cú pháp hoặc thiếu trường bắt buộc | Chạy `gdt-parse -v`; log ghi rõ file bị bỏ qua và lý do |

---

## 6. Checklist trước khi mở merge request

- [ ] File mapping đúng tên, đúng `(form_code, form_version)`, JSON hợp lệ.
- [ ] Không có `canonical_name` trùng cho hai `indicator_code` khác nhau.
- [ ] Fixture đã ẩn danh hoàn toàn (không MST/tên/số tiền thật).
- [ ] Có test trong `tests/test_parser.py` và đã chạy xanh.
- [ ] `gdt-parse` trên dữ liệu thật cho `MAPPED`, `gdt-export` mở được Excel.
- [ ] Đã cập nhật support matrix trong `gdt_tax/form_mappings/README.md`.
- [ ] `python -m ruff check .` và `python -m mypy gdt_tax` đều sạch.

---

## 7. Bản đồ file cần đụng tới

| File | Vai trò |
|---|---|
| `gdt_tax/form_mappings/<...>.json` | **Bạn thêm file ở đây** |
| `gdt_tax/form_mappings/README.md` | Quy ước + support matrix |
| `gdt_tax/parser/registry.py` | Nạp mapping, kiểm trường bắt buộc |
| `gdt_tax/parser/extract.py` | Trích metadata + chỉ tiêu theo mapping |
| `gdt_tax/parser/xml_reader.py` | Đọc XML an toàn, chuẩn hóa số |
| `gdt_tax/parser/cli.py` | `gdt-parse` |
| `tests/test_parser.py` | Test parser + mapping |
| `tests/fixtures/` | XML ẩn danh + golden |

Khi cổng phát hành XML mẫu mới, quy trình lặp lại đúng 7 bước trên với
`form_version` mới — **không** sửa mapping cũ nếu phiên bản cũ vẫn còn dùng.
