# E2, E3 lần 2: lõi hỏi-đáp so với model tự hỏi, sau khi sửa khâu điền bảng

**Kết luận theo quy tắc (thiết kế 5.4):** `tinh_toan` kém `tu_do` 9.3 điểm % về đúng kịch bản sau 3 câu (69.3% so với 78.7%). Không đạt ngưỡng 5 điểm: đề xuất bỏ phần chọn câu hỏi, giữ bảng câu chuyện. Đây là số của một lần chạy, không chạy lại để chọn.

**Biến thể khai trước `tinh_toan_min1`** (hỏi ít nhất 1 câu khi chưa có ảnh), báo riêng, không thay cho dòng trên: `tinh_toan_min1` kém `tu_do` 9.3 điểm % về đúng kịch bản sau 3 câu (69.3% so với 78.7%).

75 tình huống thử chỉ có chữ (15 kịch bản x 5), model `gemini-3.5-flash-lite` cho cả trợ lý lẫn nạn nhân giả lập. Chi phí phần chạy này (trợ lý, nạn nhân, sinh tình huống): 0.45 USD (trần 2.0 USD), tính từ token thật theo giá niêm yết dùng ở E1. Kết quả lần đầu (70 tình huống, 14 kịch bản, trước khi sửa điền bảng) giữ nguyên ở `experiments/E2/run1/`; cột "lần 1" lấy từ đó.

**Đổi gì so với lần đầu:** `dien_bang` chỉ điền trường người dùng nói rõ; mỗi trường phải có `trich` chép nguyên văn và code bỏ trường nào có `trich` không nằm trong tin nhắn (so sau khi chuẩn hóa dấu cách, hoa thường); không suy `nguoi_lien_lac`, `ai_bat_dau`, `ap_luc`, `da_gap_truc_tiep` từ giọng điệu. Prompt chỉ được chỉnh trên 12 tin nhắn riêng ở `tests/fill_dev.json` (`python -m sim.fill_eval --dev`). Thêm 5 tình huống `gia_ngan_hang`; 70 tình huống cũ giữ nguyên. Thêm trợ lý `tinh_toan_min1`.

## 1. Trần của phương pháp: người trả lời hoàn hảo (Phần 1)

So với lần đầu (entropy; lần 1: 14 kịch bản, lần 2: 15 kịch bản):

| Sau k câu | Đúng kịch bản lần 2 | lần 1 | Đúng nhóm lần 2 | lần 1 | Chưa đủ căn cứ lần 2 | lần 1 |
|---|---|---|---|---|---|---|
| 0 | 1.6% | 1.8% | 2.5% | 2.7% | 97.4% | 97.2% |
| 1 | 68.4% | 67.8% | 86.3% | 83.8% | 11.5% | 14.1% |
| 2 | 76.1% | 77.1% | 92.8% | 92.2% | 5.0% | 5.5% |
| 3 | 79.1% | 80.3% | 96.4% | 96.1% | 1.3% | 1.5% |


15 kịch bản nạp được (11 lừa đảo, 4 bình thường); 3000 phiên mỗi cách chọn. Mỗi bảng lấy mẫu từng trường theo đúng bảng xác suất của kịch bản đó; 4 trường do code điền biết từ đầu; người dùng trả lời đúng giá trị đã lấy mẫu. Sau k câu = trạng thái sau k câu, hoặc lúc dừng nếu đã dừng sớm (xác suất đứng đầu >= 0,7). Mẫu số là mọi phiên; phiên "chưa đủ căn cứ" tính là không đúng kịch bản và không đúng nhóm; đúng nhóm gồm cả đúng kịch bản.

| Cách chọn trường | Sau k câu | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ |
|---|---|---|---|---|
| entropy | 0 | 1.6% | 2.5% | 97.4% |
| entropy | 1 | 68.4% | 86.3% | 11.5% |
| entropy | 2 | 76.1% | 92.8% | 5.0% |
| entropy | 3 | 79.1% | 96.4% | 1.3% |
| ngẫu nhiên | 0 | 1.6% | 2.5% | 97.4% |
| ngẫu nhiên | 1 | 19.4% | 24.8% | 74.0% |
| ngẫu nhiên | 2 | 35.5% | 45.9% | 52.9% |
| ngẫu nhiên | 3 | 49.4% | 62.4% | 35.9% |

