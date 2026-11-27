# Kết quả thí nghiệm E7 & Chốt phương pháp tốt nhất

> **Data v1.** Every number below was measured on data version 1 (commit `2940796`). The data is now version 2 (`data.md`): rerun before quoting.

Báo cáo tóm tắt từ 24 lượt chạy (8 kịch bản × 3 seed: `20261127`, `20261128`, `20261129`). Số liệu thô đầy đủ được xuất tại `experiments/E7/report.md` và `experiments/E7/results.json`.

> **Ranh giới trung thực:** Toàn bộ số liệu dưới đây đo trên **bộ dữ liệu mock 90 ngày** (`data/E7/`). Kết quả chứng minh rõ **cơ chế, tốc độ CPU và khả năng chống các bẫy thực tế** (`shopee.vn`, SĐT nạn nhân, AI nhiễu, đường dây mới) giữa các thuật toán — **không phải** độ chính xác trên tài khoản ngân hàng thật.

---

## 1. Chốt nhanh: Phương pháp nào tốt nhất?

- **Chấm điểm từng tài khoản → Chốt `g3_hybrid_cs`** *(Hồ sơ báo cáo chat + Đồ thị cắt hub + Correct & Smooth + PPR)*:
  - Đạt **PR-AUC = `0.998`** trên bộ chuẩn `base`, giữ vững **`0.959 – 0.994`** trên toàn bộ 6 bài stress-test.
  - **Top 20 & Top 50 tài khoản đẩy lên đầu cho nhân viên duyệt (`P@20`, `P@50`): `100.0%`** là lừa đảo thật.
  - **Bắt oan shop online thật:** chỉ **`0.3%`** *(cách gom chùm cũ của app bắt oan tới **`84.9%`**)*.
  - Bắt được cả **băng cũ (`95.5%`)** lẫn **băng mới tinh (`91.1%`)**; chạy CPU chỉ mất **~0,2 giây**.
- **Trích đường dẫn giải thích cho nhân viên → Dùng kèm `g1b_ppr` + Dijkstra** ([`e7/graph_engine.py`](../../e7/graph_engine.py)):
  - Trả lý do cụ thể (che SĐT kiểu `098***003` + mã báo cáo nguồn) và tự trả `chua_du_can_cu` khi không đủ căn cứ.
- **Gom & phân loại cụm cho `/staff/clusters` → Chốt `g4_louvain_wl`** *(Cắt siêu nút + tách cụm Louvain + 1-WL/FRAUDAR)*:
  - Phá vỡ lỗi gom nhầm thành siêu cụm > 1.300 tài khoản của Union-Find cũ, đẩy **Cluster PR-AUC từ `0.000` → `0.821`** (`0.591 – 0.893` trên các stress-test), bắt được **50% – 100%** cụm đường dây mới tinh với tỷ lệ báo nhầm cụm thường chỉ **`1.5%`**.

---

## 2. Kết quả chi tiết trên bộ chuẩn `base` (trung bình 3 seed)

Tập test mù (Ngày 71–90): **505 tài khoản mới** (57 lừa đảo = 37 băng cũ + 21 băng mới tinh; 16 siêu nút bị cắt).

### A. Chấm điểm từng tài khoản (`G0` → `G3`)

