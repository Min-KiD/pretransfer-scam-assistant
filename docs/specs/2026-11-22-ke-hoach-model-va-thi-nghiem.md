# Kế hoạch model và thí nghiệm (22/11/2026)

Người viết: tab `Momo_TechContest`. Trạng thái: Minh đã duyệt hướng; chưa quyết giữ hay bỏ model nào. Tài liệu này nói sẽ đo gì để quyết. Bản thiết kế sản phẩm sẽ viết lại sau khi có số.

## 1. Sản phẩm, tóm tắt

Người dùng bấm chuyển tiền. App làm hai tầng:

- **Tầng 1, nhãn lúc xác nhận:** bình thường / vàng / đỏ, từ nhãn tài khoản nhận (dữ liệu mẫu) và vài quy tắc. Đây là đầu vào có sẵn, không phải phần mình đo.
- **Tầng 2, sau khi nhãn hiện ra:** người dùng trả lời một câu hỏi có nút bấm, có thể gửi ảnh chụp tin nhắn và chat thêm. Trợ lý so lời kể và ảnh với thư viện 15 kịch bản, nói tình huống giống chiêu nào, bước kẻ gian thường làm tiếp, và nên kiểm tra gì. Người dùng tự quyết: không chuyển nữa, hỏi thêm, nhờ nhân viên, hoặc vẫn chuyển. Mỗi lựa chọn sinh một báo cáo cho nhân viên.

## 2. Quyết định đã có (Minh, 22/11)

1. Bản demo không gọi API model đóng. Model đóng chỉ là mốc so sánh trong thí nghiệm, và là đường lùi nếu model của mình không kịp.
2. Muốn có model tự train để thể hiện kỹ thuật. Chạy đủ số liệu trước, quyết giữ hay bỏ sau.
3. Mốc so sánh không chỉ Gemini: thêm GPT và Claude khi có key.
4. Train và thí nghiệm chạy trên server công ty (RTX 4060 Ti 16GB). Host demo tính sau.

## 3. Bốn chỗ đặt model

| Mã | Model | Việc | Train bằng | Chấm trên | Thí nghiệm |
|---|---|---|---|---|---|
| M1 | VLM mở + LoRA, kèm PP-OCRv6 soát | Ảnh chat ra JSON: tin nhắn, ai nói, số tài khoản, số điện thoại, link, số tiền | Ảnh dựng từ HTML, đáp án biết trước | Ảnh chat thật đã đăng công khai | E4 |
| M2 | LLM mở cho hội thoại (cùng model gốc với M1 nếu được) | Hỏi thêm, chọn kịch bản, viết lời cảnh báo | Chưa train. Distill chỉ khi E5 cho thấy cần | 300 phiên giả lập | E5 |
| M3 | Bộ phân loại chữ nhỏ, chạy CPU | Ý kiến thứ hai về kịch bản, có xác suất | Lời kể giả lập, nhãn do mình đặt | Phiên giả lập giữ riêng + lời kể từ vụ việc thật | E6 |
| M4 | Lan nhãn trên đồ thị tài khoản | Báo cáo đã duyệt lan sang tài khoản dính với nó | Dữ liệu mẫu | Không có số đo có nghĩa; chỉ chứng minh cơ chế | E7, làm cuối, cắt đầu tiên |

## 4. Quy tắc dữ liệu

- **Model đóng được làm thầy** (Minh quyết 22/11, thay cho quy tắc cũ "model sinh không train trên đầu ra model đóng"). Lý do của Minh: đây là bài thi, mục đích là trình bày quy trình, không đưa model ra dùng thật. Điều khoản của OpenAI, Anthropic và Google cấm dùng đầu ra để phát triển model cạnh tranh (đã đọc Gemini API Additional Terms ngày 22/11; hai hãng kia qua bài tổng hợp của infro.io 21/10/2026); Minh đã biết và chấp nhận. README của bài nộp khai rõ dữ liệu train nào do model nào sinh, vì thể lệ yêu cầu khai công cụ AI đã dùng.
- **Việc được làm ngay:** lời thoại trong ảnh train (E4) và lời kể train của bộ phân loại (E6) viết bằng `gemini-3.5-flash-lite`.
- **Việc phải hỏi Minh trước, kèm ước tính chi phí:** distill hội thoại từ model đóng (sau khi có số E5); sinh thêm ảnh bằng model sinh ảnh để đưa vào tập train.
- **Bộ `gen` và `gen_ref` hiện có là bộ chấm**, không vào tập train. Muốn train trên ảnh sinh thì sinh bộ riêng.
- **Ảnh và lời kể thật** (`data/E1b/real`, `data/narr/real`) chỉ dùng để chấm, không train, không commit, không đưa ảnh vào report.
- **Tập thật chia đôi cố định:** mã số lẻ là `dev`, mã số chẵn là `test`. Chỉ được mở lỗi của `dev` ra xem để sửa prompt, bộ sinh hay cách train. `test` chỉ chấm, không xem từng lỗi cho tới khi chốt.

