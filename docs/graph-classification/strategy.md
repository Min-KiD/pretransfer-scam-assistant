# Chiến lược, Phương pháp, Mô hình & Cách đánh giá (E7)

> **Data v1.** This page describes data version 1 (commit `2940796`). The data is now version 2 (`data.md`): the method and its numbers have to be rerun on it.

Tài liệu này giải thích ngắn gọn **bài toán cần giải**, **các phương pháp thử nghiệm**, **đầu vào/đầu ra của mô hình tốt nhất**, và **cách train/đánh giá chống gian lận dữ liệu tương lai** trong [`e7/graph_engine.py`](../../e7/graph_engine.py), [`e7/models.py`](../../e7/models.py) và [`e7/eval.py`](../../e7/eval.py).

---

## 1. Bài toán & 2 Usecase thực tế

Khi kẻ lừa đảo mở số tài khoản ngân hàng mới tinh (`so_tk`), bảng tra cứu cũ báo "mới/chưa biết". Nhưng trên thực tế, tài khoản mới đó thường để lại dấu vết dùng chung **SĐT** hoặc **tên miền web** trong các báo cáo chat (`reports`).

Chúng ta dựng đồ thị dạng **"bảng ghim phá án"**: `Tài khoản ↔ SĐT / Tên miền` để phục vụ **2 việc tách biệt**:

- **Usecase 1 — Chấm điểm rủi ro từng tài khoản (`0.0 → 1.0`, Node Classification / Ranking):**
  - **Dùng ngay cho nhân viên (`/web/staff.html`):** đẩy top 20–50 tài khoản nguy hiểm nhất lên đầu danh sách kèm **đường dẫn bằng chứng** (che SĐT kiểu `098***003`) để nhân viên bấm **Duyệt tem đỏ (`da_xac_nhan`)** sớm, chặn kịp trước khi thêm người bị lừa.
  - **Dùng giai đoạn sau cho Tầng 1 (`/transfer/check`, khi có dữ liệu thật):** tự động cảnh báo sớm hoặc mở trợ lý hỏi lại với tài khoản mới có điểm rủi ro rất cao.
  - **Chốt an toàn:** hệ thống **không bao giờ tự ghi đè `account_labels`** — nhân viên vẫn là người bấm xác nhận cuối.

- **Usecase 2 — Phân loại cả cụm vụ việc (`scam_ring` vs `benign_cluster`, Graph/Subgraph Classification):**
  - Giúp nhân viên ở trang `/staff/clusters` biết **nên mở cụm/vụ án nào ra xem trước**, thay vì bị cách gom nhóm cũ dính chùm hàng nghìn tài khoản vào một cục.

---

## 2. Các phương pháp đã thử nghiệm

### A. Chấm điểm từng tài khoản (9 cách, từ thô sơ → thông minh)
- **Nhóm 0 — Cách cũ / mốc so sánh:**
  - `g0a_lookup`: chỉ tra bảng tem đỏ hiện có (tài khoản mới luôn = `0`).
  - `g0b_union_find`: cách gom nhóm hiện tại ở `/staff/clusters` — không cắt `shopee.vn`/tổng đài → bóc trần lỗi bắt oan hàng loạt shop.
  - `g0c_neighbor_count`: đếm số hàng xóm tem đỏ sát vách 1 bước (không cắt siêu nút).
- **Nhóm 1 — Lan truyền thuần trên đồ thị ĐÃ CẮT SIÊU NÚT (chỉ dùng tem đỏ nhân viên duyệt):**
  - `g1a_weighted_lp`: Label Propagation cổ điển (dễ yếu khi không có tem xanh "người tốt").
  - `g1b_ppr` *(Personalized PageRank — mực đỏ nhạt dần)*: cắt siêu nút (> 20 tài khoản) + giảm trọng số đầu mối đông người theo độ hiếm (`1 / log(1 + deg)^β`); mực đỏ chảy từ tem đỏ và **nhạt dần theo khoảng cách** → cực ít bắt oan shop, nhưng bó tay với băng mới tinh chưa có tem đỏ.
