# T2 - Sửa khâu điền bảng, chạy lại E2/E3 với đủ 15 kịch bản

Người giao: tab `Momo_TechContest`. Người làm: tab `code`. Ngày giao: 2026-11-22. Minh đã duyệt.
Nối tiếp `docs/tasks/T1-loi-hoi-dap-va-khung-app.md` và `experiments/E2/report.md`.

## Vì sao

- E2 lần đầu: `tinh_toan` 71,4% so với `tu_do` 75,7% đúng kịch bản sau 3 câu. `tinh_toan` dừng sau 0 câu ở 44/70 phiên vì `dien_bang` suy diễn quá lời người dùng kể (ví dụ "chuyển cho bạn mượn" bị điền thành nhiều trường mà người dùng không nói).
- `scenarios/gia_ngan_hang.yaml` đã được tab kế hoạch sửa (commit `0b2ce01`), giờ nạp đủ 15 kịch bản.

## Việc làm

1. **Sửa `dien_bang` (core/dialog.py):** chỉ điền một trường khi người dùng nói rõ điều đó; mỗi trường điền phải có `trich` là một đoạn chép nguyên văn từ tin nhắn, và code kiểm tra `trich` thật sự nằm trong tin nhắn (sau chuẩn hóa dấu cách, hoa thường), không có thì bỏ trường đó. Không suy ra `nguoi_lien_lac`, `ai_bat_dau`, `ap_luc`, `da_gap_truc_tiep` từ giọng điệu của người dùng (người dùng vội không có nghĩa là bị hối thúc).
2. **Bộ phát triển riêng:** viết 12 tin nhắn mở đầu mới (không lấy từ `sim/cases/`) kèm trường mong đợi, lưu ở `tests/fill_dev.json`, dùng để chỉnh prompt. **Không** chỉnh prompt bằng cách nhìn kết quả trên `sim/cases/`.
3. **Sinh thêm 5 tình huống cho `gia_ngan_hang`** (`python -m sim.cases` chỉ sinh file thiếu). 70 tình huống cũ giữ nguyên.
4. **Chạy lại Phần 1** (`sim.perfect`) với 15 kịch bản.
5. **Chạy lại Phần 5 một lần** trên 75 tình huống, ba trợ lý:
   - `tinh_toan` (đã sửa `dien_bang`);
   - `tinh_toan_min1`: như trên, nhưng khi chưa có ảnh thì phải hỏi ít nhất 1 câu rồi mới được kết luận. Đây là biến thể khai trước, báo riêng;
   - `tu_do`: chạy lại để cùng 75 tình huống.
   Giữ kết quả lần đầu ở `experiments/E2/run1/` để so.

## Số đo và giao lại

- Cùng các bảng như report lần đầu, thêm cột lần đầu bên cạnh. Thêm: số trường điền trung bình sau tin mở đầu (trước và sau khi sửa), và số trường điền bị bỏ vì `trich` không có trong tin nhắn.
- Cập nhật `experiments/E2/report.md`, mục E2/E3 trong `EXPERIMENTS.md`. `pytest` xanh. Commit local, không push.
- Tóm tắt ở terminal: ba dòng số đo chính và kết luận theo quy tắc 5 điểm.
- Trần chi phí: 2 USD.

## Không làm

- Không sửa bảng xác suất trong `scenarios/`, không đổi ngưỡng 0,7 / 0,5, không chạy lại nhiều lần để chọn số.
- Không sửa bản thiết kế và `findings.md`.
