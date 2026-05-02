# ToolSmooth 📘

Công cụ làm mượt (rewriting) truyện văn học mạng sử dụng AI Gemini.

## Tính năng chính
- **Làm mượt văn bản**: Sử dụng mô hình Gemini để biên tập lại các bản dịch thô, giúp văn phong sinh động và hấp dẫn hơn.
- **Giao diện thân thiện**: Tích hợp thanh tìm kiếm, quản lý danh sách truyện trực quan.
- **Xử lý đa luồng**: Hỗ trợ nhiều worker xử lý song song để tăng tốc độ.
- **Quản lý API Key**: Cơ chế tự động xoay vòng nhiều API Key để tránh giới hạn băng thông.
- **Tùy biến phong cách**: Cho phép chọn các bộ quy tắc (rules) khác nhau cho từng thể loại truyện.

## Cấu trúc dự án
- `main.py`: File thực thi chính của ứng dụng.
- `smooth/`: Chứa logic cốt lõi xử lý văn bản.
- `core/`: Giao diện người dùng và các tiện ích hệ thống.
- `gemini/`: Quản lý kết nối và API Key Gemini.
- `rules/`: Chứa các file cấu hình phong cách biên tập.

## Yêu cầu hệ thống
- Python 3.10+
- Các thư viện: `customtkinter`, `google-generativeai`, `python-dotenv`, `python-docx`, `json5`, `json_repair`.

## Cài đặt
1. Clone repository:
   ```bash
   git clone https://github.com/arata1592003/ToolSmooth.git
   ```
2. Cài đặt thư viện:
   ```bash
   pip install -r requirements.txt
   ```
3. Cấu hình file `.env` với các API Key Gemini của bạn.

## Cách sử dụng
Chạy lệnh sau để bắt đầu:
```bash
python main.py
```
