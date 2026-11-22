"""E4 phase B: synthetic training/validation chat screenshots with exact answers (`data/E4/`).

Two stages, two Python environments (each stage imports only what it needs):

  .venv/bin/python -m e1.gen_train text --out data/E4 --seed 20261123 [--no-llm]
      dialogs + strings + the paraphrase pool (gemini-3.5-flash-lite, hard cap 1.5 USD, cost in gen_cost.json)
      -> data/E4/<split>/convs.jsonl, data/E4/splits.json, data/E4/para_pool.json
  /home/minhnv/anaconda3/bin/python -m e1.gen_train render --out data/E4 --split train|val|val_la [--limit N] [--workers K]
      Playwright + PIL: images, gt, LoRA targets, manifest, stats (resumable: finished images are skipped)
  ... -m e1.gen_train stats --out data/E4        recompute data/E4/stats.json
  ... -m e1.gen_train sheet --out data/E4 --split train --n 30 [--dest data/E4/contact_train.jpg]

Splits: train 4000 and val 300 (same distribution, separate seed streams) use 7 UI templates (zalo, messenger,
imessage, android, telegram, viber, web) and 13 scenarios (9 scams + the 4 normal `bt_*`). val_la (300) uses ONLY the
held-out template `whatsapp` and the two held-out scam scenarios `bao_nguoi_than_cap_cuu` and `dich_vu_lay_lai_tien`,
none of which appear in train/val (also written to data/E4/splits.json).

Per image: <split>/images/<id>.png|jpg, <split>/gt/<id>.json (scorer format: strings{type: [{raw, norm, boxes}]},
messages [{order, side, text, box}], ignore{strings, messages}, plus distractors/marks/condition metadata) and
<split>/target/<id>.json = the exact e1.vlm.SCHEMA JSON the LoRA model must output.

Labelling rules (applied identically to gt and target):
- Answer strings = account numbers, phone numbers (incl. 1900/1800 hotlines), links/domains and money amounts
  that are fully visible inside the chat area of the image. A string cut by the image/screen edge goes to
  gt.ignore.strings and is left out of the target; a string scrolled out of view is in neither.
- Receipt-card rule: a bank-transfer receipt card shown in the chat (a shared screenshot of a banking app) counts
  like a bubble for strings: its amount and its recipient account number (with that card's bank and holder) ARE
  answers. This matches the real `web` gt, which counts strings printed inside posted invoices/receipts. The card's
  transaction code and timestamp are distractors. The card itself is not a message.
- Messages = text bubbles only (order = 0-based among visible bubbles, side left = other person, right = phone
  owner, text without timestamp, explicit line breaks kept as "\n"). Receipt cards, image bubbles, link-preview
  cards, missed-call rows and date chips are not messages. Link-preview cards show title, description and a site
  name, never the URL, so they add no strings.
- accounts[].bank / .holder are the bank / holder text written in the same bubble or card as the number, else null.
- Distractors (never answers): order/transaction/case codes, OTP codes, tracking numbers, dates and times,
  12-digit CCCD numbers. They are rendered in the image and listed in gt.distractors.
- Red hand-drawn marks and publisher watermarks/stamps are drawn on top; strings under them keep their label (the
  marks are thin and semi-transparent; watermarks/stamps are placed so they do not cover any string).
- Every rendered image is self-checked against the DOM: each answer's raw text equals the DOM text of its span,
  occurs in the page text, sits fully inside its bubble/card and the visible area; message texts equal the
  bubble DOM text; no distractor equals an answer (raw or normalised). Failing images are not written
  (data/E4/<split>/failures.jsonl).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from e1.scenarios import MOBILE_PREFIX, NORMALIZERS
from e1.gen_train_templates import DESKTOP_SIZES, PHONE_SIZES, TEMPLATES

ROOT = Path(__file__).resolve().parent.parent
TYPES = ("account", "phone", "link", "amount")
TARGET_KEY = {"account": "accounts", "phone": "phones", "link": "links", "amount": "amounts"}
DTYPES = ("order", "otp", "tracking", "datetime", "cccd")
SPLITS = {"train": 4000, "val": 300, "val_la": 300}
HELD_OUT_TEMPLATE = "whatsapp"
HELD_OUT_SCENARIOS = ("bao_nguoi_than_cap_cuu", "dich_vu_lay_lai_tien")
TRAIN_TEMPLATES = {"zalo": .2, "messenger": .18, "imessage": .11, "android": .14, "telegram": .13, "viber": .1, "web": .14}
CONDITIONS = {"clean": .22, "crop": .12, "jpeg": .16, "small": .12, "photo": .12, "long": .1, "stitch": .1, "_": 0}
P_NORMAL, P_NO_STRINGS, P_DARK, P_MARKS = .4, .12, .35, .22
PARA_MODEL, PARA_CAP_USD = "gemini-3.5-flash-lite", 1.5

# ----------------------------------------------------------------------------------------------- dialogs
# Placeholders: answers {acc} {phone} {link} {amt} {amt2}; with the account {bank} {holder};
# distractors {otp} {order} {track} {date} {time} {cccd}; plain fills {name} {place}.
# Beats are kept in order; a conversation takes a subset plus filler lines.
L, R = "left", "right"
DIALOGS = {
    "gia_shipper": dict(
        contacts=["Shipper GHTK", "Giao hàng - Tuấn", "Bưu tá Hùng", "Số lạ", "Shipper Nam", "Giao Hàng Nhanh"],
        hosts=["ghtk-hotro.top/huy-dv", "giaohangtietkiem-vn.cc/hoantien", "ghn-express-vn.xyz/tracking",
               "vnpost-phigiao.cc/dh", "spx-hoantien.site/xacnhan", "giaohang-hoantien.online/huy"],
        amt=(15_000, 450_000), amt2=(500_000, 5_000_000), receipt=R, place=["cổng chung cư", "bảo vệ tòa nhà", "quán nước đầu ngõ"],
        beats=[
            (L, ["Chị ơi em shipper giao hàng đây ạ, chị có nhà không?", "Alo anh ơi, em bên giao hàng, đơn của anh tới rồi ạ"]),
            (R, ["Chị đang đi làm em ơi", "Anh không có nhà, em gửi giúp anh ở {place} nhé"]),
            (L, ["Đơn {order} của chị có thu hộ ạ", "Em đang giữ đơn mã {order} của anh"]),
            (L, ["Đơn của chị tiền hàng {amt}, chị chuyển khoản giúp em rồi em để hàng ở {place} nhé",
                 "Anh ck giúp em {amt} tiền hàng, em gửi ở {place} cho anh"]),
            (L, ["Chị chuyển vào STK {acc} {bank} {holder} giúp em", "STK em: {acc}\n{bank}\n{holder}"]),
            (R, ["Ok để chị chuyển", "Chuyển rồi nhé em", "Ừ đợi anh chút"]),
            (L, ["Chết chị ơi, chị chuyển nhầm vào tài khoản đăng ký hội viên giao hàng rồi",
                 "Anh ơi anh chuyển sai cú pháp rồi, tiền vào tài khoản đăng ký dịch vụ ạ"]),
            (L, ["Không hủy là mỗi tháng bị trừ {amt2} đó chị", "Nếu không hủy hệ thống sẽ trừ {amt2} mỗi tháng ạ"]),
            (L, ["Chị gọi tổng đài {phone} để hủy giúp em nhé", "Anh liên hệ CSKH {phone} hủy ngay ạ"]),
            (L, ["Hoặc chị vào {link} để hủy dịch vụ", "Anh bấm {link} rồi làm theo hướng dẫn để hủy"]),
            (L, ["Mã vận đơn của chị là {track}, chị đọc cho tổng đài nhé", "Anh báo mã vận đơn {track} khi gọi nhé"]),
            (R, ["Sao phiền vậy em", "Để chị gọi thử", "Sao lại trừ tiền hàng tháng?"]),
            (L, ["Chị làm nhanh giúp em kẻo quá giờ hệ thống tự trừ tiền", "Anh làm ngay trong hôm nay nhé"]),
        ]),
    "gia_cong_an": dict(
        contacts=["Cán bộ Trần Nam", "Đội điều tra PC02", "Số lạ", "Thượng úy Hoàng", "Công an phường", "Điều tra viên Lâm"],
        hosts=["dichvucong-bocongan.top/khaibao", "congan-xacminh.vip/hs", "vksnd-tracuu.xyz/lenh",
               "bocongan-gov.com/vu-an", "tracuu-vuan.online/hoso"],
        amt=(50_000_000, 900_000_000), amt2=(5_000_000, 80_000_000), receipt=None,
        place=["quận Cầu Giấy", "quận Đống Đa", "phường Bến Nghé", "quận Hải Châu", "quận Ninh Kiều", "huyện Gia Lâm"],
        beats=[
            (L, ["Tôi là cán bộ công an {place}, anh đang liên quan đến một đường dây rửa tiền",
                 "Đây là cơ quan cảnh sát điều tra công an {place}, chị có liên quan đến một vụ án"]),
            (L, ["Anh có phải chủ căn cước số {cccd} không?", "Chị xác nhận số CCCD {cccd} là của chị đúng không"]),
            (R, ["Đúng rồi, nhưng tôi có làm gì đâu", "Sao lại liên quan đến tôi?", "Tôi không biết gì cả"]),
            (L, ["Việc này anh tuyệt đối giữ bí mật, không được nói với ai kể cả người nhà",
                 "Chị không được kể với ai, kể cả nhân viên ngân hàng"]),
            (L, ["Anh phải chuyển {amt} vào tài khoản tạm giữ để xác minh nguồn tiền",
                 "Yêu cầu chị chuyển toàn bộ {amt} vào tài khoản của cơ quan điều tra"]),
            (L, ["Tài khoản tạm giữ: {acc}\n{bank} - {holder}", "TK an toàn: {acc} ({bank}) chủ TK {holder}"]),
            (L, ["Anh khai báo tại cổng {link} trước cuối giờ hôm nay", "Chị truy cập {link} để khai báo thông tin"]),
            (L, ["Liên hệ điều tra viên phụ trách: {phone}", "Gọi ngay cho đồng chí Hùng số {phone}"]),
            (L, ["Lệnh tạm giữ số {order} ban hành ngày {date}", "Hồ sơ vụ án số {order}, chị lên làm việc ngày {date}"]),
            (L, ["Trước mắt anh nộp {amt2} phí bảo lãnh", "Chị đóng trước {amt2} để không bị tạm giam"]),
            (R, ["Tôi cần hỏi lại công an phường đã", "Để tôi hỏi người nhà đã"]),
            (L, ["Nếu anh không hợp tác sẽ bị khởi tố vì cản trở điều tra", "Chị chậm trễ là bị phong tỏa toàn bộ tài khoản"]),
        ]),
    "ctv_online": dict(
        contacts=["CSKH Tuyển CTV", "Mai Anh - Tuyển dụng", "Nhiệm vụ Online", "HR Lazada CTV", "Trợ lý Linh", "Tuyển dụng Shopee"],
        hosts=["nhiemvu-shopee-ctv.xyz/reg", "tiktok-hoahong.top/ctv", "lazada-nhiemvu.online/task",
               "ctv-shopee.vip/dk", "hoahong-online.site/join"],
        amt=(200_000, 6_000_000), amt2=(1_000_000, 30_000_000), receipt=R, place=["nhóm Telegram", "nhóm Zalo"],
        beats=[
            (L, ["Chào bạn, bên mình đang tuyển cộng tác viên làm tại nhà, mỗi ngày chỉ cần vài phút",
                 "Bạn ơi bên mình tuyển CTV online, việc nhẹ thu nhập tốt"]),
            (R, ["Làm như thế nào vậy ạ?", "Việc gì thế bạn?", "Có mất phí gì không ạ?"]),
            (L, ["Bạn đăng ký tài khoản tại {link} nhé", "Bạn vào {link} tạo tài khoản rồi báo mình"]),
            (L, ["Nhiệm vụ đầu tiên bạn chỉ cần thả tim video là nhận thưởng", "Bạn vào {place} để nhận nhiệm vụ nhé"]),
            (L, ["Nhiệm vụ tiếp theo bạn nạp {amt} để đặt đơn, hệ thống hoàn gốc kèm hoa hồng",
                 "Đơn này bạn ứng trước {amt}, xong hoàn lại kèm hoa hồng"]),
            (L, ["Nạp vào STK {acc} {bank}\nChủ TK: {holder}", "{bank}\n{acc}\n{holder}"]),
            (L, ["Nội dung chuyển khoản ghi mã đơn {order} giúp mình", "Bạn ghi mã nhiệm vụ {order} khi chuyển nhé"]),
            (R, ["Nạp xong bao lâu thì rút được?", "Mình chuyển rồi nhé"]),
            (L, ["Hoàn thành chuỗi nhiệm vụ bạn rút được {amt2}", "Xong chuỗi này tài khoản bạn có {amt2}"]),
            (L, ["Cần hỗ trợ bạn nhắn Zalo {phone} nhé", "Có gì gọi mình {phone}"]),
            (L, ["Lệnh rút của bạn bị treo do sai cú pháp, cần nạp thêm để mở khóa",
                 "Bạn nhập sai nội dung nên lệnh rút bị khóa rồi"]),
            (R, ["Sao lại phải nạp thêm nữa?", "Mình không có tiền nạp nữa đâu"]),
        ]),
    "chuyen_nham_tien": dict(
        contacts=["Ngọc Ánh", "Số lạ", "Em Hoa", "Linh Nguyễn", "Tuấn Anh", "Thu Trang"],
        hosts=["saoke-vietcombank.top/gd", "mbbank-hoantien.xyz/gd", "hoantien-nganhang.cc/sk",
               "qr-hoantien.site/nhan", "hoantien-nhanh.online/qr"],
        amt=(1_000_000, 20_000_000), amt2=(300_000, 3_000_000), receipt=L, place=["bệnh viện", "công an"],
        beats=[
            (L, ["Chị ơi em chuyển nhầm {amt} vào tài khoản của chị, chị kiểm tra giúp em",
                 "Anh ơi em lỡ chuyển nhầm {amt} cho anh ạ"]),
            (R, ["Để chị xem lại", "Ừ để anh kiểm tra", "Em là ai vậy?"]),
            (L, ["Giao dịch lúc {time} ngày {date} chị nhé", "Em chuyển lúc {time} hôm {date} ạ"]),
            (L, ["Chị chuyển lại giúp em vào tài khoản mẹ em: {acc} {bank} {holder}",
                 "Hoàn giúp em vào STK {acc}\n{bank} - {holder} nhé"]),
            (R, ["Sao không chuyển về tài khoản gốc?", "Sao lại chuyển vào tài khoản khác?"]),
            (L, ["Tài khoản em bị khóa rồi, sao kê em để ở {link}", "Chị quét mã hoặc bấm {link} để hoàn tiền cho nhanh"]),
            (L, ["Gấp lắm, chị gọi em số {phone} nhé", "Số em đây {phone}, có gì gọi em"]),
            (L, ["Em đang cần gấp tiền đóng viện phí", "Chị chuyển giúp em sớm nhé, em cảm ơn nhiều"]),
            (L, ["Không trả thì mỗi ngày tính lãi {amt2} đấy", "Chị giữ tiền của em lâu thì phải trả thêm {amt2} tiền lãi"]),
            (L, ["Chị không trả em sẽ báo {place} đấy", "Em sẽ trình báo {place} nếu chị không hoàn"]),
            (R, ["Để mai chị ra ngân hàng hỏi", "Anh sẽ liên hệ ngân hàng trước"]),
        ]),
    "mao_danh_nguoi_quen": dict(
        contacts=["Anh Hùng", "Chị Lan", "Dì Út", "Sếp Quang", "Minh Tuấn", "Thảo Nguyễn", "Bác Tư"],
        hosts=["binhchon-anhdep.xyz/b", "zalo-xacminh.top/vote", "cuocthi-bequangngoan.online/bc", "fb-binhchon.site/v"],
        amt=(3_000_000, 50_000_000), amt2=(1_000_000, 10_000_000), receipt=L, place=["cuộc họp", "sân bay"],
        beats=[
            (L, ["Em ơi đang bận không?", "Ê có đó không", "Cháu ơi rảnh không"]),
            (R, ["Có anh ạ", "Dạ em đây", "Sao thế chị?"]),
            (L, ["Anh đang trong {place} không nghe máy được, nhờ em chút việc", "Chị đang ở {place}, máy hỏng loa"]),
            (L, ["Em chuyển giúp anh {amt} vào tài khoản bạn anh nhé, chiều anh gửi lại",
                 "Cho chị mượn tạm {amt}, tối chị trả"]),
            (L, ["STK: {acc} {holder}\n{bank}", "Chuyển vào {bank} {acc} tên {holder} nhé"]),
            (L, ["Gấp lắm em, chuyển xong chụp màn hình cho anh", "Nhanh giúp chị nhé"]),
            (R, ["Sao anh không gọi điện?", "Chị gọi video em xem nào"]),
            (L, ["Máy anh hỏng loa, em gọi số này {phone} nhé", "Em gọi số mới của chị {phone}"]),
            (L, ["Em bình chọn giúp cháu anh ở {link} với", "Vào {link} bình chọn cho bé nhà chị nhé"]),
            (L, ["Thêm {amt2} nữa là đủ, em chuyển nốt giúp anh", "Còn thiếu {amt2}, em ứng thêm giúp chị"]),
            (L, ["Anh hứa tối nay trả em luôn", "Tối chị chuyển lại liền"]),
        ]),
    "bao_nguoi_than_cap_cuu": dict(
        contacts=["Cô giáo Hương", "Bác sĩ Thành", "Số lạ", "Phòng cấp cứu", "Thầy Phong chủ nhiệm"],
        hosts=["benhvien-tamung.top/vp", "thanhtoan-vienphi.xyz/bn", "vienphi-online.site/tt", "bv-capcuu.online/hs"],
        amt=(10_000_000, 90_000_000), amt2=(2_000_000, 15_000_000), receipt=None,
        place=["bệnh viện Việt Đức", "bệnh viện Nhi Trung ương", "bệnh viện Chợ Rẫy", "bệnh viện Bạch Mai"],
        names=["Minh", "Bảo An", "Gia Huy", "Ngọc Hân", "Khôi", "Tuệ Lâm"],
        beats=[
            (L, ["Anh là phụ huynh cháu {name} phải không ạ?", "Chị có phải mẹ bé {name} không ạ?"]),
            (R, ["Đúng rồi, có chuyện gì vậy?", "Vâng tôi đây, sao thế ạ?"]),
            (L, ["Cháu {name} ngã cầu thang ở trường, đang cấp cứu ở {place}",
                 "Bé {name} bị tai nạn, đang được đưa vào {place}"]),
            (L, ["Bác sĩ cần anh tạm ứng {amt} để mổ gấp", "Chị đóng ngay {amt} viện phí để bác sĩ phẫu thuật"]),
            (L, ["Anh chuyển vào STK bác sĩ trực: {acc} {bank} {holder}", "STK khoa cấp cứu: {acc}\n{bank}\n{holder}"]),
            (L, ["Anh gọi cho bác sĩ {phone} để nghe tình hình", "Số bác sĩ trực {phone}, chị gọi ngay"]),
            (L, ["Mã bệnh nhân của cháu là {order}", "Chị ghi mã hồ sơ {order} khi chuyển tiền"]),
            (L, ["Thanh toán viện phí online tại {link}", "Chị đóng tiền qua {link} cho nhanh"]),
            (L, ["Thêm {amt2} tiền thuốc nữa anh nhé", "Phát sinh {amt2} tiền máu, chị chuyển thêm"]),
            (R, ["Để tôi gọi cho vợ tôi đã", "Cho tôi số của cô chủ nhiệm"]),
            (L, ["Không kịp đâu anh, chậm vài phút là nguy hiểm", "Chị nhanh lên, cháu mất máu nhiều lắm"]),
        ]),
    "dat_coc_gia_re": dict(
        contacts=["Booking Du Lịch Việt", "Vé Máy Bay Giá Rẻ", "Homestay Đà Lạt Mây", "Combo Du Lịch Sale", "Điện Thoại Giá Kho"],
        hosts=["vietravel-combo.top/booking", "vemaybay-giare.vip/dat", "homestay-dalat.site/phong",
               "didong-sale.xyz/sp", "combo-phuquoc.online/giucho"],
        amt=(1_500_000, 9_000_000), amt2=(500_000, 5_000_000), receipt=R, place=["Phú Quốc", "Đà Lạt", "Nha Trang", "Sa Pa"],
        beats=[
            (R, ["Shop ơi combo {place} còn suất không ạ?", "Ad ơi phòng cuối tuần còn không?"]),
            (L, ["Dạ còn 2 suất cuối thôi ạ, chị đặt luôn em giữ chỗ", "Dạ còn ạ nhưng sắp hết rồi anh"]),
            (L, ["Combo giá {amt}/khách, chị cọc trước {amt2} là được ạ", "Giá {amt} ạ, anh cọc {amt2} em giữ phòng"]),
            (L, ["Chị chuyển cọc vào STK {acc} {bank}, chủ TK {holder}", "STK kế toán: {acc}\n{bank}\n{holder}"]),
            (L, ["Mã giữ chỗ của chị là {order}, chị ghi vào nội dung giúp em", "Nội dung ck ghi mã booking {order} ạ"]),
            (L, ["Chị xem hợp đồng tại {link}", "Anh tham khảo thêm ảnh phòng ở {link}"]),
            (L, ["Ngày nhận phòng {date}, chị kiểm tra lại giúp em", "Lịch khởi hành {date} lúc {time} ạ"]),
            (R, ["Sao chưa nhận được xác nhận vậy?", "Mình chuyển rồi nhé"]),
            (L, ["Chị chuyển sai cú pháp nên hệ thống chưa nhận, chị chuyển lại giúp em",
                 "Giao dịch bị treo, anh chuyển lại giúp em nhé"]),
            (L, ["Hotline đặt phòng {phone}", "Cần gấp chị gọi {phone}"]),
        ]),
    "dau_tu_san_gia": dict(
        contacts=["Chuyên gia Minh Đức", "Nhóm Khuyến Nghị VIP", "Trợ lý Thu Hà", "CSKH Sàn", "Thầy Quân chứng khoán"],
        hosts=["vn-invest-pro.top/app", "san-giaodich-vip.xyz/login", "coinvn-exchange.cc/dk",
               "fxvietnam.online/nap", "dautu-thongminh.site/reg"],
        amt=(5_000_000, 200_000_000), amt2=(20_000_000, 500_000_000), receipt=R, place=["nhóm khuyến nghị", "phòng VIP"],
        beats=[
            (L, ["Mã này thầy báo chốt lãi trong tuần, chị vào kịp không?", "Hôm nay {place} có kèo đẹp, anh tham gia không"]),
            (R, ["Vào như thế nào em?", "Lãi nhiều không em?"]),
            (L, ["Chị tải app và đăng ký tại {link}", "Anh mở tài khoản trên sàn {link} nhé"]),
            (L, ["Nạp tối thiểu {amt} để kích hoạt tài khoản", "Anh nạp {amt} vào để vào lệnh đầu tiên"]),
            (L, ["Nạp qua STK {acc} {bank} {holder}", "Tài khoản nạp tiền: {acc}\n{bank} - {holder}"]),
            (R, ["Sao chị không rút được tiền?", "Tôi muốn rút hết về"]),
            (L, ["Tài khoản chị đang lãi {amt2}, cần nộp thuế thu nhập trước khi rút",
                 "Lợi nhuận anh {amt2}, đóng phí xác minh là rút được"]),
            (L, ["Lệnh rút {order} đang chờ duyệt", "Mã lệnh của anh {order}, hệ thống đang khóa"]),
            (L, ["Cần hỗ trợ gọi CSKH {phone}", "Liên hệ trợ lý {phone} để được hướng dẫn"]),
            (L, ["Nạp trước cuối giờ chiều nay để kịp sóng", "Chậm là lỡ sóng đấy anh"]),
        ]),
    "dich_vu_lay_lai_tien": dict(
        contacts=["Luật sư Hoàng Long", "Hỗ trợ thu hồi tiền", "Chuyên gia an ninh mạng", "Văn phòng Luật Tâm An"],
        hosts=["thuhoi-tienlua.top/hoso", "luatsu-hotro24h.xyz/dk", "anninhmang-hotro.cc/tt", "lay-lai-tien.online/form"],
        amt=(1_000_000, 15_000_000), amt2=(3_000_000, 30_000_000), receipt=R, place=["sàn ảo", "nhóm nhiệm vụ"],
        beats=[
            (R, ["Em bị lừa mất tiền, bên mình lấy lại được không ạ?", "Tôi bị lừa trên {place}, có lấy lại được không"]),
            (L, ["Bên em cam kết thu hồi đủ trong ngày ạ", "Dạ trường hợp của chị bên em xử lý được"]),
            (L, ["Chị đóng trước phí hồ sơ {amt}", "Anh nộp {amt} phí mở hồ sơ để luật sư làm việc"]),
            (L, ["STK văn phòng: {acc} {bank} {holder}", "Chuyển vào {acc}\n{bank}\nCTK {holder}"]),
            (L, ["Mã hồ sơ của chị là {order}", "Hồ sơ số {order} đã được tiếp nhận"]),
            (L, ["Chị điền thông tin vụ việc tại {link}", "Anh khai báo chi tiết ở {link}"]),
            (L, ["Tiền của chị đang bị treo, cần {amt2} phí phá băng để giải ngân", "Cần thêm {amt2} phí giải ngân ạ"]),
            (L, ["Liên hệ luật sư phụ trách {phone}", "Gọi chuyên viên {phone} để được tư vấn"]),
            (R, ["Sao lại phát sinh thêm phí?", "Tôi không còn tiền nữa"]),
        ]),
    "gia_co_quan_nha_nuoc": dict(
        contacts=["Chi cục Thuế", "Điện lực CSKH", "Cán bộ phường", "Hỗ trợ VNeID", "Cán bộ địa chính"],
        hosts=["vneid-capnhat.top/app", "dichvucong-thue.xyz/tai", "evn-hotro.cc/thanhtoan", "thue-dientu.online/apk",
               "dinhdanh-muc2.site/cai"],
        amt=(10_000, 300_000), amt2=(500_000, 5_000_000), receipt=None, place=["phường", "chi cục thuế"],
        beats=[
            (L, ["Anh chưa đồng bộ mã số thuế với căn cước, hôm nay không làm sẽ bị phạt",
                 "Nhà mình sắp bị cắt điện do chưa cập nhật thông tin khách hàng"]),
            (L, ["Số CCCD của anh {cccd} đúng không ạ?", "Chị xác nhận giúp em số căn cước {cccd}"]),
            (R, ["Đúng rồi, sao vậy?", "Sao tôi không nhận được thông báo nào?"]),
            (L, ["Anh tải ứng dụng tại {link} để cập nhật", "Chị cài app qua {link} rồi làm theo hướng dẫn"]),
            (L, ["Anh nộp {amt} lệ phí kích hoạt hồ sơ", "Chị chuyển {amt} lệ phí qua app để hồ sơ được duyệt"]),
            (L, ["Chuyển vào tài khoản thu hộ {acc} {bank} {holder}", "TK thu hộ: {acc}\n{bank}\n{holder}"]),
            (L, ["Mã xác nhận {otp}, anh nhập vào ứng dụng giúp em", "Chị đọc giúp em mã {otp} vừa gửi về máy"]),
            (L, ["Không cập nhật sẽ bị phạt {amt2}", "Chậm trễ sẽ bị xử phạt {amt2}"]),
            (L, ["Có gì anh gọi tổng đài {phone}", "Cần hỗ trợ chị liên hệ {phone}"]),
            (L, ["Lịch làm việc tại {place} ngày {date}", "Hạn cuối là {date} chị nhé"]),
        ]),
    "gia_ngan_hang": dict(
        contacts=["CSKH Ngân Hàng", "Trung tâm thẻ", "Hỗ trợ khách hàng", "Số lạ", "Ví điện tử CSKH", "Phòng tín dụng"],
        hosts=["vietcombank-hotro.top/xacthuc", "mbbank-nanghanmuc.xyz/dk", "techcombank-khoa.cc/l",
               "vcb-digibank.site/login", "bidv-hoanphi.online/tk", "vietinbank-ipay.top/xm"],
        amt=(5_000_000, 50_000_000), amt2=(500_000, 5_000_000), receipt=None, place=["chi nhánh"],
        beats=[
            (L, ["Thẻ của chị được nâng hạn mức, chị xác nhận giúp em", "Tài khoản của anh đang bị tạm khóa do chưa xác thực"]),
            (L, ["Mã OTP của quý khách là {otp}. Không chia sẻ mã cho bất kỳ ai", "Mã xác thực {otp}, hiệu lực trong ít phút"]),
            (L, ["Tài khoản phát sinh giao dịch {amt} ở nước ngoài", "Hạn mức thẻ của chị được nâng lên {amt}"]),
            (L, ["Anh vào {link} để hủy giao dịch ngay", "Quý khách truy cập {link} để xác thực"]),
            (L, ["Chuyển số dư sang tài khoản bảo vệ: {acc} {bank} {holder}", "TK xác minh: {acc}\n{bank}\n{holder}"]),
            (L, ["Phí xác minh {amt2}, hoàn lại sau khi mở khóa", "Anh nộp {amt2} phí thường niên để kích hoạt"]),
            (L, ["Hotline ngân hàng {phone}", "Liên hệ tổng đài {phone} để được hỗ trợ"]),
            (L, ["Giao dịch lúc {time} {date} chưa được xác nhận", "Yêu cầu hết hạn lúc {time} hôm nay"]),
            (R, ["Tôi không thực hiện giao dịch nào", "Em đọc mã cho chị rồi đấy"]),
        ]),
    "bt_chuyen_cho_nguoi_than": dict(
        contacts=["Mẹ", "Bố", "Chị Hai", "Thằng Bin", "Hà Béo", "Anh Tú", "Út Nhỏ"],
        hosts=["drive.google.com/drive/folders", "photos.app.goo.gl", "maps.app.goo.gl", "facebook.com/photo"],
        legit=True, amt=(200_000, 10_000_000), amt2=(50_000, 800_000), receipt=R, place=["nhà bà", "quán quen"],
        beats=[
            (R, ["Mẹ ơi tháng này con gửi tiền nhà nhé", "Chị ơi em gửi lại tiền tháng trước nhé"]),
            (L, ["Mẹ gửi con số tài khoản mẹ: {acc} {bank} {holder}", "STK chị đây {acc}\n{bank}\n{holder}"]),
            (R, ["Con chuyển mẹ {amt} rồi nhé", "Em ck chị {amt} rồi đó"]),
            (L, ["Mẹ nhận được rồi, con ăn uống đầy đủ nhé", "Ok chị nhận rồi"]),
            (R, ["Tiền ăn hôm trước mỗi đứa {amt2} nha", "Góp tiền quà sinh nhật mỗi người {amt2} nhé"]),
            (L, ["Ảnh hôm đi chơi ở {link} nhé", "Vị trí {place} đây {link}"]),
            (L, ["Có gì gọi mẹ số mới {phone}", "Số mới của anh {phone} nhé"]),
            (L, ["Tối {date} về ăn cơm nhé", "Hẹn {date} gặp nhé"]),
            (R, ["Dạ con biết rồi", "Ok anh"]),
        ]),
    "bt_dat_coc_da_xem": dict(
        contacts=["Chị Hằng chủ trọ", "Anh Dũng thợ điện", "Cô Lan nhà trọ", "Anh Phong bán xe", "Chú Tâm sửa nhà"],
        hosts=["maps.app.goo.gl", "goo.gl/maps", "drive.google.com/file/d"], legit=True,
        amt=(1_000_000, 8_000_000), amt2=(100_000, 1_500_000), receipt=R, place=["phòng tầng hai", "chiếc xe"],
        beats=[
            (R, ["Chị ơi em vừa xem phòng xong, em lấy phòng nhé", "Anh ơi em xem {place} rồi, em lấy nhé"]),
            (L, ["Ok em, cọc trước 1 tháng {amt} nhé", "Em cọc {amt} anh giữ cho"]),
            (L, ["STK chị: {acc} {bank} {holder}", "Tài khoản anh {acc}\n{bank}\n{holder}"]),
            (R, ["Em chuyển rồi chị kiểm tra giúp em", "Em ck rồi nha anh"]),
            (L, ["Chị gửi vị trí nhà {link}", "Hợp đồng anh để ở {link} em xem"]),
            (L, ["Tiền điện nước tính riêng khoảng {amt2} một tháng", "Phí công thợ thêm {amt2} nhé"]),
            (L, ["Có gì em gọi chị {phone}", "Số anh {phone}"]),
            (L, ["Ngày {date} em dọn vào nhé", "Hẹn em {time} ngày {date}"]),
            (R, ["Dạ em cảm ơn chị", "Ok anh"]),
        ]),
    "bt_mua_online_nguoi_ban_moi": dict(
        contacts=["Shop Quần Áo Mây", "Tiệm Giày Bảo", "Hana Cosmetics", "Shop Đồ Gia Dụng Xinh", "Tiệm Bánh Nhà Mây"],
        hosts=["shopee.vn/product", "quanaomay.vn/sp", "facebook.com/hanacosmetics", "tiembanhnhamay.vn/menu"], legit=True,
        amt=(80_000, 2_000_000), amt2=(15_000, 50_000), receipt=R, place=["size M", "màu be"],
        beats=[
            (R, ["Shop ơi mẫu này còn {place} không?", "Shop ơi bánh này còn không ạ?"]),
            (L, ["Dạ còn ạ, giá {amt} chị nhé, phí ship {amt2}", "Dạ còn ạ, mẫu này {amt}, ship {amt2} ạ"]),
            (L, ["Bên em nhận chuyển khoản trước rồi gửi hàng ạ", "Chị chuyển khoản trước giúp em nhé"]),
            (L, ["STK: {acc}\n{bank}\nCTK: {holder}", "Chị chuyển khoản giúp em: {acc} {bank} {holder}"]),
            (L, ["Chị xem thêm mẫu ở {link} ạ", "Ảnh thật sản phẩm em để ở {link}"]),
            (L, ["Mã đơn của chị {order}, mã vận đơn {track}", "Đơn đã gửi, mã vận đơn {track} ạ"]),
            (L, ["Shipper sẽ gọi chị qua số {phone}", "Có gì chị gọi shop {phone}"]),
            (R, ["Ok shop, chị chuyển rồi nhé", "Cảm ơn shop"]),
        ]),
    "bt_tra_tien_nguoi_ban_quen": dict(
        contacts=["Cô Ba bán rau", "Quán Cơm Bà Tư", "Tiệm Tạp Hóa Minh", "Anh Sơn sửa xe", "Chị Mai bán trái cây"],
        hosts=["maps.app.goo.gl", "facebook.com/quancombatu"], legit=True,
        amt=(20_000, 600_000), amt2=(10_000, 200_000), receipt=R, place=["quầy"],
        beats=[
            (R, ["Cô ơi hôm nay của con hết bao nhiêu ạ?", "Anh ơi sửa xe hết bao nhiêu ạ?"]),
            (L, ["Của con hết {amt} nhé", "Hết {amt} em nhé"]),
            (L, ["Con chuyển vào {acc} {bank} {holder} cho cô", "STK anh dán ở {place}: {acc} {bank}"]),
            (R, ["Con chuyển rồi ạ", "Em ck rồi anh nhé"]),
            (L, ["Cô nhận rồi, cảm ơn con", "Ok em"]),
            (L, ["Hôm trước còn nợ {amt2} nữa nhé", "Thêm {amt2} tiền nhớt nhé"]),
            (L, ["Mai cần gì nhắn cô hoặc gọi {phone}", "Lần sau gọi anh {phone}"]),
        ]),
}
NORMAL = {s for s in DIALOGS if s.startswith("bt_")}
TRAIN_SCENARIOS = [s for s in DIALOGS if s not in HELD_OUT_SCENARIOS]
SCAM_TRAIN = [s for s in TRAIN_SCENARIOS if s not in NORMAL]
FILLERS = {
    L: ["Dạ vâng ạ", "Mình đang kiểm tra lại nhé", "Bạn đợi mình chút xíu", "Ok bạn", "Bạn còn ở đó không ạ?",
        "Dạ đúng rồi ạ", "Bạn yên tâm nhé", "Không sao đâu ạ", "Mình hiểu rồi", "Để mình hỏi lại quản lý",
        "Vâng, mình xin lỗi vì sự bất tiện", "Bạn làm theo hướng dẫn là được", "Cảm ơn bạn đã phản hồi", "Nhanh nhé"],
    R: ["Ừ", "Ok", "Thật không vậy?", "Để mình xem", "Sao lâu thế", "Mình đang bận chút", "Gửi lại giúp mình với",
        "Mình chưa hiểu lắm", "Có chắc không bạn?", "Ừ được", "Đợi mình xíu nhé", "Vậy à", "Rồi sao nữa?", "Hmm"],
}

ANSWER_PH = {"acc": "account", "phone": "phone", "link": "link", "amt": "amount", "amt2": "amount"}
DIST_PH = {"otp": "otp", "order": "order", "track": "tracking", "date": "datetime", "time": "datetime", "cccd": "cccd"}
FILL_PH = {"bank", "holder", "name", "place"}
PH_RE = re.compile(r"\{(\w+)\}")

# ----------------------------------------------------------------------------------------------- strings
BANKS = [["Vietcombank", "VCB"], ["Techcombank", "TCB"], ["MB Bank", "MB", "MBBank"], ["VPBank"], ["ACB"], ["BIDV"],
         ["VietinBank", "Vietin"], ["Sacombank"], ["TPBank"], ["Agribank"], ["VIB"], ["SHB"], ["OCB"], ["HDBank"],
         ["MSB"], ["SeABank"], ["NCB"], ["Eximbank"], ["LPBank"], ["Nam A Bank"]]
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Võ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý", "Phan", "Vũ"]
DEM = ["Văn", "Thị", "Đức", "Minh", "Thanh", "Ngọc", "Quốc", "Hoài", "Xuân", "Kim", "Thu", "Hữu", "Bảo", "Gia"]
TEN = ["Hùng", "Lan", "Tuấn", "Hoa", "Long", "Trang", "Dũng", "Phương", "Khánh", "Nam", "Linh", "Quang", "Thảo",
       "Hiếu", "Vy", "An", "Bình", "Hà", "Sơn", "Yến", "Phúc", "Mai"]
SHORTENERS = ["bit.ly", "tinyurl.com", "s.id", "shorturl.at", "cutt.ly", "rb.gy", "is.gd"]
ALNUM = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def strip_marks(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def digits(rng, n, first="0123456789"):
    return rng.choice(first) + "".join(rng.choice("0123456789") for _ in range(n - 1))


def gen_holder(rng):
    parts = [rng.choice(HO), rng.choice(DEM), rng.choice(TEN)]
    if rng.random() < .3:
        parts.insert(2, rng.choice(DEM))
    name = " ".join(parts)
    r = rng.random()
    return strip_marks(name).upper() if r < .65 else name.upper() if r < .75 else name


def gen_account(rng):
    n = rng.choices([6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19], [1, 1, 2, 4, 6, 3, 4, 5, 4, 1, 2, 1])[0]
    d = digits(rng, n, "0123456789" if rng.random() < .25 else "123456789")
    r = rng.random()
    if r < .55 or n < 8:
        return d
    if r < .75:
        g = rng.choice([3, 4])
        return " ".join(d[i:i + g] for i in range(0, n, g))
    if r < .88:
        g = rng.choice([3, 4])
        return ".".join(d[i:i + g] for i in range(0, n, g))
    k = rng.randint(3, n - 3)
    return d[:k] + " " + d[k:]


def gen_phone(rng):
    r = rng.random()
    if r < .12:  # hotline
        p = rng.choice(["1900", "1800"])
        return rng.choice([f"{p} {digits(rng, 4)}", f"{p}{digits(rng, 4)}", f"{p}.{digits(rng, 4)}",
                           f"{p} {digits(rng, 3)} {digits(rng, 3)}", f"{p}{digits(rng, 6)}"])
    d = rng.choice(MOBILE_PREFIX) + digits(rng, 7)
    a, b, c = d[:4], d[4:7], d[7:]
    st = rng.choices(["space", "dot", "plain", "intl", "intl2", "intl3", "84", "paren", "dash", "3-3-4"],
                     [3, 2, 3, 1.5, 1, 1, 1, .7, .7, 1])[0]
    return {"space": f"{a} {b} {c}", "dot": f"{a}.{b}.{c}", "plain": d, "intl": f"+84 {d[1:4]} {b} {c}",
            "intl2": f"+84 {d[1:3]} {d[3:]}", "intl3": f"+84{d[1:]}", "84": f"84{d[1:]}",
            "paren": f"(+84) {d[1:]}", "dash": f"{a}-{b}-{c}", "3-3-4": f"{d[:3]} {d[3:6]} {d[6:]}"}[st]


def lookalike(rng, host):
    name, _, tld = host.rpartition(".")
    swaps = [(i, ch) for i, ch in enumerate(name) if ch in "oil"]
    if swaps and rng.random() < .5:
        i, ch = rng.choice(swaps)
        name = name[:i] + {"o": "0", "i": "1", "l": "1"}[ch] + name[i + 1:]
    elif "m" in name and rng.random() < .3:
        name = name.replace("m", "rn", 1)
    return f"{name}.{tld}"


def code(rng, a, b, conf=.3):
    return "".join(rng.choice("0O1lI") if rng.random() < conf * .5 else rng.choice(ALNUM) for _ in range(rng.randint(a, b)))


def gen_link(rng, scenario):
    d = DIALOGS[scenario]
    legit = d.get("legit", False)
    r = rng.random()
    if not legit and r < .2:
        return rng.choice(["", "", "https://"]) + f"{rng.choice(SHORTENERS)}/{code(rng, 5, 8)}"
    if not legit and r < .27:
        return rng.choice([f"t.me/{rng.choice(['cskh', 'hotro', 'admin', 'nhiemvu'])}_{code(rng, 3, 6, 0).lower()}",
                           f"zalo.me/g/{code(rng, 6, 8, 0).lower()}"])
    hp = rng.choice(d["hosts"])
    host, _, path = hp.partition("/")
    if not legit:
        host = lookalike(rng, host)
        if rng.random() < .15:
            host = rng.choice(["www.", "m.", "id-"]) + host
    form = rng.random()
    tail = code(rng, 4, 7) if not legit or rng.random() < .7 else ""
    full = host + ("/" + path if path else "") + ("/" + tail if tail else "")
    if form < .2 and not legit:
        out = host  # bare domain
    elif form < .3 and not legit:
        out = f"{host}/{tail or code(rng, 4, 6)}"
    else:
        out = full
    if not legit and rng.random() < .12:
        out += rng.choice(["?id=", "?ref=", "?u="]) + code(rng, 4, 8, 0)
    pre = rng.choices(["", "https://", "http://", "www."], [4, 3.5, .8, .7] if not legit else [3, 5, 0, 0])[0]
    if pre == "www." and out.startswith(("www.", "m.")):
        pre = ""
    return pre + out


def fmt_vnd(v):
    return f"{v:,}".replace(",", ".")


def gen_amount(rng, lo, hi):
    """(raw) in one of the real-world formats, value roughly log-uniform in [lo, hi]."""
    v = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    st = rng.choices(["dot_d", "dot_sd", "vnd", "vnđ", "dong", "k", "tr_dec", "trieu", "trk", "tr_short", "nghin",
                      "plain_d", "comma_d", "tr"], [4, 1.5, 2, 1.2, .8, 2.5, 1.5, 1.5, .8, 1, .5, .6, .6, 1.2])[0]
    if st in ("k", "nghin") and v >= 10_000_000:
        st = "dot_d"
    if st in ("tr_dec", "trieu", "trk", "tr_short", "tr") and v < 1_000_000:
        st = "k"
    if st == "k":
        v = max(1, round(v / 1000)) if v < 1_000_000 else round(v / 100_000) * 100
        return f"{v}k"
    if st == "nghin":
        return f"{max(1, round(v / 1000))} {rng.choice(['nghìn', 'ngàn'])}"
    if st in ("tr_dec", "trieu"):
        t = round(v / 100_000) / 10
        s = (f"{t:.1f}".replace(".", ",")).replace(",0", "")
        return f"{s}tr" if st == "tr_dec" else f"{s} triệu"
    if st == "tr":
        return f"{round(v / 1_000_000)}tr" if v < 1e9 else f"{round(v / 1e6)} triệu"
    if st == "trk":
        m, k = int(v // 1_000_000), rng.randint(1, 999)
        return f"{m}tr{k:03d}k" if k >= 100 else f"{m}tr{k}k"
    if st == "tr_short":
        m, d = int(v // 1_000_000), rng.randint(1, 9)
        return f"{m}tr{d}"
    q = 1000 if v < 1_000_000 else 10_000 if v < 20_000_000 else 1_000_000
    n = max(q, round(v / q) * q)
    if st == "dot_d":
        return fmt_vnd(n) + "đ"
    if st == "dot_sd":
        return fmt_vnd(n) + " đ"
    if st == "vnd":
        return fmt_vnd(n) + rng.choice([" VND", " VND", "VND"])
    if st == "vnđ":
        return fmt_vnd(n) + rng.choice([" VNĐ", " vnđ"])
    if st == "dong":
        return fmt_vnd(n) + " đồng"
    if st == "comma_d":
        return f"{n:,}đ"
    return f"{n}đ"


ORDER_FMT = {"gia_cong_an": "case", "gia_co_quan_nha_nuoc": "case", "dich_vu_lay_lai_tien": "file",
             "bao_nguoi_than_cap_cuu": "patient", "dat_coc_gia_re": "booking", "dau_tu_san_gia": "tx"}


def gen_distractor(rng, kind, scenario=None):
    if kind == "otp":
        return digits(rng, rng.choice([6, 6, 6, 4, 8]))
    if kind == "order":
        f = ORDER_FMT.get(scenario, "shop")
        return rng.choice({
            "shop": [f"DH{digits(rng, 8)}", f"#{digits(rng, 10)}", f"{rng.choice(['SPX', 'LZD', 'TK'])}{digits(rng, 9)}",
                     f"ĐH-{digits(rng, 5)}", f"{digits(rng, 6)}{code(rng, 4, 6, 0).upper()}"],
            "case": [f"{digits(rng, 3)}/QĐ-CSĐT", f"{digits(rng, 4)}/LTG-VKS", f"HS-{digits(rng, 6)}", f"{digits(rng, 3)}/TB-CA"],
            "file": [f"HS-{digits(rng, 6)}", f"TH{digits(rng, 7)}", f"LS-{digits(rng, 5)}"],
            "patient": [f"BN{digits(rng, 8)}", f"{digits(rng, 2)}-{digits(rng, 6)}", f"HSBA-{digits(rng, 6)}"],
            "booking": [f"BK{code(rng, 6, 8, 0).upper()}", f"VN{code(rng, 6, 6, 0).upper()}", f"#{digits(rng, 7)}"],
            "tx": [f"FT{digits(rng, 5)}{code(rng, 5, 7, 0).upper()}", f"L{digits(rng, 9)}", f"#{digits(rng, 8)}"],
        }[f])
    if kind in ("tracking", "track"):
        return rng.choice([f"SPXVN0{digits(rng, 11)}", f"GHN{code(rng, 7, 9, 0).upper()}", f"VN{digits(rng, 9)}VN",
                           f"LEX{digits(rng, 10)}", f"GY{code(rng, 6, 8, 0).upper()}", f"J{digits(rng, 11)}"])
    if kind == "date":
        d, m = rng.randint(1, 28), rng.randint(1, 12)
        return rng.choice([f"{d:02d}/{m:02d}/2026", f"{d}/{m}", f"{d:02d}/{m:02d}", f"{d:02d}-{m:02d}-2026", f"{d}/{m}/2026"])
    if kind == "time":
        h, mi = rng.randint(7, 22), rng.randint(0, 59)
        return rng.choice([f"{h:02d}:{mi:02d}", f"{h}h{mi:02d}", f"{h}:{mi:02d}"])
    if kind == "cccd":
        d = rng.choice(["001", "079", "031", "036", "040", "048", "092", "025"]) + digits(rng, 9)
        return d if rng.random() < .7 else " ".join(d[i:i + 3] for i in range(0, 12, 3))
    raise ValueError(kind)


# ----------------------------------------------------------------------------------------------- paraphrase pool
FORBIDDEN = [re.compile(p, re.I) for p in (
    r"\d{3,}", r"\d\s*(k|tr|triệu|trieu|nghìn|nghin|ngàn|ngan|đ|vnd|vnđ|đồng|dong|củ|cu|usd|\$)(?!\w)",
    r"https?://|www\.|\.(com|vn|net|org|xyz|top|ly|io|me|cc|vip|online|site|info|link|shop|app|gov)\b", r"@", r"[{}]")]


def valid_variant(v: str, seed: str) -> bool:
    if not isinstance(v, str) or not v.strip() or len(v) > len(seed) * 2.2 + 40:
        return False
    if Counter(PH_RE.findall(v)) != Counter(PH_RE.findall(seed)):
        return False
    rest = PH_RE.sub(" ", v)
    return not any(p.search(rest) for p in FORBIDDEN)


STYLE_NOTE = {
    "a": "Giọng tự nhiên như tin nhắn thật, có dấu đầy đủ, lịch sự vừa phải, câu ngắn.",
    "b": "Giọng suồng sã kiểu chat: viết tắt (ck, stk, sđt, e, a, c, k, dc, nhé->nhe/nha), thiếu dấu câu, "
         "khoảng 1/3 số câu viết KHÔNG DẤU; thỉnh thoảng một emoji.",
    "c": "Câu dài hơn (thường 2 câu), có dấu đầy đủ; người kia khi thì trang trọng kiểu văn bản, khi thì gấp gáp, "
         "thêm chi tiết đời thường (xưng hô khác nhau: anh/chị/em/bạn/cô/chú/mình) nhưng không thêm số liệu.",
}


def para_prompt(scenario: str, beats, style: str, n: int) -> tuple[str, dict]:
    import yaml  # noqa: F401  (only to read the scenario card; available in both envs)
    card = yaml.safe_load((ROOT / "scenarios" / f"{scenario}.yaml").read_text(encoding="utf-8"))
    lines = []
    for j, (side, seeds) in enumerate(beats):
        who = "người kia (bên trái)" if side == L else "chủ điện thoại (bên phải)"
        lines.append(f'b{j} [{who}]: ' + " | ".join(seeds))
    prompt = f"""Bạn viết lời thoại tiếng Việt cho bộ dữ liệu ảnh chat TỔNG HỢP (dùng để huấn luyện mô hình đọc ảnh, không gửi cho ai).
