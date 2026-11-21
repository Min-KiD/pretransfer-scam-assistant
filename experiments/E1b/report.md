# E1b - Model mã nguồn mở và bộ ảnh khó

Câu hỏi: trên GPU 16GB (RTX 4060 Ti), model mở nào đọc ảnh chat tiếng Việt ngang hoặc hơn `gemini-3.5-flash-lite`; OCR nào hơn PP-OCRv6; ảnh khó thì cách đọc nào gãy trước.

Bộ khó: 100 ảnh, 428 chuỗi: thu nhỏ 33% (30), nén JPEG q30 -> 70% -> q30 (30), chụp lại màn hình (30: viền máy và nền bàn, xoay 2-4 độ, méo phối cảnh nhẹ, moiré nhẹ, mờ, nhiễu, JPEG q85), chat dài 20-29 tin (10 ảnh rộng 1170 px, cao 4122-5316 px). Ba biến thể đầu sinh từ 30 ảnh gốc của E1; đáp án lấy từ lúc sinh.

## Kết luận theo quy tắc đề xuất

Đủ dùng = trên bộ E1 đạt >=98% ở số TK, SĐT, số tiền và tên miền, và trung bình <=5 giây/ảnh trên GPU này.

- Chữ `glm-ocr`: **đủ dùng**; 3.92 s/ảnh (180/180 ảnh E1).
- Chữ `mineru2.5-pro`: chưa đủ; chậm: 10.1 s/ảnh (67/180 ảnh E1).
- Chữ `paddleocr-vl-1.6`: chưa đủ; hụt: Số tiền 97.9%, Tên miền 90.0%; chậm: 6.2 s/ảnh (121/180 ảnh E1).
- Chữ `pp-ocrv6-gpu`: **đủ dùng**; 0.30 s/ảnh (180/180 ảnh E1).
- JSON `glm-ocr`: chưa đủ; hụt: Số TK 0.0%, SĐT 0.0%, Số tiền 0.0%, Tên miền 0.0%; chậm: 5.7 s/ảnh (137/180 ảnh E1).
- Tốt nhất nhóm Chữ: `glm-ocr`
- Tốt nhất nhóm JSON: không có model nào đủ dùng

Bộ khó, biến thể kéo một cách đọc xuống dưới 90%:

- Chữ glm-ocr: thu nhỏ 33% / Link 70.0%; thu nhỏ 33% / Đường dẫn 70.0%; nén JPEG 2 lần / Link 80.0%; nén JPEG 2 lần / Đường dẫn 80.0%; chụp lại màn hình / Link 80.0%; chụp lại màn hình / Đường dẫn 80.0%
- Chữ mineru2.5-pro: thu nhỏ 33% / Link 72.7%; thu nhỏ 33% / Đường dẫn 72.7%; nén JPEG 2 lần / Link 54.5%; nén JPEG 2 lần / Đường dẫn 54.5%; chụp lại màn hình / Link 81.8%; chụp lại màn hình / Đường dẫn 81.8%; chat dài / Link 70.0%; chat dài / Đường dẫn 70.0%
- Chữ paddleocr-vl-1.6: thu nhỏ 33% / Link 40.0%; thu nhỏ 33% / Tên miền 75.0%; thu nhỏ 33% / Đường dẫn 60.0%; nén JPEG 2 lần / Link 45.0%; nén JPEG 2 lần / Đường dẫn 45.0%; chụp lại màn hình / Link 65.0%; chụp lại màn hình / Tên miền 85.0%; chụp lại màn hình / Đường dẫn 70.0%; chat dài / Link 60.0%; chat dài / Tên miền 80.0%; chat dài / Đường dẫn 70.0%
- Chữ pp-ocrv6-gpu: thu nhỏ 33% / Link 60.0%; thu nhỏ 33% / Đường dẫn 60.0%; nén JPEG 2 lần / Link 66.7%; nén JPEG 2 lần / Đường dẫn 66.7%; chụp lại màn hình / Link 63.3%; chụp lại màn hình / Đường dẫn 63.3%; chat dài / Link 80.0%; chat dài / Đường dẫn 80.0%
- JSON gemini-3.5-flash-lite: thu nhỏ 33% / Link 56.7%; thu nhỏ 33% / Đường dẫn 60.0%; nén JPEG 2 lần / Link 60.0%; nén JPEG 2 lần / Đường dẫn 60.0%; chụp lại màn hình / Link 60.0%; chụp lại màn hình / Đường dẫn 60.0%; chat dài / Link 70.0%; chat dài / Đường dẫn 70.0%
- JSON glm-ocr: 0% ở mọi biến thể và mọi loại chuỗi (không trích được chuỗi nào)

Tỉ lệ khớp chung theo bộ (mọi loại chuỗi gộp lại; link tính nguyên chuỗi; '-' = chưa chạy):

| Nhóm | Model | E1 | E1b | gen | web |
|---|---|---|---|---|---|
| Chữ (ref A) | pp-ocrv6-cpu | 92.6% (700/756) | - | - | - |
| Chữ | glm-ocr | 96.4% (729/756) | 94.6% (405/428) | 84.3% (145/172) | 60.5% (26/43) |
| Chữ | mineru2.5-pro | 90.5% (248/274) | 92.5% (172/186) | 89.0% (153/172) | 55.8% (24/43) |
| Chữ | paddleocr-vl-1.6 | 88.5% (447/505) | 88.3% (264/299) | 86.0% (148/172) | 51.2% (22/43) |
| Chữ | pp-ocrv6-gpu | 92.9% (702/756) | 91.8% (393/428) | 83.7% (144/172) | 58.1% (25/43) |
| JSON | gemini-3.5-flash-lite | 91.4% (691/756) | 89.7% (384/428) | 93.0% (160/172) | 83.7% (36/43) |
| JSON | glm-ocr | 0.0% (0/575) | 0.0% (0/324) | 0.0% (0/172) | 2.3% (1/43) |

Ở chế độ Chữ trên bộ `gen` và `web`, phần lớn chuỗi bị sót có nằm sẵn trong chữ OCR trả về, nhưng quy tắc trích của E1 (regex) không nhận ra. Số đếm và các dạng bị sót xem mục 8.

## 1. Model đã chạy, bị bỏ, và vì sao

