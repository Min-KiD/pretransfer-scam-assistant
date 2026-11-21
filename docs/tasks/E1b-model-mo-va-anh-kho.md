# E1b - Model mã nguồn mở và bộ ảnh khó hơn

Người giao: tab `Momo_TechContest` (lên kế hoạch). Người làm: tab `code`.
Nối tiếp E1 (`docs/tasks/E1-doc-anh-chat.md`, `experiments/E1/report.md`). Dùng lại code trong `e1/`.

## Vì sao có E1b

- E1 chỉ thử một OCR (PP-OCRv6, chạy CPU) và ba model Gemini đóng. Minh muốn biết model mở chạy trên GPU của mình có thay được không.
- Bộ ảnh E1 quá dễ: tính riêng **tên miền** của link thì mọi cấu hình đạt 100% (179/179), kể cả tên miền giả dạng như `c0ngan-xacminh.vip`, `rnbbank-hoantien.xyz`. Mọi lỗi link nằm ở đoạn đường dẫn ngẫu nhiên sau dấu `/`. Chạy thêm model trên bộ này sẽ ra toàn 100% và không phân biệt được gì, nên cần thêm bộ ảnh khó hơn.

## Câu hỏi cần trả lời

1. Trên GPU 16GB, model mở nào đọc ảnh chat tiếng Việt ngang hoặc hơn `gemini-3.5-flash-lite`?
2. Có OCR hay model đọc tài liệu nào đọc tốt hơn PP-OCRv6 không?
3. Khi ảnh khó hơn, cách đọc nào gãy trước, ở biến thể nào?

## Phần 0 - Chấm lại E1, không gọi model

Thêm vào `e1/score.py` hai số đo cho link, rồi chấm lại `experiments/E1`:

- **Tên miền:** phần trước dấu `/` đầu tiên, hạ chữ thường, khớp từng ký tự.
- **Đường dẫn:** phần còn lại, khớp từng ký tự, phân biệt hoa thường.

Tab kế hoạch đã tính tay từ `results.jsonl`: tên miền 179/179 ở cả 7 cấu hình. Số của bạn phải ra đúng như vậy; lệch thì báo.

## Phần 1 - Bộ ảnh khó `data/E1b/`

Sinh từ 30 ảnh gốc của E1 và từ bộ sinh HTML sẵn có. Đáp án lấy từ lúc sinh, không gán tay.

| Biến thể | Cách làm | Số ảnh |
|---|---|---|
| `nho33` | Thu nhỏ còn 33% | 30 |
| `nen2` | JPEG chất lượng 30, thu còn 70%, rồi JPEG chất lượng 30 lần nữa (ảnh bị chuyển tiếp qua nhiều app) | 30 |
| `chuplai` | Giả ảnh chụp lại màn hình bằng máy khác: xoay 2-4 độ, méo phối cảnh nhẹ, mờ, nhiễu, sọc moiré nhẹ, có viền nền ngoài màn hình | 30 |
| `dai` | Đoạn chat dài 20-30 tin nhắn chụp thành một ảnh cao (rộng 390, cao 3000-5000, hệ số 3). Chuỗi cần đọc rải ở đầu, giữa, cuối | 10 |

Tổng 100 ảnh. Xem bằng mắt 2 ảnh mỗi biến thể trước khi chạy: người đọc được thì mới giữ, không đọc nổi thì giảm mức phá.

## Phần 1b - Hai bộ ảnh giống thật (thêm 20/11, theo ý Minh)

### Bộ `web`: ảnh chat thật đã đăng công khai

Tab kế hoạch tự thu, tab `code` không phải tìm. Ảnh nằm ở `data/E1b/real/images/web_NN.*`, đáp án ở `data/E1b/real/gt/web_NN.json`, nguồn từng ảnh ở `data/E1b/real/sources.md`.

- Đáp án chỉ có `strings`, `messages` để rỗng: bỏ số đo phía gửi cho nhóm này.
- Đáp án có thể chứa số tài khoản ngoài khoảng 8-14 chữ số và tên miền không có đường dẫn. Chấm như bình thường; regex bỏ sót thì tính là sót.
- Chỉ dùng để chấm nội bộ. Không commit, không đưa vào report dưới dạng ảnh (ví dụ đọc sai của nhóm này chỉ ghi mã ảnh và chuỗi).
- Khi tab kế hoạch báo bộ này đã sẵn, đồng bộ `data/E1b/real/` lên server và chạy mọi model đã có kết quả trên nhóm này.

### Bộ `gen`: ảnh do model sinh ảnh của Gemini tạo