## 5. Điều kiện giữ hay bỏ, khai trước khi có số

| Model | Giữ nếu | Không đạt thì |
|---|---|---|
| M1 | Trên `web-test`: tỉ lệ khớp chung thua `gemini-3.5-flash-lite` không quá 5 điểm, tỉ lệ chuỗi bịa không cao hơn quá 2 điểm, và p50 không quá 2 giây mỗi ảnh trên 4060 Ti | Ghi là kết quả âm; demo dùng cách đọc tốt nhất còn lại |
| M2 | Model mở chưa train thua `gemini-3.5-flash-lite` không quá 5 điểm về đúng kịch bản sau 3 câu, và báo nhầm giao dịch bình thường không cao hơn quá 5 điểm | Minh quyết có distill không |
| M3 | Lúc M3 lệch với LLM, bắt được ít nhất 30% kết luận sai của LLM và chỉ gắn cờ nhầm không quá 15% kết luận đúng | Bỏ lớp soát |

Mỗi con số là của một lần chạy đã khai trước, không chạy lại để chọn số đẹp. Mọi tỉ lệ ghi kèm tử số, mẫu số và khoảng tin cậy Wilson 95%.

## 6. Thứ tự chạy

1. E4 Phần 0: tải weights về server, chạy nền.
2. E5 phần model đóng (không cần GPU), song song với bước 1.
3. E4 giai đoạn A: mốc so sánh trên các bộ ảnh hiện có.
4. E4 giai đoạn B: bộ sinh ảnh mới, train LoRA, chấm.
5. E5 phần model mở.
6. E6.
7. E7 nếu tới 29/11 mà 1-6 đã xong.

Đề bài: `docs/tasks/E4-vlm-doc-anh-ra-json.md`, `docs/tasks/E5-model-hoi-thoai.md`, `docs/tasks/E6-bo-phan-loai-kich-ban.md`.

## 7. Trần chi phí API

Minh, 22/11: dùng API ít thôi, chỉ gọi khi thật sự cần, không chắc thì hỏi lại.

- Gemini: trần 20 USD cho cả E4, E5, E6 và ảnh sinh. Chạm trần thì dừng và báo.
- `gemini-3.5-flash-lite` (rẻ) chạy trên mọi bộ. `gemini-3.8-flash` và `gemini-4-carbon` chỉ chạy trên bộ nhỏ sát thực tế: E4 trên `web` và `gen`; E5 trên 75 tình huống `v1`.
- GPT, Claude: mỗi hãng một model tầm trung, E4 chỉ trên `web`, E5 chỉ trên `v1`. Trần 3 USD mỗi hãng. Key đọc từ `OPENAI_API_KEY` và `CLAUDE_API_KEY` (nhận cả `ANTHROPIC_API_KEY`) trong `.env`. Ngày 22/11 cả hai key hợp lệ nhưng tài khoản chưa có tiền: gọi thử một lần, lỗi hết tiền thì bỏ qua và ghi vào report.
- Muốn chạy rộng hơn các giới hạn trên (thêm model, thêm bộ, chạy lại): dừng, báo tab kế hoạch để hỏi Minh.
- `.env` có một dòng không có dấu `=` (dòng 4). Đọc `.env` bằng cách bỏ qua dòng hỏng; đừng `source` thẳng file này trong shell.

## 8. Việc của tab kế hoạch, làm song song

- Thu thêm ảnh chat lừa đảo thật: mục tiêu khoảng 100 ảnh mới vào `data/E1b/real/` (mã `web_021` trở đi), có đáp án và nguồn.
- Thu lời kể từ vụ việc thật: mục tiêu khoảng 90 vụ vào `data/narr/real/`.
- Soát đáp án của các ảnh mới trước khi báo tab `code` là bộ đã sẵn.