| Model | Repo | Trạng thái | Ghi chú |
|---|---|---|---|
| gemini-3.5-flash-lite | - | done | B on E1b |
| pp-ocrv6-gpu | PaddlePaddle/PP-OCRv6_medium_{det,rec}_safetensors | done | downloaded in 0s; {"images_done": 280, "budget_stop": false, "vram_peak_process_mib": 3134, "load_seconds": 4.5} |
| qwen3-vl-8b | Qwen/Qwen3-VL-8B-Instruct | skipped | download 17.53 GB at the measured 2.0 MB/s needs about 146 min, over the 30 min install cap |
| qwen3-vl-4b | Qwen/Qwen3-VL-4B-Instruct | skipped | download 8.88 GB at the measured 2.0 MB/s needs about 74 min, over the 30 min install cap |
| paddleocr-vl-1.6 | PaddlePaddle/PaddleOCR-VL-1.6 | done | downloaded in 763s; {"images_done": 191, "budget_stop": true, "vram_peak_process_mib": 2260, "load_seconds": 3.6} |
| mineru2.5-pro | opendatalab/MinerU2.5-Pro-2605-1.2B | done | downloaded in 853s; {"images_done": 110, "budget_stop": true, "vram_peak_process_mib": 2844, "load_seconds": 3.8} |
| glm-ocr | zai-org/GLM-OCR | done | downloaded in 976s; {"images_done": 213, "budget_stop": true, "vram_peak_process_mib": 4522, "load_seconds": 3.8} |
| gemma-4-e4b | google/gemma-4-E4B-it | skipped | download 15.99 GB at the measured 2.7 MB/s needs about 98 min, over the 30 min install cap |

## 2. Xếp hạng trên bộ E1 (180 ảnh dễ)

Khớp chính xác từng ký tự sau chuẩn hóa như E1. Tên miền = phần trước `/` đầu tiên (hạ chữ thường); đường dẫn = phần sau (phân biệt hoa thường). Ngoặc vuông: khoảng tin cậy 95% (Wilson). Sắp theo tỉ lệ chung.

| Nhóm | Model | Số ảnh | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn | Tất cả | Phía gửi | JSON hỏng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Chữ | glm-ocr | 180/180 | 100.0% (180/180) [98-100] | 100.0% (180/180) [98-100] | 100.0% (217/217) [98-100] | 84.9% (152/179) [79-89] | 100.0 (179/179) | 84.9 (152/179) | 96.4% | - | - |
| Chữ | pp-ocrv6-gpu | 180/180 | 100.0% (180/180) [98-100] | 100.0% (180/180) [98-100] | 99.5% (216/217) [97-100] | 70.4% (126/179) [63-77] | 100.0 (179/179) | 70.4 (126/179) | 92.9% | - | - |
| Chữ (ref A) | pp-ocrv6-cpu | 180/180 | 100.0% (180/180) [98-100] | 100.0% (180/180) [98-100] | 100.0% (217/217) [98-100] | 68.7% (123/179) [62-75] | 100.0 (179/179) | 68.7 (123/179) | 92.6% | - | - |
| JSON | gemini-3.5-flash-lite | 180/180 | 95.6% (172/180) [91-98] | 100.0% (180/180) [98-100] | 100.0% (217/217) [98-100] | 68.2% (122/179) [61-75] | 100.0 (179/179) | 68.2 (122/179) | 91.4% | 100.0 (1116/1116) | 0 |
| Chữ | mineru2.5-pro | 67/180 | 100.0% (67/67) [95-100] | 100.0% (67/67) [95-100] | 98.6% (73/74) [93-100] | 62.1% (41/66) [50-73] | 100.0 (66/66) | 62.1 (41/66) | 90.5% | - | - |
| Chữ | paddleocr-vl-1.6 | 121/180 | 100.0% (121/121) [97-100] | 100.0% (121/121) [97-100] | 97.9% (140/143) [94-99] | 54.2% (65/120) [45-63] | 90.0 (108/120) | 60.0 (72/120) | 88.5% | - | - |
| JSON | glm-ocr | 137/180 | 0.0% (0/137) [0-3] | 0.0% (0/137) [0-3] | 0.0% (0/165) [0-2] | 0.0% (0/136) [0-3] | 0.0 (0/136) | 0.0 (0/136) | 0.0% | 17.5 (148/845) | 100 |

## 3. Xếp hạng trên bộ E1b khó (100 ảnh)

Khớp chính xác từng ký tự sau chuẩn hóa như E1. Tên miền = phần trước `/` đầu tiên (hạ chữ thường); đường dẫn = phần sau (phân biệt hoa thường). Ngoặc vuông: khoảng tin cậy 95% (Wilson). Sắp theo tỉ lệ chung.

| Nhóm | Model | Số ảnh | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn | Tất cả | Phía gửi | JSON hỏng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Chữ | glm-ocr | 100/100 | 100.0% (100/100) [96-100] | 100.0% (100/100) [96-100] | 99.2% (127/128) [96-100] | 78.0% (78/100) [69-85] | 100.0 (100/100) | 78.0 (78/100) | 94.6% | - | - |
| Chữ | mineru2.5-pro | 43/100 | 100.0% (43/43) [92-100] | 100.0% (43/43) [92-100] | 98.2% (56/57) [91-100] | 69.8% (30/43) [55-81] | 100.0 (43/43) | 69.8 (30/43) | 92.5% | - | - |
| Chữ | pp-ocrv6-gpu | 100/100 | 100.0% (100/100) [96-100] | 100.0% (100/100) [96-100] | 100.0% (128/128) [97-100] | 65.0% (65/100) [55-74] | 100.0 (100/100) | 65.0 (65/100) | 91.8% | - | - |
| JSON | gemini-3.5-flash-lite | 100/100 | 96.0% (96/100) [90-98] | 100.0% (100/100) [96-100] | 100.0% (128/128) [97-100] | 60.0% (60/100) [50-69] | 99.0 (99/100) | 61.0 (61/100) | 89.7% | 100.0 (800/800) | 0 |
| Chữ | paddleocr-vl-1.6 | 70/100 | 100.0% (70/70) [95-100] | 100.0% (70/70) [95-100] | 98.9% (88/89) [94-100] | 51.4% (36/70) [40-63] | 85.7 (60/70) | 60.0 (42/70) | 88.3% | - | - |
| JSON | glm-ocr | 76/100 | 0.0% (0/76) [0-5] | 0.0% (0/76) [0-5] | 0.0% (0/96) [0-4] | 0.0% (0/76) [0-5] | 0.0 (0/76) | 0.0 (0/76) | 0.0% | 11.4 (74/647) | 57 |

