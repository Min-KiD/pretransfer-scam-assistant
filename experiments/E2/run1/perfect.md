### Phần 1: người trả lời hoàn hảo (200 bảng mỗi kịch bản, seed 20261121)

14 kịch bản nạp được (10 lừa đảo, 4 bình thường); 2800 phiên mỗi cách chọn. Mỗi bảng lấy mẫu từng trường theo đúng bảng xác suất của kịch bản đó; 4 trường do code điền biết từ đầu; người dùng trả lời đúng giá trị đã lấy mẫu. Sau k câu = trạng thái sau k câu, hoặc lúc dừng nếu đã dừng sớm (xác suất đứng đầu >= 0,7). Mẫu số là mọi phiên; phiên "chưa đủ căn cứ" tính là không đúng kịch bản và không đúng nhóm; đúng nhóm gồm cả đúng kịch bản.

File kịch bản bị bỏ vì lỗi (không tự sửa): `scenarios/gia_ngan_hang.yaml:2: YAML lỗi cú pháp: mapping values are not allowed here   in "<unicode string>", line 2, column 41:      ...  nhân viên ngân hàng, ví điện tử: nâng hạn mức, khóa tài khoản,  ...                                           ^`

| Cách chọn trường | Sau k câu | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ |
|---|---|---|---|---|
| entropy | 0 | 1.8% | 2.7% | 97.2% |
| entropy | 1 | 67.8% | 83.8% | 14.1% |
| entropy | 2 | 77.1% | 92.2% | 5.5% |
| entropy | 3 | 80.3% | 96.1% | 1.5% |
| ngẫu nhiên | 0 | 1.8% | 2.7% | 97.2% |
| ngẫu nhiên | 1 | 20.0% | 25.5% | 73.2% |
| ngẫu nhiên | 2 | 36.7% | 47.1% | 51.4% |
| ngẫu nhiên | 3 | 51.3% | 63.9% | 34.3% |

Số câu hỏi trung bình trước khi dừng (entropy): 1.33; ngẫu nhiên: 2.52.

**Theo kịch bản, sau 3 câu (entropy):**

| Kịch bản | Nhóm | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ | Kết luận "giống chiêu lừa" | Mong đợi |
|---|---|---|---|---|---|---|
| `bt_chuyen_cho_nguoi_than` | binh_thuong | 92.0% | 96.0% | 2.0% | 2.0% | giống bình thường |
| `bt_dat_coc_da_xem` | binh_thuong | 79.0% | 89.5% | 4.0% | 6.5% | giống bình thường |
| `bt_mua_online_nguoi_ban_moi` | binh_thuong | 58.0% | 81.5% | 4.5% | 14.0% | chưa đủ căn cứ |
| `bt_tra_tien_nguoi_ban_quen` | binh_thuong | 80.5% | 98.0% | 0.5% | 1.5% | giống bình thường |
| `bao_nguoi_than_cap_cuu` | lua_dao | 81.5% | 98.0% | 0.5% | 98.0% | giống chiêu lừa |
| `chuyen_nham_tien` | lua_dao | 84.0% | 99.5% | 0.5% | 99.5% | giống chiêu lừa |
| `ctv_online` | lua_dao | 84.5% | 99.0% | 1.0% | 99.0% | giống chiêu lừa |
| `dat_coc_gia_re` | lua_dao | 79.5% | 95.5% | 1.5% | 95.5% | giống chiêu lừa |
| `dau_tu_san_gia` | lua_dao | 82.5% | 98.5% | 1.5% | 98.5% | giống chiêu lừa |
| `dich_vu_lay_lai_tien` | lua_dao | 79.0% | 98.5% | 1.0% | 98.5% | giống chiêu lừa |
| `gia_co_quan_nha_nuoc` | lua_dao | 76.0% | 99.5% | 0.5% | 99.5% | giống chiêu lừa |
| `gia_cong_an` | lua_dao | 88.0% | 100.0% | 0.0% | 100.0% | giống chiêu lừa |
| `gia_shipper` | lua_dao | 82.0% | 97.5% | 1.5% | 97.5% | giống chiêu lừa |
| `mao_danh_nguoi_quen` | lua_dao | 78.0% | 95.0% | 1.5% | 95.0% | giống chiêu lừa |

