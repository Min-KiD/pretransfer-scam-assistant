# E6 - Bộ phân loại kịch bản nhỏ làm ý kiến thứ hai

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-22. Minh đã duyệt. Làm sau E5.
Bối cảnh: `docs/specs/2026-11-22-ke-hoach-model-va-thi-nghiem.md`.

## Câu hỏi cần trả lời

1. Một model chữ nhỏ chạy CPU đoán kịch bản từ lời người dùng đúng tới đâu, trên phiên giả lập và trên lời kể từ vụ việc thật?
2. Khi nó lệch với LLM, đó có phải dấu hiệu LLM sai không? Nếu không thì lớp soát này vô dụng và bỏ.

## Phần 1 - Dữ liệu

| Tập | Nguồn | Cỡ | Dùng để |
|---|---|---|---|
| train | Sinh mới bằng `sim/cases.py` + nạn nhân giả lập, seed khác hẳn E5 | 15 kịch bản x 200 | Train |
| val | Như train, seed khác | 15 x 20 | Chọn model, chọn ngưỡng |
| test giả lập | 300 tình huống của E5 | 300 | Chấm. Không train trên tập này |
| test thật | `data/narr/real/*.json`, trường `loi_ke` và nhãn `kich_ban` | khoảng 90 | Chấm. Tab kế hoạch đang thu; chưa có thì chạy phần còn lại trước |

- Đầu vào của model là chữ người dùng nói. Train hai kiểu mẫu cho mỗi tình huống: chỉ tin mở đầu, và tin mở đầu nối với các câu trả lời (không kèm câu hỏi của trợ lý).
- Nhãn là kịch bản đã chọn lúc sinh, không phải nhãn do model gán.
- Lời kể train do `gemini-3.5-flash-lite` viết. Ghi rõ điều này trong report.
- Tập thật có nhãn `khac` (không thuộc 11 kịch bản lừa đảo): mong đợi model cho xác suất thấp, không ép vào một kịch bản.

## Phần 2 - Model

| Mã | Model |
|---|---|
| C0 | TF-IDF + logistic regression. Bắt buộc: nếu C0 ngang các model dưới thì fine-tune không có lý do |
| C1 | Không train: nhúng lời kể và mô tả từng kịch bản bằng một model nhúng đa ngữ, chọn kịch bản gần nhất |
| C2 | Fine-tune PhoBERT-base-v2 |
| C3 | Fine-tune một model nhúng đa ngữ cỡ nhỏ (ví dụ họ multilingual-e5) |

Kiểm tra tên repo và giấy phép trên Hugging Face trước khi tải. Train trên GPU server, đo tốc độ suy luận trên CPU.

## Phần 3 - Số đo

- Độ đúng, macro-F1, ma trận nhầm, trên từng tập test và từng kiểu đầu vào.
- Độ khớp của xác suất (ECE và bảng độ tin so với độ đúng theo 10 khoảng).
- Báo nhầm trên 80 tình huống bình thường của E5.
- Tập thật: độ đúng trên 11 kịch bản lừa đảo; với nhãn `khac`, phân bố xác suất cao nhất.
- Mili giây mỗi mẫu trên CPU, dung lượng model.

## Phần 4 - Lệch với LLM

Dùng `experiments/E5/sessions.jsonl`. Với model mở tốt nhất của E5 và với `gemini-3.5-flash-lite`, trên 300 tình huống:

- Bảng 2x2: LLM đúng/sai x bộ phân loại cùng/lệch kết luận.
- Nếu áp quy tắc "lệch thì hạ xuống `chua_du_can_cu`": độ đúng trên phần còn kết luận, tỉ lệ `chua_du_can_cu`, báo nhầm, bỏ sót, so với không áp.
- Thử thêm quy tắc có ngưỡng: chỉ tính là lệch khi xác suất cao nhất của bộ phân loại vượt ngưỡng chọn trên `val`.

Kết luận theo điều kiện M3 ở mục 5 bản kế hoạch.

## Giao lại

- `experiments/E6/report.md`, một dòng trong `EXPERIMENTS.md`, commit code và report.
- Weights để trên server, ghi đường dẫn; không commit.

## Không làm

- Không nối bộ phân loại vào app. Không sửa prompt trợ lý.