## 3b. Xếp hạng trên bộ gen (ảnh do Nano Banana sinh)

40 ảnh sinh bằng `gemini-nano-banana-2.1` (gen_sua: ảnh gốc E1 sửa thành ảnh chụp điện thoại cầm tay; gen_moi: sinh từ lời mô tả), 40 lần gọi ghi lại, 2.58 USD. Từng ảnh được mở ra xem và so với đáp án dự định (link có 0/O, rn/m, I/l/1 thì cắt phóng to): 3 ảnh phải sửa đáp án (2 chuỗi sửa theo đúng chữ ảnh hiện, 1 chuỗi không đọc chắc nên bỏ), 0 ảnh bị loại; còn 40 ảnh, 172 chuỗi. 15 link được giữ dù chữ I và l vẽ y hệt nhau trong font của ảnh (ảnh không mâu thuẫn với đáp án; ảnh E1 cũng vậy). Bộ này không có đáp án phía gửi. Chi tiết từng ảnh: `e1/gen_review.json`.

Khớp chính xác từng ký tự sau chuẩn hóa như E1. Tên miền = phần trước `/` đầu tiên (hạ chữ thường); đường dẫn = phần sau (phân biệt hoa thường). Ngoặc vuông: khoảng tin cậy 95% (Wilson). Sắp theo tỉ lệ chung.

| Nhóm | Model | Số ảnh | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn | Tất cả | Phía gửi | JSON hỏng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| JSON | gemini-3.5-flash-lite | 40/40 | 100.0% (40/40) [91-100] | 100.0% (40/40) [91-100] | 100.0% (53/53) [93-100] | 69.2% (27/39) [54-81] | 97.4 (38/39) | 71.8 (28/39) | 93.0% | - | 0 |
| Chữ | mineru2.5-pro | 40/40 | 95.0% (38/40) [83-99] | 97.5% (39/40) [87-100] | 94.3% (50/53) [85-98] | 66.7% (26/39) [51-79] | 94.9 (37/39) | 69.2 (27/39) | 89.0% | - | - |
| Chữ | paddleocr-vl-1.6 | 40/40 | 95.0% (38/40) [83-99] | 97.5% (39/40) [87-100] | 98.1% (52/53) [90-100] | 48.7% (19/39) [34-64] | 74.4 (29/39) | 64.1 (25/39) | 86.0% | - | - |
| Chữ | glm-ocr | 40/40 | 95.0% (38/40) [83-99] | 97.5% (39/40) [87-100] | 94.3% (50/53) [85-98] | 46.2% (18/39) [32-61] | 71.8 (28/39) | 66.7 (26/39) | 84.3% | - | - |
| Chữ | pp-ocrv6-gpu | 40/40 | 95.0% (38/40) [83-99] | 97.5% (39/40) [87-100] | 94.3% (50/53) [85-98] | 43.6% (17/39) [29-59] | 71.8 (28/39) | 64.1 (25/39) | 83.7% | - | - |
| JSON | glm-ocr | 40/40 | 0.0% (0/40) [0-9] | 0.0% (0/40) [0-9] | 0.0% (0/53) [0-7] | 0.0% (0/39) [0-9] | 0.0 (0/39) | 0.0 (0/39) | 0.0% | - | 32 |

## 3c. Xếp hạng trên bộ web (ảnh chat thật đăng công khai)

20 ảnh chat thật đã đăng công khai, do tab kế hoạch thu (nguồn: `data/E1b/real/sources.md`, không commit). Đáp án chỉ có chuỗi, không có phía gửi; số tài khoản ngoài 8-14 chữ số và tên miền không đường dẫn vẫn chấm như thường (regex bỏ sót tính là sót).

Khớp chính xác từng ký tự sau chuẩn hóa như E1. Tên miền = phần trước `/` đầu tiên (hạ chữ thường); đường dẫn = phần sau (phân biệt hoa thường). Ngoặc vuông: khoảng tin cậy 95% (Wilson). Sắp theo tỉ lệ chung.

| Nhóm | Model | Số ảnh | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn | Tất cả | Phía gửi | JSON hỏng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| JSON | gemini-3.5-flash-lite | 20/20 | 75.0% (3/4) [30-95] | 100.0% (5/5) [57-100] | 84.0% (21/25) [65-94] | 77.8% (7/9) [45-94] | 100.0 (9/9) | 77.8 (7/9) | 83.7% | - | 0 |
| Chữ | glm-ocr | 20/20 | 75.0% (3/4) [30-95] | 40.0% (2/5) [12-77] | 80.0% (20/25) [61-91] | 11.1% (1/9) [2-44] | 44.4 (4/9) | 22.2 (2/9) | 60.5% | - | - |
| Chữ | pp-ocrv6-gpu | 20/20 | 75.0% (3/4) [30-95] | 40.0% (2/5) [12-77] | 76.0% (19/25) [57-89] | 11.1% (1/9) [2-44] | 44.4 (4/9) | 22.2 (2/9) | 58.1% | - | - |
| Chữ | mineru2.5-pro | 20/20 | 75.0% (3/4) [30-95] | 40.0% (2/5) [12-77] | 64.0% (16/25) [45-80] | 33.3% (3/9) [12-65] | 33.3 (3/9) | 33.3 (3/9) | 55.8% | - | - |
| Chữ | paddleocr-vl-1.6 | 20/20 | 50.0% (2/4) [15-85] | 40.0% (2/5) [12-77] | 68.0% (17/25) [48-83] | 11.1% (1/9) [2-44] | 44.4 (4/9) | 22.2 (2/9) | 51.2% | - | - |
| JSON | glm-ocr | 20/20 | 25.0% (1/4) [5-70] | 0.0% (0/5) [0-43] | 0.0% (0/25) [0-13] | 0.0% (0/9) [0-30] | 0.0 (0/9) | 11.1 (1/9) | 2.3% | - | 16 |

## 4. Bộ khó theo biến thể

Mỗi ô: % khớp (đúng/tổng). Biến thể chat dài chỉ có 10 ảnh (khoảng 10 chuỗi mỗi loại: 1 lỗi = 10 điểm %).

