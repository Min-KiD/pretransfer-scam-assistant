# E1b tóm tắt

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

Chi tiết: experiments/E1b/report.md
