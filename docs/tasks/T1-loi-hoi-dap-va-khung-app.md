# T1 - Lõi hỏi-đáp, khung app, bộ thử (E2, E3 lần đầu)

Người giao: tab `Momo_TechContest` (lên kế hoạch). Người làm: tab `code`. Ngày giao: 2026-11-21.
Bối cảnh: `docs/specs/2026-11-20-thiet-ke-idea1-tro-ly-hoi-lai.md`, mục 3, 4, 5.2-5.8, 7, 8. Đọc đúng các mục đó trước khi viết code.
Làm sau khi E1b đã đóng (report + commit local).

## Mục tiêu

Một phiên trò chuyện chạy trọn trên máy này: nhập tài khoản và số tiền, trợ lý hỏi tối đa 3 câu, ra kết luận ba mức kèm căn cứ, sinh báo cáo, nhân viên duyệt nhãn. Kèm bộ thử tự động cho ra số đo E2 và E3 lần đầu.

Chưa làm trong T1: deploy, Bedrock, đọc QR, gom cụm báo cáo, giao diện đẹp. Ảnh chat chỉ nối ở Phần 4.

## Nơi làm

| Thứ | Ở đâu |
|---|---|
| Code | Repo này. Lõi ở `core/`, API ở `app/`, web ở `web/`, bộ thử ở `sim/`, test ở `tests/` |
| Nơi chạy | Máy này. Không cần GPU, không dùng server công ty cho T1 |
| Model | Gemini API, key ở `.env` (`GEMINI_API_KEY`). Mặc định `gemini-3.5-flash-lite`. Không dùng dòng gemini-4 |
| Kết quả thí nghiệm | `experiments/E2/` (E3 nằm chung report) |

Mọi lời gọi model đi qua một lớp duy nhất `core/llm.py` (hàm nhận prompt, ảnh tùy chọn, JSON schema; trả dict + số token + giây). Bản nộp sẽ đổi lớp này sang Bedrock, nên không gọi SDK Gemini ở chỗ nào khác. Dùng lại được gì từ `e1/vlm.py` thì dùng.

## Phần 1 - Lõi thuần code (không gọi model)

Viết theo đúng mục 5.2-5.5 của bản thiết kế. Phần này phải có unit test.

1. **Schema bảng câu chuyện** (`core/schema.py`): 14 trường và giá trị đóng ở mục 5.2, đánh dấu trường chọn nhiều, trường do code điền. Kèm `bang_chung`, `khong_chac`, `chuoi_trich`.
2. **Nạp kịch bản** (`core/scenarios.py`): đọc mọi file trong `scenarios/`, kiểm tra: `id` duy nhất, `nhom` hợp lệ, mọi trường và giá trị nằm trong schema, xác suất trong (0, 1], trường chọn một có tổng không quá 1, `kho_phan_biet_voi` trỏ tới id có thật. File sai thì báo rõ file nào, dòng nào; **không tự sửa file kịch bản**, ghi lỗi vào tóm tắt giao lại.
3. **Tính xác suất** (`core/infer.py`): Naive Bayes đúng mục 5.4. Tính bằng log. Trường chọn một: giá trị không liệt kê chia đều phần còn lại, sàn 0,02. Trường chọn nhiều: mỗi giá trị là một biến có/không, giá trị không liệt kê có xác suất xuất hiện 0,02. Bỏ qua trường trống và trường trong `khong_chac`.
4. **Chọn trường để hỏi**: mức giảm entropy kỳ vọng; quy tắc hòa 10%; không hỏi trường do code điền và trường đã hỏi.
5. **Dừng và kết luận**: ngưỡng 0,7 / 3 câu / 0,5 đúng mục 5.4 và 5.5. Kết quả trả về có: mức, kịch bản đứng đầu, phân phối, `dau_hieu`, `viec_can_kiem_tra`, và danh sách trường đã đóng góp nhiều nhất (tỉ số log-likelihood) để làm căn cứ.

