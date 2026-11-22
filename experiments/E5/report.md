# E5 - Model hội thoại: model mở so với các model đóng

300 tình huống chỉ có chữ (15 kịch bản x 20; `v1` = 75 tình huống của E2, 5 mỗi kịch bản). Trợ lý kiểu `tu_do` (tự hỏi tối đa 3 câu rồi chọn một kịch bản hoặc `chua_du_can_cu`), prompt giữ nguyên như E2 cho mọi model. Nạn nhân giả lập: `gemini-3.5-flash-lite` cho mọi lần chạy. Mỗi model chạy một lần, không chạy lại để chọn. Ngoặc vuông: khoảng tin cậy Wilson 95%.

## Kết luận theo điều kiện M2 (bản kế hoạch, mục 5)

Chưa có model mở chạy đủ 300 tình huống.

Kiểm tra lặp lại E2: `gemini-3.5-flash-lite` trên `v1` đúng kịch bản sau 3 câu 77.3% (58/75) [67-85], E2 lần 2 là 78,7% (59/75); lệch -1.4 điểm (trong khoảng tin cậy).

## Đúng kịch bản và đúng nhóm: Cả 300 tình huống (chỉ `gemini-3.5-flash-lite` và model mở)

| Nhóm | Model | Số phiên | Sau 0 câu | Sau 1 câu | Sau 2 câu | Sau 3 câu | Đúng nhóm | `chua_du_can_cu` |
|---|---|---|---|---|---|---|---|---|
| Đóng | `gemini-3.5-flash-lite` | 300 | 78.7% (236/300) [74-83] | 80.7% (242/300) [76-85] | 81.0% (243/300) [76-85] | 81.3% (244/300) [77-85] | 94.3% (283/300) [91-96] | 0.0% (0/300) [0-1] |
| Đóng | `anthropic:claude-sonnet-5-5` | không chạy: key hợp lệ nhưng tài khoản chưa có tiền (gọi thử 1 lần ngày 22/11, HTTP 400 "credit balance is too low"); bỏ qua theo mục 7 bản kế hoạch | | | | | | |
| Mở | `local:gemma-4-e4b` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: đĩa server dùng chung chỉ còn khoảng 24 GB trống; lý do là dung lượng, không phải kết quả | | | | | | |
| Mở | `local:qwen3.5-9b` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: đĩa server dùng chung chỉ còn khoảng 24 GB trống; lý do là dung lượng, không phải kết quả | | | | | | |
| Mở | `local:qwen3-vl-8b-fp8` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: mốc model lớn là các model đóng qua API; không phải vì kết quả | | | | | | |

## Đúng kịch bản và đúng nhóm: Tập con `v1` (75 tình huống, so với E2; mọi model)

| Nhóm | Model | Số phiên | Sau 0 câu | Sau 1 câu | Sau 2 câu | Sau 3 câu | Đúng nhóm | `chua_du_can_cu` |
|---|---|---|---|---|---|---|---|---|
| Đóng | `gemini-3.5-flash-lite` | 75 | 69.3% (52/75) [58-79] | 76.0% (57/75) [65-84] | 77.3% (58/75) [67-85] | 77.3% (58/75) [67-85] | 90.7% (68/75) [82-95] | 0.0% (0/75) [0-5] |
| Đóng | `gemini-3.8-flash@low` | 75 | 72.0% (54/75) [61-81] | 77.3% (58/75) [67-85] | 80.0% (60/75) [70-87] | 80.0% (60/75) [70-87] | 93.3% (70/75) [85-97] | 1.3% (1/75) [0-7] |
| Đóng | `gemini-4-carbon` | 75 | 58.7% (44/75) [47-69] | 74.7% (56/75) [64-83] | 81.3% (61/75) [71-89] | 82.7% (62/75) [73-90] | 90.7% (68/75) [82-95] | 4.0% (3/75) [1-11] |
| Đóng | `openai:gpt-6.2-sol` | 75 | 62.7% (47/75) [51-73] | 70.7% (53/75) [60-80] | 72.0% (54/75) [61-81] | 76.0% (57/75) [65-84] | 89.3% (67/75) [80-94] | 9.3% (7/75) [5-18] |
| Đóng | `anthropic:claude-sonnet-5-5` | không chạy: key hợp lệ nhưng tài khoản chưa có tiền (gọi thử 1 lần ngày 22/11, HTTP 400 "credit balance is too low"); bỏ qua theo mục 7 bản kế hoạch | | | | | | |
| Mở | `local:gemma-4-e4b` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: đĩa server dùng chung chỉ còn khoảng 24 GB trống; lý do là dung lượng, không phải kết quả | | | | | | |
| Mở | `local:qwen3.5-9b` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: đĩa server dùng chung chỉ còn khoảng 24 GB trống; lý do là dung lượng, không phải kết quả | | | | | | |
| Mở | `local:qwen3-vl-8b-fp8` | không chạy: bỏ ngày 22/11 theo quyết định của Minh: mốc model lớn là các model đóng qua API; không phải vì kết quả | | | | | | |