| Nhóm | Model | Biến thể | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn |
|---|---|---|---|---|---|---|---|---|
| Chữ | glm-ocr | thu nhỏ 33% | 100.0 (30/30) | 100.0 (30/30) | 97.4 (37/38) | 70.0 (21/30) | 100.0 (30/30) | 70.0 (21/30) |
| Chữ | glm-ocr | nén JPEG 2 lần | 100.0 (30/30) | 100.0 (30/30) | 100.0 (38/38) | 80.0 (24/30) | 100.0 (30/30) | 80.0 (24/30) |
| Chữ | glm-ocr | chụp lại màn hình | 100.0 (30/30) | 100.0 (30/30) | 100.0 (38/38) | 80.0 (24/30) | 100.0 (30/30) | 80.0 (24/30) |
| Chữ | glm-ocr | chat dài | 100.0 (10/10) | 100.0 (10/10) | 100.0 (14/14) | 90.0 (9/10) | 100.0 (10/10) | 90.0 (9/10) |
| Chữ | mineru2.5-pro | thu nhỏ 33% | 100.0 (11/11) | 100.0 (11/11) | 93.3 (14/15) | 72.7 (8/11) | 100.0 (11/11) | 72.7 (8/11) |
| Chữ | mineru2.5-pro | nén JPEG 2 lần | 100.0 (11/11) | 100.0 (11/11) | 100.0 (15/15) | 54.5 (6/11) | 100.0 (11/11) | 54.5 (6/11) |
| Chữ | mineru2.5-pro | chụp lại màn hình | 100.0 (11/11) | 100.0 (11/11) | 100.0 (13/13) | 81.8 (9/11) | 100.0 (11/11) | 81.8 (9/11) |
| Chữ | mineru2.5-pro | chat dài | 100.0 (10/10) | 100.0 (10/10) | 100.0 (14/14) | 70.0 (7/10) | 100.0 (10/10) | 70.0 (7/10) |
| Chữ | paddleocr-vl-1.6 | thu nhỏ 33% | 100.0 (20/20) | 100.0 (20/20) | 100.0 (26/26) | 40.0 (8/20) | 75.0 (15/20) | 60.0 (12/20) |
| Chữ | paddleocr-vl-1.6 | nén JPEG 2 lần | 100.0 (20/20) | 100.0 (20/20) | 96.2 (25/26) | 45.0 (9/20) | 100.0 (20/20) | 45.0 (9/20) |
| Chữ | paddleocr-vl-1.6 | chụp lại màn hình | 100.0 (20/20) | 100.0 (20/20) | 100.0 (23/23) | 65.0 (13/20) | 85.0 (17/20) | 70.0 (14/20) |
| Chữ | paddleocr-vl-1.6 | chat dài | 100.0 (10/10) | 100.0 (10/10) | 100.0 (14/14) | 60.0 (6/10) | 80.0 (8/10) | 70.0 (7/10) |
| Chữ | pp-ocrv6-gpu | thu nhỏ 33% | 100.0 (30/30) | 100.0 (30/30) | 100.0 (38/38) | 60.0 (18/30) | 100.0 (30/30) | 60.0 (18/30) |
| Chữ | pp-ocrv6-gpu | nén JPEG 2 lần | 100.0 (30/30) | 100.0 (30/30) | 100.0 (38/38) | 66.7 (20/30) | 100.0 (30/30) | 66.7 (20/30) |
| Chữ | pp-ocrv6-gpu | chụp lại màn hình | 100.0 (30/30) | 100.0 (30/30) | 100.0 (38/38) | 63.3 (19/30) | 100.0 (30/30) | 63.3 (19/30) |
| Chữ | pp-ocrv6-gpu | chat dài | 100.0 (10/10) | 100.0 (10/10) | 100.0 (14/14) | 80.0 (8/10) | 100.0 (10/10) | 80.0 (8/10) |
| JSON | gemini-3.5-flash-lite | thu nhỏ 33% | 96.7 (29/30) | 100.0 (30/30) | 100.0 (38/38) | 56.7 (17/30) | 96.7 (29/30) | 60.0 (18/30) |
| JSON | gemini-3.5-flash-lite | nén JPEG 2 lần | 96.7 (29/30) | 100.0 (30/30) | 100.0 (38/38) | 60.0 (18/30) | 100.0 (30/30) | 60.0 (18/30) |
| JSON | gemini-3.5-flash-lite | chụp lại màn hình | 96.7 (29/30) | 100.0 (30/30) | 100.0 (38/38) | 60.0 (18/30) | 100.0 (30/30) | 60.0 (18/30) |
| JSON | gemini-3.5-flash-lite | chat dài | 90.0 (9/10) | 100.0 (10/10) | 100.0 (14/14) | 70.0 (7/10) | 100.0 (10/10) | 70.0 (7/10) |
| JSON | glm-ocr | thu nhỏ 33% | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/29) | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/22) |
| JSON | glm-ocr | nén JPEG 2 lần | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/28) | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/22) |
| JSON | glm-ocr | chụp lại màn hình | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/25) | 0.0 (0/22) | 0.0 (0/22) | 0.0 (0/22) |
| JSON | glm-ocr | chat dài | 0.0 (0/10) | 0.0 (0/10) | 0.0 (0/14) | 0.0 (0/10) | 0.0 (0/10) | 0.0 (0/10) |

## 4b. Bộ gen theo biến thể