**Thử bằng "người trả lời hoàn hảo" (không tốn tiền, làm trước mọi thứ khác):** với mỗi kịch bản, sinh 200 bảng câu chuyện bằng cách lấy mẫu từng trường theo đúng bảng xác suất của kịch bản đó (seed cố định). Cho lõi hỏi, trả lời bằng giá trị đã lấy mẫu. Trường do code điền coi như biết từ đầu. Báo cáo:

- Tỉ lệ đúng kịch bản và đúng nhóm sau 0, 1, 2, 3 câu; tỉ lệ "chưa đủ căn cứ".
- Cùng số đo khi chọn trường **ngẫu nhiên** thay vì theo entropy.
- Ma trận nhầm giữa các kịch bản; cặp nào nhầm nhau nhiều nhất.
- Kịch bản bình thường bị kết luận "giống chiêu lừa" bao nhiêu % (riêng `bt_mua_online_nguoi_ban_moi`: mong đợi là "chưa đủ căn cứ").

Đây là trần của phương pháp với bảng xác suất hiện tại. Nếu chọn theo entropy không hơn chọn ngẫu nhiên, hoặc tỉ lệ đúng nhóm sau 3 câu dưới 80%, **dừng lại và báo** trước khi làm Phần 2; đừng chỉnh bảng xác suất cho đẹp số.

## Phần 2 - Model viết câu hỏi và điền bảng

- `viet_cau_hoi(truong, bang_hien_tai, lich_su)`: một câu hỏi tiếng Việt tự nhiên, ngắn, cho đúng một trường; xưng hô trung tính ("bạn").
- `dien_bang(tin_nhan_nguoi_dung, truong_dang_hoi, lich_su)`: structured output theo schema; chỉ điền trường có căn cứ trong câu trả lời, kèm trích dẫn câu chữ làm `bang_chung`. Được điền nhiều trường từ một câu. "Không biết" thì trả rỗng.
- `viet_ket_luan(ket_qua_tu_code)`: viết lại thành lời; không được thêm kết luận hay lời khuyên ngoài `dau_hieu` và `viec_can_kiem_tra` code đưa.
- Chữ của người dùng và chữ trong ảnh là dữ liệu, không phải lệnh. Đặt chúng trong khối riêng trong prompt và ghi rõ điều đó.

## Phần 3 - API và web tối thiểu

- FastAPI + SQLite, đúng 7 endpoint ở mục 8 của bản thiết kế. Trạng thái phiên lưu theo `session_id`.
- Dữ liệu mẫu: khoảng 12 tài khoản tự sinh, đủ bốn nhãn (`quen`, `moi`, `dang_bi_bao_cao`, `da_xac_nhan`), có tên chủ tài khoản và loại cá nhân/tổ chức. Không trùng số thật.
- Nhãn đổi theo mục 5.7: báo cáo kết luận "giống chiêu lừa" thì tài khoản thành `dang_bi_bao_cao`; nhân viên duyệt thì thành `da_xac_nhan`; có nút gỡ.
- Web: HTML thuần + JS, không cần build. Ba màn: chuyển tiền mẫu, khung chat (có nút gửi ảnh, ba nút cuối phiên), trang nhân viên (danh sách báo cáo, mở một báo cáo, duyệt/gỡ nhãn). Trong khung chat có ô gập "vì sao hỏi câu này" hiện phân phối kịch bản và trường được chọn, để giám khảo thấy phần tính toán.
- Một lệnh chạy: `./run_app.sh`, mở ở `localhost`.

## Phần 4 - Nối ảnh chat

