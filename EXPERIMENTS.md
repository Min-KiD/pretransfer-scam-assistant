# Thí nghiệm

Ghi ngắn gọn từng thí nghiệm: hỏi gì, dữ liệu nào, cấu hình nào, kết quả, quyết định kéo theo. Báo cáo chi tiết nằm ở `experiments/<mã>/report.md`.

Mọi số đo ở đây là trên dữ liệu tự dựng. Chúng dùng để chọn cách làm, không phải để khẳng định chất lượng trên dữ liệu thật.

## Tổng quan

| Mã | Câu hỏi | Trạng thái | Kết quả chính |
|---|---|---|---|
| E1 | Đọc chuỗi từ ảnh chat: có cần OCR riêng bên cạnh VLM không | Xong với Gemini (3 cách x 3 model); phải chạy lại với model Bedrock | Số tài khoản, số điện thoại, số tiền: đạt 100% ở mọi cách trừ model rẻ nhất khi không có OCR. Link: 66-93%, gần hết lỗi là nhầm `I` với `l`, OCR không sửa được |
| E1b | Model mở trên GPU 16GB có thay được Gemini không; OCR nào hơn PP-OCRv6; ảnh khó hơn thì cách nào gãy | Xong (4 bộ ảnh: E1, khó, gen, web) | Đọc chữ: GLM-OCR và PP-OCRv6 GPU đủ dùng (PP-OCRv6 0,3 giây/ảnh). Không model mở nào trả JSON dùng được. Trên 20 ảnh chat thật: Gemini flash-lite 83,7%, model mở 51-61%, phần lớn do regex trích chuỗi bỏ sót chứ không phải OCR đọc sai |
| E2 | Chọn câu hỏi bằng tính toán có hơn để model tự hỏi không | Lần 2 xong (75 tình huống chữ, sau khi sửa điền bảng); lần 1 giữ ở `experiments/E2/run1/` | Sau 3 câu: tính toán 69,3% đúng kịch bản (lần 1: 71,4%), model tự hỏi 78,7% (lần 1: 75,7%). Kém 9,3 điểm, không đạt ngưỡng hơn 5 điểm: đề xuất bỏ phần chọn câu hỏi, giữ bảng câu chuyện. Biến thể hỏi ít nhất 1 câu cũng 69,3% |
| E3 | Tỉ lệ báo nhầm giao dịch bình thường | Lần 2 xong (20 tình huống bình thường) | Tính toán 25% (5/20; lần 1: 10%), hỏi ít nhất 1 câu 10%, model tự hỏi 5% (1/20); trần với người trả lời hoàn hảo 6,2% |
| E4 | Model mở (VLM + LoRA) đọc ảnh chat ra JSON có thay được Gemini không | Đang chạy (giai đoạn A) | |
| E5 | Model mở cho hội thoại so với các model đóng | Đang chạy | |
| E6 | Bộ phân loại kịch bản nhỏ làm ý kiến thứ hai | Chưa làm | |
| E8 | Người dùng bị kẻ gian dặn trước câu trả lời (trước đây mang mã E4) | Chưa làm | |
| E9 | Thời gian và chi phí mỗi phiên (trước đây mang mã E5) | Chưa làm | |

## E1 - Đọc chuỗi chính xác từ ảnh chụp chat

Ngày: 2026-11-20. Đề bài: `docs/tasks/E1-doc-anh-chat.md`. Báo cáo: `experiments/E1/report.md`.

### Dữ liệu

- 30 ảnh chat gốc, dựng từ mẫu HTML rồi chụp bằng Playwright: 3 kiểu giao diện (giống Zalo, Messenger, SMS) x 5 tình huống x 2.
- Mỗi ảnh gốc có 6 biến thể: gốc, chế độ tối, cắt mép trên, JPEG chất lượng 40, thu nhỏ 50%, mờ nhẹ. Tổng 180 ảnh, 756 chuỗi cần đọc.
- Bốn loại chuỗi: số tài khoản, số điện thoại, link, số tiền. Tất cả tự sinh ngẫu nhiên. Link cố ý có ký tự dễ nhầm (`I`, `l`, `1`, `0`, `O`).