Số câu hỏi trung bình trước khi dừng (entropy): 1.31; ngẫu nhiên: 2.54.

**Theo kịch bản, sau 3 câu (entropy):**

| Kịch bản | Nhóm | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ | Kết luận "giống chiêu lừa" | Mong đợi |
|---|---|---|---|---|---|---|
| `bt_chuyen_cho_nguoi_than` | binh_thuong | 92.0% | 96.0% | 1.5% | 2.5% | giống bình thường |
| `bt_dat_coc_da_xem` | binh_thuong | 79.0% | 90.0% | 3.5% | 6.5% | giống bình thường |
| `bt_mua_online_nguoi_ban_moi` | binh_thuong | 58.0% | 81.5% | 4.0% | 14.5% | chưa đủ căn cứ |
| `bt_tra_tien_nguoi_ban_quen` | binh_thuong | 80.5% | 98.0% | 0.5% | 1.5% | giống bình thường |
| `bao_nguoi_than_cap_cuu` | lua_dao | 80.0% | 97.5% | 1.0% | 97.5% | giống chiêu lừa |
| `chuyen_nham_tien` | lua_dao | 76.5% | 99.0% | 1.0% | 99.0% | giống chiêu lừa |
| `ctv_online` | lua_dao | 83.5% | 99.0% | 1.0% | 99.0% | giống chiêu lừa |
| `dat_coc_gia_re` | lua_dao | 78.5% | 95.5% | 1.5% | 95.5% | giống chiêu lừa |
| `dau_tu_san_gia` | lua_dao | 80.5% | 99.0% | 1.0% | 99.0% | giống chiêu lừa |
| `dich_vu_lay_lai_tien` | lua_dao | 78.5% | 98.5% | 1.0% | 98.5% | giống chiêu lừa |
| `gia_co_quan_nha_nuoc` | lua_dao | 76.0% | 99.5% | 0.5% | 99.5% | giống chiêu lừa |
| `gia_cong_an` | lua_dao | 86.5% | 100.0% | 0.0% | 100.0% | giống chiêu lừa |
| `gia_ngan_hang` | lua_dao | 79.5% | 99.0% | 0.5% | 99.0% | giống chiêu lừa |
| `gia_shipper` | lua_dao | 80.5% | 98.0% | 1.0% | 98.0% | giống chiêu lừa |
| `mao_danh_nguoi_quen` | lua_dao | 77.5% | 95.5% | 1.0% | 95.5% | giống chiêu lừa |

Kịch bản bình thường bị kết luận "giống chiêu lừa" (trần E3): 6.2% (50/800).

**Cặp nhầm nhiều nhất (đáp án → kết luận, sau 3 câu, entropy):**

- `bt_mua_online_nguoi_ban_moi` → `bt_dat_coc_da_xem`: 33/200 (16.5%)
- `dich_vu_lay_lai_tien` → `gia_cong_an`: 21/200 (10.5%)
- `chuyen_nham_tien` → `gia_ngan_hang`: 20/200 (10.0%)
- `bt_tra_tien_nguoi_ban_quen` → `bt_mua_online_nguoi_ban_moi`: 16/200 (8.0%)
- `gia_co_quan_nha_nuoc` → `gia_cong_an`: 15/200 (7.5%)
- `bt_mua_online_nguoi_ban_moi` → `bt_tra_tien_nguoi_ban_quen`: 13/200 (6.5%)
- `bt_tra_tien_nguoi_ban_quen` → `bt_dat_coc_da_xem`: 12/200 (6.0%)
- `bt_mua_online_nguoi_ban_moi` → `dat_coc_gia_re`: 12/200 (6.0%)

Ma trận nhầm (hàng: đáp án, cột: kết luận; số cột theo thứ tự hàng; `?` = chưa đủ căn cứ):