## Báo nhầm, bỏ sót, số câu hỏi

Báo nhầm: tình huống bình thường bị kết luận giống chiêu lừa (mẫu số 80 trên 300, 20 trên `v1`). Bỏ sót: tình huống lừa đảo bị kết luận giống chuyện bình thường (mẫu số 220 trên 300, 55 trên `v1`). Sau 3 câu.

| Model | Tập | Báo nhầm | Bỏ sót | Số câu hỏi TB | Kết luận ngay, không hỏi |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 300 | 8.8% (7/80) [4-17] | 4.5% (10/220) [2-8] | 0.65 | 53.7% (161/300) [48-59] |
| `gemini-3.5-flash-lite` | v1 | 5.0% (1/20) [1-24] | 10.9% (6/55) [5-22] | 0.69 | 49.3% (37/75) [38-60] |
| `gemini-3.8-flash@low` | v1 | 15.0% (3/20) [5-36] | 1.8% (1/55) [0-10] | 1.04 | 28.0% (21/75) [19-39] |
| `gemini-4-carbon` | v1 | 15.0% (3/20) [5-36] | 1.8% (1/55) [0-10] | 1.37 | 20.0% (15/75) [13-30] |
| `openai:gpt-6.2-sol` | v1 | 5.0% (1/20) [1-24] | 0.0% (0/55) [0-7] | 1.11 | 40.0% (30/75) [30-51] |

## Định dạng, tốc độ, chi phí

Trả lời hỏng định dạng: `du_doan` không phải một mã kịch bản hợp lệ (tính là `chua_du_can_cu`). Gọi lại: số lần gọi hỏng (lỗi API hoặc JSON không đọc được) trước lần gọi được giữ. Giây mỗi lượt tính riêng lượt của trợ lý. USD theo giá niêm yết dùng ở E1; model mở tự host tính 0 USD.

| Model | Lượt | Hỏng định dạng | Gọi lại | Giây/lượt TB | p90 | Token vào/phiên | Token ra/phiên | USD/phiên | VRAM đỉnh |
|---|---|---|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 494 | 0.0% (0/494) [0-1] | 0 | 0.78 | 0.84 | 3147 | 63 | 0.00110 | - |
| `gemini-3.8-flash@low` | 153 | 0.0% (0/153) [0-2] | 0 | 3.05 | 4.50 | 3914 | 86 | 0.00326 | - |
| `gemini-4-carbon` | 178 | 0.0% (0/178) [0-2] | 0 | 19.23 | 45.06 | 5409 | 1785 | 0.02867 | - |
| `openai:gpt-6.2-sol` | 158 | 0.0% (0/158) [0-2] | 0 | 1.75 | 2.64 | 4557 | 100 | 0.01011 | - |


Kiểm tra `trich`: kiểu `tu_do` không trả `trich` (schema chỉ có `du_doan`, `cau_hoi`; E2 giữ nguyên prompt này), nên số đo "trích nguyên văn" không áp dụng cho E5.

## Theo kịch bản (đúng kịch bản sau 3 câu; `v1` 5 tình huống mỗi dòng, 300 là 20)

Tốt nhất nhóm đóng (trên `v1`): `gemini-4-carbon`. Tốt nhất nhóm mở (trên 300): `None`.

