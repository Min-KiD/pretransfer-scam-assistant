# Đề xuất: lớp hỏi lại khi câu trả lời chưa dùng được

Ngày: 2026-11-23. Trạng thái: **đề xuất, Minh chưa duyệt.** Chưa có code, chưa có số đo.

## Bối cảnh

Hướng đã chốt ngày 23/11 cho phần hỏi đáp:

- Model tự hỏi và tự kết luận (kiểu `tu_do` của E2: đúng kịch bản 78,7% so với 69,3% của cách code chọn câu hỏi, trên 75 phiên).
- Ba việc do code giữ:
  1. Giới hạn cứng: tối đa 3 câu hỏi, đầu ra ép theo JSON schema (chỉ chọn được mã kịch bản hợp lệ hoặc `chua_du_can_cu`).
  2. Các phép so chính xác: số tài khoản trong ảnh với số đang chuyển, tra nhãn tài khoản.
  3. Lớp soát M3 (bộ phân loại C0): không đồng ý với model thì hạ kết luận xuống `chua_du_can_cu`.

Chỗ còn hở: hiện mọi câu hỏi đều tính vào 3 câu, kể cả khi người dùng trả lời lạc đề hoặc hiểu nhầm câu hỏi. Model được
hỏi lại nhưng mất một lượt. Người dùng thật sẽ lạc đề nhiều hơn nạn nhân giả lập (trong E5 nạn nhân giả lập không lạc đề
lần nào; 22-31% câu trả lời của nó có "không biết / không rõ / không nhớ").

## Đề xuất

Mỗi lượt, ngoài `du_doan` và `cau_hoi`, model trả thêm một trường đánh giá câu trả lời vừa nhận:

| `tra_loi_truoc` | Nghĩa | Code làm gì |
|---|---|---|
| `dung_duoc` | Trả lời đúng câu hỏi | Tính một câu, đi tiếp |
| `khong_biet` | Người dùng nói không biết, không nhớ | Tính một câu, **không** hỏi lại câu đó; model hỏi sang ý khác |
| `lac_de` | Trả lời chuyện khác, hoặc hiểu nhầm câu hỏi | Cho hỏi lại **một lần không tính**, câu hỏi lại phải ngắn hơn và kèm nút chọn nhanh |
| `mau_thuan` | Trái với điều đã kể hoặc với ảnh | Một câu xác nhận không tính (app đã có sẵn cho trường hợp số tài khoản lệch một ký tự) |

Giới hạn do code giữ, model không tự nới được:

- Mỗi câu hỏi chỉ được hỏi lại một lần. Cả phiên tối đa 2 lượt không tính, tức trần cứng 5 lượt hỏi.
- Hết lượt mà chưa rõ thì kết luận `chua_du_can_cu`, kèm lời nhắc kiểm tra chung. Không đoán.
- Câu hỏi lại luôn có nút chọn nhanh (2-4 lựa chọn và "Không rõ"), để giảm hiểu nhầm lần hai.

Lý do không cho hỏi lại khi `khong_biet`: hỏi lại không tạo ra thông tin mới, chỉ làm người đang vội chuyển tiền bỏ qua.

## Cách đo trước khi giữ

Bộ giả lập hiện tại không đo được lớp này, vì nạn nhân giả lập luôn trả lời đúng câu hỏi. Cần thêm:

- Ba kiểu người dùng mới trong `sim/cases.py`: trả lời lạc đề, hiểu nhầm câu hỏi, trả lời cụt một hai chữ.
- So hai nhánh trên cùng tập tình huống: có lớp hỏi lại và không có.
- Số đo: đúng kịch bản, lừa đảo bị coi là bình thường, tỉ lệ `chua_du_can_cu`, số lượt hỏi trung bình.
- Điều kiện giữ (khai trước): trên các tình huống có người dùng kiểu mới, đúng kịch bản tăng ít nhất 5 điểm, và số lượt hỏi
  trung bình trên các tình huống cũ không tăng quá 0,3.

## Chưa quyết

- Trần lượt không tính: 2 (đề xuất) hay 1.
- Trường `tra_loi_truoc` do chính model hội thoại trả (một lần gọi), hay một lần gọi riêng (dễ soát hơn, tốn thêm một lần gọi).
- Nút chọn nhanh do model sinh, hay lấy từ danh sách lựa chọn viết sẵn theo từng kịch bản.
