# Danh mục PR đề xuất — review core 20/10/2026

Đọc [REPORT.md](REPORT.md) trước để biết mức bằng chứng, thứ tự triển khai và giới hạn.

Mỗi ID dưới đây là một đầu việc đề xuất, **chưa phải GitLab issue/PR đã tạo**. Đầu việc L phải chia thành các PR nhỏ như phạm vi chỉ rõ. Effort chỉ là khoảng lập kế hoạch, cần agent ước lượng lại sau khi đọc nhánh hiện tại.

Dùng [AGENT_TASK_TEMPLATE.md](AGENT_TASK_TEMPLATE.md) cùng ID cần giao. Nguồn bằng máy: [BACKLOG.json](BACKLOG.json).

<a id="core-01"></a>

## CORE-01 — Phân biệt kết quả rỗng thật với parser không còn hiểu trang

**P1 · Portal và độ đầy đủ kết quả · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R01 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Đổi downloadTkhai thành một tên handler khác trên fixture legacy: từ 2 hồ sơ còn 0, trong khi total_pages vẫn là 1. Pipeline chấp nhận HTTP 200 + total_pages>=0. Cổng đổi handler, thiếu cột hoặc parser bỏ tất cả hàng có thể bị báo không có kết quả thay vì báo thay đổi cấu trúc.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parsing.py:parse_records (L142)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parsing.py#L142)
- [gdt_tax/portals/etax_legacy.py:_total_pages (L164)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L164)
- [gdt_tax/pipeline.py:Pipeline._search_page (L174)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/pipeline.py#L174)
- [gdt_tax/gnt/pipeline.py:GntPipeline._search_page (L171)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/pipeline.py#L171)
- [gdt_tax/tb/pipeline.py:TbPipeline._search_page (L168)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/pipeline.py#L168)

**Phạm vi PR**

- Bổ sung kết quả parse có số hàng dữ liệu ứng viên, số hàng đọc được, số hàng bỏ và lý do; giữ API tương thích bằng adapter nếu cần.
- Xác nhận rỗng bằng cấu trúc/marker rỗng đã kiểm chứng, không chỉ dựa vào records=[] hoặc có bảng/pagination.
- Khi có hàng dữ liệu nhưng không đọc được hoặc chỉ đọc được một phần, trả lỗi cấu trúc hoặc kết quả PARTIAL kèm lý do; không reset bộ đếm OCR như thành công.
- Áp dụng cùng hợp đồng cho legacy, DVC, ETAX, GNT và TB; không retry cùng trang bất thường nhiều lần.

**Tiêu chí nghiệm thu**

- Fixture cũ vẫn trả đủ hồ sơ; fixture rỗng thật vẫn thành công.
- Đổi handler, bỏ cột bắt buộc, một hàng lỗi trong hai hàng: không được báo SUCCESS đầy đủ.
- Phân biệt SCHEMA_CHANGED, EMPTY_CONFIRMED và PARSED; CLI có exit khác 0 cho kết quả chưa đủ, GUI giữ các hàng đã đọc.

**Ngoài phạm vi**

- Không đoán ID từ cột bất kỳ để ép trang lạ thành thành công
- Không khẳng định cổng hiện tại đã đổi handler

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(core): distinguish confirmed empty results from schema drift`.

<a id="core-02"></a>

## CORE-02 — Đọc cột theo hợp đồng có tên và phát hiện đổi thứ tự

**P1 · Portal và độ đầy đủ kết quả · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R02 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Các parser dựa chủ yếu vào chỉ số cột và số cột tối thiểu. Hoán đổi cột ngày nộp và nơi nộp vẫn giữ nguyên số hồ sơ, nhưng trường ngày chứa tên cơ quan thuế mà không có cảnh báo.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parsing.py:etax_record (L78)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parsing.py#L78)
- [gdt_tax/parsing.py:dvc_record (L96)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parsing.py#L96)
- [gdt_tax/parsing.py:etax_legacy_record (L116)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parsing.py#L116)
- [gdt_tax/gnt/parsing.py:gnt_record (L51)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/parsing.py#L51)
- [gdt_tax/tb/parsing.py:tb_record (L43)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/parsing.py#L43)

**Phạm vi PR**

- Tạo schema bảng theo adapter: nhãn cột/thuộc tính ổn định, alias tiếng Việt chuẩn hóa Unicode, cột bắt buộc và tùy chọn.
- Ưu tiên data attribute có nghĩa; fallback theo vị trí chỉ khi fingerprint schema cũ khớp rõ ràng.
- Kiểm tra hình dạng ID, ngày và giá trị tiền; giữ raw text cùng parse warning, không suy đoán quy tắc thuế từ dữ liệu thiếu.
- Cho phép thêm cột tùy chọn mà không vỡ parser; thiếu/đổi nghĩa cột bắt buộc phải báo lỗi có tên cột.

**Tiêu chí nghiệm thu**

- Test hoán vị, thêm cột, đổi alias, colspan, dòng tiêu đề và bảng phụ; không đưa dữ liệu bảng phụ thành hồ sơ.
- Nếu không xác định chắc cột ngày/ID, trả schema mismatch thay vì điền sai trường.
- Snapshot trường của toàn bộ fixture hiện có không đổi ngoài bổ sung diagnostics.

**Ngoài phạm vi**

- Không dùng NLP/LLM để tự đoán ý nghĩa cột
- Không sửa đồng thời logic tải và lưu tệp

Phụ thuộc: CORE-01

Tên PR gợi ý: `fix(parsing): validate table schemas and column mapping`.

<a id="core-03"></a>

## CORE-03 — Định danh hồ sơ theo tài khoản, nguồn và loại tài liệu

**P1 · Định danh và cô lập dữ liệu · Effort L**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R03 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

records và các tập downloaded/failed/target_ids thường dùng ID trần. Hai nguồn trả cùng ID thì pipeline giữ một hồ sơ và vẫn báo tra cứu đủ trong phép thử. Metadata tờ khai đã dùng (nguon,ma_ho_so), nhưng pipeline và lựa chọn GUI chưa thống nhất. Cùng thư mục với tài khoản khác cũng chưa có chủ sở hữu dữ liệu được core cưỡng chế.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/pipeline.py:Pipeline._search_and_download (L118)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/pipeline.py#L118)
- [gdt_tax/storage.py:ZipStore.find_existing (L116)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/storage.py#L116)
- [gdt_tax/storage.py:write_metadata (L168)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/storage.py#L168)
- [desktop/file_store.py:DesktopZipStore (L7)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/file_store.py#L7)
- [desktop/sessions.py:ETaxSessionManager._mixed_tax (L227)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/sessions.py#L227)
- [desktop/documents.py:document_id (L36)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/documents.py#L36)

**Phạm vi PR**

- PR A: định nghĩa RecordKey(account_key, source, document_kind, remote_id), serialization ổn định; không coi account_key là cơ chế mã hóa/anonymization.
- PR B: dùng key xuyên pipeline, target selection, kết quả, catalog và file resume; giữ remote_id riêng cho request tới cổng.
- PR C: migration metadata cũ với trạng thái ownership/source chưa xác định; không tự gán cho tài khoản đang mở và không tự đổi tên/xóa tệp cũ.
- Thêm manifest chủ sở hữu thư mục hoặc namespace theo tài khoản; fail rõ khi dùng nhầm thư mục. Không coi hai nguồn là cùng một lần nộp chỉ vì trùng ID.

**Tiêu chí nghiệm thu**

- Hai nguồn cùng ID và hai loại tài liệu cùng ID đều được giữ riêng; tải đúng endpoint.
- Lựa chọn một hàng không tải nhầm hàng trùng ID ở nguồn khác; resume không nhận tệp của tài khoản khác.
- Metadata cũ vẫn đọc được hoặc có hướng dẫn chuyển đổi rõ; test migration lặp lại và rollback không mất dữ liệu.

**Ngoài phạm vi**

- Không tự hợp nhất ETAX và DVC theo kỳ/tên tờ khai
- Không đổi mã hồ sơ gửi lên cổng
- Không gom cả migration vào một PR lớn

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `refactor(identity): introduce account and source aware record keys`.

<a id="core-04"></a>

## CORE-04 — Chặn ghép manifest, parsed và classification không cùng thế hệ

**P1 · Lineage và hợp đồng dữ liệu offline · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R04 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

build_rows lặp toàn bộ parsed và không xác nhận artifact còn nằm trong manifest hiện hành. Manifest mới chỉ chứa artifact mới nhưng parsed cũ vẫn xuất được dòng cũ. Các kiểm tra root/hash vừa thêm ở bước parse không chứng minh đầu vào của bước export là cùng một lần inventory.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/export.py:build_rows (L94)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L94)
- [gdt_tax/export.py:load_inputs (L368)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L368)
- [gdt_tax/parser/cli.py:_read_manifest (L37)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/cli.py#L37)
- [gdt_tax/classify.py:_read_manifest (L189)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/classify.py#L189)
- [desktop/services.py:run_offline (L247)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/services.py#L247)

**Phạm vi PR**

- Đặt run_id/manifest fingerprint, source root identity, schema/profile/parser/mapping/rule versions và hashes đầu vào vào output mỗi stage.
- Validator dùng chung cho CLI/desktop: kiểm tra kiểu trường, schema version được hỗ trợ, membership artifact, source hash và tính duy nhất của key.
- Chỉ export bundle tương thích; trường hợp cho phép dữ liệu thiếu phải là chế độ tường minh, có cảnh báo và trạng thái chưa đủ.
- Không đọc lỗi JSON thành None rồi tiếp tục âm thầm nếu file có tồn tại nhưng hỏng.

**Tiêu chí nghiệm thu**

- Inventory A + parsed B, classification cũ, artifact bị xóa, duplicate key, schema mới chưa hỗ trợ: fail rõ trước khi ghi đè output tốt.
- Thay mapping/rule phải khiến output cũ được đánh dấu stale theo đúng stage.
- Chạy riêng export và chạy all cho cùng input cho cùng tập record và lineage, ngoại trừ timestamp.

**Ngoài phạm vi**

- Không chỉ so số lượng dòng để kết luận tương thích
- Không bỏ âm thầm parsed không khớp

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(offline): validate lineage and stage input compatibility`.

<a id="core-05"></a>

## CORE-05 — Áp dụng xử lý text an toàn cho mọi sheet và CSV

**P1 · An toàn xuất báo cáo · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R05, R06 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Cùng form_code tổng hợp '=1+1': sheet index ghi text, nhưng sheet indicators và unmapped ghi ô kiểu formula. CSV vẫn giữ prefix công thức. _excel_safe chưa được áp dụng ở mọi đường xuất. Đây là lỗi xử lý dữ liệu ngoài đã tái hiện; không phải bằng chứng có hồ sơ độc hại thực tế.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/export.py:_write_indicators_sheet (L206)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L206)
- [gdt_tax/export.py:_write_rows_sheet (L236)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L236)
- [gdt_tax/export.py:write_csv (L355)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L355)
- [gdt_tax/storage.py:write_metadata (L168)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/storage.py#L168)
- [gdt_tax/gnt/storage.py:write_gnt_metadata (L101)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/storage.py#L101)
- [gdt_tax/tb/storage.py:write_tb_metadata (L89)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/storage.py#L89)

**Phạm vi PR**

- Định nghĩa serializer theo loại cột: text phải luôn là text, số đã xác nhận phải là numeric; áp dụng tất cả sheet và các exporter.
- CSV dành cho Excel cần chính sách chống formula injection được tài liệu hóa; nếu cần CSV raw cho máy, tách chế độ rõ ràng.
- Xử lý prefix nguy hiểm sau ký tự trắng/tab/CR theo chính sách đã chọn, không làm hỏng dữ liệu số âm hoặc ID có số 0 đầu.
- Kiểm tra metadata export, báo cáo inventory/discovery và desktop/reports để không bỏ đường ghi khác.

**Tiêu chí nghiệm thu**

- Dùng '=1+1' và các chuỗi +,-,@, tab-prefix trên mọi trường text; lưu rồi mở lại workbook để kiểm tra data_type.
- CSV Excel-safe không mở như công thức; raw export nếu có được đánh dấu rõ.
- Không mất dấu âm của số hợp lệ, không chuyển MST/ID thành số, không chạy Excel hoặc lệnh ngoài trong test.

**Ngoài phạm vi**

- Không escape số bằng cách biến toàn bộ workbook thành text
- Không đưa payload gọi mạng hoặc lệnh hệ thống vào fixture

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(export): consistently serialize untrusted spreadsheet text`.

<a id="core-06"></a>

## CORE-06 — Xuất chỉ tiêu số dưới dạng numeric với chính sách độ chính xác

**P2 · Độ chính xác và tính hữu dụng của Excel · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R07 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Indicator.value giữ chuỗi là hợp lý cho JSON, nhưng exporter ghi nguyên chuỗi '-100'; ô L2 có data_type='s', không phải numeric. Pivot/SUM có thể không hoạt động như người dùng kỳ vọng. Không được sửa bằng ép float không kiểm soát vì có thể mất độ chính xác.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/export.py:_write_indicators_sheet (L206)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L206)
- [gdt_tax/export.py:_excel_safe (L166)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L166)
- [gdt_tax/parser/models.py:Indicator (L15)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/models.py#L15)

**Phạm vi PR**

- Phân biệt datatype string/integer/decimal và chuyển sang kiểu số phù hợp chỉ tại biên xuất Excel.
- Quy định giới hạn độ chính xác Excel; dữ liệu vượt khả năng biểu diễn giữ raw/normalized text và cảnh báo thay vì làm tròn âm thầm.
- Giữ NULL là ô trống, 0 là số 0, raw_value và ID/MST luôn là text.

**Tiêu chí nghiệm thu**

- Save/reload workbook: số âm, 0 và số thập phân hợp lệ là numeric khi biểu diễn an toàn; NULL khác 0.
- Số rất lớn, nhiều chữ số thập phân, datatype string trông giống số có kết quả đúng theo chính sách, có cảnh báo khi cần.
- Giá trị JSON normalized không đổi vì yêu cầu Excel.

**Ngoài phạm vi**

- Không tính lại hoặc tổng hợp nghĩa vụ thuế
- Không chọn bản nộp mới nhất để cộng vào báo cáo

Phụ thuộc: CORE-05, CORE-08

Tên PR gợi ý: `fix(export): preserve numeric types and explicit precision policy`.

<a id="core-07"></a>

## CORE-07 — Đọc XML theo namespace URI và đúng phạm vi tờ khai

**P1 · XML và thay đổi schema · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R12 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

namespace_map chỉ lấy namespace mặc định của root. XML cùng namespace URI nhưng chuyển sang prefix p: làm form_code từ 842 thành None. Ngoài ra metadata dùng .// toàn cây; khi mẫu mới có node cùng tên ở phụ lục, cần kiểm soát phạm vi thay vì lấy node đầu tiên.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parser/xml_reader.py:namespace_map (L45)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/xml_reader.py#L45)
- [gdt_tax/parser/xml_reader.py:find_text (L57)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/xml_reader.py#L57)
- [gdt_tax/parser/extract.py:extract_declaration (L211)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/extract.py#L211)
- [gdt_tax/parser/extract.py:_collect_indicators (L113)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/extract.py#L113)

**Phạm vi PR**

- Ràng buộc theo namespace URI thực của node, hỗ trợ default và prefix tương đương; không strip namespace mù quáng.
- Tách đường dẫn metadata declaration/notice và chọn đúng container tờ khai chính; phát hiện nhiều ứng viên mâu thuẫn.
- Giữ XPath có thể truy vết chính xác, bổ sung vị trí node lặp khi cần; hỗ trợ wrapper theo schema đã xác minh.

**Tiêu chí nghiệm thu**

- Default namespace và prefix bất kỳ cho kết quả chuẩn hóa tương đương.
- Root không namespace, mixed namespace, chữ ký XML, wrapper và MST/mã mẫu lặp ở phụ lục không bị lấy nhầm.
- Namespace chưa hỗ trợ báo schema chưa biết; không áp mapping chỉ vì localname trùng.

**Ngoài phạm vi**

- Không đổi ý nghĩa mapping hoặc suy ra chỉ tiêu thuế mới
- Không bỏ namespace khỏi toàn bộ XML

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(xml): resolve declaration metadata by namespace URI and scope`.

<a id="core-08"></a>

## CORE-08 — Thay đoán dấu phân cách bằng chính sách số theo nguồn/mapping

**P1 · XML và giá trị chỉ tiêu · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R13 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

normalize_number('0.125') trả '0125' không cảnh báo; '12.34.56' được chấp nhận thành '123456'. Một dấu phân cách với 3 chữ số sau bị coi là hàng nghìn. '1.234' có thể thật sự là 1234 theo locale hoặc 1.234 theo XML decimal; chưa có dữ liệu để khẳng định mọi mẫu hiện dùng nghĩa nào.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parser/xml_reader.py:_split_decimal (L83)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/xml_reader.py#L83)
- [gdt_tax/parser/xml_reader.py:normalize_number (L105)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/xml_reader.py#L105)
- [gdt_tax/parser/extract.py:_normalize_mapped_value (L84)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/extract.py#L84)
- [gdt_tax/parser/registry.py:FieldMapping (L26)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/registry.py#L26)

**Phạm vi PR**

- Mapping/nguồn khai numeric_format/locale/scale rõ: XML decimal chuẩn khác số hiển thị theo locale.
- Validate grouping trước khi bỏ dấu phân cách; trường hợp mơ hồ trả cảnh báo/giữ raw, không chọn số có thể sai hàng nghìn lần.
- Giữ Decimal hoặc normalized decimal string; tách parser số dùng cho UI hiển thị với parser nội dung XML.

**Tiêu chí nghiệm thu**

- Bảng test số nguyên, thập phân 3 chữ số, số âm, grouping VN/US, malformed grouping và khoảng trắng.
- Fixture mapping hiện tại vẫn đúng; mapping chưa khai chính sách có migration/default được chứng minh, không đổi hàng loạt số âm thầm.
- Không biến lỗi thành 0; warning phải đi tới export/audit.

**Ngoài phạm vi**

- Không tự thay toàn bộ dấu chấm thành dấu phân cách nghìn
- Không dùng float làm biểu diễn chuẩn nội bộ

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(parser): make numeric normalization explicit and ambiguity aware`.

<a id="core-09"></a>

## CORE-09 — Kiểm tra schema, trùng mapping và phạm vi phiên bản

**P1 · Mapping và mở rộng mẫu biểu · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R08, R09 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Hai mapping cùng key: mapping thêm sau đè mapping trước. fields dạng list không rỗng làm AttributeError lọt ra thay vì diagnostics có kiểm soát. effective_from/to, detect_root/namespace được nạp nhưng lookup chỉ xét code/version; wildcard version tường minh có thể tiếp tục áp khi cơ quan thuế đổi cấu trúc.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parser/registry.py:MappingRegistry.add (L67)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/registry.py#L67)
- [gdt_tax/parser/registry.py:MappingRegistry.lookup (L73)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/registry.py#L73)
- [gdt_tax/parser/registry.py:_parse_mapping (L92)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/registry.py#L92)
- [gdt_tax/parser/registry.py:load_registry (L124)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/registry.py#L124)
- [gdt_tax/parser/extract.py:extract_declaration (L211)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/extract.py#L211)

**Phạm vi PR**

- Schema mapping có kiểu, datatype được hỗ trợ, XPath hợp lệ, ID/key duy nhất; strict mode cho registry đóng gói.
- Chính sách override custom registry phải tường minh và ghi audit, không phụ thuộc thứ tự tên file.
- Làm rõ trường detect/effective được thực thi thế nào hoặc bỏ khỏi hợp đồng; version mới/wildcard cần structural compatibility check.
- Tách mapping_status, extraction_completeness và validation_status: có mapping không có nghĩa mọi chỉ tiêu đã đọc đủ.

**Tiêu chí nghiệm thu**

- Duplicate key, list thay dict, XPath lỗi, datatype lạ, missing file đều có lỗi có cấu trúc; không traceback thô hoặc bỏ qua âm thầm trong strict mode.
- Fixture phiên bản chưa biết và cấu trúc mới không tự được báo đầy đủ MAPPED.
- Mỗi mapping đóng gói có golden fixture + provenance/version hash; thiếu chỉ tiêu bắt buộc báo chưa đầy đủ.

**Ngoài phạm vi**

- Không tự tạo mapping chỉ tiêu từ tên thẻ
- Không thay mapping đã kiểm chứng nếu không có fixture/nguồn đối chiếu

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(mapping): validate registry schemas and compatibility rules`.

<a id="core-10"></a>

## CORE-10 — Ràng buộc cache với source root và phiên bản profiler

**P2 · Inventory và cache · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R10 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Cache được tái sử dụng theo rel_path + size + mtime; load_cache kiểm tra schema nhưng không kiểm root/profile_version. Hai source root có file cùng tên, kích thước và mtime có thể nhận lại profile của root cũ. Parse mới có so hash nên bắt được một phần, nhưng classify/discovery vẫn có thể dùng profile stale.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/inventory.py:scan_directory (L553)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/inventory.py#L553)
- [gdt_tax/inventory.py:load_cache (L724)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/inventory.py#L724)
- [gdt_tax/inventory.py:_scan_one (L610)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/inventory.py#L610)
- [desktop/services.py:run_offline (L247)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/services.py#L247)

**Phạm vi PR**

- Cache envelope chứa root identity, inventory/profile version và policy; invalidate khi chuyển root hoặc đổi profiler.
- Phân biệt fast cache với verified cache; tùy chọn rehash hiện có phải đi xuyên desktop/CLI và thể hiện trong báo cáo.
- Không mutate object cache cũ khi gắn metadata case cho một lần scan mới; đánh giá symlink và file thay đổi trong lúc scan.
- Tệp không phải archive vẫn cần đọc có giới hạn; tránh path.read_bytes cho file lớn trước khi kiểm dung lượng.

**Tiêu chí nghiệm thu**

- R10 không tái dùng profile khác root; profile_version mới buộc tính lại.
- Cùng root có mtime/size giữ nguyên nhưng nội dung đổi được phát hiện trong verified mode; fast mode nêu rõ giới hạn.
- Lỗi quyền/file biến mất trong lúc hash được ghi theo artifact, không làm hỏng manifest tốt trước đó.

**Ngoài phạm vi**

- Không bắt buộc băm lại mọi tệp mỗi lần nếu chưa có số đo
- Không coi mtime là bằng chứng toàn vẹn nội dung

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(inventory): bind cache entries to root and profiler identity`.

<a id="core-11"></a>

## CORE-11 — Chuẩn hóa exit code cho parse/classify/export chưa đầy đủ

**P2 · Hợp đồng CLI · Effort S**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R11 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

gdt-parse vẫn trả exit 0 khi mọi declaration đều status=error. Desktop có PARTIAL, trong khi CLI offline chưa có hợp đồng tương đương. Đây là hành vi đã xác nhận; việc đổi exit code cần xử lý tương thích vì người dùng có thể đang dùng CLI trong automation.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parser/cli.py:main (L167)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/cli.py#L167)
- [gdt_tax/classify.py:main (L235)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/classify.py#L235)
- [gdt_tax/export.py:main (L394)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L394)
- [gdt_tax/cli.py:_main (L189)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/cli.py#L189)
- [desktop/services.py:run_offline (L247)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/services.py#L247)

**Phạm vi PR**

- Định nghĩa exit success/config/input/partial/error và machine-readable summary cho bảy entrypoint.
- Có strict/allow-partial rõ hoặc kế hoạch migration; output lỗi vẫn được ghi để kiểm tra nhưng exit phản ánh chất lượng.
- Tách NEED_MAPPING hợp lệ có chủ đích với XML lỗi và dữ liệu stale.

**Tiêu chí nghiệm thu**

- All-error, mixed-success, NEED_MAPPING-only, empty-confirmed và invalid-schema có exit/summary được tài liệu hóa.
- Tests gọi entrypoint thật bằng subprocess với fixture, không chỉ test hàm helper.
- README/CLI_GUIDE và desktop status mapping nhất quán.

**Ngoài phạm vi**

- Không xóa output chỉ vì kết quả partial
- Không thay mã thoát online hiện có ngoài kế hoạch tương thích

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `feat(cli): expose explicit partial and failed offline outcomes`.

<a id="core-12"></a>

## CORE-12 — Dùng chung giới hạn XML ở download, inventory và parse

**P2 · Giới hạn tài nguyên XML · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R14 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

xml_reader khai MAX_XML_DEPTH=100 và MAX_XML_NODES=200000 nhưng parse_xml không áp hai giới hạn này; cây sâu 110 vẫn được nhận. Inventory có walk kiểm depth/node, còn validator download có parser riêng. huge_tree=False vẫn giữ giới hạn của libxml2, nên không được diễn giải phát hiện này thành không có bảo vệ XML nào.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/parser/xml_reader.py:parse_xml (L25)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/xml_reader.py#L25)
- [gdt_tax/inventory.py:profile_xml (L296)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/inventory.py#L296)
- [gdt_tax/gnt/portal.py:is_gnt_xml (L36)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/portal.py#L36)
- [gdt_tax/portals/etax_legacy.py:EtaxLegacyPortal.download (L563)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L563)
- [gdt_tax/archive_limits.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/archive_limits.py#L1)

**Phạm vi PR**

- Một XmlPolicy/reader dùng chung có trần bytes, depth, nodes, DTD/entity policy và mã lỗi ổn định.
- Kiểm giới hạn theo cách có chi phí hữu hạn; nếu cần iterparse, giữ chính sách no-network và không bật huge_tree để chữa triệu chứng.
- Chuẩn hóa kết quả rejected/quarantined/unsupported và giữ source reference.

**Tiêu chí nghiệm thu**

- Test ở biên mỗi limit và vượt 1 đơn vị; cùng input có quyết định nhất quán ở các đường đọc.
- Entity/DTD, cây sâu và nhiều node đều thất bại có kiểm soát, không truy cập mạng.
- Fixture bình thường không đổi kết quả, lỗi một artifact không làm dừng cả batch.

**Ngoài phạm vi**

- Không tăng trần chỉ để làm test quá lớn chạy được
- Không coi no_network thay thế cho mọi kiểm tra tài nguyên

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(xml): enforce shared resource limits across readers`.

<a id="core-13"></a>

## CORE-13 — Không nhận XML lạ hoặc PDF cụt là tệp tải hoàn chỉnh

**P1 · Toàn vẹn tệp tải và resume · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R15 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

is_gnt_xml nhận bất kỳ XML hợp lệ có root không phải html/error, kể cả <status><message>failed</message></status>. is_tb_pdf chỉ xét prefix %PDF-, nên PDF cụt vẫn được save/reuse và GUI đánh dấu downloaded. ZIP CRC hiện có là nền tốt nhưng không chứng minh nội dung ZIP đúng hồ sơ.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/gnt/portal.py:is_gnt_xml (L36)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/portal.py#L36)
- [gdt_tax/tb/portal.py:is_tb_pdf (L42)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/portal.py#L42)
- [gdt_tax/gnt/storage.py:GntStore.find_existing (L74)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/storage.py#L74)
- [gdt_tax/tb/storage.py:TbStore.find_existing (L62)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/storage.py#L62)
- [gdt_tax/portals/etax_legacy.py:EtaxLegacyPortal.download (L563)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L563)
- [desktop/documents.py:verify_rows (L101)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/documents.py#L101)

**Phạm vi PR**

- Validator theo document kind và schema/root đã xác minh; root/format mới trả unsupported-format để điều tra thay vì tải thành công.
- PDF có kiểm tra cấu trúc phù hợp hoặc thư viện nhẹ được đánh giá; không chỉ thêm hậu tố %%EOF rồi coi là chứng minh toàn vẹn.
- Lưu size/hash/content kind cùng source record key; resume xác minh theo metadata, giữ riêng file nghi vấn, không tự xóa file cũ.
- Không đồng nhất tính toàn vẹn bytes với tính hợp lệ chữ ký hoặc chấp nhận về nghiệp vụ thuế.

**Tiêu chí nghiệm thu**

- XML lỗi dạng SOAP/status/JSON và PDF chỉ có header không được đánh dấu downloaded.
- Tệp hợp lệ của fixture tải/save/reuse được; root mới có diagnostics rõ.
- GUI và CLI dùng cùng validator; không reuse nhầm file chỉ vì filename khớp.

**Ngoài phạm vi**

- Không xây hệ thống xác minh pháp lý/chữ ký số trong PR này
- Không xóa file người dùng đang có

Phụ thuộc: CORE-12

Tên PR gợi ý: `fix(download): validate document kinds before save and reuse`.

<a id="core-14"></a>

## CORE-14 — Kiểm soát origin, HTTPS và redirect cho form/operation

**P1 · Ranh giới tin cậy HTTP · Effort M**

Mức bằng chứng: `boundary_reproduced_not_exploited`. Ca minh họa: R16 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Form action từ HTML có thể là URL tuyệt đối ngoài cổng và helper chấp nhận. HttpClient cũng nhận URL tuyệt đối và chưa áp origin policy; requests xử lý redirect tự động. Probe chỉ xác nhận thiếu guard ở helper, không gửi dữ liệu hoặc chứng minh cổng đang chuyển tới host lạ.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/http.py:HttpClient.url (L111)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L111)
- [gdt_tax/http.py:HttpClient.request (L117)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L117)
- [gdt_tax/portals/etax_legacy.py:_form_data (L89)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L89)
- [gdt_tax/portals/etax_legacy.py:_operation_url (L108)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L108)
- [desktop/sessions.py:RoutedHttpClient (L71)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/sessions.py#L71)

**Phạm vi PR**

- Origin policy theo adapter và mục đích request; yêu cầu HTTPS, chặn userinfo và host/port ngoài danh sách tin cậy.
- Kiểm tra từng redirect trước khi gửi lại body/header/cookie/token; xử lý riêng 301/302/303 và 307/308.
- Khi cơ quan thuế chuyển domain: báo cần cập nhật adapter/policy qua review; không âm thầm tin domain được HTML đề xuất.
- URL building dùng parser và chuẩn hóa origin, không dùng startswith để quyết định route.

**Tiêu chí nghiệm thu**

- Mock form action external, scheme-relative, http downgrade, host gần giống, userinfo, redirect nhiều chặng: không gửi credential/token sang origin chưa cho phép.
- Redirect hợp lệ nội bộ và hai cổng đang hỗ trợ vẫn hoạt động với cookie tách đúng.
- Lỗi chỉ nêu origin đã làm sạch, không kèm session query.

**Ngoài phạm vi**

- Không thêm host tùy ý qua cấu hình không kiểm soát
- Không tắt kiểm tra TLS hoặc bỏ qua interstitial

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(http): enforce per-portal origin and redirect policies`.

<a id="core-15"></a>

## CORE-15 — Giới hạn response, thời gian tác vụ và retry theo operation

**P1 · HTTP, timeout và retry · Effort L**

Mức bằng chứng: `behavior_and_code_inspection`. Ca minh họa: R17 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

HTTP mặc định đọc toàn bộ response vào memory trước giới hạn ZIP/XML downstream; request timeout không phải deadline toàn tác vụ. Retry lồng ở HTTP/login/search/session. Retry-After='inf' được nhận thành vô hạn. Base64/ZIP/XML bọc nhiều lớp còn làm tăng bản sao memory.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/http.py:HttpClient.request (L117)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L117)
- [gdt_tax/http.py:HttpClient._retry_delay (L265)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L265)
- [gdt_tax/storage.py:decode_zip_bytes (L87)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/storage.py#L87)
- [gdt_tax/run_hooks.py:RunHooks (L14)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/run_hooks.py#L14)
- [gdt_tax/pipeline.py:Pipeline._search_page (L174)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/pipeline.py#L174)
- [gdt_tax/auth.py:login (L27)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/auth.py#L27)

**Phạm vi PR**

- PR A: kiểm Retry-After hữu hạn, nonnegative, hỗ trợ HTTP-date và giới hạn max delay; backoff/jitter có clock/sleep inject được.
- PR B: đọc stream có trần bytes theo operation, tính cả bytes giải nén, đóng response khi dừng; tệp lớn dùng temporary spool rồi atomic commit.
- PR C: RunBudget gồm deadline, max requests/pages/bytes/auth retries; retry chỉ với loại lỗi và operation phù hợp, có idempotency policy cho POST.
- Progress/cancellation được kiểm tra giữa chunk; vẫn không hủy giữa atomic commit. Không hứa thread có thể ngắt ngay socket đang chờ.

**Tiêu chí nghiệm thu**

- Test 429 date/inf/NaN/giá trị cực lớn, 503, disconnect giữa stream, thiếu/sai Content-Length, gzip lớn bằng local fake server hoặc stream stub.
- Không tốn toàn bộ memory cho response vượt trần; response luôn đóng.
- Có tổng số request/thời gian retry hữu hạn; dừng an toàn, không retry credential-invalid/schema-changed như lỗi mạng.

**Ngoài phạm vi**

- Không retry mù mọi POST
- Không chuyển sang async/concurrency chỉ để né thiết kế budget
- Không dùng tải song song trong cùng phiên DSE

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `feat(http): bound streaming responses and operation retry budgets`.

<a id="core-16"></a>

## CORE-16 — Che URL, Referer và body dạng chuỗi; tách dump raw khỏi gói hỗ trợ

**P1 · Log và chẩn đoán có thể chia sẻ · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R18 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

Che dict theo tên trường không xử lý JSON/HTML/form-urlencoded dạng string, URL hoặc Referer có session query. R18 giữ nguyên fake password trong JSON string và fake session trong Referer. CLI SecretsFilter/GUI Redactor đã che thêm một số literal, nhưng không bảo vệ mọi token động trong dump. Traffic module docstring đang hứa có thể chia sẻ log mà không lộ phiên quá rộng.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/traffic.py:body_as_text (L86)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/traffic.py#L86)
- [gdt_tax/traffic.py:mask_headers (L60)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/traffic.py#L60)
- [gdt_tax/traffic.py:TrafficDumper (L141)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/traffic.py#L141)
- [gdt_tax/http.py:HttpClient._log_response (L251)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L251)
- [gdt_tax/auth.py:login (L27)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/auth.py#L27)
- [desktop/jobs.py:Redactor (L30)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/jobs.py#L30)
- [gdt_tax/logging_setup.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/logging_setup.py#L1)

**Phạm vi PR**

- Redactor có cấu trúc theo URL/query, headers, JSON/form và HTML field; che cả token/CSRF/DSE và dữ liệu định danh khi xuất support bundle.
- Log mặc định chỉ event code, origin/path an toàn, kích thước/hash/fingerprint; không ghi raw body login ở INFO.
- Raw dump là lựa chọn chẩn đoán riêng có thời hạn/giới hạn và nhãn private; support bundle được sanitize trước khi ghi.
- Đồng bộ tài liệu với hành vi và test không phụ thuộc literal của tài khoản thật.

**Tiêu chí nghiệm thu**

- Fake secret ở URL, Referer, hidden input, JSON string, nested array, exception, encoded form và response redirect không lọt ra shared output.
- Không hứa raw dump đã sạch nếu còn bytes gốc; test xác nhận mặc định không ghi raw tax data.
- Diagnostics vẫn đủ để nhận biết endpoint/operation/schema mismatch mà không có token thật.

**Ngoài phạm vi**

- Không commit log/HTML/CAPTCHA thực để làm fixture
- Không dùng regex duy nhất và tuyên bố bảo đảm mọi dạng dữ liệu

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(diagnostics): separate private traffic from sanitized support output`.

<a id="core-17"></a>

## CORE-17 — Giữ error, warning và mapping version xuyên suốt tới báo cáo

**P2 · Audit và truy vết · Effort M**

Mức bằng chứng: `behavior_reproduced`. Ca minh họa: R07 trong [EVIDENCE.json](EVIDENCE.json).

**Vấn đề và ảnh hưởng**

ParsedDeclaration có error/warnings/mapping_version, nhưng build_rows bỏ các trường này. Sheet 08_PARSE_ERRORS chỉ có nguồn/status, sheet 09_MAPPING_VERSIONS chỉ liệt kê mapping_id. Người nhận workbook không thấy chính xác vì sao parse lỗi hoặc mapping revision nào đã tạo số liệu.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/export.py:build_rows (L94)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L94)
- [gdt_tax/export.py:build_workbook (L248)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L248)
- [gdt_tax/parser/models.py:ParsedDeclaration (L57)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/models.py#L57)
- [gdt_tax/parser/models.py:Indicator (L15)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/models.py#L15)

**Phạm vi PR**

- Mang declaration error, warning và indicator warning, mapping ID/version/hash, parser/rule version vào row/audit.
- Tách lỗi cú pháp, source changed, missing indicator và chưa có mapping; giữ khả năng truy ngược record/artifact/source hash/XPath.
- Đặt giới hạn text và escape nội dung khi xuất; không đưa raw hồ sơ vào audit.

**Tiêu chí nghiệm thu**

- Workbook/JSON/CSV summary thể hiện được SOURCE_CHANGED, MISSING_IN_XML và PARSE_VALUE_ERROR.
- Hai mapping cùng ID khác version không bị báo là cùng một phiên bản.
- Audit có thể xác định output đến từ stage/input nào mà không cần log máy người dùng.

**Ngoài phạm vi**

- Không coi MAPPED đồng nghĩa toàn bộ báo cáo hợp lệ
- Không thay error bằng thông báo chung làm mất mã nguyên nhân

Phụ thuộc: CORE-04

Tên PR gợi ý: `feat(audit): preserve parser diagnostics and mapping provenance`.

<a id="core-18"></a>

## CORE-18 — Giảm ghi lại toàn catalog và tránh mất cập nhật giữa hai tiến trình

**P2 · Storage và khả năng mở rộng · Effort L**

Mức bằng chứng: `code_inspection`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Mỗi hồ sơ gọi _persist, đọc/merge JSON rồi ghi lại JSON/CSV/XLSX; tổng lượng công việc có xu hướng bậc hai theo số hồ sơ. Atomic replace bảo vệ từng file nhưng không tạo transaction chung hoặc lock giữa hai EXE/CLI. Hai writer đọc cùng catalog có thể ghi đè cập nhật của nhau. Chưa chạy benchmark hoặc race stress trong lượt review này.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/pipeline.py:Pipeline._persist (L54)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/pipeline.py#L54)
- [gdt_tax/gnt/pipeline.py:GntPipeline._persist (L60)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/pipeline.py#L60)
- [gdt_tax/tb/pipeline.py:TbPipeline._persist (L59)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/pipeline.py#L59)
- [gdt_tax/storage.py:write_metadata (L168)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/storage.py#L168)
- [gdt_tax/atomic.py:replace_with_retry (L9)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/atomic.py#L9)

**Phạm vi PR**

- PR đầu benchmark 100/1000/5000 record tổng hợp, đếm workbook saves/bytes/time; tách commit catalog khỏi materialize Excel/CSV.
- Chọn journal/checkpoint hoặc SQLite có migration sau khi so tradeoff; checkpoint theo page/time, flush khi kết thúc/cancel có kiểm soát.
- Có lock hoặc optimistic revision check cho catalog; có generation marker/recovery cho các derived report.
- Giao diện query vẫn không ghi output; bản tải đã commit phải khôi phục được sau crash.

**Tiêu chí nghiệm thu**

- Test hai writer, crash giữa JSON và XLSX, disk full và file bị khóa; không mất catalog trước đó.
- Số lần build workbook không tuyến tính theo số record khi tải; benchmark so trước/sau và nêu môi trường.
- Resume sau crash không bỏ tệp đã hoàn tất và không gán thành công cho file chưa commit.

**Ngoài phạm vi**

- Không tự chọn SQLite nếu chưa đo/thiết kế migration
- Không bỏ fsync/atomic write chỉ để tăng tốc

Phụ thuộc: CORE-03

Tên PR gợi ý: `perf(storage): checkpoint catalogs and serialize concurrent writers`.

<a id="core-19"></a>

## CORE-19 — Phân loại phản hồi đăng nhập/phiên dùng chung cho DVC và legacy

**P1 · Xác thực và trạng thái phiên · Effort M**

Mức bằng chứng: `code_inspection`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Legacy vừa được sửa để nhận một số lỗi cụ thể, nhưng DVC login vẫn coi JSON không status=200 là rejected CAPTCHA. is_auth_failure chỉ biết một tập HTTP/form/chuỗi. Maintenance, SSO, OTP, đổi giao thức hoặc lỗi tài khoản mới vẫn dễ rơi vào retry/fallback sai loại. Chưa tái hiện một lỗi DVC mới trong review này.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/auth.py:login (L27)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/auth.py#L27)
- [gdt_tax/verification.py:raise_for_portal_verification (L16)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/verification.py#L16)
- [gdt_tax/portals/etax_legacy.py:EtaxLegacyPortal._submit_login (L277)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L277)
- [desktop/sessions.py:is_auth_failure (L39)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/sessions.py#L39)
- [desktop/sessions.py:ETaxSessionManager.execute (L168)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/sessions.py#L168)

**Phạm vi PR**

- AuthOutcome/PortalResponseKind: success, invalid credentials, captcha invalid, expired session, access verification, maintenance, interactive auth required, schema unknown.
- Classifier theo adapter và markup/JSON thực; giữ unknown thay vì đoán sai. Reauth một lần chỉ khi có bằng chứng hết phiên.
- Scope cookie/token/state theo nguồn; cập nhật token xoay vòng đúng response/operation.
- Nếu SSO/OTP bắt buộc, trả hành động cần người dùng hoặc luồng browser được thiết kế riêng, không tự thêm cơ chế vượt xác minh.

**Tiêu chí nghiệm thu**

- Fixture matrix cho từng outcome, gồm HTTP 200 và redirect về login; không tính mọi lỗi thành CAPTCHA.
- Invalid credentials và maintenance không retry auth liên tục; expired retry hữu hạn; cancellation giữ đúng loại.
- CLI và desktop báo cùng error code; không lộ nội dung nhạy cảm trong thông báo.

**Ngoài phạm vi**

- Không tự giải/bỏ qua lớp bảo vệ truy cập
- Không kết luận header giả trình duyệt bảo đảm truy cập
- Không đưa Playwright vào runtime chỉ để vá một trang lạ

Phụ thuộc: CORE-01, CORE-14

Tên PR gợi ý: `refactor(auth): classify portal outcomes and session recovery explicitly`.

<a id="core-20"></a>

## CORE-20 — Tách profile năng lực portal và chính sách định tuyến nguồn

**P2 · Khả năng thích ứng cổng · Effort L**

Mức bằng chứng: `architecture_proposal`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Một số endpoint ở constants, nhưng operation/selector/field/empty marker/pagination vẫn rải trong các adapter. Cutoff và thời đoạn là chính sách toàn cục; khi cơ quan thuế mở lại nguồn cũ, đổi ngày chuyển nguồn hoặc giới hạn khoảng tra cứu, sửa một hằng số có thể chưa đủ.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/constants.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/constants.py#L1)
- [gdt_tax/config.py:Settings.periods (L155)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/config.py#L155)
- [gdt_tax/config.py:Settings.source_enabled (L171)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/config.py#L171)
- [gdt_tax/portals/__init__.py:build_portals (L22)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/__init__.py#L22)
- [gdt_tax/portals/etax_legacy.py:EtaxLegacyPortal (L173)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L173)
- [gdt_tax/gnt/portal.py:GntPortal (L49)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/portal.py#L49)
- [gdt_tax/tb/portal.py:TbPortal (L47)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/portal.py#L47)

**Phạm vi PR**

- Profile có version cho endpoint, operation/form descriptors, supported document kinds, pagination strategy, date limit và response contracts.
- RoutingPolicy có ngày hiệu lực và khả năng nguồn; in execution plan trước khi đăng nhập, báo coverage gap/overlap rõ.
- Profile là cấu hình đóng gói đã review và validate, không tải rồi thực thi tùy ý từ remote.
- Chia PR theo một adapter trước; giữ fixture baseline và option cũ qua compatibility adapter.

**Tiêu chí nghiệm thu**

- Mô phỏng đổi form ID/operation/page parameter trong một profile mà không sửa generic pipeline.
- Test cutoff boundaries, gap/overlap, nguồn tắt, đổi max range; không tự báo đầy đủ khi một nguồn không truy cập được.
- Cho biết profile/routing version trong diagnostics và output lineage.

**Ngoài phạm vi**

- Không xây DSL tổng quát cho mọi website
- Không cho cấu hình chèn Python/JS/XPath tùy ý ngoài chính sách
- Không gộp bản ghi ở vùng overlap nếu chưa có identity rule

Phụ thuộc: CORE-01, CORE-19

Tên PR gợi ý: `refactor(portals): version adapter capabilities and routing policies`.

<a id="core-21"></a>

## CORE-21 — Định nghĩa Protocol/Result rồi mới rút gọn ba pipeline lặp

**P2 · Kiến trúc và bảo trì · Effort L**

Mức bằng chứng: `architecture_proposal`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Ba pipeline lặp retry/pagination/progress/target/download/persist, nên mỗi sửa dễ lệch giữa tờ khai/GNT/TB. GNT/TB kế thừa cả portal legacy và nhập private helper; response giả bọc XML thành ZIP rồi base64 để khớp requests-like API. settings/record/http dùng duck typing khá nhiều dù mypy core đang pass.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/portals/base.py:Portal (L26)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/base.py#L26)
- [gdt_tax/pipeline.py:Pipeline (L26)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/pipeline.py#L26)
- [gdt_tax/gnt/pipeline.py:GntPipeline (L26)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/gnt/pipeline.py#L26)
- [gdt_tax/tb/pipeline.py:TbPipeline (L25)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/tb/pipeline.py#L25)
- [gdt_tax/portals/etax_legacy.py:_XmlZipResponse (L623)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/portals/etax_legacy.py#L623)
- [desktop/services.py:run_online (L143)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/services.py#L143)

**Phạm vi PR**

- PR A: Protocol cho transport, solver, record/store, query outcome và DownloadArtifact; explicit bytes/stream/kind/source provenance.
- PR B: orchestration chung cho page loop, budget, completeness và progress; pagination strategy vẫn thuộc adapter.
- PR C: tách LegacySessionNavigator khỏi nghiệp vụ tờ khai để GNT/TB dùng composition; bỏ dần fake response/base64 qua compatibility layer.
- Giữ invariant search rồi tải ngay trên trang hiện tại, tuần tự trong một phiên DSE.

**Tiêu chí nghiệm thu**

- Contract tests chạy cùng bộ cho ba pipeline; behavior fixture cũ không đổi.
- Fake transport không phải giả cả requests.Response; type checker bắt thiếu capability/method trong adapter mới.
- Không đổi output filename/schema hoặc tăng memory khi refactor; PR nhỏ có rollback được.

**Ngoài phạm vi**

- Không viết lại toàn bộ core trong một PR
- Không tải song song cùng phiên DSE
- Không chuyển framework/async nếu chưa có nhu cầu và benchmark

Phụ thuộc: CORE-01, CORE-03

Tên PR gợi ý: `refactor(core): introduce typed contracts before sharing orchestration`.

<a id="core-22"></a>

## CORE-22 — Fixture có nguồn gốc, contract tests và phép biến đổi cấu trúc

**P2 · Kiểm thử khi cổng thay đổi · Effort M**

Mức bằng chứng: `test_strategy_proposal`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Bộ test hiện có nhiều tình huống hữu ích nhưng fixture chưa có manifest hợp đồng theo portal/date/profile/operation. Một parser và fixture cùng giữ vị trí cột cũ vẫn xanh khi portal có biến thể. 18 ca review cho thấy cần kiểm tra biến đổi đầu vào, không chỉ fixture một trạng thái.

**Điểm bắt đầu trong code tại baseline**

- [tests/fixtures](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/fixtures)
- [tests/test_parsing.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/test_parsing.py#L1)
- [tests/test_etax_legacy.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/test_etax_legacy.py#L1)
- [tests/test_gnt.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/test_gnt.py#L1)
- [tests/test_tb.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/test_tb.py#L1)
- [tests/test_verification.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/tests/test_verification.py#L1)
- [docs/core-review-20261020/reproduce_findings.py (L1)](reproduce_findings.py)

**Phạm vi PR**

- Fixture manifest: source, operation, sanitized_at, adapter version, content kind, expected row counts/outcomes và cách ẩn dữ liệu.
- Thêm metamorphic cases đổi namespace prefix, hoán vị/thêm cột, handler khác, token xoay, pagination thay đổi, lặp/thiếu hàng và HTML 200 maintenance.
- Chuyển từng repro đã fix thành regression test kỳ vọng hành vi đúng; không dùng script review làm green gate giữ nguyên lỗi.
- Replay trace bằng fake transport; live smoke chỉ opt-in, có account/quyền/scope/budget rõ, không chạy bằng secrets trong CI công khai.

**Tiêu chí nghiệm thu**

- Fixture mới chạy cùng parser/adapter thật và assert completeness/error classification.
- Không có credential, CAPTCHA thật hoặc hồ sơ thuế trong repo/artifact CI; sanitizer có tests.
- Tài liệu nêu cách thêm một biến thể cổng và chạy test matrix liên quan.

**Ngoài phạm vi**

- Không tự đăng nhập tài khoản thật từ pipeline CI
- Không snapshot nguyên HTML thực chưa sanitize
- Không chỉ assert độ dài list là đủ

Phụ thuộc: CORE-01, CORE-16

Tên PR gợi ý: `test(portals): version sanitized fixtures and drift contracts`.

<a id="core-23"></a>

## CORE-23 — Tách test tối thiểu, desktop Windows và nâng dependency có kiểm chứng

**P2 · CI, dependency và tái lập build · Effort M**

Mức bằng chứng: `code_inspection`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

GitLab CI hiện test Linux Python 3.10/3.12 với package tối thiểu; GUI/OCR thực không được cài trong job đó. Windows build local đã có 18 UI checks + frozen OCR, nhưng chưa là một gate CI được lưu cùng source revision. Dependency desktop pin trực tiếp nhưng chưa khóa toàn bộ transitive/hash; package core còn version 1.0.0 khác desktop 2.0.0.

**Điểm bắt đầu trong code tại baseline**

- [.gitlab-ci.yml (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/.gitlab-ci.yml#L1)
- [requirements-desktop.txt (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/requirements-desktop.txt#L1)
- [pyproject.toml (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/pyproject.toml#L1)
- [scripts/build_windows.ps1 (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/build_windows.ps1#L1)
- [scripts/smoke_test_windows.ps1 (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/smoke_test_windows.ps1#L1)
- [scripts/audit_bundle.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/audit_bundle.py#L1)

**Phạm vi PR**

- Giữ job minimal để kiểm optional imports; thêm desktop/OCR unit và Windows frozen smoke trên runner phù hợp, lịch chạy theo cost.
- Lock runtime/build-tools/transitive theo platform/Python với hash hoặc inventory được kiểm soát; lưu source SHA và build-tool versions trong artifact provenance.
- Chu kỳ update dependency bằng PR nhỏ, không đổi ORT/model chỉ vì bản mới hơn; thử source/frozen parity và bundle size.
- Tách core package version, desktop version và build revision rõ trong UI/CLI; không tự tăng bản phát hành ở PR review.

**Tiêu chí nghiệm thu**

- CI chỉ ra ca nào skip vì thiếu optional deps; có đường chạy không skip test desktop/OCR khi release.
- Build lại từ sạch không âm thầm lấy transitive khác; có SBOM/inventory và hash artifact.
- Source revision nhúng trong build/report khớp commit phát hành; kiểm version không mâu thuẫn chức năng update.

**Ngoài phạm vi**

- Không cần bit-for-bit reproducible ngay nếu chưa kiểm timestamps/toolchain
- Không đưa dependency nặng ngoài profile Full đã chọn
- Không gọi live portal để CI pass

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `ci: gate Windows desktop builds and capture dependency provenance`.

<a id="core-24"></a>

## CORE-24 — Health report và playbook chẩn đoán thay đổi cổng

**P2 · Vận hành và phát hiện thay đổi · Effort M**

Mức bằng chứng: `operational_proposal`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Hiện chủ yếu điều tra từ log và thử thật. Thiếu báo cáo fingerprint/outcome/coverage chuẩn để biết adapter nào lỗi, ở login/search/download hay offline mapping. Tài liệu kiến trúc còn một số khẳng định lịch sử như cổng không kiểm browser fingerprint, không còn đủ cơ sở để xem là bảo đảm hiện tại.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/http.py:HttpClient.request (L117)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/http.py#L117)
- [gdt_tax/run_hooks.py:RunHooks.emit (L31)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/run_hooks.py#L31)
- [desktop/jobs.py:LogBridge (L50)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/jobs.py#L50)
- [docs/ARCHITECTURE.md (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/docs/ARCHITECTURE.md#L1)
- [docs/development/REVIEW.md (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/docs/development/REVIEW.md#L1)

**Phạm vi PR**

- Structured event có trace/run/operation ID, profile version, error code, timings, counts và safe schema fingerprint.
- Lệnh doctor/offline validate-inputs và opt-in portal healthcheck chỉ đọc, tách public reachability khỏi authenticated capability; không tự chạy khi mở app.
- Playbook: dừng retry, lấy diagnostics an toàn, tạo fixture, thêm failing contract test, sửa adapter nhỏ, chạy offline rồi smoke có quyền, theo dõi/rollback.
- Ghi last_verified_at/environment cho ghi chép live; cập nhật docs để tách quan sát lịch sử khỏi hợp đồng.

**Tiêu chí nghiệm thu**

- Một báo cáo hỗ trợ chỉ rõ nguồn/operation/outcome/completeness mà không cần mật khẩu hoặc HTML thật.
- Healthcheck không tải/nộp hồ sơ, không thay đổi trạng thái nghiệp vụ và có budget.
- Runbook dẫn được từ symptom sang nhóm ticket/owner, có hướng rollback profile/build.

**Ngoài phạm vi**

- Không thêm telemetry tự động gửi ra ngoài
- Không coi healthcheck thành công là bằng chứng mọi nghiệp vụ đều dùng được
- Không tự sửa cấu hình theo remote response

Phụ thuộc: CORE-01, CORE-16, CORE-19

Tên PR gợi ý: `feat(diagnostics): add safe health reports and portal change runbook`.

<a id="core-25"></a>

## CORE-25 — Preflight, verify đủ asset và rollback khi thay release

**P2 · Phát hành và phục hồi · Effort M**

Mức bằng chứng: `code_inspection`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Helper replace đã dùng URL có hash và giữ asset ID, nhưng đổi hai link riêng rồi notes; lỗi giữa chừng có thể để release không đồng bộ. Helper chỉ tự tải lại EXE, còn checksum/tag/ID đã được kiểm bằng script ad-hoc trong lần phát hành vừa rồi. Chưa có preflight buộc metadata/version/tag/source revision tương thích.

**Điểm bắt đầu trong code tại baseline**

- [scripts/release_gitlab.py:main (L44)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/release_gitlab.py#L44)
- [scripts/release_gitlab.py:request (L37)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/release_gitlab.py#L37)
- [scripts/write_release_metadata.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/scripts/write_release_metadata.py#L1)
- [desktop/updates.py (L1)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/desktop/updates.py#L1)

**Phạm vi PR**

- Tích hợp preflight version/tag/build/source SHA/checksum và release/link IDs; snapshot trước mutation.
- Upload và xác minh cả hai package trước khi đổi link; commit link update có compensating rollback nếu API fail, ghi trạng thái recoverable.
- Verify EXE + checksum qua public/permalink URLs, tag không di chuyển và không sinh release mới trong replace.
- Lưu release manifest không chứa credential; tests API giả cho mọi vị trí thất bại và rerun idempotence.

**Tiêu chí nghiệm thu**

- Mock lỗi upload thứ hai, đổi link đầu, notes update, verify mismatch: trả lỗi rõ và có rollback/recovery kiểm chứng.
- replace không gọi create-release/tag APIs; giữ ID/link download cũ.
- Không in token, không tạo token file để tiện tự động hóa; không cần publish thật trong unit test.

**Ngoài phạm vi**

- Không đổi release/tag hiện có khi đang review
- Không xóa package cũ trước khi bản mới được xác minh
- Không hứa API update nhiều link là transaction nguyên tử

Phụ thuộc: Không bắt buộc.

Tên PR gợi ý: `fix(release): verify replacement bundles and recover partial updates`.

<a id="core-26"></a>

## CORE-26 — Phân biệt vai trò tài liệu, coverage mapping và trạng thái tiếp nhận

**P2 · Phạm vi nghiệp vụ và mở rộng phân loại · Effort M**

Mức bằng chứng: `known_capability_gap`. Đọc code/đề xuất; chưa có phép thử chuyên biệt trong lượt review này.

**Vấn đề và ảnh hưởng**

Phân loại nội dung hiện đặt has_appendix=False; mapping mới chỉ phủ một số mẫu/phiên bản. Trạng thái parse MAPPED/NEED_MAPPING khác với vai trò phụ lục/thông báo và trạng thái được cơ quan thuế chấp nhận. Nếu mở rộng báo cáo mà trộn các khái niệm này, có thể trình bày dữ liệu chưa xác minh như kết quả thuế cuối cùng.

**Điểm bắt đầu trong code tại baseline**

- [gdt_tax/classify.py:classify_artifact (L93)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/classify.py#L93)
- [gdt_tax/classification.py:classify_record (L30)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/classification.py#L30)
- [gdt_tax/parser/extract.py:extract_declaration (L211)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/parser/extract.py#L211)
- [gdt_tax/inventory.py:_case_view (L538)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/inventory.py#L538)
- [gdt_tax/export.py:build_rows (L94)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/export.py#L94)
- [gdt_tax/form_mappings](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/559892f1ff22f3e68d2fbea7be0608fd0ac597c9/gdt_tax/form_mappings)

**Phạm vi PR**

- DocumentRole từ cấu trúc có bằng chứng, giữ conflict/unknown khi tín hiệu khác nhau; hỗ trợ phụ lục theo fixture đã ẩn danh.
- Mapping coverage report theo form/version/namespace và số chỉ tiêu có/thiếu; thêm mapping từng mẫu bằng PR riêng với golden tests.
- AcceptanceStatus giữ raw status, nguồn/trích xuất và ngày kiểm chứng; unknown khi chưa có liên kết chắc với artifact.
- Giữ mọi lần nộp; declaration-family/latest selection là tính năng riêng có policy và người dùng chọn.

**Tiêu chí nghiệm thu**

- Fixture declaration/appendix/notice/unknown/conflict không bị ép chung một loại.
- Mẫu chưa mapping vẫn đọc metadata và được đánh dấu đúng; không tự tính thuế hoặc cộng các bản bổ sung.
- Báo cáo hiển thị riêng parse quality, file integrity và acceptance status.

**Ngoài phạm vi**

- Không suy đoán nghĩa chỉ tiêu từ mã ctXX
- Không tự kết luận tờ khai hợp lệ về pháp lý
- Không tự ẩn các lần nộp trước

Phụ thuộc: CORE-07, CORE-09, CORE-17

Tên PR gợi ý: `feat(classification): expose document roles and mapping coverage`.
