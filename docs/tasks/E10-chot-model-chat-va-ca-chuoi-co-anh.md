# E10 - Chốt model: model chat mở lớn hơn, mức suy nghĩ, Haiku 5.5, và cả chuỗi có ảnh (gộp so với tách)

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-23. Minh đã duyệt phần A, B, C, D ngày 23/11.
Nối tiếp E4 và E5 (`experiments/E4/report.md`, `experiments/E5/report.md`). Mã E7-E9 đã dành cho việc khác nên đợt này là E10.

## Câu hỏi cần trả lời

1. Model chat mở lớn hơn 4B, vẫn vừa card 16 GB, có vào được trong 5 điểm so với `gemini-3.5-flash-lite` không?
2. Bật suy nghĩ cho `gemini-3.5-flash-lite` có làm nó bớt kết luận vội (10/220 vụ lừa đảo bị coi là bình thường) không, với giá và độ trễ nào?
3. Claude Haiku 5.5 đứng ở đâu so với Gemini, ở cả chat lẫn đọc ảnh?
4. Khi phiên có ảnh: cho model chat nhìn thẳng ảnh ("gộp") khác gì so với đọc ảnh ra JSON rồi mới chat ("tách")?

Quyết định đã có, không cần chứng minh lại: trợ lý kiểu model tự hỏi (`tu_do`), tối đa 3 câu; app giữ cách tách hai bước
trừ khi phần D cho thấy gộp hơn rõ (luật ở phần D).

## Tiền và thứ tự

- Trước khi gọi API: cộng số Gemini đã tiêu thật từ mọi `cost.json`, `calls.jsonl` và bảng chi phí trong các report, ghi vào
  đầu `experiments/E10/report.md`. Trần Gemini hiện tại vẫn là 20 USD.
- **Phần A chạy ngay** (chỉ tốn tiền nạn nhân giả lập, khoảng 0,2 USD mỗi model). Tải model là việc lâu nhất, bắt đầu trước.
- **Phần B và D chỉ chạy khi tab kế hoạch báo Minh đã nâng trần Gemini.** Chưa có tin thì chuẩn bị code và bộ tình huống, không gọi API.
- **Phần C chỉ chạy khi key Claude có tiền** (xem phần C).
- Mỗi lần chạy có `--cap-usd` riêng ghi ở từng phần. Chạm trần thì dừng và báo, không tự nới.
- Server: một GPU, chạy lần lượt. Không giết job của người khác, không khởi động lại một lượt tải đang chạy.

## Phần A - Model chat mở lớn hơn

Cùng cách chạy E5: 300 tình huống, prompt `tu_do` giữ nguyên, nạn nhân giả lập `gemini-3.5-flash-lite`, mỗi model một lần.

| Model | Dung lượng (Hugging Face, 23/11) | Ghi chú |
|---|---|---|
| `Qwen/Qwen3-14B-AWQ` | 10,0 GB | Chỉ chữ, nén 4-bit chính thức |
| `Qwen/Qwen3-8B-FP8` | 9,4 GB | Chỉ chữ |
| `google/gemma-4-E4B-it` | 16,0 GB bản gốc: không vừa 16 GB | Dùng bản nén chính thức `google/gemma-4-E4B-it-qat-w4a16-ct` (11,5 GB). Không nạp được bằng vLLM thì ghi lỗi và báo, không tự đổi sang bản của bên thứ ba |

- Tắt suy nghĩ như E5 (`enable_thinking: false`), giải mã tham lam, ép JSON schema.
- Ghi như E5: đúng kịch bản sau 0-3 câu, báo nhầm, bỏ sót, số câu hỏi, hỏng định dạng, giây mỗi lượt (trung bình, p90), VRAM đỉnh,
  dung lượng trọng số, thời gian nạp, giấy phép và revision.
- Chạy lớp soát C0 của E6 trên phiên của từng model (CPU, không tốn tiền).
- Giữ trọng số trên server cho tới khi Minh chọn (đĩa còn 175 GB ngày 23/11). Xong thì báo `du -sh .cache/hf`.
- Điều kiện M2 như cũ: thua `gemini-3.5-flash-lite` (81,3%, 244/300) không quá 5 điểm về đúng kịch bản, báo nhầm không cao hơn quá 5 điểm.

## Phần B - Mức suy nghĩ của `gemini-3.5-flash-lite` cho chat

- Mặc định của model này là mức `minimal` (gần như tắt); mọi số E2, E5 chạy ở mức đó (trung vị 33 token ra mỗi lượt, đã gồm token suy nghĩ).
- Chạy thêm `gemini-3.5-flash-lite@medium` và `gemini-3.5-flash-lite@high`, mỗi mức 300 tình huống, mỗi mức một lần.
- Ghi thêm: token suy nghĩ mỗi lượt (trung vị, p90), giây mỗi lượt, USD mỗi phiên.
- `--cap-usd 2.0` cho mỗi mức. Sau 30 phiên đầu, ước chi phí cả 300; vượt 2 USD thì dừng ở 75 tình huống `v1` và báo.

## Phần C - Claude Haiku 5.5

