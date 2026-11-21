# Clash of Critters: nhiều đội hình mỗi stage (thiết kế ngắn)

## Ý định

Dữ liệu `tatari_formations/<chapter>/<stage>.json` đổi sang `formations: [{source, level, units}, ...]` (97 stage có 2+ đội hình, tối đa 11). Auto battle phải thử lần lượt từng đội hình, retry cùng đội hình mà không xếp lại, chỉ xếp lại khi đổi sang đội hình mới.

## Mục tiêu

- Đọc cấu trúc mới (vẫn theo `shared_with`).
- Mỗi stage có một "kế hoạch" gồm các bước theo thứ tự; mỗi bước đánh tối đa N trận (N = `auto_battle.max_formation_attempts`).
- Retry cùng bước: chỉ bấm Chiến Đấu, không xếp lại.
- Hết bước cuối mà vẫn thua: dừng auto battle (như hiện tại).

## Không làm

- Không đổi cách chọn evolution, kéo thả, nhận diện thẻ (`deploy.py`, `deployment_plan.py`).
- Không đổi `keep_formation_after_win`.
- Không đổi tên setting (chỉ đổi nghĩa: số trận tối đa cho mỗi bước thay vì mỗi stage).

## Cách tiếp cận

Chỉ có một hướng hợp lý: thêm trạng thái "bước hiện tại của stage" vào `AutoBattleMixin`, thay cho ba bộ đếm rời nhau (`_quick_deploy_stages`, `_formation_attempts`, `_count_lost_visit`). Sửa riêng từng bộ đếm không đủ, vì cả ba cùng phải biết "đang ở bước nào" mới tránh được xếp lại khi retry.

## Thiết kế

- `formation.py`: `load_formations(root, stage) -> tuple[Formation, ...]`. Mỗi `Formation` có `stage`, `index`, `level`, `units`. Đội hình hỏng thì bỏ qua và ghi warning, các đội hình còn lại vẫn dùng. `shared_with` chỉ được theo khi `formations` rỗng.
- Kế hoạch của stage (lập khi đọc được stage trên màn chuẩn bị, dựng lại khi sang stage khác):
  - Stage thường: `[Quick Deploy, F1, F2, ...]`. Quyết định của người dùng: giữ Quick Deploy làm lượt đầu, đánh tối đa N trận.
  - Boss: `[F1, F2, ...]`.
  - Không có file đội hình: chỉ `[Quick Deploy]`.
  - Stage đọc không ra: Quick Deploy mỗi lần như hiện nay, dừng khi thua quá N lần.
- Trên màn chuẩn bị: nếu bước hiện tại đã đủ N trận thì sang bước kế (hết bước thì dừng). Bước mới: Quick Deploy hoặc xếp đội hình, rồi bấm Chiến Đấu. Cùng bước (retry): chỉ bấm Chiến Đấu. Với bước đội hình, đọc bộ đếm "Đã triển khai: n/15"; nếu sân trống (n = 0) thì xếp lại như lưới an toàn.
- Một trận được tính khi bấm Chiến Đấu trong lần vào màn chuẩn bị mới. Guard `_prep_phase` giữ nguyên.
- Thắng một stage thì xóa kế hoạch của stage đó.

## Việc để người làm quyết định (lựa chọn của tôi)

- Trận đánh bằng sân giữ lại (`keep_formation_after_win`) không tính vào kế hoạch. Nếu thua thì kế hoạch bắt đầu từ bước đầu của stage.
- Retry Quick Deploy cũng không bấm lại Quick Deploy. Trước đây Quick Deploy chỉ được đánh 1 trận rồi chuyển sang đội hình, nay là N trận.

## Kiểm thử và tài liệu

- Test cho `load_formations`: cấu trúc mới, `shared_with`, đội hình hỏng.
- Test cho auto battle: retry cùng đội hình không gọi deploy, đổi đội hình thì gọi deploy, hết đội hình thì dừng, boss, stage thường có Quick Deploy trước.
- Cập nhật `CLAUDE.md` của game (mục Auto Battle) và mô tả setting `max_formation_attempts`.