- **Nhóm 2 — Lan truyền chịu nhiễu hơn:**
  - `g2a_label_spreading`: bản mềm, cho phép tem vàng tự động (`dang_bi_bao_cao`) góp trọng số nhỏ.
  - `g2b_linbp`: phân biệt 4 loại dây riêng (`SĐT hiếm`, `SĐT vừa`, `web hiếm`, `web vừa`) với độ tin cậy khác nhau + chống tín hiệu dội ngược.
- **Nhóm 3 — Máy học kết hợp Hồ sơ báo cáo chat + Đồ thị:**
  - `g3_tabular_only` *(đối chứng bỏ đồ thị)*: chỉ dùng nội dung báo cáo chat M2/M3 của riêng tài khoản.
  - **`g3_hybrid_cs` *(tốt nhất)*:** kết hợp **hồ sơ báo cáo chat** + **đặc trưng hàng xóm xung quanh (đã cắt hub)** đưa vào mô hình nhẹ chạy CPU, rồi cộng thêm bước **Correct & Smooth** (sửa sai số & làm mượt theo hàng xóm) + **PPR**.

### B. Phân loại cả cụm vụ việc cho `/staff/clusters` (4 cách)
- `g4_naive_uf_count`: cách cũ của app (Union-Find không cắt hub, xếp theo số báo cáo lừa đảo).
- `g4_hubcut_uf_ppr`: có cắt `shopee.vn`/tổng đài nhưng vẫn dùng Union-Find *(vẫn bị vài SĐT nạn nhân nối bắc cầu thành 1 cục ~900 tài khoản)*.
- `g4_louvain_max_ppr`: cắt hub + đổi sang **tách cụm Louvain** (cắt đứt các cầu nối yếu 1 sợi SĐT nạn nhân) rồi xếp theo điểm `PPR` cao nhất trong cụm.
- **`g4_louvain_wl` *(tốt nhất cho cụm)*:** cắt hub + **tách cụm Louvain** + phân loại đồ thị con bằng **1-WL Subtree Kernel** + mật độ kháng ngụy trang **FRAUDAR** + độ dồn dập thời gian + độ đồng nhất kịch bản M2/M3.

---

## 3. Mô hình đang sử dụng là gì?

Toàn bộ thí nghiệm E7 **không dùng GNN / Deep Learning và không cần GPU** — chỉ dùng:
- **Thuật toán đồ thị thuần (`scipy.sparse`, `networkx`):** PPR, Label Propagation, Label Spreading, LinBP, Dijkstra tìm đường bằng chứng, và Louvain tách cụm.
- **Machine Learning cổ điển siêu nhẹ (`scikit-learn` trên CPU):**
  - Với `g3_hybrid_cs`: tổ hợp **`LogisticRegression`** (`StandardScaler`, `class_weight="balanced"`) + **`HistGradientBoostingClassifier`** (`max_depth=3`, `class_weight="balanced"`), cộng bước hậu xử lý đồ thị **Correct & Smooth + PPR**.
  - Với `g4_louvain_wl`: **`LogisticRegression`** (`class_weight="balanced"`) trên vector cấu trúc **1-WL Subtree (`DictVectorizer` + `TfidfTransformer`)** + 18 chỉ số cấu trúc cụm.

---

## 4. Đầu vào, Đầu ra & Nguồn dữ liệu của 2 model tốt nhất

### A. Model chấm điểm từng tài khoản: `g3_hybrid_cs`
- **Đầu vào cho mỗi tài khoản (`48` con số + ma trận `W` + tem đỏ):**
  1. **Hồ sơ bản thân & báo cáo chat (13 số):** `ca_nhan`/`to_chuc`, số báo cáo, khoảng thời gian báo cáo, số SĐT/domain đi kèm, tỷ lệ `giong_chieu_lua` / `chua_du_can_cu` / `dung_lai` / `kiem_tra_them`, tỷ lệ lệch `ten_khop_tu_xung`, điểm `m3_scam_prob` trung bình & max, số tiền chuyển trung bình.
  2. **Phân phối 25 kịch bản trung bình (25 số):** từ `phan_phoi` của các báo cáo.
  3. **Hàng xóm xung quanh trên đồ thị đã cắt hub (10 số):** tổng trọng số dây nối, số hàng xóm, số SĐT hiếm (`≤ 6` STK), số domain hiếm (`≤ 8` STK), độ hiếm lớn nhất, trung bình điểm M3 / tỷ lệ lừa đảo / tỷ lệ `dung_lai` của hàng xóm, cỡ cụm & tỷ lệ lừa đảo của cụm.
  4. **Hậu xử lý đồ thị:** ma trận trọng số dây nối `W` (đã cắt hub > 20 STK) và danh sách tem đỏ `da_xac_nhan`.
