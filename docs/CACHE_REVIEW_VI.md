# Đánh giá cache và hướng xử lý

## Mục tiêu
Tóm tắt các vấn đề cache hiện tại và đề xuất hướng cải thiện an toàn, ưu tiên tính đúng đắn
trước khi tối ưu hiệu năng. Tài liệu này chỉ mô tả quyết định, chưa thay đổi mã nguồn.

## Phát hiện & đề xuất
1. **Xung đột cache giữa `head` và `cat`**  
   Cache content đang khóa theo đường dẫn nên kết quả `head` có thể “đè” lên `cat` hoặc
   `head` với số dòng khác. Đề xuất tách key theo loại thao tác và tham số (ví dụ `head:lines`)
   hoặc chỉ cache nội dung đầy đủ rồi cắt khi trả `head` (chỉ khi file nhỏ).

2. **Search cache cho thư mục dễ bị stale**  
   Trạng thái thư mục chỉ dựa vào metadata của thư mục nên chỉnh sửa nội dung file không làm
   vô hiệu cache `grep`. Đề xuất ghi nhận trạng thái theo từng file trong scope (mtime/size/hash)
   và tạo “dấu vân tay” tổng hợp; nếu scope quá lớn, dùng ngưỡng giới hạn + TTL ngắn.

3. **TTL cấu hình chưa được áp dụng**  
   `cache_search_ttl` và `cache_content_ttl` tồn tại trong cấu hình nhưng chưa điều khiển
   thời gian hết hạn thực tế. Đề xuất dùng các giá trị này để set expire; `0` nghĩa là không
   hết hạn (chỉ invalidation theo thay đổi file).

4. **invalidate_directory dùng so khớp prefix chuỗi**  
   So khớp chuỗi có thể xóa nhầm các đường dẫn cùng tiền tố. Đề xuất kiểm tra theo ranh giới
   path (segment) bằng `Path.is_relative_to()` hoặc so khớp với `os.sep`.

## Trả lời câu hỏi
- **`head` nên bỏ cache hay cache đầy đủ rồi cắt?**  
  Khuyến nghị: không dùng chung cache với `cat`. Với file nhỏ (<= `max_file_size`), có thể
  cache nội dung đầy đủ và cắt khi trả `head`. Với file lớn, nên bỏ cache `head` để tránh
  tải toàn bộ file.

- **Invalidation search: theo file hay watcher?**  
  Khuyến nghị: theo file là lựa chọn chính xác và đơn giản để triển khai; có thể bổ sung
  watcher (watchdog) như một tối ưu tùy chọn khi chạy lâu dài hoặc dữ liệu lớn.

- **TTL có nên áp dụng hay bỏ?**  
  Khuyến nghị: áp dụng TTL đúng theo cấu hình để người dùng kiểm soát hành vi cache;
  giữ `0` là không hết hạn.

- **invalidate_directory theo prefix có chấp nhận?**  
  Không nên. Cần ràng buộc theo ranh giới path để tránh invalidation sai.