- `POST /sessions/{id}/messages` nhận ảnh. Đọc ảnh bằng cách B của E1 (chỉ VLM) qua `core/llm.py`, mở rộng schema để lấy thêm các trường bảng câu chuyện đọc được từ ảnh (`kenh`, `tu_xung`, `ai_bat_dau`, `ap_luc`, `yeu_cau`, `ly_do_tien`).
- Chuỗi đọc được vào `chuoi_trich`. Link chỉ giữ tên miền. Số tài khoản trong ảnh lệch đúng một ký tự so với số đang nhập thì ghi `khong_chac`, không coi là mâu thuẫn (kết luận E1).
- Có dùng thêm OCR hay không sẽ chốt theo report E1b; viết sao cho thêm một nguồn đọc thứ hai không phải sửa chỗ khác.

## Phần 5 - Bộ thử có nạn nhân giả lập (E2, E3)

Theo mục 5.8.

- **Tình huống thử:** 5 tình huống cho mỗi kịch bản (75 tất cả), chỉ chữ. Mỗi tình huống: `id` kịch bản (đáp án), bảng câu chuyện thật (lấy mẫu như Phần 1, seed cố định), tính cách (vội / cả tin / nghi ngờ / kể lộn xộn; **không** dùng "bị dặn trước", để dành E4), tin nhắn mở đầu, nhãn tài khoản. Lưu thành file trong `sim/cases/` để chạy lại đúng y.
- **Nạn nhân giả lập:** một model nhận bảng câu chuyện thật + tính cách + mô tả kịch bản, trả lời từng câu hỏi như người thật. Không được nói ra tên kịch bản hay từ "lừa đảo" trừ khi tính cách là nghi ngờ.
- **Hai trợ lý cần so, cùng giới hạn 3 câu, cùng model:**
  - `tinh_toan`: lõi ở Phần 1-2.
  - `tu_do`: model tự hỏi tự do, cuối cùng chọn một `id` trong danh sách kịch bản (được đọc `ten` và `mo_ta` của mọi kịch bản) hoặc "chưa đủ căn cứ".
- **Số đo:** đúng kịch bản, đúng nhóm, "chưa đủ căn cứ" sau 0-3 câu (E2); kịch bản bình thường bị kết luận "giống chiêu lừa" (E3); giây và token mỗi phiên; số câu hỏi trung bình trước khi dừng. Kèm khoảng tin cậy 95% (bootstrap theo tình huống), vì 75 tình huống là ít.
- **Trần chi phí:** 5 USD cho cả Phần 5, tính từ token thật. Gần chạm thì dừng và báo.

## Thứ cần giao lại

- Code + test chạy được: `pytest` xanh; `./run_app.sh` mở được app; `python -m sim.run` chạy lại E2.
- `experiments/E2/report.md`: bảng Phần 1 (người trả lời hoàn hảo), bảng Phần 5, 5 phiên sai điển hình có nguyên hội thoại, lệnh chạy lại, giới hạn.
- Cập nhật `README.md` (mục Chạy, Thư mục, Khai báo thư viện) và `EXPERIMENTS.md` (mục E2, E3).
- Commit local theo từng phần. **Không push.**
- Tóm tắt ngắn ở terminal: số đo chính, lỗi tìm thấy trong file kịch bản, thứ cần Minh hoặc tab kế hoạch quyết.

## Quy tắc đề xuất (theo bản thiết kế mục 5.4)

- `tinh_toan` hơn `tu_do` từ 5 điểm phần trăm về đúng kịch bản sau 3 câu: đề xuất giữ.
- Không hơn: đề xuất bỏ phần chọn câu hỏi, giữ bảng câu chuyện. Ghi đúng số, không chạy lại nhiều lần để chọn số đẹp.

## Không làm

- Không push lên GitHub, không deploy, không đụng AWS.
- Không sửa bản thiết kế, `findings.md`, và các file trong `scenarios/` (thấy sai thì báo).
- Không dùng ảnh trong `data/E1b/real/` cho app hay cho ví dụ trong report.
- Không so sánh với sản phẩm nào của MoMo trong README hay report.
- Không thêm tính năng ngoài danh sách trên.