Tình huống: {card['ten']}. {card['mo_ta'].strip()}

Với MỖI mã câu bên dưới, viết {n} cách nói khác nhau của cùng ý (một tin nhắn chat, 1-2 câu ngắn), đa dạng từ ngữ và độ dài.
{STYLE_NOTE[style]}

Quy tắc bắt buộc:
- Giữ NGUYÊN mọi chỗ trống trong ngoặc nhọn như {{acc}}, {{bank}}, {{holder}}, {{phone}}, {{link}}, {{amt}}, {{amt2}}, {{otp}}, {{order}}, {{track}}, {{date}}, {{time}}, {{cccd}}, {{name}}, {{place}}: đúng chính tả, đủ số lượng như câu mẫu, không thêm chỗ trống mới, không bỏ.
- KHÔNG viết thêm bất kỳ con số, số tiền, số điện thoại, số tài khoản, mã, link hay tên miền nào ngoài các chỗ trống.
- Không dùng ký tự @ và ngoặc nhọn ngoài chỗ trống. Có thể dùng "\\n" để xuống dòng giống câu mẫu.

Các câu mẫu (mã [người nói]: mẫu 1 | mẫu 2):
""" + "\n".join(lines)
    props = {f"b{j}": {"type": "array", "items": {"type": "string"}} for j in range(len(beats))}
    return prompt, {"type": "object", "properties": props, "required": list(props)}


def build_pool(out: Path, use_llm: bool) -> dict:
    pool_path, cost_path = out / "para_pool.json", out / "gen_cost.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8")) if pool_path.exists() else {}
    cost = json.loads(cost_path.read_text(encoding="utf-8")) if cost_path.exists() else {
        "model": PARA_MODEL, "cap_usd": PARA_CAP_USD, "calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0,
        "entries": []}
    if not use_llm:
        return pool
    from core import llm
    jobs = [(s, st) for st in ("a", "b", "c") for s in DIALOGS]
    for scenario, style in jobs:
        key = f"{scenario}|{style}"
        if key in pool:
            continue
        beats = DIALOGS[scenario]["beats"]
        prompt, schema = para_prompt(scenario, beats, style, 14)
        if cost["usd"] + 0.03 > PARA_CAP_USD:
            print(f"budget: stop before {key} (spent {cost['usd']:.4f} USD)", flush=True)
            break
        try:
            r = llm.generate(prompt, schema=schema, model=PARA_MODEL, retries=3)
        except Exception as e:  # keep what we have
            print("paraphrase call failed", key, str(e)[:200], flush=True)
            continue
        cost["calls"] += 1 + r.retries
        cost["tokens_in"] += r.tokens_in
        cost["tokens_out"] += r.tokens_out
        cost["usd"] = round(cost["usd"] + r.usd, 6)
        got, kept = 0, {}
        for j, (_, seeds) in enumerate(beats):
            vs = (r.output or {}).get(f"b{j}", []) or []
            got += len(vs)
            ok = []
            for v in vs:
                v = v.replace("\\n", "\n").strip()
                if any(valid_variant(v, sd) for sd in seeds) and v not in ok and v not in seeds:
                    ok.append(v)
            kept[f"b{j}"] = ok
        pool[key] = kept
        nk = sum(len(v) for v in kept.values())
        cost["entries"].append({"key": key, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "usd": round(r.usd, 6),
                                "variants_returned": got, "variants_kept": nk})
        print(f"{key}: kept {nk}/{got}, {r.usd:.4f} USD, total {cost['usd']:.4f}", flush=True)
        pool_path.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
        cost_path.write_text(json.dumps(cost, ensure_ascii=False, indent=1), encoding="utf-8")
    cost["usd_this_process"] = round(llm.USAGE.usd, 6)
    cost_path.write_text(json.dumps(cost, ensure_ascii=False, indent=1), encoding="utf-8")
    return pool


def beat_variants(pool, scenario, j, seeds):
    vs = list(seeds)
    for st in ("a", "b", "c"):
        vs += pool.get(f"{scenario}|{st}", {}).get(f"b{j}", [])
    return vs


# ----------------------------------------------------------------------------------------------- conversation
def wchoice(rng, d: dict):
    ks = [k for k, w in d.items() if w > 0]
    return rng.choices(ks, [d[k] for k in ks])[0]


class Builder:
    def __init__(self, rng, scenario, plain: bool):
        self.rng, self.scenario, self.plain = rng, scenario, plain
        self.d = DIALOGS[scenario]
        self.strings, self.vals = {}, {}
        self.bank = rng.choice(rng.choice(BANKS))
        self.holder = gen_holder(rng)

    def sid(self, ph):
        """String id for a placeholder; one value per placeholder per conversation."""
        if ph in self.vals:
            return self.vals[ph]
        rng = self.rng
        if ph in ANSWER_PH:
            t = ANSWER_PH[ph]
            raw = {"acc": lambda: gen_account(rng), "phone": lambda: gen_phone(rng),
                   "link": lambda: gen_link(rng, self.scenario),
                   "amt": lambda: gen_amount(rng, *self.d["amt"]), "amt2": lambda: gen_amount(rng, *self.d["amt2"])}[ph]()
            s = {"type": t, "raw": raw, "norm": NORMALIZERS[t](raw), "role": "answer"}
        else:
            raw = gen_distractor(rng, ph, self.scenario)
            s = {"type": DIST_PH[ph], "raw": raw, "role": "distractor"}
        k = f"s{len(self.strings)}"
        self.strings[k] = s
        self.vals[ph] = k
        return k

    def add_string(self, t, raw, role="answer"):
        k = f"s{len(self.strings)}"
        self.strings[k] = {"type": t, "raw": raw, "role": role, **({"norm": NORMALIZERS[t](raw)} if role == "answer" else {})}
        return k

    def parts(self, tpl: str):
        out = []
        for li, line in enumerate(tpl.split("\n")):
            if li:
                out.append(["br"])
            pos = 0
            for m in PH_RE.finditer(line):
                if m.start() > pos:
                    out.append(["t", line[pos:m.start()]])
                ph = m.group(1)
                if ph in ANSWER_PH or ph in DIST_PH:
                    out.append(["s", self.sid(ph)])
                elif ph == "bank":
                    out.append(["b", self.bank])
                elif ph == "holder":
                    out.append(["h", self.holder])
                elif ph == "name":
                    out.append(["t", self.vals.setdefault("_name", self.rng.choice(self.d.get("names", ["Minh"])))])
                elif ph == "place":
                    out.append(["t", self.vals.setdefault("_place", self.rng.choice(self.d.get("place", ["đây"])))])
                pos = m.end()
            if pos < len(line):
                out.append(["t", line[pos:]])
        if self.plain or (tpl.isascii() and re.search(r"[a-z]{3}", PH_RE.sub("", tpl))):
            # a line typed without diacritics also types the inserted names/places without them
            out = [["t", strip_marks(p[1])] if p[0] == "t" else p for p in out]
        # merge adjacent text
        merged = []
        for p in out:
            if p[0] == "t" and merged and merged[-1][0] == "t":
                merged[-1] = ["t", merged[-1][1] + p[1]]
            elif p[0] != "t" or p[1]:
                merged.append(p)
        return merged


def has_answer(tpl):
    return any(p in ANSWER_PH for p in PH_RE.findall(tpl))


def has_any_ph(tpl):
    return any(p in ANSWER_PH or p in DIST_PH for p in PH_RE.findall(tpl))


def clock(rng):
    return f"{rng.randint(7, 22)}:{rng.randint(0, 59):02d}"


def make_conv(rng, split, idx, pool, template=None, scenario=None):
    if template is None:
        template = wchoice(rng, TRAIN_TEMPLATES)
    if scenario is None:
        scenario = rng.choice(sorted(NORMAL)) if rng.random() < P_NORMAL else rng.choice(SCAM_TRAIN)
    cond = wchoice(rng, CONDITIONS)
    if template == "web" and cond in ("long", "stitch"):
        cond = rng.choice(["clean", "jpeg", "crop"])
    no_strings = rng.random() < P_NO_STRINGS
    plain = rng.random() < (.22 if template in ("android", "imessage") and scenario not in NORMAL else .08)
    b = Builder(rng, scenario, plain)
    beats = b.d["beats"]
    n_target = rng.randint(20, 30) if cond == "long" else rng.randint(13, 24) if cond == "stitch" else \
        min(14, max(3, round(rng.triangular(3, 14, 7))))

    # choose beats in order
    chosen = []
    for j, (side, seeds) in enumerate(beats):
        vs = beat_variants(pool, scenario, j, seeds)
        if no_strings:
            vs = [v for v in vs if not has_answer(v)]
            if not vs:
                continue
            p = .7
        else:
            p = .8 if any(has_answer(v) for v in seeds) else .55
        if rng.random() < p:
            chosen.append((side, rng.choice(vs)))
    if not no_strings and not any(has_answer(t) for _, t in chosen):
        cands = [(s, v) for j, (s, seeds) in enumerate(beats) for v in seeds if has_answer(v)]
        chosen.insert(0, rng.choice(cands))
    if not any(s == R for s, _ in chosen):
        rs = [(s, rng.choice(seeds)) for s, seeds in beats if s == R]
        rs = [x for x in rs if not (no_strings and has_answer(x[1]))]
        if rs:
            pos = rng.randint(1, max(1, len(chosen)))
            chosen.insert(pos, rng.choice(rs))
    # trim / extend to the target length
    while len(chosen) > n_target:
        drop = [i for i, (_, t) in enumerate(chosen) if not has_answer(t)] or list(range(len(chosen)))
        if len(chosen) - 1 < 2:
            break
        chosen.pop(rng.choice(drop))
    fill_pool = {s: rng.sample(FILLERS[s], len(FILLERS[s])) for s in (L, R)}
    while len(chosen) < n_target:
        pos = rng.randint(0, len(chosen))
        prev = chosen[pos - 1][0] if pos else R
        side = L if prev == R or rng.random() < .45 else R
        if not fill_pool[side]:
            fill_pool[side] = rng.sample(FILLERS[side], len(FILLERS[side]))
        chosen.insert(pos, (side, fill_pool[side].pop()))

    # items
    items = []
    t0h, t0m = rng.randint(7, 21), rng.randint(0, 59)
    tick = [t0h * 60 + t0m]

    def tnow():
        tick[0] += rng.choice([0, 0, 1, 1, 2, 5])
        return f"{(tick[0] // 60) % 24:02d}:{tick[0] % 60:02d}"

    if rng.random() < .75:
        r = rng.random()
        if r < .35:
            items.append({"kind": "chip", "parts": [["t", rng.choice(["Hôm nay ", "Hôm qua ", "Thứ Bảy ", ""]) +
                                                       f"{t0h:02d}:{t0m:02d}"]]})
        else:
            dsid = b.add_string("datetime", gen_distractor(rng, "date"), "distractor")
            items.append({"kind": "chip", "parts": [["s", dsid], ["t", f" {t0h:02d}:{t0m:02d}"]] if rng.random() < .6
                          else [["t", f"{t0h:02d}:{t0m:02d} "], ["s", dsid]]})
    if rng.random() < .14:
        items.append({"kind": "call", "side": L, "video": rng.random() < .3, "time": tnow()})
    for side, tpl in chosen:
        it = {"kind": "text", "side": side, "parts": b.parts(tpl), "time": tnow()}
        if template in ("zalo", "messenger", "telegram", "viber", "web") and rng.random() < .07:
            it["react"] = rng.choice(["❤️", "👍", "😆", "😮", "❤️ 2"])
        items.append(it)
        sids = [p[1] for p in it["parts"] if p[0] == "s"]
        types = {b.strings[k]["type"] for k in sids if b.strings[k]["role"] == "answer"}
        if "link" in types and rng.random() < .35:
            items.append({"kind": "lcard", "side": side, "title": rng.choice(LCARD_TITLES[scenario in NORMAL]),
                          "desc": rng.choice(LCARD_DESC), "site": rng.choice(LCARD_SITE[scenario in NORMAL]),
                          "bg": rand_pic(rng)})
        if "account" in types and b.d.get("receipt") and not no_strings and rng.random() < .3:
            items.append(make_receipt(rng, b, side_of=b.d["receipt"]))
        if rng.random() < .05:
            items.append({"kind": "img", "side": side, "pw": rng.randint(170, 240), "ph": rng.randint(130, 260),
                          "bg": rand_pic(rng)})
        if rng.random() < .04 and len(items) > 3:
            items.append({"kind": "call", "side": L, "video": rng.random() < .4, "time": tnow()})
    # a receipt for normal scenarios without an explicit account line
    if not no_strings and b.d.get("receipt") == R and scenario in NORMAL and rng.random() < .08 and \
            not any(i["kind"] == "receipt" for i in items):
        items.append(make_receipt(rng, b, side_of=R))
    # android/imessage: time under the last bubble of a group
    for k, it in enumerate(items):
        nxt = items[k + 1] if k + 1 < len(items) else None
        it["tm_out"] = it["kind"] == "text" and (nxt is None or nxt.get("side") != it.get("side") or rng.random() < .15)
        it["first"] = k == 0 or items[k - 1].get("side") != it.get("side")

    if no_strings:  # strings never come from fills; drop any answer that slipped in
        assert not any(s["role"] == "answer" for s in b.strings.values()), (scenario, chosen)

    # screen / capture parameters
    if template == "web":
        w, h = rng.choice(DESKTOP_SIZES)
        dpr = rng.choice([1, 1, 1.25])
        os_ = "desktop"
    else:
        w, h = rng.choice(PHONE_SIZES)
        dpr = rng.choice([2, 2.625, 3]) if cond not in ("long", "stitch") else 2
        os_ = "ios" if template == "imessage" else "android" if template == "android" else rng.choice(["ios", "android"])
    cp = {}
    if cond == "crop":
        top = rng.uniform(-.1, .35)
        cp = {"top": top, "bot": top + rng.uniform(.45, .85)}
    elif cond == "jpeg":
        cp = {"q": rng.randint(18, 60), "resize": rng.choice([1, 1, .75, .6]), "q2": rng.choice([0, 0, rng.randint(25, 70)])}
    elif cond == "small":
        cp = {"scale": rng.uniform(.3, .55) if template != "web" else rng.uniform(.55, .8)}
        dpr = 3 if template != "web" else 1
    elif cond == "photo":
        cp = {"seed": rng.randrange(2 ** 31)}
    elif cond == "stitch":
        cp = {"k": rng.choice([2, 2, 3]), "gap": rng.choice([0, 8, 16, 24]), "gapcol": rng.choice(["#fff", "#000", "#ddd"])}
    marks = []
    if rng.random() < P_MARKS:
        marks = rng.choice([["x"], ["x"], ["circle"], ["arrow"], ["stamp"], ["logo"], ["x", "logo"], ["circle", "logo"],
                            ["stamp", "logo"], ["x", "stamp"]])
    texts = [i for i, it in enumerate(items) if it["kind"] == "text"]
    ans = [k for k, s in b.strings.items() if s["role"] == "answer"]
    win = rng.choices(["end", "start", "focus"], [.55, .15, .3])[0]
    window = {"mode": win, "sid": rng.choice(ans) if ans else None, "frac": rng.uniform(.15, .7)}
    if win == "focus" and not ans:
        window["mode"] = "end"
    vis = {"avc": rng.choice(["#6aa4f0", "#e17076", "#7bc862", "#ee7aae", "#6ec9cb", "#faa774", "#a695e7", "#65aadd",
                              "#9b8d82", "#c0a35a"]),
           "subtitle": rng.choice(SUB[template]), "online": rng.random() < .6, "unread": rng.choice([0, 0, 3, 12, 27]),
           "batt": rng.randint(15, 95), "net4g": rng.random() < .5, "status": rng.random() < .85,
           "nav3": rng.random() < .4, "home_ind": rng.random() < .6, "sms_green": rng.random() < .3,
           "font": rng.choice([None, None, "Arial, sans-serif", "'Liberation Sans', Arial, sans-serif",
                               "'DejaVu Sans', sans-serif"]),
           "anchor_bottom": rng.random() < .8}
    if template == "web":
        names = rng.sample(SIDE_NAMES, 7)
        vis.update(side_snip=rng.choice(SIDE_SNIPS), side_list=[(n, rng.choice(SIDE_SNIPS)) for n in names],
                   side_cols=[rng.choice(["#6aa4f0", "#e17076", "#7bc862", "#ee7aae", "#faa774", "#a695e7"]) for _ in range(8)],
                   side_times=["Vài giây"] + [rng.choice(["5 phút", "1 giờ", "2 giờ", "Hôm qua", "T2", "T5", "CN"])
                                             for _ in range(7)])
    return {"id": f"{split}_{idx:05d}", "split": split, "scenario": scenario, "normal": scenario in NORMAL,
            "template": template, "dark": rng.random() < P_DARK, "os": os_, "screen": {"w": w, "h": h, "dpr": dpr},
            "condition": cond, "cond": cp, "marks": marks, "mark_seed": rng.randrange(2 ** 31), "window": window,
            "contact": rng.choice(b.d["contacts"]), "clock": clock(rng), "no_strings_planned": no_strings,
            "plain": plain, "vis": vis, "items": items, "strings": b.strings, "n_text": len(texts)}


SUB = {"zalo": ["Vừa truy cập", "Truy cập 5 phút trước", "Truy cập 1 giờ trước", ""],
       "messenger": ["Đang hoạt động", "Hoạt động 12 phút trước", "Hoạt động 1 giờ trước", ""],
       "telegram": ["truy cập gần đây", "online", "last seen recently", "truy cập lúc 21:40"],
       "viber": ["Online", "Truy cập 10 phút trước", ""], "whatsapp": ["online", "trực tuyến", "đang nhập...", ""],
       "web": ["Vừa truy cập", "Truy cập 3 phút trước", "Người lạ - Chưa là bạn bè"], "android": [""], "imessage": [""]}
LCARD_TITLES = {False: ["Tra cứu đơn hàng - Hỗ trợ khách hàng", "Cổng xác thực thông tin trực tuyến", "Đăng ký nhận nhiệm vụ",
                        "Hoàn tiền giao dịch lỗi", "Xác minh tài khoản ngân hàng", "Ưu đãi chỉ hôm nay"],
                True: ["Ảnh chia sẻ", "Vị trí trên bản đồ", "Bộ sưu tập mới", "Thực đơn hôm nay", "Album gia đình"]}
LCARD_DESC = ["Vui lòng đăng nhập để tiếp tục", "Xem chi tiết tại đây", "Nhấn để mở liên kết", "Cập nhật thông tin nhanh chóng",
              "Hệ thống tự động xử lý"]
LCARD_SITE = {False: ["Hỗ trợ khách hàng", "Trang chính thức", "Trung tâm dịch vụ", "Cổng thông tin"],
              True: ["Google Drive", "Ảnh", "Bản đồ", "Facebook", "Shopee"]}
SIDE_NAMES = ["Nhóm Lớp Cũ", "Cloud của tôi", "Mẹ", "Anh Hải", "Phòng Kế Toán", "Hội Phụ Huynh", "Chị Vân", "Lan Anh",
              "Team Dự Án", "Gia đình", "Minh Khoa", "Thu Hà"]
SIDE_SNIPS = ["Ok bạn", "Đã gửi một ảnh", "Bạn: cảm ơn nhé", "[Sticker]", "Hẹn mai nhé", "Bạn đã bỏ lỡ cuộc gọi",
              "Dạ vâng ạ", "Bạn: để mình xem", "[Hình ảnh]", "Tối nay họp nhé"]
MEMOS = ["chuyen tien", "CK tien hang", "tien coc phong", "hoan tien", "chuyen khoan", "thanh toan don hang", "gui me"]


def rand_pic(rng):
    c = ["#8fb3d9", "#d9a68f", "#a3c99a", "#c7b07a", "#9a8fc7", "#d98fae", "#7fb8b0", "#b0a090"]
    a, b2, c2 = rng.sample(c, 3)
    return (f"radial-gradient(circle at {rng.randint(20, 80)}% {rng.randint(20, 70)}%, {a} 0 18%, transparent 19%),"
            f"linear-gradient({rng.randint(0, 180)}deg, {b2}, {c2})")


def make_receipt(rng, b: Builder, side_of):
    """Bank-app transfer receipt card (shared screenshot). See module docstring for the labelling rule."""
    if side_of == R and "acc" in b.vals:  # the phone owner paid the account given in the chat
        raw_acc = re.sub(r"\D", "", b.strings[b.vals["acc"]]["raw"])
        bank, holder = b.bank, b.holder
    else:  # the other side "proves" a transfer to the phone owner (or a fresh account)
        raw_acc, bank, holder = re.sub(r"\D", "", gen_account(rng)), rng.choice(rng.choice(BANKS)), gen_holder(rng)
    v_src = b.strings[b.sid("amt")]["raw"]  # same value as the {amt} the chat states (fixed now if not yet used)
    from e1.scenarios import amount_value
    v = amount_value(v_src) if v_src else None
    if not v:
        v = round(math.exp(rng.uniform(math.log(b.d["amt"][0]), math.log(b.d["amt"][1]))) / 1000) * 1000
    amt_raw = fmt_vnd(v) + rng.choice([" VND", " VND", " đ", "đ", " VNĐ"])
    return {"kind": "receipt", "side": side_of, "amt": b.add_string("amount", amt_raw),
            "acc": b.add_string("account", raw_acc), "bank": bank, "holder": holder, "memo": rng.choice(MEMOS),
            "tx": b.add_string("order", f"FT{digits(rng, 5)}{code(rng, 5, 7, 0).upper()}" if rng.random() < .6 else
                               digits(rng, rng.choice([9, 10, 12])), "distractor") if rng.random() < .8 else None,
            "when": b.add_string("datetime", f"{gen_distractor(rng, 'time')} {gen_distractor(rng, 'date')}", "distractor")
            if rng.random() < .8 else None,
            "title": rng.choice(["Chuyển tiền thành công", "Giao dịch thành công", "Chuyển khoản thành công"]),
            "sign": rng.choice(["", "", "-"]), "color": rng.choice(["#0f7a3b", "#e2231a", "#1a4795", "#00a650", "#7b2c8e",
                                                                   "#f37021", "#0d5c9e", "#004b8d", "#ac1f2d"])}


def cmd_text(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pool = build_pool(out, not args.no_llm)
    meta = {"seed": args.seed, "sizes": SPLITS, "train_templates": list(TRAIN_TEMPLATES), "train_scenarios": TRAIN_SCENARIOS,
            "normal_scenarios": sorted(NORMAL), "val_la": {"template": HELD_OUT_TEMPLATE, "scenarios": list(HELD_OUT_SCENARIOS)},
            "conditions": {k: v for k, v in CONDITIONS.items() if v}, "p_normal": P_NORMAL, "p_no_strings_planned": P_NO_STRINGS,
            "p_dark": P_DARK, "p_marks": P_MARKS}
    (out / "splits.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    for split, n in SPLITS.items():
        d = out / split
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "convs.jsonl", "w", encoding="utf-8") as f:
            for i in range(n):
                rng = random.Random(f"{args.seed}-{split}-{i}")
                if split == "val_la":
                    spec = make_conv(rng, split, i, pool, template=HELD_OUT_TEMPLATE, scenario=rng.choice(HELD_OUT_SCENARIOS))
                else:
                    spec = make_conv(rng, split, i, pool)
                f.write(json.dumps(spec, ensure_ascii=False) + "\n")
        print(split, n, "conversations", flush=True)


# ----------------------------------------------------------------------------------------------- render
MEASURE_JS = """(win) => {
  const chat = document.querySelector('.chat');
  if (win && win.anchor) { const inn = chat.querySelector('.inner'); inn.style.minHeight = '100%';
    inn.style.justifyContent = 'flex-end'; }
  if (win && win.mode) {
    const max = chat.scrollHeight - chat.clientHeight;
    let top = max;
    if (win.mode === 'start') top = 0;
    else if (win.mode === 'page') top = win.page * chat.clientHeight * win.step;
    else if (win.mode === 'focus' && win.sid) {
      const el = document.querySelector(`[data-sid="${win.sid}"]`);
      if (el) { const cb = chat.getBoundingClientRect(), eb = el.getBoundingClientRect();
        top = eb.top - cb.top + chat.scrollTop - chat.clientHeight * win.frac; }
    }
    chat.scrollTop = Math.max(0, Math.min(max, top));
  }
  const R = e => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  const RS = e => [...e.getClientRects()].map(b => [b.left, b.top, b.right, b.bottom]);
  const item = e => +e.closest('[data-item]').dataset.item;
  return {
    clip: R(chat), page: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
    msgs: [...document.querySelectorAll('[data-msg]')].map(e => ({i: +e.dataset.msg, box: R(e),
      text: e.querySelector('.txt').innerText})),
    items: [...document.querySelectorAll('[data-item]')].map(e => ({i: +e.dataset.item, box: R(e)})),
    strs: [...document.querySelectorAll('[data-sid]')].map(e => ({sid: e.dataset.sid, item: item(e), rects: RS(e),
      text: e.textContent, cont: R(e.closest('.bubble,.card,.chip'))})),
    banks: [...document.querySelectorAll('[data-bank]')].map(e => ({item: item(e), box: R(e), text: e.textContent})),
    holders: [...document.querySelectorAll('[data-holder]')].map(e => ({item: item(e), box: R(e), text: e.textContent})),
    body: document.body.innerText,
  };
}"""


def ws(s):
    return " ".join(s.split())


def inside(b, v, tol=0.6):
    return b[0] >= v[0] - tol and b[1] >= v[1] - tol and b[2] <= v[2] + tol and b[3] <= v[3] + tol


def overlaps(b, v):
    return b[0] < v[2] and b[2] > v[0] and b[1] < v[3] and b[3] > v[1]


def plain_text(parts, strings):
    return "".join("\n" if p[0] == "br" else strings[p[1]]["raw"] if p[0] == "s" else p[1] for p in parts)


class SelfCheckError(Exception):
    pass


def label_screen(spec, meas, view, fmap, sc):
    """Visible messages/strings of one rendered screen. view: visible rect (CSS px). fmap: CSS px -> final px."""
    strings = spec["strings"]

    def mb(b):
        pts = [fmap(x, y) for x, y in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3]))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]

    msgs, ign_msgs = [], []
    for m in sorted(meas["msgs"], key=lambda m: m["box"][1]):
        it = spec["items"][m["i"]]
        text = plain_text(it["parts"], strings)
        if ws(m["text"]) != ws(text):
            raise SelfCheckError(f"message DOM text differs: {m['text']!r} vs {text!r}")
        rec = {"side": it["side"], "text": text, "box": mb(m["box"]), "item": m["i"]}
        if inside(m["box"], view):
            msgs.append(rec)
        elif overlaps(m["box"], view):
            ign_msgs.append(rec)
    occ = defaultdict(list)
    for s in meas["strs"]:
        occ[s["sid"]].append(s)
    found, ign, dist = [], [], []
    for sid, os_ in occ.items():
        s = strings[sid]
        state = None
        for o in os_:
            if ws(o["text"]) != ws(s["raw"]) or o["text"] != s["raw"]:
                raise SelfCheckError(f"string DOM text differs: {o['text']!r} vs {s['raw']!r}")
            if not all(r[0] >= o["cont"][0] - .6 and r[2] <= o["cont"][2] + .6 for r in o["rects"]):
                raise SelfCheckError(f"string clipped by its bubble: {s['raw']!r}")
            if all(inside(r, view) for r in o["rects"]):
                state = ("vis", o)
                break
            if any(overlaps(r, view) for r in o["rects"]) and state is None:
                state = ("part", o)
        if state is None:
            continue
        o = state[1]
        if s["role"] == "distractor":
            if state[0] == "vis":
                dist.append({"type": s["type"], "raw": s["raw"], "boxes": [mb(r) for r in o["rects"]]})
            continue
        if state[0] == "part":
            ign.append({"type": s["type"], "norm": s["norm"], "raw": s["raw"]})
            continue
        if ws(s["raw"]) not in ws(meas["body"]) and s["raw"].replace(" ", "") not in meas["body"].replace(" ", "").replace("\n", ""):
            raise SelfCheckError(f"answer not in page text: {s['raw']!r}")
        e = {"type": s["type"], "raw": s["raw"], "norm": s["norm"], "boxes": [mb(r) for r in o["rects"]],
             "item": o["item"], "y": o["rects"][0][1], "x": o["rects"][0][0]}
        if s["type"] == "account":
            bk = [x for x in meas["banks"] if x["item"] == o["item"] and inside(x["box"], view)]
            hd = [x for x in meas["holders"] if x["item"] == o["item"] and inside(x["box"], view)]
            e["bank"] = bk[0]["text"] if bk else None
            e["holder"] = hd[0]["text"] if hd else None
        found.append(e)
    found.sort(key=lambda e: (round(e["y"]), e["x"]))
    return msgs, ign_msgs, found, ign, dist


def render_task(spec, page_for, out_dir: Path):
    """Render one spec, write image/gt/target. Returns a manifest row (raises SelfCheckError)."""
    import io
    from PIL import Image
    from e1.gen_train_templates import page_html

    sc = spec["screen"]
    cond = spec["condition"]
    items = list(enumerate(spec["items"]))
    texts = [i for i, it in items if it["kind"] == "text"]
    if cond == "stitch":  # k consecutive scroll positions of the same chat, side by side
        chunks = [items] * spec["cond"]["k"]
    else:
        chunks = [items]
    step = random.Random(spec["mark_seed"]).uniform(.8, .95)
    tops = set()
    screens = []
    for ci, chunk in enumerate(chunks):
        long = cond == "long"
        doc = page_html(spec, chunk, sc, long=long)
        page = page_for(sc["dpr"])
        page.set_viewport_size({"width": sc["w"], "height": sc["h"]})
        page.set_content(doc, wait_until="domcontentloaded")
        page.evaluate("document.fonts.ready")
        win = None if long else {**spec["window"], "anchor": spec["vis"]["anchor_bottom"]}
        if cond == "stitch":
            win = {"mode": "page", "page": ci, "step": step, "anchor": True, "sid": None, "frac": .5}
        meas = page.evaluate(MEASURE_JS, win)
        if cond == "stitch":
            st = round(page.evaluate("document.querySelector('.chat').scrollTop"))
            if st in tops:  # conversation shorter than k screens: no duplicate screen
                continue
            tops.add(st)
        if long:
            hgt = math.ceil(meas["page"][1])
            page.set_viewport_size({"width": sc["w"], "height": hgt})
            meas = page.evaluate(MEASURE_JS, None)
            png = page.screenshot(full_page=True)
        else:
            png = page.screenshot()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        screens.append((img, meas))

    dpr = sc["dpr"]
    # per-screen crop + placement
    placed = []
    for img, meas in screens:
        W, H = img.width / dpr, img.height / dpr
        clip = meas["clip"]
        crop = [0, 0, W, H]
        if cond == "crop":
            ch = clip[3] - clip[1]
            top = max(0.0, clip[1] + spec["cond"]["top"] * ch)
            bot = min(H, clip[1] + spec["cond"]["bot"] * ch)
            if bot - top < 120:
                bot = min(H, top + 160)
            crop = [0, top, W, bot]
            img = img.crop((0, round(top * dpr), img.width, round(bot * dpr)))
        view = [max(clip[0], crop[0]), max(clip[1], crop[1]), min(clip[2], crop[2]), min(clip[3], crop[3])]
        placed.append([img, meas, view, crop])
    # stitch side by side
    if len(placed) > 1:
        gap = spec["cond"]["gap"]
        Wt = sum(p[0].width for p in placed) + gap * (len(placed) - 1)
        Ht = max(p[0].height for p in placed)
        canvas = Image.new("RGB", (Wt, Ht), spec["cond"]["gapcol"])
        x = 0
        for p in placed:
            canvas.paste(p[0], (x, 0))
            p.append(x)
            x += p[0].width + gap
        img = canvas
    else:
        placed[0].append(0)
        img = placed[0][0]
    # global transforms
    scale, photo_fn = 1.0, None
    if cond == "small":
        scale = spec["cond"]["scale"]
    if cond == "jpeg" and spec["cond"]["resize"] != 1:
        scale = spec["cond"]["resize"]
    if cond == "stitch" and img.width > 2200:
        scale = 2200 / img.width
    if scale != 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    if cond == "photo":
        from e1.gen_hard import rephotograph
        img, photo_fn = rephotograph(img, random.Random(spec["cond"]["seed"]))

    all_msgs, all_ign_m, all_str, all_ign_s, all_dist = [], [], [], [], []
    for img_s, meas, view, crop, ox in placed:
        def fmap(x, y, crop=crop, ox=ox):
            px, py = ((x - crop[0]) * dpr + ox) * scale, ((y - crop[1]) * dpr) * scale
            return photo_fn(px, py) if photo_fn else (px, py)
        m, im_, s, is_, d = label_screen(spec, meas, view, fmap, sc)
        all_msgs += m
        all_ign_m += im_
        all_str += s
        all_ign_s += is_
        all_dist += d

    # dedupe answers by (type, norm), reading order; ignored strings that are also fully visible elsewhere drop out
    strings = {t: [] for t in TYPES}
    seen = set()
    for e in all_str:
        key = (e["type"], e["norm"])
        if key in seen:
            for x in strings[e["type"]]:
                if x["norm"] == e["norm"]:
                    x["boxes"] += e["boxes"]
            continue
        seen.add(key)
        rec = {"raw": e["raw"], "norm": e["norm"], "boxes": e["boxes"]}
        if e["type"] == "account":
            rec.update(bank=e["bank"], holder=e["holder"])
        strings[e["type"]].append(rec)
    ign_s, seen_i = [], set()
    for e in all_ign_s:
        if (e["type"], e["norm"]) not in seen and (e["type"], e["norm"]) not in seen_i:
            seen_i.add((e["type"], e["norm"]))
            ign_s.append(e)
    # self-check: distractors never answers
    ans_raw = {x["raw"] for t in TYPES for x in strings[t]}
    for d in all_dist:
        if d["raw"] in ans_raw or any(NORMALIZERS[t](d["raw"]) in {x["norm"] for x in strings[t]} for t in TYPES):
            raise SelfCheckError(f"distractor equals an answer: {d['raw']!r}")
    # a bubble seen on several stitched screens is one message: first fully visible occurrence
    seen_items, msgs_u = set(), []
    for m in all_msgs:
        if m["item"] not in seen_items:
            seen_items.add(m["item"])
            msgs_u.append(m)
    messages = [{"order": k, "side": m["side"], "text": m["text"], "box": m["box"]} for k, m in enumerate(msgs_u)]
    ign_m, seen_ig = [], set()
    for m in all_ign_m:
        if m["item"] not in seen_items and m["item"] not in seen_ig:
            seen_ig.add(m["item"])
            ign_m.append({"side": m["side"], "text": m["text"], "box": m["box"]})

    # marks (drawn after the capture condition, like a news publisher)
    if spec["marks"]:
        img = draw_marks(img, spec, [b for t in TYPES for x in strings[t] for b in x["boxes"]] +
                         [b for d in all_dist for b in d["boxes"]] + [m["box"] for m in messages])

    iid = spec["id"]
    ext = "png" if cond in ("clean", "crop", "long") else "jpg"
    path = out_dir / "images" / f"{iid}.{ext}"
    if ext == "png":
        img.save(path, optimize=False, compress_level=6)
    else:
        q = {"jpeg": spec["cond"].get("q", 85), "photo": 90}.get(cond, 92)
        if cond == "jpeg" and spec["cond"].get("q2"):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=spec["cond"]["q2"])
            img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        img.save(path, quality=q)
    target = {"messages": [{"order": m["order"], "side": m["side"], "text": m["text"]} for m in messages],
              "accounts": [{"number": x["raw"], "bank": x["bank"], "holder": x["holder"]} for x in strings["account"]],
              "phones": [x["raw"] for x in strings["phone"]], "links": [x["raw"] for x in strings["link"]],
              "amounts": [x["raw"] for x in strings["amount"]]}
    gt = {"image_id": iid, "variant": cond, "style": spec["template"], "scenario": spec["scenario"],
          "normal": spec["normal"], "dark": spec["dark"], "marks": spec["marks"], "screen": sc,
          "size": list(img.size), "n_screens": len(placed), "strings": strings, "messages": messages,
          "ignore": {"strings": ign_s, "messages": ign_m}, "distractors": all_dist}
    (out_dir / "gt" / f"{iid}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "target" / f"{iid}.json").write_text(json.dumps(target, ensure_ascii=False), encoding="utf-8")
    return {"image_id": iid, "path": f"images/{iid}.{ext}", "variant": cond, "style": spec["template"],
            "scenario": spec["scenario"], "dark": spec["dark"], "split": spec["split"]}


PUBLISHERS = ["TIN NHANH 24H", "BÁO MẪU SỐ", "NEWS ONLINE", "ĐỜI SỐNG PLUS", "AN NINH SỐ", "THỜI SỰ 360", "VNNEWS"]
STAMPS = ["LỪA ĐẢO", "CẢNH BÁO", "Lua dao", "THỦ ĐOẠN LỪA ĐẢO"]


def draw_marks(img, spec, protect):
    """Hand-drawn red strokes / circles / arrows, publisher watermark and stamp."""
    from PIL import Image, ImageDraw, ImageFont
    rng = random.Random(spec["mark_seed"])
    W, H = img.size
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    col = rng.choice([(228, 30, 38), (235, 50, 60), (220, 20, 60), (240, 60, 120), (30, 90, 230)])
    wid = max(3, round(min(W, H) * rng.uniform(.006, .014)))
    alpha = rng.randint(170, 225)

    def stroke(p0, p1, n=12):
        pts = []
        for k in range(n + 1):
            t = k / n
            j = min(W, H) * .006
            pts.append((p0[0] + (p1[0] - p0[0]) * t + rng.uniform(-j, j), p0[1] + (p1[1] - p0[1]) * t + rng.uniform(-j, j)))
        dr.line(pts, fill=(*col, alpha), width=wid, joint="curve")

    for mk in spec["marks"]:
        if mk == "x":
            m = rng.uniform(.03, .15)
            stroke((W * m, H * rng.uniform(.03, .2)), (W * (1 - m), H * rng.uniform(.8, .97)))
            stroke((W * (1 - m), H * rng.uniform(.03, .2)), (W * m, H * rng.uniform(.8, .97)))
        elif mk in ("circle", "arrow") and protect:
            b = rng.choice(protect)
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            rx, ry = (b[2] - b[0]) / 2 + wid * 3, (b[3] - b[1]) / 2 + wid * 3
            if mk == "circle":
                pts = [(cx + rx * math.cos(a) * (1 + rng.uniform(-.04, .04)), cy + ry * math.sin(a) * (1 + rng.uniform(-.08, .08)))
                       for a in [k * 2 * math.pi / 40 for k in range(44)]]
                dr.line(pts, fill=(*col, alpha), width=max(2, wid // 2 + 1), joint="curve")
            else:
                sx, sy = min(W - 5, cx + rx + W * .25), min(H - 5, cy + H * .08)
                stroke((sx, sy), (cx + rx, cy), 6)
                ang = math.atan2(cy - sy, cx + rx - sx)
                for da in (2.6, -2.6):
                    stroke((cx + rx, cy), (cx + rx + math.cos(ang + da) * W * .04, cy + math.sin(ang + da) * W * .04), 3)
    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    dr = ImageDraw.Draw(img, "RGBA")
    for mk in spec["marks"]:
        if mk not in ("logo", "stamp"):
            continue
        text = rng.choice(PUBLISHERS if mk == "logo" else STAMPS)
        size = max(14, round(W * (rng.uniform(.035, .055) if mk == "logo" else rng.uniform(.06, .09))))
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        tb = dr.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = size * .4
        spots = [(W * .03, H * .02), (W - tw - W * .03 - 2 * pad, H * .02), (W * .03, H - th - H * .02 - 2 * pad),
                 (W - tw - W * .03 - 2 * pad, H - th - H * .02 - 2 * pad), ((W - tw) / 2, (H - th) / 2)]
        rng.shuffle(spots)
        for x, y in spots:
            box = [x, y, x + tw + 2 * pad, y + th + 2 * pad]
            if not any(overlaps(box, p) for p in protect):
                if mk == "logo":
                    dr.rounded_rectangle(box, radius=size * .3, fill=(0, 0, 0, 70))
                    dr.text((x + pad, y + pad - tb[1]), text, font=font, fill=(255, 255, 255, 215))
                else:
                    dr.rectangle(box, outline=(220, 20, 30, 230), width=max(2, size // 10))
                    dr.text((x + pad, y + pad - tb[1]), text, font=font, fill=(220, 20, 30, 230))
                break
    return img


_WORKER = {}


def _worker_init():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    args = ["--disable-gpu", "--renderer-process-limit=2", "--disable-extensions", "--disable-dev-shm-usage"]
    try:
        br = pw.chromium.launch(channel="chrome", args=args)
    except Exception:
        br = pw.chromium.launch(args=args)
    _WORKER.update(pw=pw, br=br, pages={})


def _page_for(dpr):
    """One live context per worker (each holds its own renderer); switch only when the scale factor changes."""
    pages = _WORKER["pages"]
    if dpr not in pages:
        for p in pages.values():
            p.context.close()
        pages.clear()
        ctx = _WORKER["br"].new_context(viewport={"width": 390, "height": 844}, device_scale_factor=dpr)
        pages[dpr] = ctx.new_page()
        pages[dpr].set_default_timeout(90_000)
    return pages[dpr]


def _worker_run(args):
    spec, out_dir = args
    t0 = time.perf_counter()
    try:
        try:
            row = render_task(spec, _page_for, Path(out_dir))
        except Exception as e:  # browser hiccup under memory pressure: fresh pages, one retry
            if isinstance(e, SelfCheckError) or "Timeout" not in type(e).__name__:
                raise
            for p in _WORKER["pages"].values():
                p.context.close()
            _WORKER["pages"].clear()
            row = render_task(spec, _page_for, Path(out_dir))
        return {"ok": True, "row": row, "sec": time.perf_counter() - t0}
    except SelfCheckError as e:
        return {"ok": False, "id": spec["id"], "error": f"selfcheck: {e}"}
    except Exception as e:  # noqa: BLE001 - report and keep going
        import traceback
        return {"ok": False, "id": spec["id"], "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-1500:]}


def cmd_render(args):
    import multiprocessing as mp
    out = Path(args.out)
    d = out / args.split
    for sub in ("images", "gt", "target"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    specs = [json.loads(l) for l in open(d / "convs.jsonl", encoding="utf-8")]
    if args.limit:
        specs = specs[: args.limit]
    if args.ids:
        want = set(args.ids.split(","))
        specs = [s for s in specs if s["id"] in want]
    todo = [s for s in specs if args.force or not (d / "gt" / f"{s['id']}.json").exists()]
    todo.sort(key=lambda s: s["screen"]["dpr"])  # workers rarely switch context
    print(f"{args.split}: {len(specs)} specs, {len(todo)} to render, {args.workers} workers", flush=True)
    t0 = time.time()
    fails = []
    done = 0
    if todo:
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.workers, initializer=_worker_init, maxtasksperchild=200) as pool:
            for r in pool.imap_unordered(_worker_run, [(s, str(d)) for s in todo], chunksize=8):
                done += 1
                if not r["ok"]:
                    fails.append(r)
                    print("FAIL", r["id"], r["error"], flush=True)
                if done % 100 == 0 or done == len(todo):
                    el = time.time() - t0
                    print(f"{done}/{len(todo)} {el:.0f}s ({el / done:.2f}s/img) fails={len(fails)}", flush=True)
    wall = time.time() - t0
    with open(d / "failures.jsonl", "a", encoding="utf-8") as f:
        for r in fails:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_manifest(d)
    log = out / "render_log.jsonl"
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"split": args.split, "rendered": len(todo) - len(fails), "fails": len(fails),
                            "workers": args.workers, "wall_s": round(wall, 1),
                            "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
    print(f"done {args.split}: {len(todo) - len(fails)} written, {len(fails)} failed, {wall:.0f}s", flush=True)
    cmd_stats(args)


def write_manifest(d: Path):
    specs = {}
    for l in open(d / "convs.jsonl", encoding="utf-8"):
        s = json.loads(l)
        specs[s["id"]] = s
    rows = []
    for iid, s in specs.items():
        g = d / "gt" / f"{iid}.json"
        if not g.exists():
            continue
        img = next((d / "images").glob(f"{iid}.*"), None)
        if img is None:
            continue
        rows.append({"image_id": iid, "path": f"images/{img.name}", "target": f"target/{iid}.json", "variant": s["condition"],
                     "style": s["template"], "dark": s["dark"], "scenario": s["scenario"], "normal": s["normal"],
                     "marks": s["marks"]})
    with open(d / "manifest.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_stats(args):
    out = Path(args.out)
    stats = {}
    for split in SPLITS:
        d = out / split
        if not (d / "manifest.jsonl").exists():
            continue
        c = defaultdict(Counter)
        n = 0
        for l in open(d / "manifest.jsonl", encoding="utf-8"):
            m = json.loads(l)
            g = json.loads((d / "gt" / f"{m['image_id']}.json").read_text(encoding="utf-8"))
            n += 1
            c["template"][g["style"]] += 1
            c["theme"]["dark" if g["dark"] else "light"] += 1
            c["condition"][g["variant"]] += 1
            c["marks"]["+".join(g["marks"]) or "none"] += 1
            c["scenario"][g["scenario"]] += 1
            c["kind"]["normal" if g["normal"] else "scam"] += 1
            k = sum(len(v) for v in g["strings"].values())
            c["images"]["no_strings" if k == 0 else "with_strings"] += 1
            for t in TYPES:
                c["strings"][t] += len(g["strings"][t])
                c["images_with_type"][t] += bool(g["strings"][t])
            for dd in g["distractors"]:
                c["distractors"][dd["type"]] += 1
            c["ignored"]["strings"] += len(g["ignore"]["strings"])
            c["ignored"]["messages"] += len(g["ignore"]["messages"])
            c["messages"]["total"] += len(g["messages"])
            c["messages"]["max_per_image"] = max(c["messages"]["max_per_image"], len(g["messages"]))
            c["receipt_or_wrap"]["wrapped_links"] += sum(len(x["boxes"]) > 1 and len({round(b[1]) for b in x["boxes"]}) > 1
                                                         for x in g["strings"]["link"])
        s = {k: dict(sorted(v.items())) for k, v in c.items()}
        s["n_images"] = n
        s["no_string_share"] = round(c["images"]["no_strings"] / n, 3) if n else None
        stats[split] = s
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    for split, s in stats.items():
        print(split, s["n_images"], "no-string share", s["no_string_share"], "strings", s.get("strings"))


def cmd_sheet(args):
    from PIL import Image, ImageDraw, ImageFont
    out = Path(args.out)
    d = out / args.split
    rows = [json.loads(l) for l in open(d / "manifest.jsonl", encoding="utf-8")]
    rng = random.Random(args.seed)
    pick = rng.sample(rows, min(args.n, len(rows)))
    tw, th, cols = 260, 440, 6
    nrows = math.ceil(len(pick) / cols)
    sheet = Image.new("RGB", (cols * tw, nrows * (th + 18)), "#888")
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    for k, r in enumerate(pick):
        im = Image.open(d / r["path"]).convert("RGB")
        im.thumbnail((tw - 6, th - 4))
        x, y = (k % cols) * tw, (k // cols) * (th + 18)
        sheet.paste(im, (x + (tw - im.width) // 2, y + 2))
        dr.text((x + 4, y + th + 2), f"{r['image_id'][-5:]} {r['style']} {r['variant']}", fill="white", font=font)
    dest = Path(args.dest) if args.dest else out / f"contact_{args.split}.jpg"
    sheet.save(dest, quality=88)
    print("wrote", dest, [r["image_id"] for r in pick])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("text")
    t.add_argument("--out", default="data/E4")
    t.add_argument("--seed", type=int, default=20261123)
    t.add_argument("--no-llm", action="store_true", help="use the cached pool only (no Gemini calls)")
    r = sub.add_parser("render")
    r.add_argument("--out", default="data/E4")
    r.add_argument("--split", choices=list(SPLITS), required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--ids", default="")
    r.add_argument("--force", action="store_true")
    s = sub.add_parser("stats")
    s.add_argument("--out", default="data/E4")
    h = sub.add_parser("sheet")
    h.add_argument("--out", default="data/E4")
    h.add_argument("--split", default="train")
    h.add_argument("--n", type=int, default=30)
    h.add_argument("--seed", type=int, default=7)
    h.add_argument("--dest", default="")
    args = ap.parse_args()
    {"text": cmd_text, "render": cmd_render, "stats": cmd_stats, "sheet": cmd_sheet}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