| Đáp án | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | ? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 `bt_chuyen_cho_nguoi_than` | 184 | 5 |  | 3 |  |  |  |  |  |  |  |  | 1 |  | 4 | 3 |
| 2 `bt_dat_coc_da_xem` | 6 | 158 | 5 | 11 | 3 |  |  | 6 |  | 2 | 1 |  | 1 |  |  | 7 |
| 3 `bt_mua_online_nguoi_ban_moi` | 1 | 33 | 116 | 13 | 2 | 1 | 2 | 12 | 2 | 1 | 2 | 2 | 1 |  | 4 | 8 |
| 4 `bt_tra_tien_nguoi_ban_quen` | 7 | 12 | 16 | 161 |  |  |  |  |  | 3 |  |  |  |  |  | 1 |
| 5 `bao_nguoi_than_cap_cuu` | 2 |  | 1 |  | 160 | 3 | 5 |  | 5 | 7 | 2 |  | 5 | 5 | 3 | 2 |
| 6 `chuyen_nham_tien` |  |  |  |  | 7 | 153 | 1 | 1 | 1 | 4 | 3 | 2 | 20 | 4 | 2 | 2 |
| 7 `ctv_online` |  |  |  |  | 5 | 3 | 167 | 5 | 3 | 5 | 3 | 1 | 2 | 2 | 2 | 2 |
| 8 `dat_coc_gia_re` |  | 2 | 4 |  | 1 | 4 | 2 | 157 | 4 | 4 | 3 | 5 | 3 | 4 | 4 | 3 |
| 9 `dau_tu_san_gia` |  |  |  |  | 4 | 4 | 2 | 3 | 161 | 4 | 5 |  | 6 | 5 | 4 | 2 |
| 10 `dich_vu_lay_lai_tien` |  | 1 |  |  | 2 | 2 |  | 3 | 1 | 157 | 3 | 21 | 4 | 2 | 2 | 2 |
| 11 `gia_co_quan_nha_nuoc` |  |  |  |  | 5 | 1 | 3 | 2 | 4 | 5 | 152 | 15 | 3 | 5 | 4 | 1 |
| 12 `gia_cong_an` |  |  |  |  | 3 | 4 | 2 | 2 | 4 | 1 | 3 | 173 | 5 | 2 | 1 |  |
| 13 `gia_ngan_hang` |  |  | 1 |  | 4 | 3 | 3 | 7 | 5 | 3 | 4 | 4 | 159 | 4 | 2 | 1 |
| 14 `gia_shipper` |  |  | 2 |  | 4 | 1 | 4 | 2 | 2 | 4 | 4 | 5 | 4 | 161 | 5 | 2 |
| 15 `mao_danh_nguoi_quen` | 7 |  |  |  | 4 | 5 |  | 2 | 4 | 4 | 4 | 4 | 3 | 6 | 155 | 2 |

## 2. Khâu điền bảng: trước và sau khi sửa

Một lần gọi `dien_bang` trên tin mở đầu của 75 tình huống (`python -m sim.fill_eval --openings`; prompt lần 1 chép nguyên trong file đó để đo):

| | Prompt lần 1 | Prompt lần 2 |
|---|---|---|
| Số trường điền TB sau tin mở đầu | 4.35 | 3.89 |
| Trường có `trich` không nằm trong tin nhắn | 4 (lần 1 không kiểm, vẫn điền) | 0 (bị bỏ) |
| Số tin mở đầu điền `nguoi_lien_lac` | 21 | 20 |
| Số tin mở đầu điền `kenh` | 52 | 46 |
| Số tin mở đầu điền `tu_xung` | 38 | 44 |
| Số tin mở đầu điền `ai_bat_dau` | 19 | 8 |
| Số tin mở đầu điền `ap_luc` | 51 | 32 |
| Số tin mở đầu điền `yeu_cau` | 64 | 62 |
| Số tin mở đầu điền `ly_do_tien` | 64 | 72 |
| Số tin mở đầu điền `da_gap_truc_tiep` | 9 | 5 |
| Số tin mở đầu điền `duoc_dan_cach_tra_loi` | 3 | 2 |
| Số tin mở đầu điền `da_chuyen_truoc_do` | 5 | 1 |

