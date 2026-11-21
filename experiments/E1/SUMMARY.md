# E1 tóm tắt

Khớp chính xác (gộp 6 biến thể):
- A paddleocr (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 68.7%, Số tiền 100.0%
- B gemini-3.5-flash-lite (180 ảnh): Số TK 95.6%, SĐT 100.0%, Link 68.2%, Số tiền 100.0%
- B gemini-3.8-flash (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 69.3%, Số tiền 100.0%
- B gemini-4-carbon (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 92.7%, Số tiền 100.0%
- C gemini-3.5-flash-lite (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 65.9%, Số tiền 100.0%
- C gemini-3.8-flash (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 67.0%, Số tiền 100.0%
- C gemini-4-carbon (180 ảnh): Số TK 100.0%, SĐT 100.0%, Link 93.3%, Số tiền 100.0%

**Đề xuất: giữ cả OCR riêng và VLM** (cách B không qua quy tắc với model nào).
- gemini-3.5-flash-lite, Số TK: B sai 8; A (OCR) đúng 8 trong số đó; C sửa được 8, ở biến thể: mờ nhẹ (3), tối (2), thu nhỏ 50% (2), gốc (1); C làm hỏng 0 chuỗi B vốn đúng.
- gemini-3.5-flash-lite, Link: B sai 57; A (OCR) đúng 18 trong số đó; C sửa được 9, ở biến thể: JPEG q40 (2), cắt mép trên (2), gốc (2), thu nhỏ 50% (1), tối (1), mờ nhẹ (1); C làm hỏng 13 chuỗi B vốn đúng.
- gemini-3.8-flash, Link: B sai 55; A (OCR) đúng 15 trong số đó; C sửa được 11, ở biến thể: JPEG q40 (3), mờ nhẹ (2), cắt mép trên (2), tối (2), gốc (2); C làm hỏng 15 chuỗi B vốn đúng.
- gemini-4-carbon, Link: B sai 13; A (OCR) đúng 4 trong số đó; C sửa được 5, ở biến thể: cắt mép trên (2), JPEG q40 (1), gốc (1), mờ nhẹ (1); C làm hỏng 4 chuỗi B vốn đúng.

Chi tiết: experiments/E1/report.md
