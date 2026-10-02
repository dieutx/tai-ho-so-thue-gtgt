# Form Mapping Registry

Mỗi phiên bản tờ khai có **một file JSON** ở đây, được `gdt_tax.parser.registry`
nạp tự động (quét cả thư mục con). Parser **không** hard-code mẫu biểu trong code.

## Quy ước

- File bắt đầu bằng `_` sẽ **bị bỏ qua** (dùng cho template).
- Tên file gợi ý: `<tax_type>_<form_code>_v<version>.json`, ví dụ
  `gtgt_842_v2.8.3.json` (mã mẫu 842 = 01/GTGT, TT80/2021).
- **Không** điền mapping bằng suy đoán. Chỉ thêm khi đã đối chiếu XML thật và có
  fixture kiểm chứng; nếu chưa chắc, để chỉ tiêu ở trạng thái `NEED_MAPPING`.

## Cấu trúc

```json
{
  "mapping_id": "GTGT_842_v2.8.3",
  "mapping_version": "1",
  "tax_type": "GTGT",
  "form_code": "842",
  "form_version": "2.8.3",
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
      "datatype": "decimal"
    }
  }
}
```

- `indicator_code`: mã chỉ tiêu **chính thức** trong XML (`ct21`, `ct43`, `ctB1`…).
- `canonical_name`: tên chuẩn hóa dùng cho cột Excel/query.
- Chưa có mapping ⇒ parser trả `NEED_MAPPING` cho mọi chỉ tiêu và **không** tự gán
  tên. Đây là hành vi có chủ đích (spec §3.1, §45).

## Thêm mapping mới

1. Lấy một XML đại diện của đúng `form_code` + `form_version`.
2. Liệt kê các mã chỉ tiêu và đối chiếu với mẫu biểu chính thức.
3. Viết file JSON, thêm fixture ẩn danh + test trong `tests/`.
4. Chạy `python -m gdt_tax.parser.cli <folder>` và kiểm tra `status = MAPPED`.
