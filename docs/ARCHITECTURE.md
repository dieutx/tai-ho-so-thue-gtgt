# Kiến trúc

Tài liệu này dành cho người đọc mã nguồn hoặc muốn mở rộng công cụ. Mục tiêu là
mỗi module chỉ có một trách nhiệm, và mọi phần dễ đổi (CAPTCHA, nguồn dữ liệu,
quy tắc ngày tháng) đều tách riêng để thay mà không ảnh hưởng phần còn lại.

Trạng thái triển khai, test thật và quy trình chuyển máy ở
[HANDOFF](development/HANDOFF.md); backlog và giới hạn ở
[REVIEW](development/REVIEW.md). Phân loại hiện chỉ ở metadata cấp hồ sơ,
chưa có artifact inventory hoặc parser chỉ tiêu XML.

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
| `storage.py` | Kiểm tra ZIP, chống tải trùng, ghi ZIP, CSV/JSON | Gọi mạng |
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
  └─ Giai đoạn 5  classify_record() + write_metadata() → CSV/JSON + danh mục nhóm
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
