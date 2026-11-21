# E2, E3 lần đầu: lõi hỏi-đáp so với model tự hỏi

**Kết luận theo quy tắc (thiết kế 5.4):** `tinh_toan` kém `tu_do` 4.3 điểm % về đúng kịch bản sau 3 câu (71.4% so với 75.7%). Không đạt ngưỡng 5 điểm: đề xuất bỏ phần chọn câu hỏi, giữ bảng câu chuyện. Đây là số của một lần chạy, không chạy lại để chọn.

70 tình huống thử chỉ có chữ (14 kịch bản x 5), model `gemini-3.5-flash-lite` cho cả trợ lý lẫn nạn nhân giả lập. Chi phí cả Phần 5: 0.25 USD (trần 5.0 USD), tính từ token thật theo giá niêm yết dùng ở E1.

Kịch bản bị bỏ vì file lỗi (không tự sửa, đã báo tab kế hoạch): `scenarios/gia_ngan_hang.yaml:2: YAML lỗi cú pháp: mapping values are not allowed here`

## 1. Trần của phương pháp: người trả lời hoàn hảo (Phần 1)


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

## 2. Nạn nhân giả lập (Phần 5)

Mẫu số là mọi phiên; phiên "chưa đủ căn cứ" tính là không đúng kịch bản và không đúng nhóm; đúng nhóm gồm cả đúng kịch bản. Sau k câu = dự đoán khi đã hỏi k câu, hoặc kết luận cuối nếu trợ lý dừng sớm hơn. Ngoặc vuông: khoảng tin cậy 95% bootstrap theo tình huống (2000 lần).

| Trợ lý | Sau k câu | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ |
|---|---|---|---|---|
| tinh_toan | 0 | 58.6% [47.1-70.0] | 77.1% [67.1-85.7] | 18.6% [10.0-28.6] |
| tinh_toan | 1 | 67.1% [55.7-78.6] | 87.1% [78.6-94.3] | 8.6% [2.9-15.7] |
| tinh_toan | 2 | 70.0% [58.6-80.0] | 91.4% [84.3-97.1] | 4.3% [0.0-10.0] |
| tinh_toan | 3 | 71.4% [60.0-81.4] | 94.3% [88.6-98.6] | 2.9% [0.0-7.1] |
| tu_do | 0 | 72.9% [62.9-82.9] | 87.1% [78.6-94.3] | 5.7% [1.4-11.4] |
| tu_do | 1 | 77.1% [67.1-87.1] | 91.4% [84.3-97.1] | 0.0% [0.0-0.0] |
| tu_do | 2 | 75.7% [65.7-85.7] | 91.4% [84.3-97.1] | 1.4% [0.0-4.3] |
| tu_do | 3 | 75.7% [65.7-85.7] | 92.9% [87.1-98.6] | 0.0% [0.0-0.0] |

| Trợ lý | E3: bình thường bị kết luận "giống chiêu lừa" | Kịch bản khó phân biệt (mong đợi "chưa đủ căn cứ") | Số câu hỏi TB | Giây TB/phiên (chỉ phía trợ lý) | Token TB/phiên | USD TB/phiên |
|---|---|---|---|---|---|---|
| tinh_toan | 10.0% [0.0-25.0] (n=20) | binh_thuong: 3, lua_dao: 1, chưa đủ căn cứ: 1 | 0.63 | 3.7 | 2613 | 0.0018 |
| tu_do | 5.0% [0.0-15.0] (n=20) | binh_thuong: 5 | 0.87 | 1.9 | 3449 | 0.0012 |

**Dừng sau mấy câu, và kết luận cuối đúng kịch bản bao nhiêu (số phiên, tỉ lệ đúng):**

| Trợ lý | Dừng sau 0 câu | Dừng sau 1 câu | Dừng sau 2 câu | Dừng sau 3 câu |
|---|---|---|---|---|
| tinh_toan | 44, 79.5% | 15, 60.0% | 4, 25.0% | 7, 71.4% |
| tu_do | 27, 81.5% | 28, 82.1% | 12, 58.3% | 3, 33.3% |

**Theo kịch bản, sau 3 câu (số tình huống đúng kịch bản / 5):**

