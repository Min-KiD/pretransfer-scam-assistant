# Dữ liệu cho thí nghiệm Đồ thị rủi ro tài khoản (E7)

Tài liệu này giải thích ngắn gọn, dễ hiểu về **dữ liệu hiện có của app**, **cấu trúc thư mục thí nghiệm E7**, **format từng file mock data**, và **logic sinh dữ liệu giả lập** trong [`e7/gen_graph.py`](../../e7/gen_graph.py).

---

## 1. Hiện trạng dữ liệu của app (4 bảng SQLite)

File SQLite của app nằm mặc định ở `data/app/app.sqlite` (xem [`app/db.py`](../../app/db.py)), gồm **4 bảng**:

- **`account_labels`** — trạng thái hiện tại của từng số tài khoản nhận (`so_tk` là khóa chính, mỗi tài khoản 1 dòng, sửa là ghi đè):
  - `so_tk`, `ngan_hang`, `chu_tk`, `loai` (`ca_nhan` hoặc `to_chuc`).
  - `nhan`: 4 trạng thái — `quen`, `moi`, `dang_bi_bao_cao` (cảnh báo vàng), `da_xac_nhan` (cảnh báo đỏ).
  - `dat_boi`: ai đặt nhãn lần cuối (`du_lieu_mau`, `bao_cao_tu_dong`, `nhan_vien`, `nhan_vien_go`).
  - `cap_nhat`: mốc thời gian cập nhật gần nhất.
- **`sessions`** — lưu trạng thái từng phiên chat (`id`, `so_tk`, `so_tien`, JSON `state`, `tao_luc`).
- **`messages`** — lưu từng dòng tin nhắn người dùng và trợ lý (`session_id`, `role`, `text`, `co_anh`, `ts`).
- **`reports`** *(bảng quan trọng nhất để dựng đồ thị)* — lưu 1 dòng sau khi phiên chat kết luận và người dùng bấm nút quyết định:
  - `id`, `session_id`, `so_tk`, `tao_luc`.
  - `muc`: `giong_chieu_lua`, `giong_binh_thuong`, hoặc `chua_du_can_cu`.
  - `kich_ban`: mã kịch bản cao điểm nhất trong 25 kịch bản (`scenarios/*.yaml`).
  - `nut`: lựa chọn của người dùng (`dung_lai`, `kiem_tra_them`, `van_chuyen`).
  - `sdt`, `link`: mảng JSON các số điện thoại và tên miền trích từ ảnh chat.
  - `noi_dung`: JSON chứa `bang_cau_chuyen`, `phan_phoi` (xác suất 25 kịch bản), `so_tien`, `hoi_thoai`.