Trong phiên chạy chính (mọi lần gọi `dien_bang`, cả tin mở đầu lẫn câu trả lời):

| Trợ lý | Trường điền TB sau tin mở đầu | Số lần gọi | Trường được giữ | Trường bị bỏ vì `trich` không có trong tin nhắn |
|---|---|---|---|---|
| tinh_toan | 3.87 | 129 | 367 | 4 |
| tinh_toan_min1 | 3.80 | 181 | 422 | 4 |

## 3. Nạn nhân giả lập (Phần 5)

Mẫu số là mọi phiên; phiên "chưa đủ căn cứ" tính là không đúng kịch bản và không đúng nhóm; đúng nhóm gồm cả đúng kịch bản. Sau k câu = dự đoán khi đã hỏi k câu, hoặc kết luận cuối nếu trợ lý dừng sớm hơn. Ngoặc vuông: khoảng tin cậy 95% bootstrap theo tình huống (2000 lần). Lần 1: 70 tình huống, không có `gia_ngan_hang`.

| Trợ lý | Sau k câu | Đúng kịch bản | lần 1 | Đúng nhóm | lần 1 | Chưa đủ căn cứ | lần 1 |
|---|---|---|---|---|---|---|---|
| tinh_toan | 0 | 58.7% [46.7-69.3] | 58.6% | 78.7% [69.3-88.0] | 77.1% | 18.7% [10.7-28.0] | 18.6% |
| tinh_toan | 1 | 68.0% [57.3-78.7] | 67.1% | 86.7% [78.7-93.3] | 87.1% | 6.7% [1.3-13.3] | 8.6% |
| tinh_toan | 2 | 68.0% [57.3-78.7] | 70.0% | 89.3% [82.7-96.0] | 91.4% | 4.0% [0.0-9.3] | 4.3% |
| tinh_toan | 3 | 69.3% [58.7-80.0] | 71.4% | 89.3% [81.3-96.0] | 94.3% | 2.7% [0.0-6.7] | 2.9% |
| tinh_toan_min1 | 0 | 54.7% [44.0-65.3] | - | 73.3% [62.7-82.7] | - | 25.3% [16.0-36.0] | - |
| tinh_toan_min1 | 1 | 72.0% [61.3-81.3] | - | 89.3% [81.3-96.0] | - | 6.7% [1.3-13.3] | - |
| tinh_toan_min1 | 2 | 68.0% [57.3-78.7] | - | 89.3% [81.3-96.0] | - | 6.7% [1.3-13.3] | - |
| tinh_toan_min1 | 3 | 69.3% [58.7-80.0] | - | 94.7% [89.3-98.7] | - | 1.3% [0.0-4.0] | - |
| tu_do | 0 | 74.7% [64.0-84.0] | 72.9% | 86.7% [78.7-93.3] | 87.1% | 6.7% [1.3-13.3] | 5.7% |
| tu_do | 1 | 80.0% [69.3-89.3] | 77.1% | 92.0% [85.3-97.3] | 91.4% | 0.0% [0.0-0.0] | 0.0% |
| tu_do | 2 | 80.0% [69.3-89.3] | 75.7% | 93.3% [86.7-98.7] | 91.4% | 0.0% [0.0-0.0] | 1.4% |
| tu_do | 3 | 78.7% [69.3-88.0] | 75.7% | 92.0% [85.3-97.3] | 92.9% | 0.0% [0.0-0.0] | 0.0% |

Chỉ trên 70 tình huống chung với lần 1, đúng kịch bản sau 3 câu: `tinh_toan` 72.9%; `tinh_toan_min1` 71.4%; `tu_do` 80.0%.

