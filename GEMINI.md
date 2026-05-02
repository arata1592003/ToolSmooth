# Hướng dẫn Phát triển ToolSmooth

Tài liệu này dành cho các AI agent và lập trình viên tham gia phát triển dự án.

## Kiến trúc Hệ thống
Hệ thống tuân theo mô hình tập trung vào việc xử lý văn bản bằng AI (Gemini).

### Quy ước và Tiêu chuẩn
- **Giao diện**: Sử dụng `customtkinter`. Các widget danh sách phải được tối ưu hóa để tránh lag (sử dụng debounce cho tìm kiếm, cache danh sách folder).
- **Xử lý Văn bản**: 
  - Luôn chia nhỏ văn bản thành các phần (part) nếu độ dài vượt quá giới hạn token của AI (mặc định 1000 chữ/phần).
  - Sử dụng `response_schema` để đảm bảo AI trả về định dạng JSON hợp lệ.
  - Kiểm tra tỉ lệ độ dài giữa bản gốc và bản edit (ngưỡng 0.8 - 1.3).
- **Quản lý API**:
  - Không bao giờ lưu API Key trực tiếp vào mã nguồn. Sử dụng `.env` hoặc `keys.txt`.
  - Luôn thực hiện cơ chế xoay vòng Key để tối ưu hóa hạn ngạch API.

### Workflow Chỉnh sửa
- Sử dụng công cụ `replace` để thực hiện các thay đổi "phẫu thuật", không ghi đè toàn bộ file trừ khi thực sự cần thiết.
- Luôn kiểm tra tính tương thích của UI trên nhiều kích thước văn bản khác nhau (đặc biệt là tên file dài).

### Lưu ý quan trọng
- Thư mục đầu vào và đầu ra mặc định nằm ở cấp cha của thư mục dự án: `../output/translate` và `../output/smooth`.
- Không commit các file nhạy cảm như `.env`, `keys.txt`, và các thư mục log lỗi (`error/`).