### 5 chỗ đang thiếu khi đưa dữ liệu app lên Đồ thị ("bảng ghim phá án")
- **Chưa có lịch sử đổi nhãn theo thời gian:** `account_labels` ghi đè khi sửa nên không biết tài khoản nào được duyệt tem đỏ vào ngày nào.
- **Chưa có nhãn "đã xác minh bình thường" (`verified_normal`):** nhân viên bấm **Gỡ** ở [`app/main.py`](../../app/main.py#L189-L190) chỉ đưa tài khoản về `moi`, nên hiện tại chỉ có tem đỏ (`da_xac_nhan`), chưa có tem xanh.
- **Không biết SĐT/link trong ảnh là của ai:** máy đọc ảnh bốc tất cả SĐT/link trên màn hình, không phân biệt SIM rác của kẻ gian, SĐT của nạn nhân, hay tổng đài công ty.
- **Dễ dính chùm oan vì đầu mối "cả làng cùng dùng":** cách gom cụm cũ ở `/staff/clusters` nối mọi báo cáo trùng SĐT/link, nên chỉ cần 1 link `shopee.vn` hay tổng đài giao hàng là hàng loạt shop bình thường bị gom chung với kẻ lừa đảo.
- **Chưa có dữ liệu đồ thị tài khoản ngân hàng thật:** repo mới có kịch bản, ảnh chat và lời kể riêng lẻ; chưa có đồ thị tài khoản thật nên E7 cần bộ **mock data 90 ngày** để kiểm chứng cơ chế.

---

## 2. Cấu trúc thư mục của thí nghiệm E7

Toàn bộ phần E7 nằm gọn trong **3 thư mục**:

- **`e7/`** *(code thí nghiệm trên nhánh `e7`)*:
  - [`e7/gen_graph.py`](../../e7/gen_graph.py): sinh dữ liệu mock 90 ngày.
  - [`e7/graph_engine.py`](../../e7/graph_engine.py): dựng đồ thị `Tài khoản ↔ SĐT / Tên miền`, cắt siêu nút, chạy lan truyền, tách cụm và trích đường dẫn bằng chứng.
  - [`e7/models.py`](../../e7/models.py): các phương pháp thử nghiệm (`G0` → `G4`).
  - [`e7/eval.py`](../../e7/eval.py) & [`e7/report.py`](../../e7/report.py): chạy bài thi chia thời gian, chấm điểm và xuất báo cáo.
- **`tests/test_e7.py`** ([`tests/test_e7.py`](../../tests/test_e7.py)): bộ unit test tự động kiểm tra logic E7.
- **`data/E7/`** *(dữ liệu mock sinh ra trên máy local, `.gitignore` bỏ qua không commit)*:
  - Gồm 7 thư mục con ứng với 1 bộ chuẩn (`base/`) và 6 bài stress-test (`s1_hub_explosion/` → `s6_cold_start_heavy/`).
- **`experiments/E7/`** *(kết quả chạy thí nghiệm trên máy local, không commit)*:
  - `report.md`: bảng so sánh kết quả dễ đọc.
  - `results.json`: số liệu chi tiết từng lần chạy.

---

## 3. Format chi tiết 6 file trong mỗi bộ dữ liệu (ví dụ `data/E7/base/`)

Mỗi file `.jsonl` có format đơn giản: **mỗi dòng là 1 đối tượng JSON**. Các trường có tiền tố **`gt_`** là **đáp án bí mật chỉ dùng để chấm thi** — tuyệt đối không đưa vào model lúc train hay dự đoán.

- **1. `accounts.jsonl`** *(3.000 dòng — danh sách tài khoản ngân hàng)*:
  - Trường quan sát: `so_tk` (mã giả `0009...`), `loai` (`ca_nhan` / `to_chuc`), `created_day`.
  - Trường đáp án bí mật: `gt_is_scam` (`1` = lừa đảo, `0` = bình thường), `gt_role` (`scam_organizer`, `scam_mule`, `normal_merchant`, `normal_personal`, `hijacked_account`), `gt_ring_id`, `gt_is_heldout_ring`.
  - Ví dụ 1 dòng thật:
    ```json
    {"so_tk": "000900000001", "loai": "ca_nhan", "created_day": 19, "gt_is_scam": 1, "gt_role": "scam_organizer", "gt_ring_id": "scam_ring_001", "gt_is_heldout_ring": 0}
    ```

- **2. `entities.jsonl`** *(313 dòng — danh sách SĐT và tên miền)*:
  - Trường quan sát: `entity_id`, `type` (`phone` hoặc `domain`), `value`.
  - Trường đáp án bí mật: `gt_entity_role` (`popular_benign_domain`, `shared_hotline`, `victim_phone`, `scammer_burner_phone`, `phishing_domain`, `benign_shared_phone`), `gt_description`.
  - Ví dụ 1 dòng thật:
    ```json
    {"entity_id": "domain_00001", "type": "domain", "value": "shopee.vn", "gt_entity_role": "popular_benign_domain", "gt_ring_id": null, "gt_description": "e-commerce platform (Shopee)"}
    ```

- **3. `reports.jsonl`** *(3.376 dòng — báo cáo chat sinh ra các sợi dây nối đồ thị)*:
  - Khớp trực tiếp bảng `reports` của app: `id`, `session_id`, `so_tk`, `day`, `muc`, `kich_ban`, `nut`, `sdt`, `link`, `so_tien`, `m3_scam_prob`, `ten_khop_tu_xung`, `phan_phoi` (xác suất trên 25 kịch bản).
  - Ví dụ rút gọn 1 dòng thật:
    ```json
    {"id": 644, "session_id": "e7s_000644", "so_tk": "000900000288", "day": 1, "muc": "chua_du_can_cu", "kich_ban": "bt_tra_shipper_khi_nhan_hang", "nut": "kiem_tra_them", "sdt": [], "link": [], "so_tien": 420000, "m3_scam_prob": 0.242}
    ```

- **4. `label_events.jsonl`** *(392 dòng — lịch sử gắn nhãn theo ngày)*:
  - Lưu chính xác ngày nào nhân viên duyệt tem đỏ (`da_xac_nhan`, `by: "nhan_vien"`) hay app tự gắn tem vàng (`dang_bi_bao_cao`, `by: "bao_cao_tu_dong"`).
  - Ví dụ 1 dòng thật:
    ```json
    {"so_tk": "000900000037", "label": "dang_bi_bao_cao", "by": "bao_cao_tu_dong", "day": 2}
    ```

- **5. `graph_manifest.json`**: thống kê tổng quan, tham số sinh, top 20 đầu mối nhiều tài khoản dùng nhất và mã SHA-256 để tái lập 100%.
- **6. `sample_preview.json`**: bản rút gọn pretty-printed chứa vài mẫu đại diện mỗi loại để mở đọc nhanh bằng mắt.

---

## 4. Logic 5 bước sinh Mock Data trong [`e7/gen_graph.py`](../../e7/gen_graph.py)

Để thí nghiệm không tự đánh lừa mình (nếu dữ liệu quá sạch thì thuật toán nào cũng đạt 99%), bộ sinh mô phỏng một "thành phố 90 ngày" gồm **3.000 tài khoản** với đủ các bẫy ngoài đời:

1. **Tạo đầu mối bẫy dùng chung:**
   - **8 trang web phổ thông:** `shopee.vn`, `facebook.com`, `zalo.me`, `tiki.vn`, `lazada.vn`, `ghn.vn`, `viettelpost.vn`, `momo.vn` *(trong `base`, mỗi trang dính 67–119 tài khoản)*.
   - **8 số tổng đài công cộng:** tổng đài Shopee (`19001221`), GHN (`1900636677`), Viettel Post (`19008095`), J&T (`19001088`), Tiki, MoMo và 2 tổng đài ngân hàng *(mỗi số dính 40–71 tài khoản)*.
   - **~85 số điện thoại nạn nhân (`victim_phone`):** để trộn ngẫu nhiên vào cả báo cáo lừa đảo lẫn báo cáo thường, tạo cầu nối sai.
2. **Đúc 12 băng nhóm lừa đảo (tổng 4,5% = 135 tài khoản lừa đảo):**
   - Gồm 2 kiểu: **băng dùng chung SIM rác** (`gia_shipper`, `gia_cong_an`, `dat_coc_gia_re`...) và **chiến dịch web giả** (`dau_tu_san_gia`, `ctv_online`, `dich_vu_lay_lai_tien`...).
   - **3/12 băng (25%) là băng mới tinh (`cold-start`):** chỉ xuất hiện sau ngày 55, hoàn toàn không có tem đỏ cũ.
   - **9 băng còn lại xoay vòng STK:** ~55% STK hoạt động sớm (ngày 1–49), ~45% STK mới xuất hiện muộn hơn (ngày 56–86) nhưng xài lại SIM/web cũ.
3. **Tạo 2.865 tài khoản bình thường (95,5%) + 18 tài khoản bị chiếm đoạt:**
   - **~28% là cụm shop online đàng hoàng:** hay dính `shopee.vn`, `facebook.com`, `zalo.me` và tổng đài giao hàng → dùng để đo tỷ lệ **bắt oan shop thật**.
   - **~18% là cụm gia đình/bạn bè:** dễ bị trợ lý chat báo nhầm thành `mao_danh_nguoi_quen` (đúng lỗi thực tế ở E2/E3).
   - **18 tài khoản bị chiếm đoạt (`hijacked_account`):** trước ngày bị hack là người bình thường, sau đó bị kéo vào băng lừa đảo.
4. **Mô phỏng 3.376 báo cáo kèm lỗi thật của AI (bám số liệu E4/E5/E6 trong `EXPERIMENTS.md`):**
   - Máy đọc ảnh M1: rớt ~12% chuỗi, dính thừa 1 `victim_phone` ở ~14% báo cáo.
   - Kẻ gian ngụy trang: ~28% báo cáo lừa đảo nhét thêm link phổ thông, ~20% nhét thêm tổng đài.
   - Trợ lý chat M2/M3: ~7,5% giao dịch bình thường bị báo nhầm `giong_chieu_lua`; ~7% lừa đảo bị bỏ sót; ~16% rơi vào `chua_du_can_cu`.
5. **Sinh lịch sử nhãn theo ngày:**
   - Chỉ ~25% tài khoản lừa đảo xuất hiện sớm được nhân viên duyệt tem đỏ trước ngày 55 (**13 tem đỏ**, **0 tem xanh**).
   - Trong khi đó có tới **379 tem vàng tự động (`dang_bi_bao_cao`)** — phần lớn là báo nhầm trên người bình thường.

### 7 bộ kịch bản đã sinh sẵn trong `data/E7/`
- **`base`**: bộ chuẩn (4,5% lừa đảo, 13 tem đỏ, `shopee.vn` nối 119 tài khoản).
- **`s1_hub_explosion`**: siêu nút phình gấp đôi (`shopee.vn` nối 237 tài khoản).
- **`s2_high_heterophily`**: 32% báo cáo dính SĐT nạn nhân + tăng tài khoản bị chiếm đoạt.
- **`s3_heavy_noise`**: AI lỗi nặng (rớt 24% chuỗi, tem vàng báo nhầm vọt lên 573).
- **`s4_sparse_imbalance`**: lừa đảo siêu hiếm (2%, chỉ có đúng 4 tem đỏ).
- **`s5_camouflage_drift`**: kẻ gian ngụy trang mạnh + đổi STK nhiều.
- **`s6_cold_start_heavy`**: 50% (6/12) băng nhóm là đường dây mới tinh sau ngày 55.