| Trợ lý | E3: bình thường bị kết luận "giống chiêu lừa" | lần 1 | Kịch bản khó phân biệt (mong đợi "chưa đủ căn cứ") | Số câu hỏi TB | lần 1 | Giây TB/phiên (chỉ phía trợ lý) | Token TB/phiên | USD TB/phiên |
|---|---|---|---|---|---|---|---|---|
| tinh_toan | 25.0% [5.0-45.0] (n=20) | 10.0% (n=20) | binh_thuong: 3, lua_dao: 2 | 0.72 | 0.63 | 2.8 | 3109 | 0.0017 |
| tinh_toan_min1 | 10.0% [0.0-25.0] (n=20) | - | binh_thuong: 5 | 1.41 | - | 3.8 | 4295 | 0.0022 |
| tu_do | 5.0% [0.0-15.0] (n=20) | 5.0% (n=20) | binh_thuong: 5 | 0.64 | 0.87 | 1.3 | 3179 | 0.0011 |

**Dừng sau mấy câu, và kết luận cuối đúng kịch bản bao nhiêu (số phiên, tỉ lệ đúng):**

| Trợ lý | Dừng sau 0 câu | Dừng sau 1 câu | Dừng sau 2 câu | Dừng sau 3 câu |
|---|---|---|---|---|
| tinh_toan | 46, 76.1% | 14, 64.3% | 5, 80.0% | 10, 40.0% |
| tinh_toan_min1 | 0 | 57, 77.2% | 5, 60.0% | 13, 38.5% |
| tu_do | 37, 83.8% | 30, 73.3% | 6, 83.3% | 2, 50.0% |
| tinh_toan (lần 1) | 44, 79.5% | 15, 60.0% | 4, 25.0% | 7, 71.4% |
| tu_do (lần 1) | 27, 81.5% | 28, 82.1% | 12, 58.3% | 3, 33.3% |

**Theo kịch bản, sau 3 câu (số tình huống đúng kịch bản / 5):**

| Kịch bản | Nhóm | tinh_toan | tinh_toan_min1 | tu_do | tinh_toan lần 1 | tu_do lần 1 |
|---|---|---|---|---|---|---|
| `bt_chuyen_cho_nguoi_than` | binh_thuong | 3/5 | 2/5 | 5/5 | 4/5 | 4/5 |
| `bt_dat_coc_da_xem` | binh_thuong | 4/5 | 4/5 | 4/5 | 4/5 | 4/5 |
| `bt_mua_online_nguoi_ban_moi` | binh_thuong | 1/5 | 3/5 | 4/5 | 0/5 | 3/5 |
| `bt_tra_tien_nguoi_ban_quen` | binh_thuong | 4/5 | 3/5 | 3/5 | 4/5 | 4/5 |
| `bao_nguoi_than_cap_cuu` | lua_dao | 5/5 | 5/5 | 4/5 | 5/5 | 4/5 |
| `chuyen_nham_tien` | lua_dao | 5/5 | 5/5 | 5/5 | 5/5 | 3/5 |
| `ctv_online` | lua_dao | 4/5 | 3/5 | 4/5 | 4/5 | 4/5 |
| `dat_coc_gia_re` | lua_dao | 1/5 | 2/5 | 2/5 | 2/5 | 2/5 |
| `dau_tu_san_gia` | lua_dao | 4/5 | 4/5 | 4/5 | 3/5 | 4/5 |
| `dich_vu_lay_lai_tien` | lua_dao | 4/5 | 5/5 | 4/5 | 3/5 | 4/5 |
| `gia_co_quan_nha_nuoc` | lua_dao | 2/5 | 2/5 | 5/5 | 2/5 | 5/5 |
| `gia_cong_an` | lua_dao | 5/5 | 5/5 | 4/5 | 5/5 | 4/5 |
| `gia_ngan_hang` | lua_dao | 1/5 | 2/5 | 3/5 | - | - |
| `gia_shipper` | lua_dao | 4/5 | 3/5 | 3/5 | 4/5 | 3/5 |
| `mao_danh_nguoi_quen` | lua_dao | 5/5 | 4/5 | 5/5 | 5/5 | 5/5 |

## 4. Năm phiên sai điển hình của `tinh_toan` (nguyên hội thoại)

