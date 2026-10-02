# Kiến trúc

Tài liệu này dành cho người đọc mã nguồn hoặc muốn mở rộng công cụ. Mục tiêu là
mỗi module chỉ có một trách nhiệm, và mọi phần dễ đổi (CAPTCHA, nguồn dữ liệu,
quy tắc ngày tháng) đều tách riêng để thay mà không ảnh hưởng phần còn lại.

Trạng thái triển khai, test thật và quy trình chuyển máy ở
[HANDOFF](development/HANDOFF.md); backlog và giới hạn ở
[REVIEW](development/REVIEW.md). Đã có inventory/profile cấu trúc XML, phân loại
artifact, khung parser theo mapping và export offline. Hiện mapping đã kiểm chứng
cho 01/GTGT, hai mẫu 05/KK-TNCN và 03/TNDN mã 892 phiên bản 2.5.1/2.9.4; các
mẫu còn lại vẫn cần làm.

## Bản đồ module

Chính sách hiện tại: `Settings.periods()` ánh xạ đoạn trước cutoff thành
`ETAX_LEGACY` mặc định; `Settings.source_enabled()` chặn ETAX/DVC trên cổng DVC
khi `dvc_enabled=False`. Pipeline lập kế hoạch trước khi đăng nhập DVC. Legacy
tự đăng nhập phiên DSE riêng ở lần tra cứu đầu. `EtaxLegacyFallback` chỉ còn
được giữ như adapter cũ, không tham gia luồng mặc định.

| Module | Trách nhiệm | Không được làm |
|---|---|---|
| `constants.py` | Địa chỉ cổng, endpoint, header, giá trị mặc định | Chứa logic |
| `models.py` | `CaseRecord`, `SearchPeriod`, `PageResult`, `RunSummary` | Gọi mạng |
| `errors.py` | Cây ngoại lệ | — |
| `dates.py` | Đọc/ghi ngày, chia đoạn tra cứu, mốc ETAX | Gọi mạng |
| `config.py` | `Settings` từ `.env` + biến môi trường | Gọi mạng |
| `http.py` | `HttpClient`: nối URL, timeout, thử lại khi 429, gắn proxy, log và dump từng request | Hiểu nghiệp vụ |
| `proxy.py` | Đọc chuỗi proxy của mọi nhà cung cấp thành `Proxy` (URL cho `requests`, cách che bí mật) | Gọi mạng, hiểu nghiệp vụ |
| `traffic.py` | Che dữ liệu nhạy cảm, định dạng log, ghi file dump request/response | Gọi mạng, hiểu nghiệp vụ |
| `logging_setup.py` | Cấu hình log ra màn hình và ra file, gắn `SecretsFilter` để che bí mật (mật khẩu proxy) | Ghi log nghiệp vụ |
| `csrf.py` | Đọc CSRF token từ HTML | Gọi mạng |
| `parsing.py` | Đọc bảng kết quả thành `CaseRecord` | Gọi mạng |
| `naming.py` | Tạo tên file ZIP | Đọc/ghi file |
| `classification.py` | Phân nhóm hồ sơ từ tên tờ khai/TTHC, ghi lý do và phiên bản rule | Gọi mạng, parse chỉ tiêu XML |
| `inventory.py` | Kiểm kê ZIP/member, SHA-256, profile cấu trúc XML, manifest + báo cáo discovery | Gọi mạng, trích xuất chỉ tiêu thuế, sửa file nguồn |
| `parser/` | Khung parser tờ khai: reader an toàn, registry mapping, trích metadata + chỉ tiêu kèm provenance | Hard-code mẫu biểu, đoán ý nghĩa chỉ tiêu, gọi mạng |
| `parser/models.py` | `ParsedDeclaration`, `Indicator`, `Period`, `Taxpayer` | Đọc file |
| `parser/xml_reader.py` | Parse XML an toàn, chuẩn hóa số (giữ NULL ≠ 0) | Gọi mạng, resolve entity |
| `parser/registry.py` | Nạp mapping từ `gdt_tax/form_mappings` hoặc thư mục CLI chỉ định | Hard-code XPath trong code |
| `parser/extract.py` | Trích metadata + chỉ tiêu tổng hợp từ `CTieuTKhaiChinh` | Lấy bảng kê chi tiết |
| `parser/cli.py` | Lệnh offline parse từ manifest | Gọi mạng |
| `classify.py` | Phân loại từng artifact theo nội dung XML (nhóm thuế, vai trò, bằng chứng/conflict) | Gọi mạng, đoán khi thiếu tín hiệu |
| `export.py` | Ghép manifest+parsed+classification, lọc, xuất Excel đa sheet/CSV | Gọi mạng, đổi số âm thành text |
| `storage.py` | Kiểm tra ZIP, chống tải trùng, ghi ZIP, Excel/CSV/JSON | Gọi mạng |
| `captcha/` | Nhận dạng CAPTCHA (nhiều backend) | Gọi endpoint nghiệp vụ |
| `portals/` | Tra cứu và tải theo từng nguồn | Đọc/ghi file |
| `portals/etax_legacy.py` | Nguồn chính trước cutoff: login DSE, kiểm tra XML rồi gói ZIP; adapter fallback cũ được giữ | Đọc/ghi file |
| `auth.py` | Đăng nhập, mở trang hồ sơ | Đọc/ghi file |
| `pipeline.py` | Ghép các giai đoạn | Chi tiết giao thức |
| `cli.py` | Tham số dòng lệnh, mã thoát, log | Nghiệp vụ |

