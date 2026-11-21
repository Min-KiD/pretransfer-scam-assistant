# E4 - VLM mở đọc ảnh chat ra JSON: mốc so sánh, fine-tune, soát bằng OCR

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-22. Minh đã duyệt.
Bối cảnh và quy tắc chung: `docs/specs/2026-11-22-ke-hoach-model-va-thi-nghiem.md` (đọc mục 4 và 5 trước). Nối tiếp E1 và E1b, dùng lại code trong `e1/`.

## Câu hỏi cần trả lời

1. Một VLM mở chạy trên 4060 Ti 16GB, sau khi train LoRA trên ảnh dựng, đọc ảnh chat thật ra JSON tốt tới đâu so với các model đóng?
2. Có cần nhìn ảnh không, hay OCR rồi đưa chữ cho một LLM là đủ?
3. PP-OCRv6 chạy kèm để soát thì bắt được bao nhiêu lỗi của VLM, và gắn cờ nhầm bao nhiêu?
4. Cần bao nhiêu ảnh train?

## Đổi so với E1b

- **Bỏ hạn 30 phút cho cài và tải.** Minh cho dùng server thoải mái. Tải weights chạy nền, có resume, để qua đêm được.
- **Được tạo env riêng trong thư mục dự án** (`.conda/` hoặc `.venv/`), cài `peft`, `bitsandbytes`, và `vllm` nếu cần. Vẫn không cài hay sửa gì trong `~/vidoc-dev`.
- Máy dùng chung: trước mỗi job xem `nvidia-smi`; có tiến trình của người khác thì chờ, không kill. Xong việc thì kiểm `du -sh .cache/hf` (lần trước xóa `models--*` còn sót 6,5 GB trong `hub/blobs`).

## Phần 0 - Tải weights (làm trước, chạy nền)

`qwen3-vl-4b`, `qwen3-vl-8b`, `gemma-4-e4b` (đã có trong `e1/open_models.py`), thêm bản Qwen3-VL cỡ 2B nếu có trên Hugging Face. Trước khi tải, kiểm tra trên Hugging Face: tên repo, giấy phép, dung lượng. Model nào khác với ghi ở đây thì ghi vào report. Được đề xuất thêm tối đa 2 model mở khác nếu có lý do rõ (ghi lý do).

## Phần 1 - Các bộ chấm

| Bộ | Ảnh | Ghi chú |
|---|---|---|
| `E1` | 180 | Đã có |
| `E1b` khó | 100 | Đã có |
| `gen` | 40 | Đã có; Phần 4 thêm `gen_ref` |
| `web` | 20, sẽ thêm khoảng 100 | Tab kế hoạch đang thu, mã `web_021` trở đi. Khi tab kế hoạch báo sẵn thì đồng bộ lên server và chạy lại mọi cấu hình trên phần mới |

Bộ `web` chia `dev`/`test` theo mã số: lẻ là `dev`, chẵn là `test`. Report ghi riêng `web-dev`, `web-test` và gộp. Chỉ mở lỗi của `web-dev` ra xem.

Số đo (thêm vào `e1/score_e1b.py`):

- Như E1b: khớp nguyên chuỗi theo loại (số tài khoản, số điện thoại, link, tên miền, đường dẫn, số tiền) và khớp chung.
- **Mới, chuỗi bịa:** số chuỗi model trả mà không có trong đáp án, chia cho tổng số chuỗi model trả, theo loại và gộp. Chuỗi nằm trong `skipped` của đáp án thì không tính là bịa.
- Phía gửi và chữ từng tin (tỉ lệ ký tự sai): chỉ trên bộ có `messages`.
- Tỉ lệ JSON hợp lệ; giây mỗi ảnh (trung bình, p50, p90); VRAM đỉnh; USD mỗi 1000 ảnh với model đóng.

**Soát đáp án bộ `web` mới:** với mỗi ảnh, so đáp án với kết quả của hai model đóng mạnh nhất đã chạy. Chuỗi nào cả hai model cùng đọc khác đáp án, hoặc cả hai cùng trả một chuỗi đáp án không có, thì ghi vào `experiments/E4/gt_audit.md` (mã ảnh, loại, đáp án, hai kết quả). Không tự sửa đáp án; tab kế hoạch xem ảnh và sửa.