### Cấu hình

| Cách | Mô tả |
|---|---|
| A | PaddleOCR 3.7.0, PP-OCRv6 tiếng Việt, chạy CPU, rồi regex |
| B | Chỉ VLM, structured output, nhiệt độ và mức suy nghĩ mặc định |
| C | Như B, thêm toàn bộ chữ OCR của A vào prompt; chuỗi nào lệch với OCR thì gắn cờ "không chắc" |

Model cho B và C: `gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-4-carbon`. Từ thí nghiệm sau không dùng dòng gemini-4 (giá gấp đôi từ 01/12/2026).

### Kết quả (khớp chính xác, gộp 6 biến thể, 180 ảnh)

| Cách | Model | Số tài khoản | Số điện thoại | Link | Link khi coi `I` = `l` | Số tiền | Giây/ảnh | USD/1000 ảnh |
|---|---|---|---|---|---|---|---|---|
| A | PaddleOCR | 100% | 100% | 68,7% | 97,8% | 100% | 20,0 (CPU) | 0 |
| B | gemini-3.5-flash-lite | 95,6% | 100% | 68,2% | 96,1% | 100% | 5,8 | 1,53 |
| B | gemini-3.8-flash | 100% | 100% | 69,3% | 97,2% | 100% | 31,2 | 12,53 |
| B | gemini-4-carbon | 100% | 100% | 92,7% | 100% | 100% | 18,7 | 16,93 |
| C | gemini-3.5-flash-lite | 100% | 100% | 65,9% | 97,2% | 100% | 5,5 | 1,62 |
| C | gemini-3.8-flash | 100% | 100% | 67,0% | 97,8% | 100% | 27,7 | 12,36 |
| C | gemini-4-carbon | 100% | 100% | 93,3% | 100% | 100% | 21,9 | 19,50 |

Mẫu số: 180 số tài khoản, 180 số điện thoại, 179 link, 217 số tiền. Phía gửi (ai nói câu nào): 100% (1116/1116) ở mọi cấu hình B và C. Giây/ảnh của C chưa cộng thời gian OCR.

### Đọc từ số đo

- **OCR chỉ giúp ở một chỗ:** model rẻ nhất làm rơi một chữ số ở 8/180 số tài khoản; thêm chữ OCR thì sửa được cả 8 và không làm hỏng chuỗi nào. Hai model còn lại đã đạt 100% khi không có OCR.
- **OCR không sửa được link.** OCR tự nó cũng chỉ đọc đúng 68,7% link. Ở cách C, chữ OCR sửa được 5-11 link nhưng làm hỏng 4-15 link mà VLM vốn đọc đúng.
- **Gần hết lỗi link là nhầm `I` với `l`:** 50/55 đến 13/13 lỗi tùy cấu hình. Trong font không chân của app chat, hai chữ này gần như trùng nét. Lỗi còn lại là sai hoa/thường ở phần đường dẫn.
- **Tên miền của link đạt 100% (179/179) ở cả 7 cấu hình**, kể cả tên miền giả dạng (`c0ngan-xacminh.vip`, `rnbbank-hoantien.xyz`). Mọi lỗi link nằm ở đoạn đường dẫn ngẫu nhiên sau dấu `/`, thứ sản phẩm không cần đọc đúng từng ký tự.
- **Cờ "không chắc" gần như không bắt được lỗi link:** chỉ gắn đúng 8-25% chuỗi sai, vì OCR sai cùng chỗ với VLM. Với `gemini-4-carbon` cờ còn báo nhầm 45/167 link đúng.
- **`gemini-3.8-flash` ở mức suy nghĩ mặc định không đáng tiền cho việc này:** trung bình 2761 token suy nghĩ mỗi ảnh, 31 giây/ảnh (p90 67 giây), giá gần bằng `gemini-4-carbon`, mà link không hơn model rẻ nhất.
- **Biến thể ảnh (tối, mờ, JPEG 40, thu nhỏ) không làm đổi kết quả rõ rệt:** chênh giữa các biến thể nằm trong 1-3 chuỗi mỗi ô.

