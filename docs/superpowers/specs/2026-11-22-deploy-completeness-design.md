# Xếp đủ đội hình trước khi đánh, setting chờ swipe, log rõ ràng (thiết kế ngắn)

## Mục đích

Hiện tại `_deploy_formation` (`deploy.py`) chỉ báo lỗi khi sân trống hoàn toàn (0 quân). Thiếu quân vẫn bấm Chiến Đấu, làm thua oan và tốn lượt thử của plan. Người dùng muốn: thiếu quân thì bù cho đủ rồi mới đánh; không bù được thì đổi đội hình khác; hết đội hình thì dừng và báo.

## Mục tiêu

- Không bấm Chiến Đấu khi đội hình chưa đủ quân (mà người chơi có tatari để xếp đủ).
- Thời gian chờ sau khi cuộn tray chỉnh được trong setting.
- Log cho biết hệ nào, màn nào, đội hình nào, tiến độ ra sao.

## Không làm

- Không đổi cách nhận diện thẻ, cách tính `plan_deployment`, hay logic plan (`max_formation_attempts`, Quick Deploy, boss).
- Không thêm setting cho số lần bù (cố định 5, hằng số `_FILL_ATTEMPTS`).
- Không đổi frontend (setting mới tự hiện qua Pydantic schema).

## Các cách đã cân nhắc

- **A (đã chọn):** bù đúng các ô còn thiếu ngay trong `_deploy_formation`, không xóa sân, tối đa 5 vòng.
- B: xóa sân và xếp lại từ đầu mỗi lần thiếu. Chậm (quét lại tray từng hệ) và có thể hỏng đúng ô cũ.

## Thiết kế

### 1. Xếp đủ đội hình (`deploy.py`)

- "Số cần" = số placement có `evolution_id` (ô mà người chơi có tatari). Ô không có tatari không tính là thiếu (log warning như hiện nay).
- Sau khi xong các hệ, đọc bộ đếm. Nếu `đếm < số cần`: bù tối đa `_FILL_ATTEMPTS = 5` vòng. Mỗi vòng chỉ xếp lại các ô chưa đặt được (theo dõi qua `_place_card` trả về False hoặc ô không còn trong `_occupied`), rồi đọc lại bộ đếm.
- Bộ đếm không đọc được (None): dùng số quân đã đặt thành công, không bù vô hạn.
- `_deploy_formation` trả về kết quả có phân biệt "đủ" và "thiếu" (ví dụ dataclass `DeployResult(count, needed)`), thay cho `int`.

### 2. Đổi đội hình / dừng (`auto_battle.py`, `_play_plan_step`)

- Kết quả thiếu sau 5 vòng: log warning rồi nhảy sang bước kế tiếp của plan (`_plan_pos += 1`, `_plan_fights = 0`) và xếp bước đó trong cùng lần gọi (lặp lại cho đến khi xếp đủ hoặc hết bước).
- Quick Deploy không phải phương án thay thế; chỉ xét các bước còn lại của plan.
- Hết bước: log error nêu màn, đội hình và số quân thiếu, rồi trả về False (dừng auto battle).
- Kết quả 0 quân vẫn dừng như cũ.

### 3. Setting thời gian chờ

- Thêm vào `AutoBattleSettings`: `tray_settle_poll_seconds` (float, mặc định 0.5, khoảng 0.1 đến 5), thay `_STABLE_POLL_SECONDS` trong `_wait_tray_stable`.
- Giả định cần xác nhận: "thời gian chờ sau swipe" là khoảng này. `_DRAG_SETTLE_SECONDS` (chờ sau kéo thả) giữ nguyên.
- Cập nhật `src-tauri/settings/ClashOfCritters.toml` và CLAUDE.md của game.

### 4. Log

- Sau khi quét tray của mỗi hệ: `Hệ {element}: nhận diện {n} tatari trong tray, đủ {k}/{k} tatari cần` hoặc `thiếu {danh sách}`.
- Bắt đầu mỗi bước: `Stage {stage}: đội hình {i}/{tổng}, lần đánh {j}/{max}`.
- Xếp từng hệ: `Hệ {element}: đã xếp {x}/{y}`.
- Kết thúc xếp: `Đã xếp {count}/{needed} quân (bù lần {n})`.
- Chuyển đội hình và dừng như mục 2.
- Chi tiết từng thẻ giữ ở mức debug.

## Để người xây quyết định

- Tên chính xác của kết quả trả về và cách theo dõi ô chưa đặt.
- Cách `DeployMixin` truy cập `self.settings.auto_battle`.
- Test hồi quy: thiếu quân thì bù, 5 vòng thất bại thì đổi đội hình, hết đội hình thì dừng, setting mới, plan không có tatari thì không bù vô hạn.