Mục đích: có ảnh trông như app thật và như ảnh chụp ngoài đời, mà vẫn biết trước đáp án.

| Biến thể | Cách làm | Số ảnh |
|---|---|---|
| `gen_sua` | Đưa ảnh gốc E1 cho model sửa ảnh: biến thành ảnh chụp một chiếc điện thoại đang mở đoạn chat đó (cầm tay, có bóng, lóa nhẹ, nghiêng). Yêu cầu giữ nguyên mọi chữ | 20 |
| `gen_moi` | Sinh từ lời mô tả: ảnh chụp màn hình một đoạn chat tiếng Việt, liệt kê đúng các tin nhắn và các chuỗi cần có | 20 |

- Model: bản Nano Banana mới nhất key gọi được (trang giá ghi `gemini-nano-banana-2.1`, 0,0504 USD mỗi ảnh 2K). Trần chi phí cho cả bộ: 5 USD, tính cả ảnh sinh lại.
- **Model sinh ảnh hay viết sai chữ số và dấu tiếng Việt, nên đáp án dự định chưa phải đáp án thật.** Với từng ảnh: mở ảnh ra xem, so từng chuỗi với đáp án dự định. Chuỗi nào ảnh hiện khác thì sửa đáp án theo đúng thứ ảnh hiện; chuỗi nào không đọc chắc được thì bỏ khỏi đáp án. Ảnh không còn chuỗi nào thì loại. Ghi vào report: bao nhiêu ảnh phải sửa đáp án, bao nhiêu ảnh bị loại.
- `messages` để rỗng cho bộ này.
- Ảnh bộ `gen` là của mình, được commit vào `experiments/E1b/examples/` khi làm ví dụ.

## Phần 2 - Model cần thử

Chạy theo thứ tự ưu tiên dưới đây. Hết giờ thì dừng ở đâu báo ở đó.

| Thứ tự | Model | Cỡ | Giấy phép | Nhóm | Ghi chú |
|---|---|---|---|---|---|
| 1 | PP-OCRv6 medium, chạy GPU | 34,5M | Apache 2.0 | Chữ | Cùng weights với E1, mục đích là đo tốc độ thật. Wheel GPU của Paddle lần trước timeout vì pip không tải tiếp được; thử tải file wheel bằng công cụ có resume rồi cài từ file, hoặc chạy bằng ONNX Runtime GPU |
| 2 | Qwen3-VL-8B-Instruct | 8B | Apache 2.0 | JSON | Không vừa 16GB thì dùng bản lượng tử hóa hoặc Qwen3-VL-4B-Instruct; ghi rõ bản nào |
| 3 | PaddleOCR-VL-1.6 | 0,9B | Apache 2.0 | Chữ | |
| 4 | MinerU2.5-Pro | 1,2B | Apache 2.0 (weights) | Chữ | `~/vidoc-dev/.venvs` có thể đã có env MinerU. Được gọi env đó, không cài thêm hay sửa gì trong đó |
| 5 | GLM-OCR | 0,9B | MIT | Chữ và JSON | Chạy cả hai chế độ: đọc chữ, và điền JSON theo schema |
| 6 | Gemma 4 E4B-it | 4,5B hiệu dụng | Apache 2.0 | JSON | |
| Dự bị | OvisOCR2 (0,8B), TeleOCR (1,2B) | | Apache 2.0 | Chữ | Chỉ khi còn giờ |

Tên, cỡ, giấy phép ở bảng lấy từ hai bài tổng hợp (docsumo.com 30/09/2026, andrew.ooo 10/11/2026), tab kế hoạch chưa mở từng trang model. Trước khi tải, kiểm tra trên Hugging Face: tên repo, giấy phép, dung lượng, có hỗ trợ tiếng Việt không. Lệch với bảng thì ghi vào report.

Hai dòng tham chiếu chạy thêm trên bộ khó (trên bộ E1 đã có số):

- A: PP-OCRv6 (bản nào chạy được: GPU nếu mục 1 xong, không thì CPU).
- B: `gemini-3.5-flash-lite`, trên bộ khó, bộ `gen` và bộ `web`, dự kiến dưới 0,5 USD. Không gọi model đọc ảnh nào khác của Gemini.

### Cách đọc theo nhóm

- **Nhóm Chữ:** lấy toàn bộ chữ model trả về, đưa qua regex `e1/extract.py` như cách A. Nhóm này không có số đo phía gửi. Ghi lại model có trả tọa độ từng khối chữ không.
- **Nhóm JSON:** cùng prompt và schema với cách B trong `e1/vlm.py`. JSON hỏng hoặc sai schema thì tính mọi chuỗi của ảnh đó là đọc sai, và đếm riêng số ảnh như vậy.
- Không chạy cách C (E1 đã cho thấy ghép chữ OCR vào prompt không giúp).