Kịch bản bình thường bị kết luận "giống chiêu lừa" (trần E3): 6.0% (48/800).

**Cặp nhầm nhiều nhất (đáp án → kết luận, sau 3 câu, entropy):**

- `bt_mua_online_nguoi_ban_moi` → `bt_dat_coc_da_xem`: 33/200 (16.5%)
- `dich_vu_lay_lai_tien` → `gia_cong_an`: 22/200 (11.0%)
- `gia_co_quan_nha_nuoc` → `gia_cong_an`: 18/200 (9.0%)
- `bt_tra_tien_nguoi_ban_quen` → `bt_mua_online_nguoi_ban_moi`: 16/200 (8.0%)
- `bt_mua_online_nguoi_ban_moi` → `bt_tra_tien_nguoi_ban_quen`: 13/200 (6.5%)
- `bt_tra_tien_nguoi_ban_quen` → `bt_dat_coc_da_xem`: 12/200 (6.0%)
- `bt_mua_online_nguoi_ban_moi` → `dat_coc_gia_re`: 12/200 (6.0%)
- `bt_dat_coc_da_xem` → `bt_tra_tien_nguoi_ban_quen`: 11/200 (5.5%)

Ma trận nhầm (hàng: đáp án, cột: kết luận; số cột theo thứ tự hàng; `?` = chưa đủ căn cứ):

| Đáp án | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | ? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 `bt_chuyen_cho_nguoi_than` | 184 | 5 |  | 3 |  |  |  |  |  |  |  |  |  | 4 | 4 |
| 2 `bt_dat_coc_da_xem` | 6 | 158 | 4 | 11 | 3 |  | 1 | 6 |  | 2 | 1 |  |  |  | 8 |
| 3 `bt_mua_online_nguoi_ban_moi` | 1 | 33 | 116 | 13 | 2 | 1 | 2 | 12 | 2 | 1 | 2 | 2 |  | 4 | 9 |
| 4 `bt_tra_tien_nguoi_ban_quen` | 7 | 12 | 16 | 161 |  |  |  |  |  | 3 |  |  |  |  | 1 |
| 5 `bao_nguoi_than_cap_cuu` | 2 |  | 1 |  | 163 | 4 | 5 |  | 5 | 7 | 2 | 1 | 6 | 3 | 1 |
| 6 `chuyen_nham_tien` |  |  |  |  | 8 | 168 | 3 | 1 | 1 | 5 | 4 | 2 | 4 | 3 | 1 |
| 7 `ctv_online` |  |  |  |  | 5 | 3 | 169 | 5 | 3 | 5 | 3 | 1 | 2 | 2 | 2 |
| 8 `dat_coc_gia_re` |  | 2 | 4 |  | 1 | 4 | 3 | 159 | 4 | 4 | 3 | 5 | 4 | 4 | 3 |
| 9 `dau_tu_san_gia` |  |  |  |  | 4 | 4 | 3 | 3 | 165 | 4 | 5 |  | 5 | 4 | 3 |
| 10 `dich_vu_lay_lai_tien` |  | 1 |  |  | 3 | 2 |  | 3 | 2 | 158 | 3 | 22 | 2 | 2 | 2 |
| 11 `gia_co_quan_nha_nuoc` |  |  |  |  | 5 | 1 | 3 | 2 | 4 | 5 | 152 | 18 | 5 | 4 | 1 |
| 12 `gia_cong_an` |  |  |  |  | 3 | 4 | 2 | 2 | 5 | 2 | 3 | 176 | 2 | 1 |  |
| 13 `gia_shipper` |  |  | 2 |  | 4 | 1 | 4 | 2 | 2 | 4 | 4 | 5 | 164 | 5 | 3 |
| 14 `mao_danh_nguoi_quen` | 7 |  |  |  | 4 | 5 |  | 3 | 4 | 4 | 4 | 4 | 6 | 156 | 3 |