| Kịch bản | Nhóm | `gemini-4-carbon` v1 | `gemini-3.5-flash-lite` v1 | `gemini-3.5-flash-lite` 300 |
|---|---|---|---|---|
| `bao_nguoi_than_cap_cuu` | lua_dao | 80% (4/5) | 80% (4/5) | 80% (16/20) |
| `bt_chuyen_cho_nguoi_than` | binh_thuong | 60% (3/5) | 80% (4/5) | 80% (16/20) |
| `bt_dat_coc_da_xem` | binh_thuong | 80% (4/5) | 80% (4/5) | 85% (17/20) |
| `bt_mua_online_nguoi_ban_moi` | binh_thuong | 80% (4/5) | 60% (3/5) | 70% (14/20) |
| `bt_tra_tien_nguoi_ban_quen` | binh_thuong | 40% (2/5) | 100% (5/5) | 85% (17/20) |
| `chuyen_nham_tien` | lua_dao | 100% (5/5) | 100% (5/5) | 75% (15/20) |
| `ctv_online` | lua_dao | 100% (5/5) | 80% (4/5) | 90% (18/20) |
| `dat_coc_gia_re` | lua_dao | 80% (4/5) | 40% (2/5) | 55% (11/20) |
| `dau_tu_san_gia` | lua_dao | 80% (4/5) | 80% (4/5) | 90% (18/20) |
| `dich_vu_lay_lai_tien` | lua_dao | 80% (4/5) | 80% (4/5) | 75% (15/20) |
| `gia_co_quan_nha_nuoc` | lua_dao | 100% (5/5) | 100% (5/5) | 90% (18/20) |
| `gia_cong_an` | lua_dao | 80% (4/5) | 80% (4/5) | 90% (18/20) |
| `gia_ngan_hang` | lua_dao | 80% (4/5) | 60% (3/5) | 75% (15/20) |
| `gia_shipper` | lua_dao | 100% (5/5) | 40% (2/5) | 80% (16/20) |
| `mao_danh_nguoi_quen` | lua_dao | 100% (5/5) | 100% (5/5) | 100% (20/20) |

## Cặp nhầm nhiều nhất (kịch bản thật -> kết luận, sau 3 câu)

- `gemini-4-carbon` (v1): `bt_chuyen_cho_nguoi_than` -> `chua_du_can_cu` 2; `bt_mua_online_nguoi_ban_moi` -> `bt_tra_tien_nguoi_ban_quen` 1; `bt_dat_coc_da_xem` -> `mao_danh_nguoi_quen` 1; `bt_tra_tien_nguoi_ban_quen` -> `dau_tu_san_gia` 1; `bt_tra_tien_nguoi_ban_quen` -> `mao_danh_nguoi_quen` 1; `dat_coc_gia_re` -> `mao_danh_nguoi_quen` 1; `bt_tra_tien_nguoi_ban_quen` -> `bt_mua_online_nguoi_ban_moi` 1; `bao_nguoi_than_cap_cuu` -> `chua_du_can_cu` 1
- `gemini-3.5-flash-lite` (v1): `bt_mua_online_nguoi_ban_moi` -> `bt_tra_tien_nguoi_ban_quen` 2; `bao_nguoi_than_cap_cuu` -> `dich_vu_lay_lai_tien` 1; `bt_dat_coc_da_xem` -> `bt_chuyen_cho_nguoi_than` 1; `bt_chuyen_cho_nguoi_than` -> `mao_danh_nguoi_quen` 1; `ctv_online` -> `gia_ngan_hang` 1; `dat_coc_gia_re` -> `bt_chuyen_cho_nguoi_than` 1; `dat_coc_gia_re` -> `mao_danh_nguoi_quen` 1; `dat_coc_gia_re` -> `bt_mua_online_nguoi_ban_moi` 1
- `gemini-3.5-flash-lite` (300): `bt_tra_tien_nguoi_ban_quen` -> `bt_chuyen_cho_nguoi_than` 3; `dat_coc_gia_re` -> `bt_mua_online_nguoi_ban_moi` 3; `bao_nguoi_than_cap_cuu` -> `gia_shipper` 2; `bt_chuyen_cho_nguoi_than` -> `mao_danh_nguoi_quen` 2; `bt_mua_online_nguoi_ban_moi` -> `bt_tra_tien_nguoi_ban_quen` 2; `dat_coc_gia_re` -> `mao_danh_nguoi_quen` 2; `dich_vu_lay_lai_tien` -> `bt_mua_online_nguoi_ban_moi` 2; `gia_ngan_hang` -> `ctv_online` 2

## Chi phí API thật

| Model | Trợ lý (USD) | Nạn nhân giả lập (USD) |
|---|---|---|
| `gemini-3.5-flash-lite` | 0.331 | 0.054 |
| `gemini-3.8-flash@low` | 0.244 | 0.021 |
| `gemini-4-carbon` | 2.150 | 0.029 |
| `openai:gpt-6.2-sol` | 0.758 | 0.022 |

Sinh 225 tin mở đầu mới: 0.059 USD. Tổng E5: 3.67 USD (trần lần chạy 5.0 USD; trần Gemini chung cho E4, E5, E6 là 20 USD, GPT 3 USD).