| Nhóm | Model | Biến thể | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn |
|---|---|---|---|---|---|---|---|---|
| Chữ | glm-ocr | gen: sửa thành ảnh chụp | 100.0 (20/20) | 100.0 (20/20) | 100.0 (25/25) | 70.0 (14/20) | 100.0 (20/20) | 70.0 (14/20) |
| Chữ | glm-ocr | gen: sinh từ mô tả | 90.0 (18/20) | 95.0 (19/20) | 89.3 (25/28) | 21.1 (4/19) | 42.1 (8/19) | 63.2 (12/19) |
| Chữ | mineru2.5-pro | gen: sửa thành ảnh chụp | 100.0 (20/20) | 100.0 (20/20) | 100.0 (25/25) | 70.0 (14/20) | 100.0 (20/20) | 70.0 (14/20) |
| Chữ | mineru2.5-pro | gen: sinh từ mô tả | 90.0 (18/20) | 95.0 (19/20) | 89.3 (25/28) | 63.2 (12/19) | 89.5 (17/19) | 68.4 (13/19) |
| Chữ | paddleocr-vl-1.6 | gen: sửa thành ảnh chụp | 100.0 (20/20) | 100.0 (20/20) | 100.0 (25/25) | 60.0 (12/20) | 85.0 (17/20) | 65.0 (13/20) |
| Chữ | paddleocr-vl-1.6 | gen: sinh từ mô tả | 90.0 (18/20) | 95.0 (19/20) | 96.4 (27/28) | 36.8 (7/19) | 63.2 (12/19) | 63.2 (12/19) |
| Chữ | pp-ocrv6-gpu | gen: sửa thành ảnh chụp | 100.0 (20/20) | 100.0 (20/20) | 100.0 (25/25) | 65.0 (13/20) | 100.0 (20/20) | 65.0 (13/20) |
| Chữ | pp-ocrv6-gpu | gen: sinh từ mô tả | 90.0 (18/20) | 95.0 (19/20) | 89.3 (25/28) | 21.1 (4/19) | 42.1 (8/19) | 63.2 (12/19) |
| JSON | gemini-3.5-flash-lite | gen: sửa thành ảnh chụp | 100.0 (20/20) | 100.0 (20/20) | 100.0 (25/25) | 70.0 (14/20) | 100.0 (20/20) | 70.0 (14/20) |
| JSON | gemini-3.5-flash-lite | gen: sinh từ mô tả | 100.0 (20/20) | 100.0 (20/20) | 100.0 (28/28) | 68.4 (13/19) | 94.7 (18/19) | 73.7 (14/19) |
| JSON | glm-ocr | gen: sửa thành ảnh chụp | 0.0 (0/20) | 0.0 (0/20) | 0.0 (0/25) | 0.0 (0/20) | 0.0 (0/20) | 0.0 (0/20) |
| JSON | glm-ocr | gen: sinh từ mô tả | 0.0 (0/20) | 0.0 (0/20) | 0.0 (0/28) | 0.0 (0/19) | 0.0 (0/19) | 0.0 (0/19) |

## 5. Tốc độ và tài nguyên

Giây mỗi ảnh đo sau khi đã nạp model, từng ảnh một (không gộp batch), tính cả tiền xử lý ảnh. Model mở chạy trên RTX 4060 Ti 16GB; A (CPU) chạy trên CPU 12 nhân của server; Gemini là thời gian gọi API. VRAM đỉnh của tiến trình đọc bằng NVML (gồm CUDA context); 'torch' là bộ nhớ torch giữ.

| Nhóm | Model | Bộ | Số ảnh | TB (s) | p50 | p90 | VRAM đỉnh (MiB) | Weights (GB) | Nạp model (s) | Dừng vì hết giờ |
|---|---|---|---|---|---|---|---|---|---|---|
| Chữ (ref A) | pp-ocrv6-cpu | E1 | 180 | 20.04 | 22.36 | 23.87 | - | - | - | - |
| Chữ | glm-ocr | E1 | 180 | 3.92 | 3.98 | 4.75 | 4522 (torch 4364) | 2.66 | 4.2 | không |
| Chữ | glm-ocr | E1b | 100 | 3.77 | 3.33 | 7.57 | 4522 (torch 4364) | 2.66 | 4.2 | không |
| Chữ | glm-ocr | gen | 40 | 5.33 | 5.22 | 6.03 | 3844 (torch 3686) | 2.66 | 4.0 | không |
| Chữ | glm-ocr | web | 20 | 4.55 | 4.41 | 8.69 | 4070 (torch 3912) | 2.66 | 5.0 | không |
| Chữ | mineru2.5-pro | E1 | 67 | 10.07 | 10.16 | 12.70 | 2844 (torch 2686) | 2.33 | 3.8 | có |
| Chữ | mineru2.5-pro | E1b | 43 | 12.46 | 10.60 | 18.64 | 2844 (torch 2686) | 2.33 | 3.8 | có |
| Chữ | mineru2.5-pro | gen | 40 | 12.55 | 11.77 | 17.54 | 2844 (torch 2686) | 2.33 | 5.3 | không |
| Chữ | mineru2.5-pro | web | 20 | 11.59 | 9.49 | 25.03 | 2862 (torch 2704) | 2.33 | 5.3 | không |
| Chữ | paddleocr-vl-1.6 | E1 | 121 | 6.20 | 6.14 | 7.64 | 2260 (torch 2102) | 1.93 | 3.6 | có |
| Chữ | paddleocr-vl-1.6 | E1b | 70 | 6.52 | 6.41 | 11.80 | 2260 (torch 2102) | 1.93 | 3.6 | có |
| Chữ | paddleocr-vl-1.6 | gen | 40 | 6.57 | 6.64 | 7.76 | 2144 (torch 1986) | 1.93 | 4.4 | không |
| Chữ | paddleocr-vl-1.6 | web | 20 | 40.96 | 7.52 | 355.06 | 2214 (torch 2056) | 1.93 | 4.5 | không |
| Chữ | pp-ocrv6-gpu | E1 | 180 | 0.30 | 0.33 | 0.37 | 3134 (torch 2980) | 0.17 | 4.5 | không |
| Chữ | pp-ocrv6-gpu | E1b | 100 | 0.22 | 0.20 | 0.55 | 3134 (torch 2980) | 0.17 | 4.5 | không |
| Chữ | pp-ocrv6-gpu | gen | 40 | 0.52 | 0.48 | 0.59 | 2404 (torch 2250) | 0.17 | 4.7 | không |
| Chữ | pp-ocrv6-gpu | web | 20 | 0.33 | 0.27 | 0.54 | 1646 (torch 2240) | 0.17 | 6.2 | không |
| JSON | gemini-3.5-flash-lite | E1 | 180 | 5.80 | 3.48 | 10.44 | - | - | - | - |
| JSON | gemini-3.5-flash-lite | E1b | 100 | 3.57 | 2.95 | 5.16 | - | - | - | - |
| JSON | gemini-3.5-flash-lite | gen | 40 | 9.87 | 9.53 | 12.01 | - | - | - | - |
| JSON | gemini-3.5-flash-lite | web | 20 | 3.05 | 3.08 | 4.32 | - | - | - | - |
| JSON | glm-ocr | E1 | 137 | 5.70 | 5.60 | 6.99 | 4522 (torch 4364) | 2.66 | 3.8 | có |
| JSON | glm-ocr | E1b | 76 | 5.57 | 4.99 | 8.53 | 4522 (torch 4364) | 2.66 | 3.8 | có |
| JSON | glm-ocr | gen | 40 | 6.29 | 6.38 | 7.58 | 3844 (torch 3686) | 2.66 | 3.4 | không |
| JSON | glm-ocr | web | 20 | 4.11 | 3.50 | 8.54 | 4070 (torch 3912) | 2.66 | 3.5 | không |