Quan hệ phụ thuộc chỉ đi một chiều:

```text
cli ─► pipeline ─► auth, portals, storage, config
                       │           │
                       │           ├─► parsing, csrf, constants
                       │           └─► http ─► headers, traffic, proxy, constants
                       └─► captcha ─► http, headers, constants
config ─► proxy
```

`config` chỉ import `proxy` để kiểm tra chuỗi proxy lúc khởi động; `dates`,
`models`, `naming` là lá: chỉ dùng thư viện chuẩn và không import module nào ở
trên chúng.

## Năm giai đoạn của một lần chạy

```text
main()  (gdt_tax/cli.py)
  │  Settings.from_env()      đọc .env rồi tới biến môi trường, tham số dòng lệnh thắng
  │  create_solver()          nạp bộ nhận dạng CAPTCHA (nạp muộn, không kéo theo easyocr)
  ▼
Pipeline.run()  (gdt_tax/pipeline.py)
  │
  ├─ Giai đoạn 1  Settings.periods() + source_enabled() → đoạn chạy / đoạn bỏ qua
  ├─ Giai đoạn 2  DVC: login() + open_landing() nếu cần; legacy: login trì hoãn
  │
  ├─ Giai đoạn 3  với mỗi đoạn: portal.search(period, page) cho tới hết trang
  │                  portal lấy CAPTCHA → gọi endpoint tra cứu → parsing đọc bảng
  │
  ├─ Giai đoạn 4  với mỗi hồ sơ: portal.fetch_detail_csrf() → portal.download()
  │                  → storage.decode_zip_bytes() → ZipStore.save()
  │
  └─ Giai đoạn 5  classify_record() + write_metadata() → Excel/CSV/JSON + danh mục nhóm
```

**Vì sao tải ngay trong lúc phân trang?** Cổng chỉ giữ danh sách hồ sơ của trang
tra cứu gần nhất trong phiên. Nếu gom hết mã hồ sơ rồi mới tải, các trang trước
đó sẽ bị coi là không hợp lệ (`validateIdTkhai`). Vì vậy giai đoạn 3 và 4 lồng
vào nhau thay vì chạy tuần tự.

## Endpoint đang dùng

Các đường `/tthc/...` dưới đây thuộc adapter DVC/ETAX được giữ để phát triển
sau, không gọi khi `GDT_DVC_ENABLED=false`. Luồng mặc định chỉ dùng các dòng legacy.