## Phần 2 - Giai đoạn A: mốc so sánh trên các bộ đang có

Chạy trên cả bốn bộ. Ô nào đã có kết quả từ E1/E1b thì dùng lại, không chạy lại.

| Nhóm | Cấu hình | Ghi chú |
|---|---|---|
| Đóng, ảnh ra JSON (cách B của E1) | `gemini-3.5-flash-lite`, `gemini-3.8-flash` mức suy nghĩ thấp, `gemini-4-carbon` | |
| Đóng, GPT và Claude | Mỗi hãng một model tầm trung, **chỉ trên bộ `web`** | Tên model lấy từ trang giá chính thức lúc chạy. Giới hạn và key: mục 7 bản kế hoạch. `gemini-3.8-flash` và `gemini-4-carbon` ở dòng trên cũng chỉ chạy trên `web` và `gen` (bộ `E1` đã có số từ trước) |
| Mở, ảnh ra JSON, chưa train | Mỗi VLM ở Phần 0 | Thử giải mã ràng buộc theo JSON Schema nếu công cụ chạy model hỗ trợ; báo cả có và không ràng buộc |
| Mở, chỉ chữ | PP-OCRv6 GPU đọc chữ kèm tọa độ, rồi đưa chữ (không đưa ảnh) cho cùng model mở để điền JSON | Trả lời câu hỏi 2. Phía gửi suy từ tọa độ ngang của khối chữ |
| Mở, chữ rồi regex | Như E1b | Đã có số, chỉ thêm cột chuỗi bịa |

Xong giai đoạn A thì viết `experiments/E4/report_A.md` và báo ở terminal, rồi làm tiếp giai đoạn B không cần chờ.

## Phần 3 - Giai đoạn B: bộ sinh ảnh train và fine-tune

### 3.1 Bộ sinh `e1/gen_train.py`, ra `data/E4/`

Bộ sinh E1 chỉ có 30 đoạn chat gốc trên 3 giao diện; train trên đó model sẽ thuộc lòng. Bộ mới:

- **Lời thoại:** từ 15 kịch bản trong `scenarios/` (cả 4 kịch bản bình thường), viết bằng mẫu câu có chỗ trống cộng diễn đạt lại bằng `gemini-3.5-flash-lite` (Minh cho phép, xem mục 4 bản kế hoạch). Ghi số lần gọi và chi phí. Khoảng 40% đoạn chat là chuyện bình thường; khoảng 15% không chứa chuỗi nào.
- **Chuỗi, theo dạng gặp ngoài đời** (regex E1 từng sót các dạng này):
  - số điện thoại: `0xxx xxx xxx`, `+84 86 9448260`, `84...`, có dấu chấm, số tổng đài 1900/1800;
  - số tài khoản: 6-19 chữ số, có dấu cách hoặc dấu chấm, kèm tên ngân hàng và tên chủ tài khoản;
  - link: có và không có `https://`, tên miền trần, link rút gọn, tên miền giả dạng, link bị xuống dòng giữa chừng;
  - số tiền: `1.500.000đ`, `1,5tr`, `500k`, `8tr999k`, `2 triệu`, `VND`;
  - **chuỗi gây nhiễu không thuộc đáp án:** mã đơn hàng, mã OTP, mã vận đơn, ngày giờ, số CCCD.
- **Giao diện:** ít nhất 6 mẫu (Zalo, Messenger, iMessage, tin nhắn Android, Telegram, một mẫu chat trên máy tính), sáng và tối, nhiều cỡ màn hình. Có bong bóng ảnh, thẻ xem trước link, dòng cuộc gọi nhỡ, thẻ biên lai chuyển khoản. Xem ảnh trong `data/E1b/real/images/` để dựng cho giống, không chép ảnh thật vào ảnh train.
- **Điều kiện chụp:** sạch, cắt, nén JPEG, thu nhỏ, giả chụp lại màn hình, ảnh dài, ghép 2-3 màn thành một ảnh, có nét đỏ vẽ tay và logo đóng dấu như ảnh trên báo.
- **Cỡ:** 4000 ảnh train, 300 ảnh `val`. Thêm 300 ảnh `val_la` sinh từ một mẫu giao diện và hai kịch bản không có trong train.
- Đáp án lấy từ lúc sinh, theo `e1.vlm.SCHEMA`. Xem bằng mắt 30 ảnh ngẫu nhiên trước khi train.