- **Nguồn lấy trong app thật ([`app/db.py`](../../app/db.py)):**
  - `loai` lấy từ `account_labels`; các trường báo cáo lấy từ cột & JSON `noi_dung` của bảng `reports`; 10 đặc trưng hàng xóm & ma trận `W` tự tính từ `reports.sdt` và `reports.link`; tem đỏ lấy từ `account_labels` (`nhan == "da_xac_nhan"` và `dat_boi == "nhan_vien"`).
  - *Duy nhất 1 trường chưa lưu sẵn trong `reports` hiện tại:* `m3_scam_prob` (có ở [`e6/classify.py`](../../e6/classify.py), khi lên app có thể lưu thêm hoặc thay bằng tổng xác suất nhóm `lua_dao` từ `phan_phoi`).
- **Đầu ra:** điểm rủi ro **`score` trong `[0.0, 1.0]`**, trạng thái gợi ý (`can_nhan_vien_xem` hoặc `chua_du_can_cu`), kèm **top 2 đường dẫn bằng chứng** đã che SĐT (từ Dijkstra).

### B. Model phân loại cụm: `g4_louvain_wl`
- **Đầu vào cho mỗi cụm (sau khi cắt hub và tách Louvain):** 18 chỉ số thống kê cụm (số STK/SĐT/domain, mật độ nối dây, mật độ **FRAUDAR**, độ dồn dập thời gian, **entropy kịch bản**, tỷ lệ `giong_chieu_lua`/`dung_lai`/`ca_nhan`/lệch tên, M3 trung bình & max) + vector tần suất cấu trúc 2 vòng **1-WL Subtree**.
- **Đầu ra:** điểm **`score` trong `[0.0, 1.0]`** để sắp xếp thứ tự cụm ưu tiên duyệt trên `/staff/clusters`.

---

## 5. Cách train & Cách đánh giá (Chống nhìn trộm tương lai)

- **Chia 3 giai đoạn thời gian không chồng lấn:**
  - **Ngày 1 → 55 (Train / Nền):** ~1.143 tài khoản có báo cáo, chỉ có ~13 tem đỏ nhân viên duyệt.
  - **Ngày 56 → 70 (Validation — ~350 tài khoản mới):** chỉ dùng để chọn siêu tham số và khóa ngưỡng báo động (sao cho báo nhầm trên Validation ≤ 2%).
  - **Ngày 71 → 90 (Test mù — ~505 tài khoản mới):** khóa kín hoàn toàn tới bước chấm điểm cuối (gồm ~37 tài khoản thuộc băng cũ + ~21 tài khoản thuộc băng mới tinh).
- **Train trung thực (chế độ PU, không nhìn `gt_is_scam`):**
  - Trên tập Train, chỉ gán `y = 1` cho ~13 tài khoản đã có tem đỏ `da_xac_nhan`, phần còn lại gán `y = 0`, bật `class_weight="balanced"`.
  - 10 đặc trưng hàng xóm ở Bước 1 **không dùng nhãn tem đỏ** để tránh tự lộ đáp án khi train; thông tin tem đỏ chỉ đi vào ở Bước 2 (Correct & Smooth + PPR).
- **6 thước đo chấm thi (lặp trên 3 seed `20261127`, `20261128`, `20261129` cho cả 8 kịch bản):**
  - **PR-AUC** (chuẩn cho dữ liệu lệch lớp 2–4,5%).
  - **Precision@20 & Precision@50** (có chia đều khi điểm hòa để chống ảo).
  - **Recall @ FPR ≤ 1%** (tính chuẩn theo đường ROC).
  - **Bắt oan Shop thật (`Honest-Shop FPR`)**.
  - **Bắt băng cũ (`Seen-Ring`) vs Bắt băng mới tinh (`Unseen-Ring`)**.
  - **Tốc độ chạy CPU (ms)** và **độ tinh khiết / kích thước cụm lớn nhất**.