| Nguồn | Việc | Gọi |
|---|---|---|
| chung | Mở trang đăng nhập | `GET /tthc/login` |
| chung | CAPTCHA đăng nhập | `GET /tthc/login/getCaptcha` |
| chung | Đăng nhập | `POST /tthc/loginLDAP` |
| chung | CAPTCHA tra cứu | `GET /tthc/getCaptcha` |
| chung | Trang hồ sơ | `GET /tthc/tchs` |
| chung | Trang chi tiết (lấy CSRF) | `GET /tthc/tchs/files/detail/{id}?loai=` |
| ETAX | Tra cứu | `POST /tthc/tchs/thuedientu` |
| ETAX | Tải ZIP | `POST /tthc/tchs/downloadhoso-tdt?loaiTraCuu=ETAX` |
| legacy | Đăng nhập trang cũ | `GET/POST thuedientu.gdt.gov.vn/etaxnnt/...` (EstablishSession → loginForm) |
| legacy | Tra cứu | `POST thuedientu.gdt.gov.vn/etaxnnt/Request` (`traCuuToKhaiProc/query`) |
| legacy | Tải XML | `GET thuedientu.gdt.gov.vn/etaxnnt/Request` (`downTkhai&messageId=...`) |
| DVC | Tra cứu | `GET /tthc/ho-so/search` |
| DVC | Kiểm tra trước khi tải | `GET /tthc/tchs/validateIdTkhai` |
| DVC | Tải ZIP | `POST /tthc/tchs/downloadhoso` |
| DVC | Dự phòng khi AJAX tắt | `POST /tthc/downloadhoso` |

Thứ tự cột của bảng kết quả nằm ở đầu `gdt_tax/parsing.py`.

## Một số điều đã kiểm chứng khi chạy thật

Các ghi chép DVC sau là lịch sử trước đợt sửa 27/09/2026; chưa xác minh lại
DVC ở đợt này. Test legacy mới và giới hạn suy luận được ghi ở REVIEW.

- **CAPTCHA chỉ thực sự bị kiểm ở bước đăng nhập.** Gửi CAPTCHA sai, thậm chí
  để rỗng, ở `GET /tthc/ho-so/search` vẫn nhận đủ kết quả của trang tra cứu.
  Vì vậy độ chính xác CAPTCHA chỉ đáng tối ưu cho `login()`; phần tra cứu chỉ
  cần gửi đúng tham số `captcha` là đủ.
- **Phải tải ngay trong lúc phân trang**, nếu gom hết mã hồ sơ rồi mới tải sẽ
  gặp lỗi `validateIdTkhai` (xem phần Năm giai đoạn).
- **Cổng có lúc trả `429`** khi tra cứu nhanh; `HttpClient` tự đọc `Retry-After`,
  còn `Pipeline._pause()` thêm jitter (chỉ cộng thêm) để nhịp không đều như máy.
- **Cổng chặn theo IP quốc gia.** Đo thật từ Đức: `GET /tthc/login` hỏng ngay ở
  tầng kết nối (`Max retries exceeded`); cùng request qua proxy Hà Nội trả `200`
  kèm thẻ CSRF. Đây là lý do proxy Việt Nam là bắt buộc khi chạy trên VPS nước ngoài.
- **Cổng không kiểm dấu vân tay trình duyệt** (chỉ 429 ở tầng ứng dụng + CAPTCHA ở
  bước đăng nhập), nhưng công cụ vẫn mặc định gửi header như Chrome. Phần không sửa
  được bằng header là HTTP/1.1 (không ALPN/HTTP2) và dấu vân tay TLS — xem mục
  *Không bị nhận diện là Python* trong README.

## Ghi log và lưu traffic

`http.py` là điểm duy nhất gọi mạng, nên mọi thứ cần quan sát đều nằm ở đó:

* mỗi request được log một dòng `INFO` (phương thức, URL, tham số, mã trạng thái,
  thời gian, dung lượng) — đây là thứ giúp đọc hiểu luồng khi cổng đổi;
* header, tham số và body được log ở mức `DEBUG` (``-v``, hoặc luôn có trong file
  khi dùng ``--log-file``);
* `--dump-http` gọi :class:`gdt_tax.traffic.TrafficDumper` để ghi nguyên
  request/response ra file, phục vụ dựng lại fixture.

`extra_headers` của `HttpClient` được gộp **sau** header mà portal đặt, nên
`--header`/`GDT_EXTRA_HEADERS` ghi đè được. Nhờ vậy khi cổng yêu cầu thêm một
header, có thể xử lý ngay lúc chạy; nếu thành yêu cầu lâu dài thì sửa
`gdt_tax/headers.py` cho đúng chỗ.