### `bt_chuyen_cho_nguoi_than__0` (tính cách voi): đáp án `bt_chuyen_cho_nguoi_than`, kết luận `mao_danh_nguoi_quen` (lua_dao); đã hỏi không câu nào

- **Người dùng:** Chuyển tiền cho bạn mượn thêm chứ gì nữa, hỏi lắm thế. Làm ơn cho qua nhanh giùm cái!
- **Trợ lý:** Tình huống này giống chiêu lừa "Chiếm hoặc giả tài khoản Zalo, Facebook của người quen để mượn tiền". Bạn đã kể việc đưa ra lý do phải chuyển tiền là "Chuyển tiền cho bạn mượn thêm chứ gì nữa" và tài khoản nhận là cá nhân. Trước khi chuyển, bạn nên gọi điện thường theo số đã lưu trong danh bạ, không gọi qua chính ứng dụng đó.

### `bt_dat_coc_da_xem__1` (tính cách ca_tin): đáp án `bt_dat_coc_da_xem`, kết luận `bt_chuyen_cho_nguoi_than` (binh_thuong); đã hỏi không câu nào

- **Người dùng:** À, tôi chuyển chút tiền viện phí giúp đứa bạn thân vừa gọi điện nhờ lúc nãy, nó đang kẹt quá mà hai đứa vừa gặp nhau xong nên tôi gửi luôn cho nhanh.
- **Trợ lý:** Tình huống bạn chia sẻ giống giao dịch bình thường vì đã gặp trực tiếp người nhận và gọi điện liên lạc, đúng như bạn kể "hai đứa vừa gặp nhau xong nên tôi gửi luôn cho nhanh". Cảm ơn bạn và chúc bạn một ngày tốt lành!

### `bt_mua_online_nguoi_ban_moi__0` (tính cách voi): đáp án `bt_mua_online_nguoi_ban_moi`, kết luận `gia_shipper` (lua_dao); đã hỏi tu_xung, nguoi_lien_lac

- **Người dùng:** Mua đồ trên mạng thôi, giục em làm gì lắm thế.
- **Trợ lý:** Người bán hàng online này tự xưng là ai vậy bạn, gửi ảnh tin nhắn nếu tiện nhé?
- **Người dùng:** Bạn bè gì đâu, người bán hàng trên Messenger thôi mà, hỏi mãi thế.
- **Trợ lý:** Người này là người quen hay người lạ với bạn vậy?
- **Người dùng:** Người lạ chứ quen gì, hỏi lắm thế.
- **Trợ lý:** Tình huống của bạn giống chiêu "Giả shipper đòi tiền hàng, rồi báo chuyển nhầm để đòi chuyển thêm". Bạn đã gặp điểm trùng là lý do phải chuyển tiền ("Mua đồ trên mạng thôi"). Trước khi chuyển, bạn nên mở app mua hàng xem có đơn nào đang giao, mã đơn và số tiền có trùng không.

### `bt_tra_tien_nguoi_ban_quen__4` (tính cách voi): đáp án `bt_tra_tien_nguoi_ban_quen`, kết luận `mao_danh_nguoi_quen` (lua_dao); đã hỏi nguoi_lien_lac, da_gap_truc_tiep, tu_xung

- **Người dùng:** Trả hàng cho bạn thôi, chuyển nhanh giùm cái đang vội.
- **Trợ lý:** Người này là người quen hay người lạ mà bạn muốn chuyển tiền?
- **Người dùng:** Người quen.
- **Trợ lý:** Bạn đã bao giờ gặp trực tiếp người này ngoài đời chưa?
- **Người dùng:** Chưa gặp, mà hỏi gì lắm thế, lẹ lên xem nào.
- **Trợ lý:** Người này tự xưng là ai vậy, hay bạn gửi ảnh chụp tin nhắn cho nhanh nhé?
- **Người dùng:** Bạn bè chứ ai, lẹ lên cái coi, trễ giờ của tôi rồi.
- **Trợ lý:** Tình huống bạn gặp rất giống chiêu trò chiếm hoặc giả tài khoản Zalo, Facebook của người quen để mượn tiền. Bạn đã kể việc có "người quen", "bạn bè chứ ai", cùng với việc bị hối thúc "chuyển nhanh giùm cái đang vội". Trước khi chuyển tiền, bạn nên gọi điện thường theo số đã lưu trong danh bạ, không gọi qua chính ứng dụng đó.

