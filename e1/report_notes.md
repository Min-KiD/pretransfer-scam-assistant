## 10. Nhận xét

{{INTERPRETATION}}

## 11. Cách làm và các điểm lệch so với đề bài

- **Ba cách đọc.** A: PaddleOCR 3.7.0, `lang="vi"`, `ocr_version="PP-OCRv6"` (det `PP-OCRv6_medium_det`, rec `PP-OCRv6_medium_rec`; đây là họ mới nhất trong bản 3.7 có tiếng Việt), rồi regex trong `e1/extract.py`. B: Gemini chỉ nhận ảnh, structured output theo schema trong `e1/vlm.py`. C: cùng lời gọi B, thêm toàn bộ dòng chữ OCR của A vào prompt; code so chuỗi C với chuỗi A sau chuẩn hóa, lệch thì gắn `khong_chac`.
- **Ba model Gemini**, cùng schema, nhiệt độ và mức suy nghĩ mặc định: `gemini-3.5-flash-lite` (flash rẻ nhất), `gemini-3.8-flash` (thêm theo yêu cầu tab kế hoạch), `gemini-4-carbon` (model mạnh nhất key gọi được, theo trang latest-model của Google ngày 2026-11-20). Theo tab kế hoạch, các thí nghiệm sau E1 không dùng dòng gemini-4 nữa.
- **OCR chạy trên CPU, không phải GPU.** Lần cài `paddlepaddle-gpu==3.3.1` từ `paddle-whl.cdn.bcebos.com` (index cu126 chính thức) hết 30 phút mà chưa xong: CDN chỉ trả khoảng 2 MB/s và liên tục `ReadTimeoutError`. Đã dừng đúng hạn và xóa cache. Lần thứ hai cài `paddlepaddle==3.3.1` (CPU) + `paddleocr==3.7.0` từ PyPI, xong trong khoảng 9 phút. Không tìm thấy env nào khác trên server đã có paddle (`~/vidoc-dev` chỉ có rapidocr và mineru), nên không dùng lại env nào.
- **Tắt oneDNN** (`enable_mkldnn=False`): paddle 3.3.1 CPU bật oneDNN thì PP-OCRv6 lỗi `ConvertPirAttribute2RuntimeAttribute not support`. Hệ quả: OCR chậm (xem bảng 7). Thời gian của A trong báo cáo là CPU 12 nhân, đang chạy chung với các lượt gọi API, nên không đại diện cho GPU.
- **paddle ghi vào `~/.cache/paddle` và `~/.paddlex`** bất kể biến `PADDLE_PDX_CACHE_HOME`. Hai thư mục rỗng do lần thử đầu tạo ra đã được xóa. Từ đó mọi tiến trình paddle chạy với `HOME=<dự án>/.cache/home`, nên không ghi gì ra ngoài thư mục dự án.
- **Lỗi dữ liệu đã sửa giữa chừng:** bản sinh đầu để vài link dài tràn ra ngoài mép màn hình, tức đáp án có ký tự không nhìn thấy. Bộ sinh giờ loại mọi chuỗi không nằm gọn trong bong bóng. 13/30 ảnh gốc (78 ảnh) được sinh lại, và kết quả API của các ảnh đó đã được gọi lại.
- **Giới hạn:** ảnh tổng hợp từ HTML, chưa phải ảnh chụp thật. Font là Noto Sans / Arial, nơi `I` và `l` gần như trùng nét. Mỗi ô biến thể × loại chỉ có khoảng 30 chuỗi, nên một lỗi bằng khoảng 3,3 điểm %. Số và tên đều sinh ngẫu nhiên, không đối chiếu với số thật nên không loại trừ tuyệt đối khả năng trùng.