`traffic.py` cũng giữ quy tắc che dữ liệu nhạy cảm (`mask_headers`, `mask_data`,
`mask_secrets`) — thêm tên header hay trường mới cần che thì sửa hai hằng số ở đầu
module. Không module nào khác được tự ghi ra file log hay file dump.

## Proxy (chạy ở nước ngoài)

Cổng chỉ phục vụ IP Việt Nam, nên `Settings.proxy_url` (từ `--proxy` hoặc
`GDT_PROXY_URL`) được `proxy.parse_proxy()` đọc thành một `Proxy`, rồi truyền vào
`HttpClient`; `http.py` chỉ làm một việc là `kwargs.setdefault("proxies",
proxy.proxies())` cho **mọi** request, kể cả tải ZIP. Lỗi mạng được đổi thành
`NetworkError` đã che bí mật thay vì traceback của `urllib3`.

Hai điểm cần nhớ khi sửa:

1. `proxy.py` chỉ hiểu **chuỗi**, không biết gì về `requests` ngoài `proxies()`.
   Thêm nhà cung cấp hay dạng chuỗi mới thì sửa `parse_proxy` và bổ sung test
   trong `tests/test_proxy.py`.
2. **Mật khẩu proxy không bao giờ được lọt vào log.** `urllib3` in cả URL proxy
   kèm tài khoản khi lỗi, nên `configure_logging` gắn `SecretsFilter(secrets)` cho
   mọi handler. Solver CAPTCHA `remote` gọi dịch vụ ngoài vẫn đi trực tiếp, không
   qua proxy — cố ý, vì proxy chỉ dành cho cổng thuế.

## Header gửi đi (không bị nhận diện là Python)

`headers.py` là nơi duy nhất quyết định một request gửi header gì, theo hai profile
(`GDT_HEADER_PROFILE`): ``browser`` (mặc định) và ``minimal``.

Quan hệ giữa ba module, cần nhớ khi sửa:

```text
portals/* , auth.py , captcha/images.py
        │  chọn builder theo loại request (page / xhr / image)
        ▼
   headers.py       bộ header + client hint + thứ tự Chrome
        │
        ▼
   http.py          xoá header mặc định của Session, gộp header lúc chạy,
                    tính lại sec-ch-ua* theo User-Agent cuối cùng, sắp lại thứ tự
```

Hai cạm bẫy đã kiểm chứng và được ghi bằng test:

1. **Thứ tự phải sắp ở bộ cuối cùng**, trong `http.py`: `requests` gộp header của
   `Session` lên trước rồi mới tới header của request, nên sắp xếp trong builder là
   chưa đủ. Profile ``browser`` cũng xoá luôn header mặc định của `requests`
   (``python-requests/…``) — vừa là dấu hiệu lộ công cụ, vừa chèn lên trước.
2. **`Accept-Encoding` không được khai `zstd`**: urllib3 (tới 2.8) chỉ giải mã
   ``gzip``/``deflate``/``br``/``x-gzip``. `accept_encoding()` chỉ thêm ``br`` khi
   có ``brotli``, còn ``zstd`` thì không bao giờ thêm.

`sec-ch-ua*` luôn được tính từ ``User-Agent`` thực sự gửi đi
(`reconcile_client_hints`), nên ``--header "User-Agent=..."`` không tạo ra cặp giá
trị mâu thuẫn: hint được tính lại, hoặc bị bỏ hẳn nếu ``User-Agent`` không phải
Chrome.

## Mở rộng

Lộ trình inventory → phân loại file theo nội dung → parser theo mẫu/phiên bản
→ export và các prompt triển khai độc lập nằm ở
[development/README.md](development/README.md). `parsing.py` hiện chỉ đọc HTML,
không dùng làm module parse XML tờ khai trong các stage mới.

### Kiểm kê artifact và profile XML (stage 02)

`inventory.py` là công cụ **offline, chỉ đọc**: quét đệ quy một thư mục, liệt kê
mọi member trong ZIP, băm SHA-256, nhận diện định dạng từ bytes (không tin đuôi
file) và dựng profile cấu trúc cho từng XML. Chạy bằng
`python -m gdt_tax.inventory <folder> --output <dir>` (hoặc `gdt-inventory`).