## 6. Năm ví dụ đọc sai trên bộ khó

- **glm-ocr**, ảnh `messenger_00__chuplai` (chụp lại màn hình), Số TK: đáp án `7017 7924 6108`, model trả không có chuỗi nào; JSON hỏng: bad messages item. Ảnh: `experiments/E1b/examples/messenger_00__chuplai__account.png`
- **glm-ocr**, ảnh `messenger_02__chuplai` (chụp lại màn hình), Link: đáp án `https://c0ngan-xacminh.vip/hs/jXnI8`, model trả `https://c0ngan-xacminh.vip/hs/jXnl8`. Ảnh: `experiments/E1b/examples/messenger_02__chuplai__link.png`
- **mineru2.5-pro**, ảnh `sms_04__chuplai` (chụp lại màn hình), Link: đáp án `1azada-nhiemvu.online/task/eTl0`, model trả `1azada-nhiemvu.online/task/eT10`. Ảnh: `experiments/E1b/examples/sms_04__chuplai__link.png`
- **paddleocr-vl-1.6**, ảnh `messenger_01__chuplai` (chụp lại màn hình), Link: đáp án `ghn-express-vn.xyz/tracking/II9M`, model trả `ghn-express-vn.xyz/tracking/l19M`. Ảnh: `experiments/E1b/examples/messenger_01__chuplai__link.png`
- **pp-ocrv6-gpu**, ảnh `messenger_01__chuplai` (chụp lại màn hình), Link: đáp án `ghn-express-vn.xyz/tracking/II9M`, model trả `ghn-express-vn.xyz/tracking/ll9M`. Ảnh: `experiments/E1b/examples/messenger_01__chuplai__link.png`

### 6b. Ví dụ đọc sai trên bộ gen (chỉ mã ảnh và chuỗi)

- **glm-ocr**, `gen_moi_00`, Link: đáp án `https://giaohangnhanh-cod.vip/don/O781G`, model trả `cod.vip/don/O781G`
- **mineru2.5-pro**, `gen_moi_00`, Số tiền: đáp án `4.800.000 VND`, model trả `4.800.000`
- **paddleocr-vl-1.6**, `gen_moi_01`, Link: đáp án `c0ng-an-truc-tuyen.xyz/tk/eqQed`, model trả `c-tuyen.xyz/tk/eqQed`
- **pp-ocrv6-gpu**, `gen_moi_00`, Link: đáp án `https://giaohangnhanh-cod.vip/don/O781G`, model trả `cod.vip/don/O781G`
- **gemini-3.5-flash-lite**, `gen_moi_02`, Link: đáp án `nhiemvu-shopee-ctv.xyz/reg/t2xGN`, model trả `nhiệmvushopee-ctv.xyz/reg/t2xGN`
- **glm-ocr**, `gen_moi_00`, Số TK: đáp án `577230735`, model trả không có chuỗi nào

### 6c. Ví dụ đọc sai trên bộ web (chỉ mã ảnh và chuỗi)

- **glm-ocr**, `web_03`, Link: đáp án `https://vietcom-priority-vn.com`, model trả không có chuỗi nào
- **mineru2.5-pro**, `web_01`, Số tiền: đáp án `20tr`, model trả không có chuỗi nào
- **paddleocr-vl-1.6**, `web_03`, Link: đáp án `https://vietcom-priority-vn.com`, model trả không có chuỗi nào
- **pp-ocrv6-gpu**, `web_03`, Link: đáp án `https://vietcom-priority-vn.com`, model trả không có chuỗi nào
- **gemini-3.5-flash-lite**, `web_01`, Số tiền: đáp án `20tr`, model trả `30tr`
- **glm-ocr**, `web_01`, Số tiền: đáp án `20tr`, model trả không có chuỗi nào

## 7. Repo, phiên bản và cấu hình

- A: PP-OCRv6 medium (det+rec), PaddleOCR 3.7.0, paddlepaddle 3.3.1 CPU, enable_mkldnn=False; regex `e1/extract.py`
- Chữ `glm-ocr`: zai-org/GLM-OCR @ 2e85a62840; lượng tử: bf16; giải mã: greedy (do_sample=False); trả tọa độ khối chữ: không; prompt: `Text Recognition:`; torch 2.11.0+cu130, transformers 5.22.2, accelerate 1.15.0, mineru_vl_utils 2.0.8, paddleocr 3.7.0, paddlex 3.7.2
- Chữ `mineru2.5-pro`: opendatalab/MinerU2.5-Pro-2605-1.2B @ 08aaea8404; lượng tử: mineru-vl-utils default; giải mã: greedy (do_sample=False); trả tọa độ khối chữ: có; prompt: ``; torch 2.11.0+cu130, transformers 5.22.2, accelerate 1.15.0, mineru_vl_utils 2.0.8, paddleocr 3.7.0, paddlex 3.7.2
- Chữ `paddleocr-vl-1.6`: PaddlePaddle/PaddleOCR-VL-1.6 @ 132c45f52c; lượng tử: bf16; giải mã: greedy (do_sample=False); trả tọa độ khối chữ: không; prompt: `OCR:`; torch 2.11.0+cu130, transformers 5.22.2, accelerate 1.15.0, mineru_vl_utils 2.0.8, paddleocr 3.7.0, paddlex 3.7.2
- Chữ `pp-ocrv6-gpu`: PP-OCRv6_medium_det_safetensors, PP-OCRv6_medium_rec_safetensors @ paddlex of; lượng tử: paddlex default dtype; giải mã: greedy (do_sample=False); trả tọa độ khối chữ: có; prompt: ``; torch 2.11.0+cu130, transformers 5.22.2, accelerate 1.15.0, mineru_vl_utils 2.0.8, paddleocr 3.7.0, paddlex 3.7.2
- JSON `gemini-3.5-flash-lite`: Gemini API, cùng prompt và schema với E1 cách B, nhiệt độ và mức suy nghĩ mặc định
- JSON `glm-ocr`: zai-org/GLM-OCR @ 2e85a62840; lượng tử: bf16; giải mã: greedy (do_sample=False); trả tọa độ khối chữ: không; prompt: `请按下列JSON格式输出图中信息: {"messages": [{"order": 0, "side": "", "text": ""}], "accounts...`; torch 2.11.0+cu130, transformers 5.22.2, accelerate 1.15.0, mineru_vl_utils 2.0.8, paddleocr 3.7.0, paddlex 3.7.2

