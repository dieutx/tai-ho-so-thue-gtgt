# Bộ prompt phát triển theo từng lần

Đọc [HANDOFF.md](HANDOFF.md) khi chuyển máy, rồi [REVIEW.md](REVIEW.md) để biết
lỗi đã sửa, kết quả test offline/thật và hạn chế còn lại. Copy
[MASTER.md](prompts/MASTER.md), chọn một STAGE rồi copy prompt tương ứng vào
cùng phiên làm việc. Mỗi stage phải giao code, kiểm thử và tài liệu; không chỉ
trả lời kế hoạch. Cập nhật trạng thái ở đây sau khi hoàn thành.

Stage 01 có phần nền tảng đã làm trong lần rà soát này: legacy trực tiếp, DVC
tạm tắt, summary cho khoảng bỏ qua, sửa dry-run và metadata. Phân loại metadata
cũng đã có. Prompt vẫn yêu cầu đọc code hiện tại và chỉ làm phần thiếu.

Cập nhật 02/10/2026: đã thêm báo cáo Excel 11 cột từ metadata tra cứu và lưu
trường hồ sơ đính kèm của DVC. Test thật legacy trước đó 6/6, chạy lại
không tải lại ZIP, không có request DVC. Các kết quả này **không** có nghĩa
stage 01 hoặc toàn bộ parser GTGT/TNCN/TNDN đã hoàn tất.

Cập nhật 02/10/2026 (stage 02): đã thêm `gdt_tax/inventory.py` — quét đệ quy
ZIP/member, SHA-256, profile cấu trúc XML, manifest + báo cáo discovery, CLI
offline. Chạy trên `download/`: 1262 file, 1268 member (1265 XML, 3 PDF), 96
signature/92 skeleton, 32 mã mẫu, 31 phiên bản.

Cập nhật 02/10/2026 (stage 04–05): đã thêm `gdt_tax/parser/` — khung parser tách
khỏi mapping (`gdt_tax/form_mappings`), reader an toàn, trích metadata + chỉ tiêu tổng hợp
kèm provenance XPath, phân biệt NULL/0. Đã thêm mapping đầu tiên
ba mapping: `gtgt_842_01-gtgt` (01/GTGT), `tncn_864_05kk-tt80`,
`tncn_394_05kk-tt92`, dựng theo logic VBA người dùng cung cấp + tên theo thông tư.
Chạy trên `download/`: 1265 tờ khai, 0 lỗi, **459 `MAPPED`** (842: 245, 864: 138,
394: 76), phần còn lại `NEED_MAPPING`.

Cập nhật 02/10/2026 (stage 03 + 08): `classify.py` phân loại từng artifact theo
nội dung (1265 artifact); `export.py` xuất `Tax_Return_Summary.xlsx` 11 sheet +
CSV + bộ lọc + audit log, giữ provenance và không cộng dồn lần nộp. Còn lại:
mapping TNDN (892) và quyết toán TNCN (953) cần logic XPath; stage 09 DVC.

| Stage | Kết quả cần có | Phụ thuộc | Prompt | Trạng thái |
|---|---|---|---|---|
| 01 | Tải/resume/auth/config/storage ổn định, không phụ thuộc DVC khi tắt | Baseline hiện tại | [01](prompts/01-stability.md) | Đã làm phần nền tảng; còn hardening trong REVIEW |
| 02 | Inventory file bên trong ZIP, identity/hash/provenance và lệnh offline | 01 | [02](prompts/02-artifacts.md) | Đã làm phần nền tảng: inventory/member/hash/signature + CLI offline; còn provenance theo tài khoản và phân loại role |
| 03 | Phân loại từng artifact theo nội dung, mã mẫu/phiên bản, conflict/unknown | 02 | [03](prompts/03-classification.md) | Đã có `classify.py` (nội dung, bằng chứng/conflict); còn rule vai trò phụ lục theo marker |
| 04 | Framework parser và schema output chung có phiên bản | 02–03 | [04](prompts/04-parser-core.md) | Đã làm khung + extractor generic + registry + CLI offline |
| 05 | Parser một mẫu GTGT có fixture đại diện | 04 | [05](prompts/05-gtgt.md) | Đã có mapping 01/GTGT (mã 842), fixture ẩn danh và golden test |
| 06 | Parser TNCN, bảng chi tiết/phụ lục được chọn | 04; ưu tiên sau 05 | [06](prompts/06-tncn.md) | Đã có mapping 05/KK-TNCN TT80 (864) + TT92 (394); còn quyết toán 05/QTT-TNCN, phụ lục, 02/KK-TT156 |
| 07 | Parser TNDN, phiên bản/phụ lục được chọn | 04; ưu tiên sau 05 | [07](prompts/07-tndn.md) | Chưa làm |
| 08 | Export và truy vấn theo nhóm/kỳ/phiên bản nộp, báo cáo chất lượng | 05; tận dụng 06–07 nếu có | [08](prompts/08-export.md) | Đã có `export.py` (Excel 11 sheet + CSV + lọc + audit log) |
| 09 | Xác minh adapter DVC, có thể bật lại chủ động, vẫn giữ mặc định tắt | 01; không chặn 02–08 | [09](prompts/09-dvc.md) | Hoãn tới khi cần |

Trật tự chính: 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08. Stage 09 độc lập.
Không làm parser GTGT/TNCN/TNDN đồng loạt trước khi kiểm chứng khung parser với
một mẫu. Không cần GUI ở các stage này; CLI/offline trước, giao diện sau.

Đích dữ liệu, chưa phải schema đang được triển khai:

```text
Case (nguồn, tài khoản, mã hồ sơ, ngày nộp, chính thức/bổ sung)
  └─ Artifact[] (ZIP/member, hash, định dạng, đường dẫn, trạng thái)
       ├─ Classification (nhóm thuế, vai trò, mã mẫu, phiên bản, bằng chứng)
       └─ ParsedDeclaration (parser/version, thông tin chung, chỉ tiêu, phụ lục, lỗi)
```

Nhóm thuế (GTGT/TNCN/TNDN) khác vai trò tài liệu (tờ khai/phụ lục/thông báo),
khác loại lần nộp (chính thức/bổ sung), khác định dạng (XML/PDF/ZIP). Giữ các
chiều này riêng để thêm nhóm mới không phải sửa pipeline tải.

## Lần làm tiếp được đề xuất

Ưu tiên stage 07: thêm mapping TNDN mã 892 từ fixture ẩn danh đã đối chiếu mẫu
biểu chính thức; sau đó quyết toán TNCN mã 953. Song song, tiếp tục phần thiếu
stage 01 (che log/dump, identity/resume) và stage 02 (nối ZIP với hồ sơ khi tên
không khớp metadata). Không commit raw hồ sơ thật hoặc suy đoán XPath/chỉ tiêu.