Hai loại dấu vết cấu trúc:

* `structure_signature` — băm của root + namespace + mã mẫu + phiên bản + đường
dẫn phần tử (path), dùng để tham chiếu chi tiết một biến thể;
* `structure_skeleton` — băm của **tập tên phần tử** (không theo path), ổn định
hơn: hai XML cùng mẫu chỉ khác do có/không bảng tùy chọn vẫn cùng skeleton. Dùng
skeleton để phát hiện thay đổi cấu trúc thật và báo `MULTIPLE_STRUCTURES`.

Đầu ra: `manifest_artifact.json` (schema `artifact-inventory-v2`) và
`bao_cao_discovery.{json,md}` (schema/profile version, gợi ý nhóm thuế, mã
mẫu/phiên bản, trạng thái tiếp nhận từ metadata, điểm cần xác nhận, câu hỏi mở).
Cả hai chỉ chứa metadata/đường dẫn nguồn — **không** chứa chỉ tiêu thuế.

An toàn: giới hạn số member/bytes/tỉ lệ nén/tổng dung lượng, chặn Zip Slip/đường
dẫn tuyệt đối/drive Windows/`..`/symlink/ZIP mã hóa; XML dùng parser không resolve
entity/DTD, không gọi mạng, có trần bytes/depth/nodes. File lỗi được ghi riêng và
lượt quét tiếp tục. Chạy lại dùng cache theo `(rel_path, size, mtime)` nên không
băm lại toàn bộ khi file không đổi. **Không** đổi tên/di chuyển/xóa file nguồn.

Giới hạn hiện tại: chưa nối ZIP với hồ sơ khi tên file không khớp metadata; gợi ý
nhóm thuế chỉ từ tên mẫu (chưa phải mapping); chưa phân loại vai trò tài liệu theo
nội dung (stage 03).

### Khung parser tờ khai (stage 04)

`gdt_tax/parser/` tách **parsing engine** khỏi **form mapping**:

* `xml_reader.py` — parse XML an toàn (không resolve entity/DTD, không mạng, có
trần bytes), tìm text theo XPath (hỗ trợ cả XML không namespace), và chuẩn hóa số:
bỏ dấu phân cách nghìn, giữ dấu trừ, **phân biệt NULL với ``0``**; số lỗi trả
``PARSE_VALUE_ERROR`` thay vì 0.
* `registry.py` — nạp mapping đóng gói từ `gdt_tax/form_mappings/*.json`; tra theo
``(form_code, form_version)``. Không có bản khớp **version cụ thể** thì **không**
tự áp bản gần nhất (spec §45).
* `extract.py` — trích metadata chung (mã/tên/phiên bản mẫu, MST, kỳ, loại nộp,
lần bổ sung) và chỉ tiêu từ node `CTieuTKhaiChinh`. Chỉ lấy **chỉ tiêu tổng hợp**:
node con trực tiếp có tên dạng mã (`ct21`, `ctB12`…), đi xuống **một cấp** trong
các node nhóm, và **không** đi vào `PLuc`/bảng kê chi tiết.

Mỗi chỉ tiêu có ``code``, ``value`` (đã chuẩn hóa), ``raw_value``, ``xpath``
(provenance), ``canonical_name``/``display_name`` (từ mapping, ``None`` nếu chưa có),
và ``status`` (``MAPPED``/``NEED_MAPPING``). **Chưa có mapping thì trả
``NEED_MAPPING`` và ``canonical_name = None`` — không tự suy đoán ý nghĩa** (spec §3.1).

Chạy offline từ manifest: `python -m gdt_tax.parser.cli <folder> --output <dir>`
(hoặc `gdt-parse`). Kết quả `parsed_declarations.json` có schema/parser version và
giữ `source_zip`/`source_inner_file`/`source_sha256`/`artifact_id` để truy vết.

Đã đóng gói năm mapping:

