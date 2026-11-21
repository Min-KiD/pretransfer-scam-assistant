# E1 - Đọc chuỗi chính xác từ ảnh chụp chat

Người giao: tab `Momo_TechContest` (lên kế hoạch). Người làm: tab `code`.
Bối cảnh đầy đủ: `docs/specs/2026-11-20-thiet-ke-idea1-tro-ly-hoi-lai.md`, mục 5.1 và mục 7. Chỉ cần đọc hai mục đó.

## Câu hỏi cần trả lời

Để lấy số tài khoản, số điện thoại, link, số tiền từ ảnh chụp đoạn chat tiếng Việt, có cần một OCR riêng bên cạnh VLM không?

Ba cách đọc cần so:

- **A. Chỉ OCR:** PaddleOCR (bản PP-OCR mới nhất đọc được tiếng Việt) + regex lấy chuỗi.
- **B. Chỉ VLM:** Gemini, structured output theo schema. Chạy 2 model: một model flash rẻ và một model mạnh nhất key gọi được.
- **C. Cả hai:** đưa chữ OCR kèm ảnh cho VLM; code so chuỗi của A với chuỗi của B, lệch thì gắn cờ `khong_chac`.

## Nơi làm

| Thứ | Ở đâu |
|---|---|
| Code (bản gốc) | Máy này: `/home/minhnv/Documents/CV/momo-techcontest/pretransfer-scam-assistant/` (tạo mới, `git init`) |
| Nơi chạy | Server GPU riêng (địa chỉ ở dòng `SERVER=` trong `.env`), thư mục `~/pretransfer-scam-assistant/`. Đồng bộ code bằng rsync |
| Key | `~/pretransfer-scam-assistant/.env` trên server, biến `GEMINI_API_KEY` |
| Kết quả | `experiments/E1/` trong thư mục code, chép về máy này |

## Ràng buộc trên server

- Server là máy dùng chung của công ty. Chỉ ghi trong `~/pretransfer-scam-assistant/`. Không đụng thư mục, container, env của dự án khác. Không dùng code của công ty.
- Đĩa còn 46GB (đầy 95%). Toàn bộ env + model + dữ liệu của E1 phải dưới 10GB. Dọn cache tải về sau khi cài.
- GPU RTX 4060 Ti 16GB, lúc kiểm tra đang trống. Xem `nvidia-smi` trước mỗi lần chạy; nếu có job khác đang dùng thì chạy OCR bằng CPU.
- PaddleOCR: Python hệ thống chưa có (`import paddle` lỗi). Chưa kiểm tra các env trong `~/anaconda3`. Xem `conda env list` trước; nếu chưa có thì tạo env riêng tên `pretransfer`.
- Không in key ra terminal, log, hay file kết quả. Không commit `.env`.
- Hết 30 phút mà chưa cài được PaddleOCR thì dừng, báo lại lỗi, không thử cách cài lạ.

## Dữ liệu cần dựng

30 ảnh chụp chat, sinh từ mẫu HTML rồi chụp bằng Playwright ở khung điện thoại (khoảng 390x844, hệ số 3).

- 3 kiểu giao diện, mỗi kiểu 10 ảnh: giống Zalo, giống Messenger, giống SMS. Chỉ giống bố cục và màu; không dùng logo hay tài sản của hãng.
- Nội dung lấy từ 5 tình huống, tiếng Việt có dấu, 4-8 tin nhắn mỗi ảnh, có cả hai phía:
  1. Giả shipper đòi phí giao hàng.
  2. Giả công an yêu cầu chuyển vào "tài khoản an toàn".
  3. Tuyển cộng tác viên online, nạp tiền làm nhiệm vụ.
  4. Chuyển nhầm tiền, đòi hoàn lại vào tài khoản khác.
  5. Bình thường: người bán quen gửi số tài khoản để trả tiền hàng.
- Mỗi ảnh chứa các chuỗi cần đọc, viết theo nhiều kiểu như người thật:
  - Số tài khoản 8-14 chữ số, kèm tên ngân hàng và tên chủ tài khoản viết hoa không dấu.
  - Số điện thoại: `0912 345 678`, `0912.345.678`, `+84 912 345 678`.
  - Link: tên miền giả dạng, ví dụ `giaohang-tietkiem-vn.top/don/8K2x`. Có ký tự dễ nhầm (`0/O`, `1/l/I`).
  - Số tiền: `30.000đ`, `1.500.000 VND`, `2tr5`, `500k`.
- Tất cả số và tên là giả, tự sinh, không trùng số thật.
- Mỗi ảnh có file đáp án JSON: danh sách chuỗi theo loại, và với mỗi tin nhắn: phía gửi (trái/phải), thứ tự, nội dung.
- Từ 30 ảnh gốc, sinh thêm các biến thể: chế độ tối, cắt mất mép trên, JPEG chất lượng 40, thu nhỏ 50%, làm mờ nhẹ. Tổng khoảng 180 ảnh.

## Số đo

| Số đo | Cách tính |
|---|---|
| Khớp chính xác theo loại chuỗi | Đúng từng ký tự sau khi chuẩn hóa (bỏ dấu cách, dấu chấm trong số; link không phân biệt hoa thường ở tên miền). Báo riêng cho số tài khoản, số điện thoại, link, số tiền |
| Theo biến thể | Cùng số đo trên, tách theo gốc / tối / cắt / JPEG / thu nhỏ / mờ |
| Cờ `khong_chac` của cách C | Trong các chuỗi đọc sai, bao nhiêu % được gắn cờ. Trong các chuỗi đọc đúng, bao nhiêu % bị gắn cờ nhầm |
| Phía gửi (chỉ B và C) | % tin nhắn được gán đúng trái/phải |
| Thời gian và chi phí | Giây mỗi ảnh; token vào/ra mỗi ảnh |

## Thứ cần giao lại

- `experiments/E1/report.md`: bảng số đo, 5 ví dụ đọc sai điển hình (ảnh + đáp án + kết quả), tên và phiên bản model, lệnh chạy lại.
- `experiments/E1/results.jsonl`: một dòng mỗi (ảnh, cách đọc).
- Code sinh dữ liệu và code chấm, chạy lại được bằng một lệnh.
- Một đoạn tóm tắt ngắn trả lời ở terminal: số đo chính và đề xuất theo quy tắc dưới.

## Quy tắc đề xuất

- Nếu cách B đạt từ 98% khớp chính xác ở cả bốn loại chuỗi trên mọi biến thể, và cách C không hơn B quá 2 điểm phần trăm: đề xuất bỏ OCR riêng.
- Ngược lại: đề xuất giữ cả hai, và ghi rõ loại chuỗi nào, biến thể nào OCR cứu được.

## Không làm

- Không sửa bản thiết kế và `findings.md`; tab kế hoạch sẽ ghi kết quả vào đó.
- Không dựng backend, frontend, hay phần hội thoại. Chỉ E1.
- Không dùng ảnh lừa đảo thật lấy trên mạng.