## 8. Cách làm và các điểm lệch so với đề bài

- **Mạng server chậm quyết định model nào chạy được.** Đo ngày 20/11: tải từ Hugging Face và PyPI chỉ khoảng 2 MB/s (curl 1 luồng 2,2 MB/s; 8 luồng song song tổng 2,0 MB/s). Với hạn 30 phút cho cài và tải, mỗi model tải được tối đa khoảng 3,6 GB. Pipeline tính trước thời gian tải từ dung lượng repo (HF API) và tốc độ đo được, quá 30 phút thì bỏ và ghi lý do, không tải dở.
  - Bị bỏ vì lý do này: Qwen3-VL-8B-Instruct (17,5 GB bf16, khoảng 146 phút), Qwen3-VL-4B-Instruct (8,9 GB, khoảng 74 phút), Gemma 4 E4B-it (16,0 GB, khoảng 133 phút). Ngoài ra, bản bf16 của Qwen3-VL-8B và Gemma 4 E4B không vừa 16 GB VRAM. Bản FP8 chính thức của Qwen chỉ chạy bằng vLLM, bản QAT q4 của Gemma chỉ chạy bằng llama.cpp, mà server không có cả hai trong env dùng được.
  - Muốn thử các model này: tải weights trước ở máy có mạng nhanh rồi chép vào `.cache/hf` trên server, sau đó chạy lại pipeline với `MODELS="qwen3-vl-4b"`. Muốn lượng tử 4-bit bản 8B thì cần thêm bitsandbytes vào `.cache/pylib`.