* `gdt_tax/form_mappings/gtgt_842_01-gtgt.json` — 01/GTGT (mã 842), 27 chỉ tiêu `ct22`…`ct43`
(+`ct23a`/`ct24a`), tên theo TT80/2021/TT-BTC.
* `gdt_tax/form_mappings/tncn_864_05kk-tt80.json` — 05/KK-TNCN (mã 864), `ct16`…`ct32`, TT80/2021.
* `gdt_tax/form_mappings/tncn_394_05kk-tt92.json` — 05/KK-TNCN (mã 394), `ct21`…`ct36`, TT92/2015.
* `gdt_tax/form_mappings/tndn_892_03-tndn_v2.5.1.json` — 03/TNDN (mã 892),
  63 chỉ tiêu tờ khai chính theo TT80/2021.
* `gdt_tax/form_mappings/tndn_892_03-tndn_v2.9.4.json` — 03/TNDN (mã 892),
  65 trường; C7 là bộ thu nhập/tên thuế suất/thuế suất động.

Ba mapping GTGT/TNCN khai `form_version = null` vì XPath đã kiểm chứng resolve
trên các phiên bản hiện có. Hai mapping TNDN khai đúng version 2.5.1/2.9.4 và
không tự áp cho version chưa xác minh. **Hai bản TNCN là hai
mapping tách biệt theo `form_code`** vì mã chỉ tiêu `[21]`… trùng số nhưng khác ý
nghĩa giữa TT80 và TT92 (spec §45). Chỉ tiêu không có trong mapping (ví dụ `ct21`
của mẫu 842 — cờ "không phát sinh", `ct15` của 864) vẫn giữ ``NEED_MAPPING``;
mẫu/phiên bản khác chưa mapping cũng vậy. Khi mapping có XPath, extractor dùng
đúng XPath đó; nếu XML thiếu chỉ tiêu đã mapping thì giữ ``null`` kèm cảnh báo
``MISSING_IN_XML`` (không điền 0).

Mẫu **02/KK-TNCN (TT156/2013)** chưa có mapping vì thư mục hiện tại không có XML
nào của mẫu đó (không đủ dữ liệu để xác minh XPath).

Mẫu **03/TNDN** chỉ lấy `CTieuTKhaiChinh`; báo cáo tài chính và phụ lục trong
cùng hồ sơ không bị gán thành tờ khai chính. Chi tiết support matrix và nguồn
đối chiếu nằm trong `gdt_tax/form_mappings/README.md`.

### Phân loại theo nội dung (stage 03)

`classify.py` phân loại **từng artifact** từ profile XML (không chỉ metadata cấp
hồ sơ như `classification.py`): nhóm thuế, vai trò tài liệu (`DECLARATION`/
`NOTICE`/`APPENDIX`/`UNKNOWN`), mã mẫu, phiên bản. Ưu tiên mapping đã đăng ký
(bằng chứng mạnh); nếu không có thì dựa tên mẫu và ghi rõ là bằng chứng yếu.
Thiếu tín hiệu ⇒ `UNKNOWN`; mâu thuẫn ⇒ `CONFLICT` kèm bằng chứng hai phía.
Chạy `python -m gdt_tax.classify <folder>`; kết quả `phan_loai_artifact.json`.

### Xuất và truy vấn (stage 08)

`export.py` ghép manifest + parsed + classification thành các dòng tờ khai, giữ
provenance (`record_id` = SHA-256 của `source_sha256`+`artifact_id`, `source_zip`,
`source_inner_file`, `source_sha256`). Xuất workbook `Tax_Return_Summary.xlsx`
gồm `00_README`, `01_RETURN_INDEX`, `02_GTGT`, `03_TNCN`, `04_TNDN`,
`06_OTHER_RETURNS`, `05_INDICATORS` (chỉ tiêu dạng dài, kèm XPath), `07_UNMAPPED_FORMS`,
`08_PARSE_ERRORS`, `09_MAPPING_VERSIONS`, `10_AUDIT_LOG`. Lọc theo
nhóm/mẫu/phiên bản/kỳ/loại nộp/trạng thái qua CLI; xuất thêm CSV UTF-8 BOM.

Nguyên tắc: NULL (ô trống) khác `0`; **tiền âm giữ nguyên dạng số** (chỉ escape
chuỗi không phải số bắt đầu `=,+,-,@`); **không** tự chọn bản bổ sung mới nhất
hay cộng dồn nhiều lần nộp cùng kỳ — mọi dòng giữ nguyên, người dùng tự quyết.
Chạy `python -m gdt_tax.export <folder> [--tax-group GTGT ...]`.