### Quyết định

Quy tắc đặt trước (bỏ OCR riêng nếu VLM đạt từ 98% ở mọi loại chuỗi và mọi biến thể) cho ra "giữ cả hai" với cả ba model, nhưng chỉ vì link, và link là thứ OCR không sửa được. Đề xuất, chờ Minh duyệt:

- Với link, sản phẩm chỉ dùng tên miền. Không dùng cờ "lệch với OCR" cho link, không coi sai đường dẫn là đọc sai.
- Có giữ OCR hay không tùy model của bản nộp: model rẻ thì cần OCR để soát số tài khoản; model đọc đủ chữ số thì bỏ được. Chốt sau khi chạy lại E1 với model Bedrock.

### Giới hạn

- Ảnh dựng từ HTML sạch hơn ảnh chụp màn hình thật. Chưa có số đo trên ảnh thật.
- Mỗi ô biến thể chỉ có khoảng 30 chuỗi, một lỗi là 3,3 điểm phần trăm.
- Bộ ảnh này quá dễ: mọi thứ sản phẩm cần đều đạt 100% trừ một ô. Nó không phân biệt được các cách đọc; E1b thêm bộ ảnh khó hơn.
- Link trong dữ liệu cố ý chứa `I` và `l` cạnh nhau, nên tỉ lệ sai link cao hơn link ngoài đời.
- Thời gian OCR đo trên CPU 12 nhân, tắt oneDNN, chạy chung với các lượt gọi API; không đại diện cho GPU.
- Chưa thử `gemini-3.8-flash` với mức suy nghĩ thấp.
- Bản nộp dùng model trên Bedrock, nên E1 phải chạy lại với model đó; số của Gemini không dùng thay được.

## E2 - Chọn câu hỏi bằng tính toán so với để model tự hỏi

Lần 1: 2026-11-21, đề bài `docs/tasks/T1-loi-hoi-dap-va-khung-app.md` (Phần 1, Phần 5), kết quả giữ nguyên ở `experiments/E2/run1/`. Lần 2: đề bài `docs/tasks/T2-sua-dien-bang-chay-lai-E2.md`, sau khi sửa khâu điền bảng. Báo cáo: `experiments/E2/report.md` (có cột lần 1 cạnh mỗi số).

### Dữ liệu

- Lần 2: 15 kịch bản (11 lừa đảo, 4 bình thường). Lần 1 chỉ có 14, vì `scenarios/gia_ngan_hang.yaml` lỗi cú pháp; tab kế hoạch đã sửa file đó.
- Phần 1: người trả lời hoàn hảo, 200 bảng câu chuyện mỗi kịch bản, lấy mẫu từ chính bảng xác suất của kịch bản (seed 20261121). Không gọi model.
- Phần 5: 75 tình huống chỉ có chữ, 5 tình huống mỗi kịch bản, lưu ở `sim/cases/`. 70 tình huống của lần 1 giữ nguyên; lần 2 thêm 5 tình huống `gia_ngan_hang`. Mỗi tình huống có bảng câu chuyện thật lấy mẫu như Phần 1, một tính cách (vội / cả tin / nghi ngờ / kể lộn xộn), tin mở đầu do model viết một lần rồi giữ nguyên, và nhãn tài khoản.
- Bộ phát triển cho prompt điền bảng: 12 tin nhắn tự viết, không lấy từ `sim/cases/`, kèm trường mong đợi (`tests/fill_dev.json`). Prompt chỉ được chỉnh trên bộ này.

### Cấu hình

