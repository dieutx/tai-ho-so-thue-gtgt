# XML policy và namespace

CORE-07/12: `gdt_tax.xml_policy` là reader chung cho inventory và parser. Trần
32 MiB, depth 100 (root tính là 1) và 200.000 element nodes được thực thi;
DOCTYPE chỉ định schema ngoài được giữ để đọc XML lịch sử, nhưng không nạp
DTD, resolve entity hoặc gọi mạng. Mọi khai báo/tham chiếu ENTITY đều bị từ
chối, kể cả XML UTF-16. Lỗi chỉ ghi mã policy,
không lặp lại XML có thể chứa dữ liệu người nộp thuế.

Namespace được chọn theo URI của element, hỗ trợ prefix tương đương default
namespace. Extractor chọn một declaration chính và `TTinChung`, loại phụ lục
khỏi việc tìm metadata/chỉ tiêu. Hai declaration chính trả lỗi ambiguous;
không tự chọn hồ sơ đầu tiên. Wrapper được hỗ trợ khi có một payload rõ ràng.

Inventory profile và parser algorithm version được tăng để phân biệt kết quả
được tạo trước/sau thay đổi. Phiên bản desktop/release không thay đổi.

Validator file tải sẽ dùng cùng policy trong PR CORE-13; XML syntax/resource
validation không chứng minh tính đúng của chữ ký, chỉ tiêu hoặc acceptance.