| Kịch bản | Nhóm | tinh_toan | tu_do |
|---|---|---|---|
| `bt_chuyen_cho_nguoi_than` | binh_thuong | 4/5 | 4/5 |
| `bt_dat_coc_da_xem` | binh_thuong | 4/5 | 4/5 |
| `bt_mua_online_nguoi_ban_moi` | binh_thuong | 0/5 | 3/5 |
| `bt_tra_tien_nguoi_ban_quen` | binh_thuong | 4/5 | 4/5 |
| `bao_nguoi_than_cap_cuu` | lua_dao | 5/5 | 4/5 |
| `chuyen_nham_tien` | lua_dao | 5/5 | 3/5 |
| `ctv_online` | lua_dao | 4/5 | 4/5 |
| `dat_coc_gia_re` | lua_dao | 2/5 | 2/5 |
| `dau_tu_san_gia` | lua_dao | 3/5 | 4/5 |
| `dich_vu_lay_lai_tien` | lua_dao | 3/5 | 4/5 |
| `gia_co_quan_nha_nuoc` | lua_dao | 2/5 | 5/5 |
| `gia_cong_an` | lua_dao | 5/5 | 4/5 |
| `gia_shipper` | lua_dao | 4/5 | 3/5 |
| `mao_danh_nguoi_quen` | lua_dao | 5/5 | 5/5 |

## 3. Năm phiên sai điển hình của `tinh_toan` (nguyên hội thoại)

### `bt_chuyen_cho_nguoi_than__0` (tính cách voi): đáp án `bt_chuyen_cho_nguoi_than`, kết luận `mao_danh_nguoi_quen` (lua_dao); đã hỏi không câu nào

- **Người dùng:** Chuyển tiền cho bạn mượn thêm chứ gì nữa, hỏi lắm thế. Làm ơn cho qua nhanh giùm cái!
- **Trợ lý:** Tình huống bạn kể giống chiêu "Chiếm hoặc giả tài khoản Zalo, Facebook của người quen để mượn tiền". Điểm trùng là tên chủ tài khoản nhận không khớp và có lý do mượn tiền ("Chuyển tiền cho bạn mượn thêm chứ gì nữa"). Trước khi thực hiện giao dịch, bạn nên gọi điện thường theo số đã lưu trong danh bạ, không gọi qua chính ứng dụng đó.

### `bt_dat_coc_da_xem__1` (tính cách ca_tin): đáp án `bt_dat_coc_da_xem`, kết luận `bt_chuyen_cho_nguoi_than` (binh_thuong); đã hỏi không câu nào

- **Người dùng:** À, tôi chuyển chút tiền viện phí giúp đứa bạn thân vừa gọi điện nhờ lúc nãy, nó đang kẹt quá mà hai đứa vừa gặp nhau xong nên tôi gửi luôn cho nhanh.
- **Trợ lý:** Tình huống bạn kể giống giao dịch bình thường vì đã gặp trực tiếp người nhận tiền ("hai đứa vừa gặp nhau xong nên tôi gửi luôn") và liên lạc qua cuộc gọi ("vừa gọi điện nhờ lúc nãy"). Tên chủ tài khoản đúng là người thân và đã nghe giọng hoặc gặp mặt. Tình huống giống giao dịch bình thường; không làm phiền thêm.

### `bt_mua_online_nguoi_ban_moi__0` (tính cách voi): đáp án `bt_mua_online_nguoi_ban_moi`, kết luận `mao_danh_nguoi_quen` (lua_dao); đã hỏi tu_xung

- **Người dùng:** Mua đồ trên mạng thôi, giục em làm gì lắm thế.
- **Trợ lý:** Người bán hàng trên mạng tự xưng là ai vậy bạn, hoặc bạn gửi ảnh tin nhắn nhé?
- **Người dùng:** Nó là bạn em trên Messenger thôi, nhanh lên em còn bận.
- **Trợ lý:** Tình huống này giống chiêu "Chiếm hoặc giả tài khoản Zalo, Facebook của người quen để mượn tiền". Bạn đã kể điểm trùng là liên lạc qua messenger và người kia có hối thúc ("nhanh len em con ban"). Trước khi chuyển, bạn nên gọi điện thường theo số đã lưu trong danh bạ, không gọi qua chính ứng dụng đó.