- `tinh_toan`: code chọn trường có lợi ích thông tin kỳ vọng cao nhất; model viết câu hỏi và điền bảng; dừng khi xác suất đứng đầu từ 0,7 hoặc đã hỏi 3 câu.
- Điền bảng ở lần 2: chỉ điền trường người dùng nói rõ. Mỗi trường phải kèm `trich` chép nguyên văn; code bỏ trường nào có `trich` không nằm trong tin nhắn (so sau khi chuẩn hóa Unicode, dấu cách, hoa thường, bỏ ngoặc kép và dấu câu ở hai đầu). Không suy `nguoi_lien_lac`, `ai_bat_dau`, `ap_luc`, `da_gap_truc_tiep` từ giọng điệu.
- `tinh_toan_min1` (khai trước, báo riêng): như `tinh_toan`, nhưng khi chưa có ảnh thì phải hỏi ít nhất 1 câu rồi mới kết luận.
- `tu_do`: model đọc `ten` và `mo_ta` của mọi kịch bản, tự hỏi tối đa 3 câu, rồi chọn một `id` hoặc "chưa đủ căn cứ".
- Mọi trợ lý và nạn nhân giả lập đều dùng `gemini-3.5-flash-lite`. Chi phí Phần 5 lần 2 là 0,45 USD (ba trợ lý); đo điền bảng thêm khoảng 0,15 USD. Lần 1: 0,25 USD.

### Kết quả

Đúng kịch bản (lần 2, lần 1 trong ngoặc):

| | Sau 0 câu | Sau 1 câu | Sau 2 câu | Sau 3 câu |
|---|---|---|---|---|
| Người trả lời hoàn hảo, `tinh_toan` | 1,6% (1,8%) | 68,4% (67,8%) | 76,1% (77,1%) | 79,1% (80,3%) |
| Nạn nhân giả lập, `tinh_toan` | 58,7% (58,6%) | 68,0% (67,1%) | 68,0% (70,0%) | 69,3% [58,7-80,0] (71,4%) |
| Nạn nhân giả lập, `tinh_toan_min1` | 54,7% | 72,0% | 68,0% | 69,3% [58,7-80,0] |
| Nạn nhân giả lập, `tu_do` | 74,7% (72,9%) | 80,0% (77,1%) | 80,0% (75,7%) | 78,7% [69,3-88,0] (75,7%) |

Đúng nhóm sau 3 câu: `tinh_toan` 89,3% (94,3%), `tinh_toan_min1` 94,7%, `tu_do` 92,0% (92,9%). Chỉ trên 70 tình huống chung với lần 1, đúng kịch bản sau 3 câu: `tinh_toan` 72,9%, `tinh_toan_min1` 71,4%, `tu_do` 80,0%. Số câu hỏi trung bình: `tinh_toan` 0,72 (0,63), `tinh_toan_min1` 1,41, `tu_do` 0,64 (0,87). Ngoặc vuông là khoảng tin cậy 95% bootstrap.

Điền bảng từ tin mở đầu của 75 tình huống (một lần gọi mỗi tin, `python -m sim.fill_eval --openings`):

| | Prompt lần 1 | Prompt lần 2 |
|---|---|---|
| Số trường điền trung bình | 4,35 | 3,89 |
| Trường có `trich` không nằm trong tin nhắn | 4 (không kiểm, vẫn điền) | 0 (bị bỏ) |
| Số tin điền `ap_luc` | 51 | 32 |
| Số tin điền `ai_bat_dau` | 19 | 8 |

Trong Phần 5 lần 2, code bỏ 4 trường vì `trich` không có trong tin nhắn ở `tinh_toan` (129 lần gọi điền bảng) và 4 ở `tinh_toan_min1` (181 lần gọi).

Trên bộ phát triển 12 tin, prompt lần 1 điền đủ 28/31 trường mong đợi và điền thừa 6 trường, trong đó có hai lần lấy việc người dùng đang vội làm `ap_luc`. Prompt lần 2 sau khi chỉnh: đủ 29/31, thừa 1.

### Đọc từ số đo