## Số đo

Chấm trên bốn bộ, báo riêng: E1 (180 ảnh), E1b khó (100 ảnh), `gen`, `web`.

| Số đo | Cách tính |
|---|---|
| Khớp chính xác theo loại | Như E1: số tài khoản, số điện thoại, số tiền, link nguyên chuỗi |
| Link tách đôi | Tên miền, đường dẫn (định nghĩa ở Phần 0) |
| Theo biến thể | Cùng các số trên, tách theo biến thể |
| Phía gửi | Chỉ nhóm JSON |
| JSON hỏng | Số ảnh, chỉ nhóm JSON |
| Tốc độ | Giây mỗi ảnh trên GPU sau khi đã nạp model, từng ảnh một; trung bình, p50, p90 |
| Tài nguyên | VRAM đỉnh, dung lượng weights trên đĩa, thời gian nạp model |

## Ràng buộc trên server

- Địa chỉ server nằm ở dòng `SERVER=` trong `.env` (không đưa vào git); script nhận biến `SERVER`.
- Chỉ ghi trong `~/pretransfer-scam-assistant/`. `HF_HOME` và mọi cache đặt trong thư mục dự án. Không dùng `ollama` của hệ thống (nó ghi ra ngoài thư mục dự án). Không đụng container, env của dự án khác.
- **Đĩa còn 43GB (đầy 96%).** Env + weights của E1b không quá 25GB ở mọi thời điểm, và luôn để trống ít nhất 15GB. Model nào chạy và chấm xong thì xóa weights nếu cần chỗ.
- **GPU RTX 4060 Ti 16GB, trống lúc 20:40 ngày 20/11.** Mỗi lúc một model. Trước mỗi model xem `nvidia-smi`: có tiến trình khác chiếm trên 2GB thì chờ 10 phút, vẫn còn thì bỏ model đó và ghi lại. Chạy xong phải nhả GPU.
- RAM 15GB. Cẩn thận lúc nạp model 8B.
- **Giới hạn mỗi model:** 30 phút cho cài và tải; 20 phút cho chạy 280 ảnh. Quá giờ cài thì bỏ, ghi lỗi, sang model kế. Chạy quá chậm thì dừng khi đã có ít nhất 60 ảnh và báo số trên phần đó.
- Chạy tách rời trên server như E1 (có `status.json`, laptop ngủ vẫn chạy). Khác E1: một model lỗi thì ghi lại và chạy tiếp model kế.
- Không in key. Không commit `.env`.

## Thứ cần giao lại

- `experiments/E1b/report.md`: bảng xếp hạng trên từng bộ ảnh, bảng theo biến thể của bộ khó, bảng tốc độ và tài nguyên, 5 ví dụ đọc sai trên bộ khó, tên repo và phiên bản từng model, model nào bị bỏ và vì sao, lệnh chạy lại.
- `experiments/E1b/results.jsonl`, `experiments/E1b/SUMMARY.md`.
- `experiments/E1/report.md` chấm lại có hai số đo link mới.
- `scripts/server_status.sh` in được trạng thái E1b.
- Commit local. Không push.
- Trả lời ngắn ở terminal: số đo chính và đề xuất theo quy tắc dưới.

## Quy tắc đề xuất

- Một model mở được coi là **đủ dùng** nếu trên bộ E1 nó đạt từ 98% ở số tài khoản, số điện thoại, số tiền và tên miền, và chạy không quá 5 giây mỗi ảnh trên GPU này.
- Báo model đủ dùng tốt nhất của mỗi nhóm (Chữ, JSON). Không có model nào đủ dùng thì nói rõ nó hụt ở đâu.
- Với bộ khó: báo biến thể nào kéo cách đọc nào xuống dưới 90%, ở loại chuỗi nào.

## Không làm

- Không gọi `gemini-3.8-flash` hay dòng `gemini-4` để đọc ảnh. Model sinh ảnh ở Phần 1b là ngoại lệ duy nhất.
- Không fine-tune, không viết prompt riêng cho từng model ngoài phần bắt buộc để model chạy được.
- Không sửa `findings.md`, `EXPERIMENTS.md`, `README.md`; tab kế hoạch sẽ ghi.
- Không dựng backend, frontend, hay phần hội thoại.
- Không tự tải thêm ảnh trên mạng; bộ `web` do tab kế hoạch thu và ghi nguồn.