- Gọi thử một lần trước. Ngày 23/11 18:00 key trong `.env` vẫn trả HTTP 400 "credit balance is too low". Còn lỗi này thì bỏ qua phần C và ghi vào report.
- Giá (trang giá Anthropic, đọc 23/11): 0,10 / 0,50 USD mỗi 1M token vào / ra với prompt tới 100.000 token. Thêm vào `PRICES`.
- Gọi bằng API gốc của Anthropic và ép đầu ra theo JSON schema. Lớp tương thích OpenAI bỏ qua `response_format` nên không dùng để so sánh.
- Chat: 300 tình huống. Đọc ảnh: cách B của E1 trên `web`, `gen`, `gen_ref`, `E1`, `E1b`, chấm bằng `e1.score_e4`.
- Trần 2 USD cho cả phần C (thay giới hạn "chỉ `web` và `v1`" ở mục 7 bản kế hoạch, riêng cho Haiku; Minh duyệt 23/11).

## Phần D - Cả chuỗi có ảnh: gộp so với tách

### Bộ tình huống

- 300 tình huống, 20 mỗi kịch bản, lấy ảnh từ `data/E4/val` (13 kịch bản) và `data/E4/val_la` (2 kịch bản), seed cố định, ghi danh sách ảnh vào repo.
- Tin mở đầu: chọn theo seed từ 5 câu trung tính viết sẵn (kiểu "Mình nhận được tin nhắn này, có nên chuyển không?"), không gọi model.
  Mục đích: thông tin về vụ việc chỉ nằm trong ảnh.
- Nạn nhân giả lập trả lời theo nội dung trong ảnh: prompt của nó nhận mô tả kịch bản và lời thoại trong đáp án của ảnh (`messages`).
  Các trường của `bang_that` mà ảnh thể hiện (kênh, tự xưng, yêu cầu...) phải khớp ảnh. Soát bằng mắt 15 tình huống (mỗi kịch bản một) trước khi chạy.
- Nhãn tài khoản nhận: lấy mẫu như `sim/cases.py`.
- Ảnh thật không có nhãn kịch bản nên không dùng được ở đây. Ghi rõ giới hạn này trong report.

### Các nhánh

| Nhánh | Model chat thấy gì | Ghi chú |
|---|---|---|
| `khong_anh` | Chỉ tin mở đầu | Mức sàn: cho biết ảnh đóng góp bao nhiêu |
| `tach` | JSON do `core.vision.read_image` đọc từ ảnh, chèn vào prompt như dữ liệu | Cách app đang làm |
| `tach` lần 2 | Như trên, chạy lại từ đầu (cả bước đọc ảnh) | Để đo độ lệch giữa hai lần chạy cùng cấu hình |
| `gop` | Chính ảnh, gửi kèm ở mọi lượt; không có JSON | Một lần gọi mỗi lượt |

- Cặp model chính: `gemini-3.5-flash-lite` cho cả đọc ảnh lẫn chat, ở cả bốn nhánh. Cùng model ở mọi nhánh để chỉ có cách nối thay đổi.
- Cặp thứ hai, chỉ nhánh `tach`: đọc ảnh `gemini-3.5-flash-lite`, chat bằng model mở tốt nhất của phần A (cấu hình "đọc ảnh đóng, chat mở").
- Nếu phần C chạy được: Haiku 5.5 ở nhánh `tach` và `gop`.
- Prompt chat giống nhau ở mọi nhánh, chỉ khác khối dữ liệu ảnh. Ghi nguyên văn phần khác nhau vào report.

### Số đo

- Đúng kịch bản sau tối đa 3 câu; lừa đảo bị coi là bình thường; bình thường bị báo là lừa đảo; `chua_du_can_cu`; số câu hỏi.
- Thời gian người dùng chờ tới câu trả lời đầu tiên của trợ lý (nhánh `tach` gồm cả bước đọc ảnh), và tổng mỗi phiên.
- Token và USD mỗi phiên.
- Nhánh `tach`: tỉ lệ khớp chuỗi của bước đọc ảnh trên đúng 300 ảnh này, và số phiên kết luận sai mà bước đọc ảnh đã đọc sai.
- So ghép cặp trên cùng tình huống: bảng 2x2 đúng/sai giữa hai nhánh, kiểm định McNemar, khoảng tin cậy bootstrap ghép cặp cho hiệu số.

### Luật khai trước

- Độ lệch nền = hiệu số đúng kịch bản giữa `tach` lần 1 và lần 2.
- `gop` và `tach` coi là **ngang nhau** nếu hiệu số đúng kịch bản không quá 5 điểm, hoặc khoảng tin cậy ghép cặp 95% chứa 0.
- App chỉ đổi sang `gop` nếu `gop` hơn `tach` trên 5 điểm, khoảng tin cậy không chứa 0, và hiệu số lớn hơn độ lệch nền. Khi đó báo Minh, không tự đổi app.
- Mỗi nhánh chạy một lần (trừ `tach` lần 2 đã khai), không chạy lại để chọn số.

`--cap-usd 3.0` cho cả phần D.

## Không làm trong đợt này

- LoRA trên `qwen3.5-4b`: Minh chưa duyệt.
- Lớp hỏi lại (`docs/specs/2026-11-23-de-xuat-lop-hoi-lai.md`): mới là đề xuất.
- Sửa `app/`: chờ kết quả đợt này.

## Giao nộp

- `experiments/E10/report.md` (tiếng Việt): bốn phần, mỗi tỉ lệ ghi `tử/mẫu` và khoảng tin cậy Wilson 95%; chi phí thật; phần nào không chạy thì ghi lý do.
- `EXPERIMENTS.md`: thêm mục E10 ngắn bằng tiếng Anh, cùng kiểu các mục trước.
- Commit, push. Không commit trọng số, không commit `experiments/`.
- Xong từng phần thì báo tab kế hoạch một dòng, không đợi cả đợt.