| Phương pháp | PR-AUC | Top 20 (`P@20`) | Top 50 (`P@50`) | Recall @ FPR≤1% | Bắt oan Shop | Bắt băng cũ | Bắt băng mới | CPU (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `g0a_lookup` *(tra bảng cũ)* | 0.114 | 11.4% | 11.4% | 0.0% | 0.0% | 0.0% | 0.0% | 0.1 |
| `g0b_union_find` *(gom chùm cũ của app)* | 0.168 | 16.8% | 16.8% | 0.0% | **84.9%** | 100.0% | 100.0% | 11.2 |
| `g0c_neighbor_count` *(đếm hàng xóm 1 bước)* | 0.276 | 44.5% | 32.0% | 8.1% | 1.8% | 13.0% | 3.2% | 1.9 |
| `g1a_weighted_lp` *(LP cổ điển)* | 0.591 | 78.3% | 66.0% | 25.1% | 0.9% | 24.0% | 0.0% | 39.8 |
| `g1b_ppr` *(mực đỏ nhạt dần + cắt hub)* | 0.702 | 96.7% | 68.7% | 58.1% | **0.2%** | 82.1% | 0.0% | 35.4 |
| `g2a_label_spreading` *(thêm tem vàng)* | 0.958 | 98.3% | 98.0% | 93.0% | 3.0% | 91.8% | 95.0% | 37.4 |
| `g2b_linbp` *(học trọng số theo loại dây)* | 0.929 | 100.0% | 97.3% | 88.9% | 0.8% | 87.2% | 89.8% | 38.2 |
| `g3_tabular_only` *(chỉ báo cáo chat, bỏ graph)* | 0.879 | 96.7% | 86.0% | 73.2% | 3.7% | 74.5% | 82.6% | 108.6 |
| **`g3_hybrid_cs`** *(Chat + Graph + C&S)* | **0.998** | **100.0%** | **100.0%** | **99.4%** | **0.3%** | **95.5%** | **91.1%** | 194.5 |

### B. Phân loại cả cụm vụ việc (`G4` — cho `/staff/clusters`)

| Phương pháp | Cluster PR-AUC | `P@10` | F1 | Bắt cụm mới tinh | Bắt oan cụm thường | Cụm lớn nhất |
|---|---:|---:|---:|---:|---:|---:|
| `g4_naive_uf_count` *(cách cũ của app)* | 0.000 | 0.0% | 0.000 | 0.0% | 23.9% | **1.329 TK** |
| `g4_hubcut_uf_ppr` *(cắt hub, vẫn dùng Union-Find)* | 0.003 | 0.2% | 0.000 | 0.0% | 0.5% | **911 TK** |
| `g4_louvain_max_ppr` *(cắt hub + Louvain + PPR)* | 0.520 | 40.0% | 0.300 | 0.0% | 0.9% | **53 TK** |
| **`g4_louvain_wl`** *(cắt hub + Louvain + 1-WL/FRAUDAR)* | **0.821** | **63.3%** | **0.660** | **50.0%** | 1.5% | **53 TK** |

---

## 3. So sánh PR-AUC trên toàn bộ 8 kịch bản

### Node-level PR-AUC
| Phương pháp | `base` | `s1` (Hub nổ) | `s2` (SĐT nạn nhân) | `s3` (AI nhiễu nặng) | `s4` (Hiếm 2%, 4 seed) | `s5` (Ngụy trang) | `s6` (50% băng mới) | `base` + 10% tem xanh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `g0a_lookup` | 0.114 | 0.113 | 0.105 | 0.115 | 0.055 | 0.123 | 0.130 | 0.114 |
| `g0b_union_find` | 0.168 | 0.145 | 0.136 | 0.160 | 0.080 | 0.179 | 0.187 | 0.168 |
| `g1b_ppr` | 0.702 | 0.733 | 0.631 | 0.601 | 0.674 | 0.656 | 0.559 | 0.702 |
| `g2a_label_spreading` | 0.958 | 0.984 | 0.942 | 0.888 | 0.928 | 0.973 | 0.970 | 0.944 |
| `g2b_linbp` | 0.929 | 0.921 | 0.907 | 0.859 | 0.847 | 0.933 | 0.952 | 0.928 |
| `g3_tabular_only` | 0.879 | 0.889 | 0.887 | 0.852 | 0.753 | 0.907 | 0.927 | 0.930 |
| **`g3_hybrid_cs`** | **0.998** | **0.965** | **0.991** | **0.980** | **0.959** | **0.976** | **0.994** | **0.992** |

### Cluster-level PR-AUC (`G4`)
| Phương pháp | `base` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `base` + 10% tem xanh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `g4_naive_uf_count` | 0.000 | 0.000 | 0.000 | 0.017 | 0.024 | 0.000 | 0.000 | 0.000 |
| `g4_hubcut_uf_ppr` | 0.003 | 0.000 | 0.000 | 0.006 | 0.008 | 0.278 | 0.000 | 0.003 |
| `g4_louvain_max_ppr` | 0.520 | 0.392 | 0.301 | 0.350 | 0.342 | 0.664 | 0.401 | 0.520 |
| **`g4_louvain_wl`** | **0.821** | **0.882** | **0.727** | **0.591** | **0.772** | **0.893** | **0.814** | **0.821** |

---

## 4. 3 phát hiện kỹ thuật quan trọng nhất

- **Phát hiện 1 — Cắt mỗi `shopee.vn` vẫn chưa đủ cho `/staff/clusters`:**
  - Khi chỉ cắt 16 siêu nút (`shopee.vn`, tổng đài...) mà vẫn giữ Union-Find (`g4_hubcut_uf_ppr`), các số điện thoại nạn nhân (bậc 5–12) vẫn nối bắc cầu gom thành **1 siêu cụm 911 tài khoản** → Cluster PR-AUC gần `0.000`.
  - Đổi sang **tách cụm Louvain theo trọng số (`g4_louvain_wl`)** giúp cắt đứt các cầu nối yếu, đưa kích thước cụm lớn nhất từ `911 → 53` tài khoản và kéo Cluster PR-AUC lên **`0.821`** (tới **`0.893`** ở `s5`).
- **Phát hiện 2 — Đồ thị giúp giảm hơn 10 lần tỷ lệ bắt oan shop thật:**
  - So sánh `g3_tabular_only` (chỉ dùng báo cáo chat: PR-AUC `0.879`, ShopFPR `3.7%`, Recall@FPR≤1% `73.2%`) với `g3_hybrid_cs` (thêm đồ thị: PR-AUC `0.998`, ShopFPR `0.3%`, Recall@FPR≤1% `99.4%`).
- **Phát hiện 3 — Bền vững kể cả khi thiếu tem đỏ hoặc 50% là băng mới tinh:**
  - Ở `s4` (lừa đảo chỉ 2%, chỉ có 4 tem đỏ), `g3_hybrid_cs` vẫn đạt PR-AUC **`0.959`** (hơn `g3_tabular_only` tới +20 điểm).
  - Ở `s6` (50% băng mới tinh), `g1b_ppr` bỏ sót hoàn toàn băng mới (`0%`), nhưng `g3_hybrid_cs` bắt được **`93.3%`** và `g4_louvain_wl` bắt được **`100%`** cụm mới tinh.

---

## 5. Ví dụ đầu ra thực tế (kèm đường dẫn bằng chứng cho nhân viên)

Chạy `score_account_graph` trên `data/E7/base`: 16 siêu nút (`shopee.vn`, `facebook.com`, `19001221`...) bị lọc sạch; một tài khoản mới bị gắn cờ ưu tiên xem sẽ hiện kèm giải thích kiểm chứng được:

```json
{
  "so_tk": "000900000010",
  "score": 0.24652,
  "status": "can_nhan_vien_xem",
  "evidence_paths": [
    {
      "seed_account": "000900000008",
      "hops": 1,
      "summary": "Lien he 1 buoc toi STK xac nhan 000900000008 qua phone 098***003 (7 STK dung chung, bao cao [17, 19, 25])"
    }
  ]
}
```
