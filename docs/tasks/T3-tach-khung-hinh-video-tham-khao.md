# T3 - Tách khung hình từ video quay màn hình, mô tả luồng chuyển tiền

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-22. Minh đã duyệt.

## Mục đích

Minh quay màn hình một app ví khi đi qua luồng chuyển tiền. Tab kế hoạch cần biết bố cục từng màn để thiết kế một giao diện **ví mẫu** (không dùng logo, tên hay tài sản hình ảnh của app gốc) và chọn chỗ đặt phần cảnh báo. T3 chỉ thu thông tin, không dựng giao diện.

## Đầu vào

`/home/minhnv/Documents/CV/momo-techcontest/ref/momo_app.mp4` (720x1560, 30 fps, 113 giây, có tiếng). Thư mục `ref/` nằm ngoài repo.

## Việc làm

1. Tách khung hình bằng `ffmpeg`: mỗi màn khác nhau giữ một khung rõ nhất (không nhòe do đang chuyển cảnh), bỏ khung trùng. Lưu PNG gốc 720x1560 vào `ref/frames/`, tên `NN_mmss_<ten-ngan>.png` theo thứ tự thời gian. Màn cuộn dài thì giữ đủ các đoạn cuộn.
2. Một ảnh tổng hợp `ref/contact_sheet.png` (lưới các khung, có số thứ tự và mốc thời gian).
3. **Mở từng khung ra xem** rồi viết `ref/screens.md`. Với mỗi màn:
   - số thứ tự, mốc thời gian, tên file, màn đó là gì, từ màn trước bấm vào đâu để tới;
   - bố cục từ trên xuống: thanh tiêu đề, các ô nhập, nhãn, nút (chữ trên nút), bàn phím, thanh dưới;
   - nguyên văn các dòng chữ quan trọng: tiêu đề, nhãn ô, lời nhắc, cảnh báo, chữ trên nút;
   - màu chính lấy mẫu từ ảnh (mã hex): nền, nút chính, chữ, màu cảnh báo nếu có;
   - chỗ nào trên màn có thể chen một dòng hoặc một tấm cảnh báo mà không che thông tin giao dịch.
4. Cuối `ref/screens.md`, một bảng đối chiếu với danh sách màn cần có dưới đây: có / thiếu / có nhưng mờ. Với màn thiếu, ghi cụ thể Minh cần bấm vào đâu để quay hoặc chụp bổ sung.

Danh sách màn cần có:

- trang chủ, và lối vào chuyển tiền;
- màn chọn kiểu chuyển (tới ví, tới ngân hàng, quét QR);
- nhập số tài khoản ngân hàng, lúc tên chủ tài khoản hiện ra;
- quét mã QR, và màn sau khi quét;
- chọn người nhận đã lưu hoặc đã từng chuyển;
- nhập số tiền và lời nhắn;
- màn xác nhận trước khi nhập mật khẩu;
- bất kỳ nhãn, dòng cảnh báo hay tấm thông báo nào về người nhận (xanh, vàng, đỏ, "lần đầu chuyển"...);
- lối vào trợ lý hoặc chat hỗ trợ trong app, nếu video có.

## Giao lại

- `ref/frames/`, `ref/contact_sheet.png`, `ref/screens.md`.
- Tóm tắt ngắn ở terminal: số màn tách được, luồng nào đủ, màn nào thiếu, và có thấy nhãn cảnh báo người nhận nào trong video không.

## Không làm

- Không chép gì từ `ref/` vào repo, không commit ảnh, không đưa ảnh lên bất kỳ dịch vụ nào ngoài model đang dùng để xem ảnh.
- Video có số dư, tên, số tài khoản thật của Minh: không ghi các giá trị đó vào `screens.md`, thay bằng `<số dư>`, `<tên>`, `<số tài khoản>`.
- Không dựng HTML/CSS, không sửa app. Chỉ T3.