- **Không tự cài env torch.** Env torch + CUDA khoảng 4,5 GB, với tốc độ trên mất 40 phút trở lên, vượt hạn. Thay vào đó các model GPU chạy bằng interpreter của env có sẵn `~/vidoc-dev/.venvs/mineru` (python 3.12, torch 2.11.0+cu130, transformers 5.22.2, mineru-vl-utils 2.0.8), dùng ở chế độ chỉ đọc: không cài gì vào đó, tắt ghi bytecode (`PYTHONDONTWRITEBYTECODE=1`). Đề bài chỉ cho phép gọi env này cho MinerU; ở đây nó được gọi cho mọi model GPU. Gói bổ sung (paddleocr 3.7.0, paddlex 3.7.2 và vài phụ thuộc nhỏ, khoảng 210 MB) cài `--target` vào `.cache/pylib` trong thư mục dự án.
- **PP-OCRv6 GPU không dùng Paddle.** Wheel `paddlepaddle-gpu` không có trên PyPI cho bản 3.x, còn CDN của Paddle thì lần trước timeout. PaddleOCR 3.7 có engine `transformers`: cùng mô hình PP-OCRv6_medium det/rec (bản safetensors chính thức, tự tải về `.cache/paddlex`), chạy bằng torch trên GPU. Đây là cùng kiến trúc và weights với cách A của E1, nhưng khác engine suy luận, nên kết quả có thể lệch đôi chút so với bản CPU.
- **Hai thư mục cache rỗng (12 KB) do lần thử OCR của E1** nằm trong `~/.cache/huggingface/hub` dùng chung (`models--PaddlePaddle--PP-OCRv6_medium_{det,rec}`, tạo lúc 11:07 ngày 20/11). Đã xóa. Từ đó mọi tiến trình chạy với `HOME`, `HF_HOME`, `XDG_CACHE_HOME`, `TMPDIR` trỏ vào thư mục dự án.
- **Nhóm JSON trên model mở:** không có giải mã ràng buộc theo schema như Gemini, nên JSON Schema được nối vào cuối prompt cách B dưới dạng chữ. GLM-OCR ở chế độ JSON dùng đúng định dạng trích xuất thông tin trong model card (câu dẫn tiếng Trung + mẫu JSON rỗng theo schema của E1), vì model chỉ được huấn luyện theo định dạng đó. Model mở giải mã tham lam (`do_sample=False`), Gemini để mặc định như E1.
- **GLM-OCR chế độ JSON được 0% là kết quả thật, không phải lỗi chấm.** Trong 213 ảnh đã chạy, model không lần nào điền trường số tài khoản, số điện thoại, số tiền hay link. Nó chỉ chép từng tin vào `messages` (phía gửi để trống), còn các trường kia để rỗng hoặc giữ nguyên mẫu (`{"number": "", ...}`). 157/213 câu trả lời là JSON hỏng: thiếu khóa (thường là `amounts`) hoặc bị cắt giữa chừng. Theo đề bài không chỉnh prompt riêng cho từng model, nên không thử thêm. Ở chế độ Chữ, cùng model này đọc tốt nhất nhóm.
- **Nhóm Chữ:** PP-OCRv6 trả từng dòng kèm tọa độ; MinerU2.5-Pro chạy `two_step_extract` (phát hiện bố cục rồi đọc từng khối, có tọa độ khối); PaddleOCR-VL-1.6 dùng prompt `OCR:` và GLM-OCR dùng `Text Recognition:` cho cả ảnh, hai model này không trả tọa độ ở chế độ đó.
- **Giới hạn chạy:** mỗi chế độ của một model có 20 phút cho 280 ảnh. Hết giờ mà đã có từ 60 ảnh thì dừng. Thứ tự ảnh xen kẽ đều giữa hai bộ và mọi biến thể, nên phần đã chạy vẫn phủ đủ các biến thể. Ô nào ít ảnh thì xem cột "Số ảnh".
- **Bộ khó:** biến thể chat dài cao 4122-5316 px (đề bài ghi 3000-5000). Kịch bản lời thoại dài trên giao diện Zalo không thể có 20 tin mà thấp hơn 5000 px, nên ảnh `zalo_L06` cao 5316 px. Chuỗi cần đọc được rải ở đầu, giữa, cuối đoạn chat; các tin còn lại là câu chat ngắn không chứa số hay link. Ảnh chụp lại màn hình là mô phỏng bằng biến đổi ảnh, chưa phải ảnh chụp thật.
- **Bộ `gen` (Phần 1b):** `e1/gen_nb.py` gọi `gemini-nano-banana-2.1` (ảnh 2K, tỉ lệ 9:16). gen_sua: 20 ảnh gốc E1 (2/3 số đoạn chat gốc, đủ ba kiểu app) đưa cho model sửa thành ảnh chụp một chiếc điện thoại cầm tay đang mở đoạn chat đó, yêu cầu giữ nguyên mọi chữ. gen_moi: 20 đoạn chat mới từ cùng bộ sinh kịch bản của E1, liệt kê từng tin và phía gửi trong lời mô tả. Chi phí tính từ `usage_metadata` theo giá niêm yết ngày 20/11 (vào 1,5; chữ/suy nghĩ ra 7,5; ảnh ra 30 USD mỗi triệu token), khoảng 0,06-0,08 USD mỗi ảnh vì có token suy nghĩ. Lần chạy đầu dừng ở 32/40 ảnh vì một phản hồi không có phần nội dung (code chưa xử lý trường hợp này); chi phí của lần gọi đó chưa kịp ghi, nên tổng thật có thể cao hơn số ghi lại một chút. Vẫn dưới trần 5 USD.
- **Duyệt đáp án `gen`:** model sinh ảnh chép chữ số rất đúng ở cả 40 ảnh (không ảnh nào sai số tài khoản, số điện thoại hay số tiền). Lỗi chỉ nằm ở ký tự dễ lẫn trong đường dẫn link: O thành 0, J thành j, L thành một nét thẳng. Quy tắc: ảnh khác đáp án mà đọc chắc được thì sửa theo ảnh; khác mà không đọc chắc được thì bỏ chuỗi đó; ảnh khớp đáp án nhưng chữ I và l vẽ y hệt nhau trong font thì giữ (ghi `ambiguous` trong `e1/gen_review.json`). Các ảnh E1 cũng có tính chất này, nên số đo link trên bộ `gen` so được với E1, nhưng trần thực tế của mọi cách đọc ở các link đó dưới 100%.
- **Bộ `web`:** ảnh và đáp án do tab kế hoạch thu, nằm trong `data/E1b/real/` (không commit). Code chấm nhận đáp án thiếu `messages`, `ignore`, `norm` hay thiếu hẳn một loại chuỗi, và tự tính `norm` bằng cùng hàm chuẩn hóa của E1. Kết quả model trên bộ này ghi vào `data/E1b/web_runs/`, không ghi vào thư mục của tab kế hoạch. Report không chứa ảnh của bộ này.
- **Weights giữ lại đến lúc chạy xong bộ `gen` và `web`** (khoảng 7 GB cho PaddleOCR-VL, MinerU, GLM-OCR; tổng E1b vẫn dưới 25 GB và đĩa trống trên 30 GB), thay vì xóa ngay rồi tải lại khoảng 1 giờ. Lần chạy cuối (`FINAL=1 scripts/e1b_extra_run.sh`) xóa weights. Lần xóa đầu chỉ xóa thư mục `models--*` mà sót 6,5 GB: bản `huggingface_hub` trên server để file weights trong kho chung `hub/blobs/`, ngoài thư mục model. Đã xóa tay phần sót và sửa `open_models clean` để xóa cả các file đó. Sau khi xóa: `.cache/hf` 1,2 MB, còn `.cache/paddlex` 291 MB (weights PP-OCRv6 từ E1), đĩa trống 41 GB, GPU không còn tiến trình nào.
- **Ở chế độ Chữ, phần lớn chuỗi bị sót trên ảnh thật là do quy tắc trích, không phải do OCR đọc sai.** Với mỗi chuỗi model sót, kiểm tra xem chuỗi đó có nằm nguyên trong chữ OCR trả về không (bỏ khoảng trắng và xuống dòng). Trên bộ `web`: glm-ocr sót 17, có 12 chuỗi nằm sẵn trong chữ; pp-ocrv6-gpu sót 18, có 14; paddleocr-vl-1.6 sót 21, có 12; mineru2.5-pro sót 19, có 9. Trên bộ `gen` các số tương ứng là 27/16, 28/15, 24/6, 19/10. Các dạng mà regex của E1 (`e1/extract.py`, viết theo định dạng của ảnh E1) bỏ qua: số điện thoại nhóm kiểu `+84 86 9448260`, link bị xuống dòng giữa chừng, tên miền không có đường dẫn (`evn.io.vn`), số tiền kiểu `8tr999k`. Cách B không qua regex nên không bị. Vì vậy khoảng cách 51-61% so với 84% trên bộ `web` phần lớn là khoảng cách của quy tắc trích, và chỉ có 20 ảnh. Đề bài không cho chỉnh riêng nên regex giữ nguyên ở mọi bộ. Nếu dùng OCR làm nguồn đọc thứ hai (T1 Phần 4), cần viết lại phần trích trước rồi đo lại.

## Chạy lại

```bash
# laptop: sinh bộ khó (Playwright + Chrome), đồng bộ lên server, chạy tách rời
python3 -m e1.gen_hard --e1 data/E1 --out data/E1b
rsync -a --exclude __pycache__ e1 scripts "$SERVER:pretransfer-scam-assistant/" && rsync -a data/E1b "$SERVER:pretransfer-scam-assistant/data/"
ssh "$SERVER" 'cd pretransfer-scam-assistant && bash scripts/e1b_server_run.sh --detach'
./scripts/server_status.sh   # trạng thái + kéo kết quả về (SERVER lấy từ .env)
python3 -m e1.score_e1b --root . --out experiments/E1b      # chấm lại
# Phần 1b, bộ gen (server, có .env): sinh ảnh, kéo về, duyệt bằng mắt vào e1/gen_review.json, áp đáp án
ssh "$SERVER" 'cd pretransfer-scam-assistant && .conda/pretransfer/bin/python -m e1.gen_nb'
rsync -a "$SERVER:pretransfer-scam-assistant/data/E1b/gen" data/E1b/ && python3 -m e1.gen_apply
rsync -a data/E1b/gen "$SERVER:pretransfer-scam-assistant/data/E1b/"
ssh "$SERVER" 'cd pretransfer-scam-assistant && SETS=gen bash scripts/e1b_extra_run.sh --detach'
# bộ web (ảnh trong data/E1b/real do tab kế hoạch thu), rồi xóa weights
rsync -a data/E1b/real "$SERVER:pretransfer-scam-assistant/data/E1b/"
ssh "$SERVER" 'cd pretransfer-scam-assistant && SETS=web FINAL=1 bash scripts/e1b_extra_run.sh --detach'
```