### `bt_tra_tien_nguoi_ban_quen__4` (tính cách voi): đáp án `bt_tra_tien_nguoi_ban_quen`, kết luận `bt_mua_online_nguoi_ban_moi` (binh_thuong); đã hỏi da_gap_truc_tiep

- **Người dùng:** Trả hàng cho bạn thôi, chuyển nhanh giùm cái đang vội.
- **Trợ lý:** Bạn đã gặp trực tiếp người nhận tiền này lần nào chưa?
- **Người dùng:** Chưa gặp bao giờ, nhanh lên nha.
- **Trợ lý:** Tình huống bạn kể là mua hàng online của người bán chưa từng mua, chuyển khoản trước, trả hàng và tài khoản nhận là tổ chức, giống giao dịch bình thường. Tình huống này giống giao dịch bình thường; không làm phiền thêm.

### `ctv_online__0` (tính cách voi): đáp án `ctv_online`, kết luận `chuyen_nham_tien` (lua_dao); đã hỏi tu_xung, nguoi_lien_lac, da_chuyen_truoc_do

- **Người dùng:** Chuyển tiền mở khóa tài khoản bên ngân hàng trên Zalo, anh đừng hỏi nhiều nữa, nhanh hộ em cái.
- **Trợ lý:** Người kia tự xưng là ai vậy, bạn gửi ảnh chụp tin nhắn giúp mình nhé?
- **Người dùng:** Người ta bảo là bên ngân hàng, tôi đang vội nên không chụp ảnh đâu, cứ chuyển nhanh giùm cái.
- **Trợ lý:** Bạn có quen người nhận khoản tiền này ở ngoài đời không?
- **Người dùng:** Không quen, tôi chưa gặp ngoài đời bao giờ, mau bấm chuyển giùm cái đi!
- **Trợ lý:** Bạn đã từng chuyển tiền cho người hoặc nhóm này trước đây chưa?
- **Người dùng:** Chưa, đây là lần đầu tôi chuyển, mà lẹ lên giùm cái coi, tôi đang vội lắm rồi.
- **Trợ lý:** Tình huống bạn kể giống chiêu "Cố ý "chuyển nhầm" tiền rồi đòi hoàn vào tài khoản khác hoặc đòi lãi". Bạn đã gặp các điểm trùng như: "Người ta bảo là bên ngân hàng", "Chưa, đây là lần đầu tôi chuyển", và "Chuyển tiền mở khóa tài khoản bên ngân hàng trên Zalo". Do có dấu hiệu "Yêu cầu hoàn vào tài khoản khác với tài khoản đã chuyển tới", bạn nên kiểm tra: So số tài khoản được yêu cầu hoàn với số tài khoản đã gửi tiền tới.

## 4. Chạy lại

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # một lần
.venv/bin/python -m pytest -q                      # unit test
.venv/bin/python -m sim.perfect                    # Phần 1, không tốn tiền
.venv/bin/python -m sim.cases                      # chỉ sinh file còn thiếu trong sim/cases/
.venv/bin/python -m sim.run --fresh                # Phần 5: chạy lại hai trợ lý, viết report này
```

## 5. Giới hạn

- Nạn nhân giả lập và trợ lý dùng cùng một model, và nạn nhân được đọc mô tả kịch bản: lời kể có thể giống lời mô tả hơn người thật, làm số đo đẹp hơn thực tế.
- Bảng câu chuyện thật của mỗi tình huống được lấy mẫu từ chính bảng xác suất của kịch bản, giống Phần 1: số đo cho biết lõi dùng bảng đó tốt đến đâu, không cho biết bảng đó có đúng với chiêu lừa ngoài đời không.
- 5 tình huống mỗi kịch bản là ít: một tình huống sai đổi tỉ lệ của kịch bản đó 20 điểm %.
- Ba trường tra cứu (nhãn, loại tài khoản, tên chủ tài khoản khớp hay không) được coi là đã biết từ đầu ở cả hai trợ lý. Trong app, `ten_khop_tu_xung` chỉ được code điền khi người kia tự xưng là một tổ chức.
- Chưa có ảnh trong tình huống thử (E4 và bộ có ảnh làm sau); chưa có tính cách "bị dặn trước".