### `ctv_online__0` (tính cách voi): đáp án `ctv_online`, kết luận `gia_ngan_hang` (lua_dao); đã hỏi tu_xung, ap_luc, ai_bat_dau

- **Người dùng:** Chuyển tiền mở khóa tài khoản bên ngân hàng trên Zalo, anh đừng hỏi nhiều nữa, nhanh hộ em cái.
- **Trợ lý:** Người yêu cầu chuyển tiền tự xưng là ai vậy bạn, gửi ảnh tin nhắn nếu tiện nhé?
- **Người dùng:** Nhân viên ngân hàng trên Zalo chứ ai, họ hối với hứa cho rút tiền gốc nên cứ chuyển lẹ giùm em cái.
- **Trợ lý:** Họ có hối thúc, dọa dẫm, hứa hẹn lợi ích hay bảo bạn giữ bí mật không, gửi ảnh tin nhắn nếu tiện nhé?
- **Người dùng:** Có, họ hối thúc với hứa hẹn đủ thứ, anh mau chuyển giùm em cái đi.
- **Trợ lý:** Lúc đầu bạn hay họ chủ động liên lạc trước, gửi ảnh tin nhắn nếu tiện nhé?
- **Người dùng:** Họ chủ động liên lạc trước, anh cứ bấm chuyển nhanh giùm em cái đang vội lắm rồi.
- **Trợ lý:** Tình huống này giống chiêu giả nhân viên ngân hàng. Bạn đã gặp việc họ chủ động liên lạc trước, tự xưng là nhân viên ngân hàng và yêu cầu chuyển tiền để mở khóa tài khoản. Trước khi chuyển, bạn nên cúp máy, gọi số tổng đài in trên thẻ hoặc trong app chính thức để kiểm tra lại.

## 5. Chạy lại

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # một lần
.venv/bin/python -m pytest -q                      # unit test
.venv/bin/python -m sim.perfect                    # Phần 1, không tốn tiền
.venv/bin/python -m sim.fill_eval --dev            # bộ phát triển của prompt điền bảng
.venv/bin/python -m sim.fill_eval --openings       # số trường điền từ tin mở đầu, prompt lần 1 và lần 2
.venv/bin/python -m sim.cases                      # chỉ sinh file còn thiếu trong sim/cases/
.venv/bin/python -m sim.run --fresh --cap-usd 2    # Phần 5: ba trợ lý, viết report này
```

## 6. Giới hạn

- Nạn nhân giả lập và trợ lý dùng cùng một model, và nạn nhân được đọc mô tả kịch bản: lời kể có thể giống lời mô tả hơn người thật, làm số đo đẹp hơn thực tế.
- Bảng câu chuyện thật của mỗi tình huống được lấy mẫu từng trường độc lập từ bảng xác suất của kịch bản, giống Phần 1: số đo cho biết lõi dùng bảng đó tốt đến đâu, không cho biết bảng đó có đúng với chiêu lừa ngoài đời không, và có những câu chuyện không tự nhiên.
- 5 tình huống mỗi kịch bản là ít: một tình huống sai đổi tỉ lệ của kịch bản đó 20 điểm %. Lần 1 và lần 2 khác nhau cả lời nạn nhân giả lập (model sinh lại mỗi lần), không chỉ ở khâu điền bảng.
- Bộ phát triển của prompt chỉ có 12 tin nhắn do tab code tự viết.
- Ba trường tra cứu (nhãn, loại tài khoản, tên chủ tài khoản khớp hay không) được coi là đã biết từ đầu ở cả ba trợ lý. Trong app, `ten_khop_tu_xung` chỉ được code điền khi người kia tự xưng là một tổ chức.
- Chưa có ảnh trong tình huống thử; chưa có tính cách "bị dặn trước" (để cho E8, trước đây mang mã E4).