### 3.2 Train

- Model gốc: model mở tốt nhất ở giai đoạn A mà train vừa 16GB. Nếu còn giờ, thêm một model cỡ khác (nhỏ hơn hoặc 8B lượng tử 4-bit).
- LoRA trên phần ngôn ngữ; phần nhìn đóng băng ở lần đầu. Tự chọn siêu tham số, ghi đủ: rank, tốc độ học, số bước, cỡ ảnh tối đa, seed, thời gian, VRAM đỉnh, đường loss.
- Chọn checkpoint bằng `val` và `web-dev`. Không dùng `web-test`, `gen`, `E1`, `E1b` để chọn.

### 3.3 Các lần chạy phải có

| Mã | Cấu hình |
|---|---|
| B1 | LoRA, chỉ ảnh, 4000 ảnh train |
| B2 | Như B1 với 500 ảnh và với 2000 ảnh (trả lời câu hỏi 4) |
| B3 | LoRA, ảnh kèm chữ PP-OCRv6 trong prompt (train cũng có chữ OCR) |
| B4 | B1, rồi soát: mỗi số tài khoản và số điện thoại model trả phải có trong chữ PP-OCRv6 (bỏ dấu cách, dấu chấm); không có thì gắn cờ. Báo: cờ bắt được bao nhiêu chuỗi sai, gắn nhầm bao nhiêu chuỗi đúng |

Chấm mọi lần chạy trên cả bốn bộ và `val_la`.

## Phần 4 - Ảnh `gen_ref`: sinh theo ảnh thật

Mở rộng `e1/gen_nb.py`: đưa cho model sinh ảnh một ảnh thật trong `data/E1b/real/images/` làm mẫu về giao diện và điều kiện chụp, kèm nội dung đoạn chat mới (tin nhắn và chuỗi từ bộ sinh), yêu cầu ra ảnh mới giống kiểu ảnh mẫu nhưng nội dung khác hẳn, không giữ tên, số hay link của ảnh mẫu.

- 150 ảnh, trải đều các ảnh mẫu và các kịch bản. Trần 10 USD, nằm trong trần Gemini chung.
- Đáp án: giữ chuỗi dự định nếu cả `gemini-4-carbon` lẫn chữ PP-OCRv6 đều đọc lại đúng chuỗi đó; chuỗi còn lại xem bằng mắt như E1b (sửa theo ảnh, hoặc bỏ). Xem bằng mắt thêm 30 ảnh ngẫu nhiên trong số đã tự khớp. Ghi số ảnh sửa, số ảnh loại.
- Bộ này chỉ để chấm và làm ảnh mẫu cho demo. **Không đưa vào train.**
- Lưu ảnh mẫu nào sinh ra ảnh nào trong `data/E1b/gen/manifest.jsonl`.

## Giao lại

- `experiments/E4/report_A.md`, rồi `experiments/E4/report.md`: bảng mọi cấu hình x mọi bộ, bảng theo loại chuỗi, bảng chuỗi bịa, bảng tốc độ và VRAM, đường học theo số ảnh train, kết quả soát bằng OCR, ví dụ lỗi (bộ `web` chỉ ghi mã ảnh và chuỗi).
- Kết luận theo điều kiện ở mục 5 của bản kế hoạch, ghi rõ đạt hay không đạt từng vế trên `web-test`.
- `experiments/E4/gt_audit.md`.
- Adapter LoRA để trên server, ghi đường dẫn và dung lượng; không commit weights.
- Một dòng trong `EXPERIMENTS.md`. Commit code và report.
- Chi phí API thật, theo model.

## Không làm

- Không sửa app, không đổi model của app.
- Không train trên ảnh thật hay trên các bộ chấm (`E1`, `E1b`, `gen`, `gen_ref`, `web`).
- Không sinh thêm ảnh bằng model sinh ảnh để train, không gọi model đóng ngoài giới hạn ở mục 7 bản kế hoạch, khi chưa hỏi.
- Không commit `data/`.
