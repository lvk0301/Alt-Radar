# Alt-Radar

Máy quét altcoin trên Binance theo **mô hình nhóm 1**: coin "thức dậy" cùng đợt BTC bứt phá, giữ giá và giữ khối lượng khi BTC nghỉ, rồi bứt phá khi BTC đứng im ở vùng cao.

> Công cụ tham khảo kỹ thuật, **không phải lời khuyên đầu tư**. Các ngưỡng được rút ra từ **một chu kỳ duy nhất** (8–10/2026) và 6 coin — hãy chạy `backtest` trên nhiều năm dữ liệu trước khi tin vào nó.

## Cài đặt và chạy

Chỉ cần Python 3.10+, không cần thư viện ngoài. Máy phải truy cập được `api.binance.com` (hoặc `data-api.binance.vision`).

```bash
python -m altradar scan                       # quét tất cả cặp USDT, xếp hạng coin
python -m altradar scan --all --top 100       # hiện cả coin yếu / bị loại
python -m altradar explain OPUSDT             # giải thích từng điều kiện của 1 coin
python -m altradar --days 1100 backtest       # kiểm tra ngược ~3 năm
python -m altradar --days 1100 backtest --horizon 30 --list
```

Dữ liệu tải về được lưu tạm trong `.cache/` (6 giờ). Nến ngày đang chạy dở bị bỏ qua.

Chạy offline với dữ liệu mẫu (11 coin, 1/8–14/10/2026; giá lấy từ TradingView, khối lượng Binance chỉ có cho BTC, OP, BAT, KMNO, WAL, ZK):

```bash
python -m altradar --data tests/fixtures scan --date 2026-10-08 --all
python -m altradar --data tests/fixtures explain ZKUSDT --date 2026-10-08
python -m unittest discover -s tests
```

## Logic

### Bối cảnh BTC (radar chỉ bật sau khi BTC tăng)

| Khái niệm | Định nghĩa |
|---|---|
| Đợt BTC tăng | BTC tăng ≥ 10% trong ≤ 5 ngày. Đợt đầu tiên trong 90 ngày là "đợt đánh thức". |
| BTC nghỉ | Các ngày nằm ngoài những đợt tăng. |
| Mức nền khối lượng | Trung vị khối lượng (USDT) của coin trong 20 ngày trước đợt đánh thức. |
| Cửa sổ mùa alt | BTC đã nghỉ ≥ 7 ngày, cách đỉnh 90 ngày ≤ 10%, khối lượng BTC 7 ngày < 1x mức nền. |

### Chấm điểm (100 điểm)

| Mã | Điều kiện | Điểm |
|---|---|---|
| A1 | Ở đợt đánh thức, coin tăng ≥ 60% mức tăng của BTC | 10 |
| A2 | Trong đợt đó có ngày khối lượng ≥ 3x nền | 5 |
| R1 | Tổng lợi nhuận trong các ngày BTC nghỉ ≥ của BTC − 5 điểm | 10 |
| R2 | Khối lượng trung bình các ngày BTC nghỉ ≥ 2x nền | 10 |
| L | Ở đợt BTC tăng tiếp theo, coin tăng mạnh hơn BTC | 10 |
| B1 | Biên độ 20 ngày ≤ 40% | 5 |
| B3 | ≥ 4/9 tuần có đáy cao hơn tuần trước | 5 |
| B2 | Đóng cửa trên SMA20 ≥ 20/30 ngày | 5 |
| B4 | Lợi nhuận 30 ngày cao hơn BTC | 5 |
| B5 | Khối lượng trung bình 14 ngày ≥ 2x nền | 7,5 |
| B6 | ≥ 4 ngày nến xanh có khối lượng ≥ 3x nền (trong 30 ngày) | 7,5 |
| B7 | RSI 14 trong khoảng 45–68 | 5 |
| B8 | Giá thấp hơn đỉnh 90 ngày từ 3% đến 25% | 5 |
| C | BTC giảm ≥ 4% trong 10 ngày qua; coin giảm ≤ 3 lần mức đó và giữ đáy nền (5 điểm), đã hồi trên SMA20 (10 điểm) | 10 |

Điều kiện thiếu dữ liệu (chưa có đợt BTC thứ 2, không có khối lượng…) được **bỏ ra khỏi thang điểm** thay vì tính là trượt: điểm = điểm đạt / điểm có thể đạt × 100.

### Loại trừ (nhóm 3, quá nóng, thanh khoản thấp)

- **X1** Giá thấp hơn đỉnh 90 ngày hơn 50% và nằm dưới SMA20.
- **X2** RSI > 80 và cao hơn SMA20 hơn 50% — không mua đuổi.
- **X3** Đã tăng > 100% trong 20 ngày trước khi BTC tăng (pump độc lập).
- **X4** Khối lượng trung bình 7 ngày < $500k.

### Trạng thái

| Trạng thái | Điều kiện |
|---|---|
| **KÍCH HOẠT** | Hôm qua "sẵn sàng", hôm nay đóng cửa vượt đỉnh 20 ngày, tăng ≥ 10%, khối lượng ≥ 4x nền, BTC không giảm > 2%, và không dính loại trừ |
| sẵn sàng | ≥ 70 điểm |
| đang hình thành | 50–69 điểm |
| yếu | < 50 điểm |
| loại trừ | Dính X1–X4 |
| chờ BTC | Chưa có đợt BTC tăng trong 90 ngày |

Mọi ngưỡng nằm trong `altradar/rules.py` (`Config`).

## Kết quả trên dữ liệu mẫu

Ngày 8/10/2026 (một ngày trước đợt bứt phá):

| Coin | Trạng thái | Điểm | Sau đó |
|---|---|---|---|
| BAT | sẵn sàng | 100 | 9/10 KÍCH HOẠT, +32% |
| TRAC | sẵn sàng | 100 | không bứt phá (tín hiệu giả) |
| WAL | sẵn sàng | 95 | 14/10 KÍCH HOẠT, +26% |
| ZK | sẵn sàng | 95 | 9/10 KÍCH HOẠT, +24% |
| OP | sẵn sàng | 85 | 13/10 KÍCH HOẠT, +21% |
| KMNO | sẵn sàng | 80 | đi ngang (đã chạy từ 26/9) |
| ALEO | đang hình thành | 64 | |
| QUAC | yếu | 36 | |
| CASHCAT, AIARTIFI, BTWBI | loại trừ | | |

Đây là kết quả **trong mẫu** (logic được rút ra từ chính dữ liệu này), nên không chứng minh được gì về tương lai. Muốn biết tỷ lệ đúng thật, chạy `backtest` trên nhiều năm.

## Cấu trúc

```
altradar/
  data.py        tải nến ngày từ Binance, đọc/ghi CSV
  indicators.py  SMA, RSI, drawdown, đáy tuần
  phases.py      đợt BTC tăng, ngày BTC nghỉ, cửa sổ mùa alt
  rules.py       chấm điểm và trạng thái
  backtest.py    kiểm tra ngược không nhìn trước tương lai
  cli.py         lệnh scan / explain / backtest
tests/           test + dữ liệu mẫu 8–10/2026
```
