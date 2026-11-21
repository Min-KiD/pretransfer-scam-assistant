# E5 - Đổi model hội thoại: model mở so với các model đóng

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-22. Minh đã duyệt.
Bối cảnh: `docs/specs/2026-11-22-ke-hoach-model-va-thi-nghiem.md`. Nối tiếp E2 (`experiments/E2/report.md`, `sim/run.py`).

## Câu hỏi cần trả lời

1. Thay `gemini-3.5-flash-lite` bằng một model mở tự host thì trợ lý kém đi bao nhiêu?
2. Model đóng mạnh nhất đạt tới đâu? Đây là trần để biết còn bao nhiêu chỗ cải thiện.
3. Có cần distill không (điều kiện ở mục 5 của bản kế hoạch)?

## Phần 1 - Bộ tình huống lớn hơn

75 tình huống thì một tình huống đã là 1,3 điểm, và chỉ có 20 tình huống bình thường. Sinh thêm bằng `sim/cases.py`, cùng cách, seed mới:

- Tổng 300 tình huống: 15 kịch bản x 20. 75 tình huống cũ giữ nguyên, là tập con `v1`.
- Report ghi riêng `v1` (để so với E2) và cả 300.
- 300 tình huống này là tập chấm. Không bao giờ dùng để train bất cứ model nào (E6 sẽ sinh tập train riêng).

## Phần 2 - Cách chạy

- Chỉ chạy trợ lý kiểu `tu_do` (model tự hỏi, tối đa 3 câu, rồi chọn một mã kịch bản hoặc `chua_du_can_cu`). Đây là kiểu đã chốt sau E2.
- Nạn nhân giả lập giữ nguyên `gemini-3.5-flash-lite` cho mọi lần chạy, để chỉ có trợ lý thay đổi.
- `core/llm.py` là chỗ duy nhất gọi model. Thêm lựa chọn backend bằng biến môi trường: Gemini như hiện tại, và một endpoint kiểu OpenAI cho model mở chạy trên server (và cho GPT, Claude, OpenRouter khi có key). Model mở: ép JSON theo schema nếu công cụ chạy hỗ trợ; không thì parse và gọi lại, đếm số lần hỏng.

## Phần 3 - Model làm trợ lý

| Nhóm | Model | Ghi chú |
|---|---|---|
| Đóng | `gemini-3.5-flash-lite` | Chạy lại trên 300 tình huống; trên `v1` phải ra gần 78,7% của E2, lệch nhiều thì báo |
| Đóng | `gemini-3.8-flash` mức suy nghĩ thấp, `gemini-4-carbon` | |
| Đóng, GPT và Claude | Mỗi hãng một model tầm trung, **chỉ trên 75 tình huống `v1`** | Giới hạn và key: mục 7 bản kế hoạch. `gemini-3.8-flash` và `gemini-4-carbon` ở dòng trên cũng chỉ chạy trên `v1` |
| Mở | Các VLM đã tải ở E4 Phần 0, dùng như LLM chữ | Mục tiêu là một model phục vụ cả đọc ảnh lẫn hội thoại |
| Mở | Tối đa 2 LLM chữ mở khác vừa 16GB, nếu có lý do tin là tiếng Việt tốt hơn | Kiểm tra giấy phép trên Hugging Face, ghi lý do chọn |

Phần model đóng không cần GPU: chạy ngay, song song với việc tải weights của E4.

## Phần 4 - Số đo, theo từng model

- Đúng kịch bản sau 3 câu; đúng nhóm (lừa đảo / bình thường); tỉ lệ `chua_du_can_cu`.
- Báo nhầm: tình huống bình thường bị kết luận giống chiêu lừa (mẫu số 80).
- Bỏ sót: tình huống lừa đảo bị kết luận giống bình thường (mẫu số 220).
- Số câu hỏi trung bình; tỉ lệ kết luận ngay không hỏi câu nào.
- Tỉ lệ câu trả lời hỏng định dạng, số lần phải gọi lại.
- `trich` trong kết luận có nằm nguyên văn trong lời người dùng không (code đã có phép kiểm này).
- Giây mỗi lượt (trung bình, p90), token vào và ra, USD mỗi phiên với model đóng; VRAM với model mở.
- Bảng theo kịch bản và cặp nhầm nhiều nhất cho ba model: tốt nhất nhóm đóng, tốt nhất nhóm mở, `gemini-3.5-flash-lite`.

Mọi tỉ lệ kèm tử số, mẫu số, khoảng tin cậy Wilson 95%. Một lần chạy cho mỗi model, không chạy lại để chọn.

## Giao lại

- `experiments/E5/report.md`, `experiments/E5/sessions.jsonl` (ghi đủ từng lượt, để E6 dùng).
- Kết luận theo điều kiện M2 ở mục 5 bản kế hoạch: model mở tốt nhất đạt hay không đạt, từng vế.
- Một dòng trong `EXPERIMENTS.md`. Commit code và report. Chi phí API thật theo model.

## Không làm

- Không train hay distill gì ở E5. Không đổi model mặc định của app.
- Không sửa prompt trợ lý để hợp riêng một model. Nếu một model mở cần đổi định dạng prompt mới chạy được, ghi rõ đổi gì.
