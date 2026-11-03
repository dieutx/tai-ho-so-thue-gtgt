# Form Mapping Registry

Mỗi cấu trúc tờ khai đã kiểm chứng có **một file JSON** ở đây, được
`gdt_tax.parser.registry` nạp tự động (quét cả thư mục con). Parser **không**
hard-code mẫu biểu trong code.

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

Khi nhiều phiên bản có cấu trúc giống nhau và đều đã được kiểm chứng, dùng
`"verified_form_versions": ["2.5.1", "2.9.3"]` thay cho `form_version`. Registry
chỉ đăng ký đúng các phiên bản trong danh sách; phiên bản khác vẫn
`NEED_MAPPING`. `form_version: null` chỉ dùng khi chủ động hỗ trợ mọi phiên bản.

- `indicator_code`: mã chỉ tiêu **chính thức** trong XML (`ct21`, `ct43`, `ctB1`…).
- `canonical_name`: tên chuẩn hóa dùng cho cột Excel/query.
- Chưa có mapping ⇒ parser trả `NEED_MAPPING` cho mọi chỉ tiêu và **không** tự gán
  tên. Đây là hành vi có chủ đích (spec §3.1, §45).

## Thêm mapping mới

1. Lấy một XML đại diện của đúng `form_code` + `form_version`.
2. Liệt kê các mã chỉ tiêu và đối chiếu với mẫu biểu chính thức.
3. Viết file JSON, thêm fixture ẩn danh + test trong `tests/`.
4. Chạy `python -m gdt_tax.parser.cli <folder>` và kiểm tra `status = MAPPED`.

## Support matrix đã kiểm chứng

| Nhóm | Mẫu | Mã | Phiên bản XML | Vai trò | Định dạng | Phạm vi |
|---|---|---:|---|---|---|---|
| GTGT | 01/GTGT | 842 | 2.5.1/2.6.8/2.7.4/2.8.3 | Tờ khai chính | XML | Chỉ tiêu tổng hợp đã mapping |
| TNCN | 05/KK-TNCN TT80 | 864 | Các version trong fixture/dữ liệu hiện có | Tờ khai chính | XML | Chỉ tiêu `ct16`–`ct32` |
| TNCN | 05/KK-TNCN TT92 | 394 | Các version trong fixture/dữ liệu hiện có | Tờ khai chính | XML | Chỉ tiêu `ct21`–`ct36` |
| TNCN | 05/QTT-TNCN TT80 | 953 | 2.5.1/2.7.9/2.8.4/2.9.3 | Tờ khai chính | XML | 26 chỉ tiêu `ct16`–`ct41`; không đọc bảng kê cá nhân/KHBS |
| TNDN | 03/TNDN TT80 | 892 | 2.5.1 | Tờ khai chính | XML | 63 chỉ tiêu; C7 cố định 20% |
| TNDN | 03/TNDN TT80 | 892 | 2.9.4 | Tờ khai chính | XML | 65 trường; C7 có nhãn/thuế suất động |

TNDN 892 đã kiểm trên 20 XML cục bộ: 17 bản 2.5.1 và 3 bản 2.9.4, gồm chính
thức và bổ sung. XPath đều nằm dưới `CTieuTKhaiChinh`; `PLuc`, bảng kê và báo
cáo tài chính không thuộc mapping. Tên chỉ tiêu 03/TNDN đối chiếu Phụ lục II
Thông tư 80/2021/TT-BTC trong [Công báo bản gốc](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/9/34774/37499-1-2021969-97080-2021-tt-btc.pdf)
và [Văn bản hợp nhất 15/VBHN-BTC](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2024/5/42004/50395-1-2024717-71815-vbhn-btc.pdf);
cấu trúc C7 2.9.4 lấy từ XML thật. Không hỗ trợ ngầm version 892 khác hai
version trên.

TNCN 953 đã kiểm trên 36 XML cục bộ (5 chính thức, 31 bổ sung), không warning.
Tên chỉ tiêu đối chiếu mẫu 05/QTT-TNCN trong
[Công báo Thông tư 80/2021](https://congbao.chinhphu.vn/tai-ve-van-ban-so-80-2021-tt-btc-34774-37502?format=pdf)
và [Văn bản hợp nhất 15/VBHN-BTC](https://congbao.chinhphu.vn/tai-ve-van-ban-so-15-vbhn-btc-42004-50398?format=pdf).
Mapping chỉ đọc hai nhóm tổng hợp `NVuKhauTruThue` và `NVuQToanThay`; các bảng
kê 05-1/05-2/05-3 và phụ lục KHBS có dữ liệu cá nhân nằm ngoài phạm vi.

Kiểu dữ liệu mặc định là `decimal`; thuế suất dùng `percentage`, nhãn C7 của
2.9.4 dùng `string`. Parser chỉ trích số đã khai, không tính lại công thức hoặc
sửa số. `null`, `0` và số âm được giữ riêng.