- **Sửa điền bảng không đổi kết luận.** `tinh_toan` vẫn ở khoảng 70% (69,3% lần 2, 71,4% lần 1), `tu_do` vẫn cao hơn (78,7%). Khoảng cách tăng từ 4,3 lên 9,3 điểm, nhưng hai khoảng tin cậy vẫn chồng lên nhau, và lần 2 sinh lại cả lời nạn nhân giả lập nên không tách được phần do sửa prompt.
- **Điền bảng bớt suy diễn nhưng chưa hết.** Số tin mở đầu bị điền `ap_luc` giảm từ 51 xuống 32, `ai_bat_dau` từ 19 xuống 8. Nhưng trong phiên sai `bt_tra_tien_nguoi_ban_quen__4`, lời kết luận vẫn trích chính câu người dùng tự giục ("chuyển nhanh giùm cái đang vội") làm bằng chứng bị hối thúc.
- **`tinh_toan` vẫn dừng sớm:** 46/75 phiên kết luận ngay sau tin mở đầu (đúng 76%). Buộc hỏi 1 câu (`tinh_toan_min1`) nâng đúng kịch bản sau 1 câu lên 72,0%, nhưng sau 3 câu vẫn 69,3%: hỏi thêm không bù được.
- **Báo nhầm dồn vào một kịch bản lừa:** 4 trong 5 lần `tinh_toan` báo nhầm kết luận `mao_danh_nguoi_quen`; 2 trong số đó người dùng kể chuyển cho bạn hoặc em họ mượn tiền. Với lý do "mượn tiền", bảng xác suất hiện tại nghiêng về chiêu mạo danh người quen. Đây là chuyện bảng xác suất, tab code không sửa.
- **Trần của phương pháp gần như không đổi** khi thêm `gia_ngan_hang` (79,1% sau 3 câu); cặp nhầm mới lớn nhất là `chuyen_nham_tien` → `gia_ngan_hang` (10%).

### Quyết định

Quy tắc đặt trước: `tinh_toan` hơn `tu_do` từ 5 điểm về đúng kịch bản sau 3 câu thì giữ. Lần 2 kém 9,3 điểm (lần 1 kém 4,3), nên đề xuất bỏ phần chọn câu hỏi và giữ bảng câu chuyện. Biến thể `tinh_toan_min1` cũng kém 9,3 điểm. Đây là số của một lần chạy, không chạy lại để chọn. Chờ Minh và tab kế hoạch quyết.

### Giới hạn

- Nạn nhân giả lập và trợ lý dùng cùng một model, và nạn nhân được đọc mô tả kịch bản.
- Bảng câu chuyện thật lấy mẫu từng trường độc lập, nên có những câu chuyện không tự nhiên (ví dụ "đặt cọc giá rẻ" mà kể là cho mượn tiền).
- 5 tình huống mỗi kịch bản; một tình huống là 20 điểm % của kịch bản đó.
- Lần 1 và lần 2 khác nhau cả lời nạn nhân giả lập, không chỉ ở prompt điền bảng.
- Bộ phát triển của prompt chỉ có 12 tin do tab code tự viết; số "trước, sau" của điền bảng đo bằng một lần gọi mỗi tin.
- Chưa có ảnh, chưa có tính cách "bị dặn trước" (để cho E8).

## E3 - Báo nhầm giao dịch bình thường

Cùng lần chạy với E2. Đo tỉ lệ tình huống bình thường bị kết luận "giống chiêu lừa" sau 3 câu.

| Cách đo | Lần 2 | Lần 1 |
|---|---|---|
| Người trả lời hoàn hảo (trần) | 6,2% (50/800) | 6,0% (48/800) |
| Nạn nhân giả lập, `tinh_toan` | 25% (5/20) [5-45] | 10% (2/20) |
| Nạn nhân giả lập, `tinh_toan_min1` | 10% (2/20) [0-25] | - |
| Nạn nhân giả lập, `tu_do` | 5% (1/20) [0-15] | 5% (1/20) |

`tinh_toan` báo nhầm nhiều hơn lần 1 (5 so với 2 trên 20), nhưng 20 tình huống là quá ít để so: khoảng tin cậy rộng 40 điểm. `bt_mua_online_nguoi_ban_moi` được đặt là khó phân biệt (mong đợi "chưa đủ căn cứ"); với người trả lời hoàn hảo chỉ 4% số phiên kết thúc ở "chưa đủ căn cứ" và 14,5% bị kết luận "giống chiêu lừa". Bảng xác suất của kịch bản này vẫn cần tab kế hoạch xem lại.
