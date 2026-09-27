# Stage 02 — Inventory file và manifest

Áp dụng master prompt. Phụ thuộc stage 01. Mục tiêu: tra được mỗi file gốc và
mỗi member trong ZIP thuộc hồ sơ nào, không cần login để xem/kiểm kê lại.

Thiết kế CaseIdentity và Artifact riêng. Một Case có nhiều Artifact; một ZIP
là container, không mặc định là một tờ khai. Trường tối thiểu: artifact id,
case identity, parent/container id, tên member gốc, format phát hiện từ bytes,
byte size, SHA-256, storage reference, inventory status/error và schema version.
Không sửa bytes raw chỉ để thuận tiện parser. Hỗ trợ XML legacy trong ZIP và
ZIP trực tiếp từ adapter DVC được bật rõ ràng.

Triển khai inventory đọc từ file đã tải, kèm CLI offline độc lập; không cần
GDT_USERNAME/PASSWORD, solver OCR hay HTTP client. Dò XML/PDF/ZIP/unknown bằng
chữ ký/nội dung giới hạn, không tin đuôi file hay MIME. Tên trùng nhau trong
ZIP vẫn có identity không đè nhau; giữ đường dẫn/tên gốc trong manifest.

Giới hạn số member, bytes mỗi file, tổng bytes giải nén, compression ratio,
depth container. Tránh Zip Slip, đường dẫn tuyệt đối, drive Windows, `..`,
symlink, archive mã hóa hoặc thuật toán không hỗ trợ. Nếu chưa cần extract,
đọc member có giới hạn trực tiếp và giữ storage reference container+member.
Không extract all vào thư mục raw bằng tên không kiểm chứng.

Migration: đọc ZIP/metadata cũ, tạo manifest không di chuyển/xóa dữ liệu gốc.
Không gán file mơ hồ cho case chỉ bằng chuỗi con của tên. Ghi lỗi riêng cho
artifact hỏng, vẫn inventory được các artifact khác. Re-run cùng bytes không
tạo trùng; metadata/hash/version cập nhật có kiểm soát.

Test: nhiều XML/PDF/phụ lục trong ZIP, tên trùng, file sai đuôi, ZIP hỏng,
path traversal, bomb giới hạn thấp, encrypted, XML standalone, re-run và
migration metadata thiếu field. Giao schema manifest, module inventory,
lệnh offline, fixture synthetic/ẩn danh và tài liệu giới hạn.