### Bộ nhận dạng CAPTCHA có sẵn

| Tên | Lớp | Ghi chú |
|---|---|---|
| `ddddocr` | `DdddOcrSolver` | **Mặc định.** ONNX, huấn luyện riêng cho CAPTCHA chữ-số, cài ~131MB. Đo trên CAPTCHA đăng nhập thật: 6/6 đúng, 0,06s/ảnh |
| `easyocr` | `EasyOcrSolver` | 2/6 đúng, 3,14s/ảnh, cài ~555MB (chủ yếu là torch) |
| `paddleocr` | `PaddleOcrSolver` | 3/6 đúng, 0,60s/ảnh, cài ~304MB; tự nhận biết API 2.x (`.ocr()`) và 3.x (`.predict()`) |
| `manual` | `ManualSolver` | Lưu ảnh và hỏi người vận hành; dùng khi cổng đổi kiểu CAPTCHA |
| `remote` | `RemoteHttpSolver` | Gọi một endpoint HTTP bên ngoài, không gắn cứng nhà cung cấp |

Cách đo: đăng nhập một lần, sau đó với mỗi solver thực hiện 6 lần "lấy CAPTCHA
mới → đọc → gửi lên cổng", đếm số lần cổng trả `status = 200`. Cỡ mẫu nhỏ nên
coi là tín hiệu định hướng, không phải benchmark đầy đủ; muốn đánh giá lại thì
giữ nguyên quy trình này.

### Thêm bộ nhận dạng CAPTCHA mới

Viết một lớp kế thừa `CaptchaSolver` rồi đăng ký. Không cần sửa pipeline.

```python
# goi_cua_toi/solver.py
from gdt_tax.captcha import CaptchaSolver


class MyOcrSolver(CaptchaSolver):
    name = "myocr"

    def solve(self, image: bytes) -> str:
        return doc_ma_tu_anh(image)


# goi_cua_toi/__init__.py
from gdt_tax.captcha import register_solver

register_solver("myocr", "goi_cua_toi.solver:MyOcrSolver")
```

Hoặc đăng ký qua cấu hình, không cần sửa mã nguồn:

```dotenv
GDT_CAPTCHA_PLUGINS=myocr=goi_cua_toi.solver:MyOcrSolver
GDT_CAPTCHA_SOLVER=myocr
```

Bộ `remote` có sẵn để gọi một dịch vụ HTTP bên ngoài mà không gắn cứng nhà cung
cấp nào:

```dotenv
GDT_CAPTCHA_SOLVER=remote
GDT_CAPTCHA_OPTIONS={"url": "https://example.com/solve", "api_key": "...", "result_field": "data.text"}
```

`GDT_CAPTCHA_OPTIONS` được truyền thẳng thành tham số khởi tạo của lớp solver,
nên mọi solver đều cấu hình được mà không phải thêm biến môi trường mới.

### Thêm nguồn dữ liệu mới

1. Thêm endpoint vào `constants.py`.
2. Tạo lớp con của `Portal` trong `portals/`, cài `source`, `detail_loai`,
   `search()` và `download()`.
3. Đăng ký trong `PORTAL_CLASSES` ở `portals/__init__.py`.
4. Nếu bảng kết quả khác cột, bổ sung nhánh trong `parsing.parse_records`.
5. Thêm fixture HTML vào `tests/fixtures/` và test tương ứng.

### Đổi quy tắc ngày tháng

Mốc chuyển nguồn và số ngày tối đa là tham số của `dates.split_periods`, có thể
ghi đè bằng `GDT_ETAX_CUTOFF` và `GDT_MAX_DAYS_PER_SEARCH` mà không cần sửa code.
Nếu cổng thay đổi giới hạn, sửa `MAX_DAYS_PER_SEARCH_DEFAULT` trong `dates.py`.

## Kiểm thử

`tests/support.py` cung cấp `FakeHttp` định tuyến theo `(method, đường dẫn)`,
nên `test_pipeline.py` chạy nguyên luồng 5 giai đoạn mà không ra Internet. Khi
cổng đổi giao diện, cách nhanh nhất là cập nhật fixture trong `tests/fixtures/`
rồi chạy lại test để thấy chỗ nào vỡ.
