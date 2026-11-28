# quick_formation – xếp đội hình tức thì cho Clash of Critters

Module Python thuần (chỉ dùng thư viện chuẩn) để thay thế phần xếp đội hình bằng kéo thả
trong `adb_auto_player/games/clash_of_critters/deploy.py`. Một lần bấm nút
"Triển Khai Nhanh" của game là cả đội hình (tối đa 15 Tatari) ra sân ngay, thay vì kéo
từng con (~1,6 giây mỗi con).

## Nó hoạt động thế nào

Màn chuẩn bị trận của game viết bằng Lua. Khi bạn bấm "Triển Khai Nhanh", game gọi hàm
`AutoLineup` của `Src.UI.Battle.View.StageBattlePrepareView`. Module này:

1. dùng root (`su`) để đọc bộ nhớ tiến trình game qua `/proc/<pid>/mem`, tìm hàm `AutoLineup`
   (địa chỉ Lua state được suy ra từ export `igame_getLuaState` của game, không ghi cứng offset);
2. ghi đè **bytecode của hàm đó trong RAM** thành: xóa sân, rồi với mỗi Tatari của bạn có
   `tid` nằm trong đội hình thì gọi `self:AddUnitToGrid(pet, x, y, true, false)` (đúng lời gọi
   mà game dùng cho từng con khi tự xếp);
3. bấm nút "Triển Khai Nhanh" (callback do bạn cung cấp);
4. đọc bộ đếm "Đã triển khai: n/15" để xác nhận (callback do bạn cung cấp);
5. trả lại bytecode gốc, nên nút thật của game vẫn hoạt động như bình thường.

Không sửa file game, không gắn debugger, không chèn thư viện. Thay đổi chỉ nằm trong RAM và
mất khi game khởi động lại.

## Yêu cầu và giới hạn

* MuMu (hoặc giả lập) **đã bật root**, lệnh `su -c "..."` chạy được. Nếu root dùng cú pháp khác,
  truyền `su="su 0 sh -c"` (hoặc tương tự) cho `QuickDeployer`.
* Đã kiểm chứng với game **0.51.1** (gói `com.farlightgames.pgame.gp.vn`) trên **màn chuẩn bị
  trận thường** (sân 5x5). Hàm `AutoLineup` được kiểm tra hằng số trước khi ghi; nếu game cập
  nhật làm cấu trúc đổi, module ném `UnsupportedBuild` và **không ghi gì**.
* **Võ Đường (sân 3x4, tối đa 5 quân) chưa được kiểm chứng**: `deploy(..., layout="dojo")` ném
  `UnsupportedLayout`. Với màn đó hãy giữ nguyên code kéo thả cũ (xem bảng việc còn lại ở
  `research/TODO.md`).
* Module không biết bạn có sở hữu loài nào. Loài chưa sở hữu bị bỏ qua và bộ đếm sẽ thấp hơn
  `needed`; khi đó `result.complete` là `False` như code cũ.
* Cú bấm nút phải rơi đúng màn chuẩn bị trận. Nếu game không ở màn đó, bộ đếm không đọc được và
  `result.verified` là `False`.

## Cài vào AdbAutoPlayer

Chép nguyên thư mục `quick_formation/` (không cần thư mục `tests/`) vào:

```
adb_auto_player/games/clash_of_critters/quick_formation/
```

Module dùng import tương đối nên chạy được như một gói con. Gói con này không phụ thuộc
`adb_auto_player`, nên cũng chạy độc lập bằng `python -m quick_formation` (xem bên dưới).

### Sửa `deploy.py` (thay thế xử lý xếp đội hình cũ)

Đổi tên hàm cũ để làm đường dự phòng, rồi thêm hàm mới. Đoạn dưới đây là toàn bộ thay đổi:

```python
# --- phần import ---
from adb_auto_player.games.clash_of_critters.quick_formation import (
    QuickDeployError,
    QuickDeployer,
)


class DeployMixin(Game):
    ...
    _quick_deployer: QuickDeployer | None = None

    def _get_quick_deployer(self) -> QuickDeployer:
        if self._quick_deployer is None:
            self._quick_deployer = QuickDeployer(
                shell=lambda cmd: self.device.d.shell(cmd, encoding=None),
                # "Triển Khai Nhanh" (390, 1800) trên màn 1080x1920
                press_quick_deploy=lambda: self.tap(
                    self._apply_vertical_offset(Point(390, 1800)), log=False
                ),
                read_deployed_count=self._read_deployed_count,  # OCR "Đã triển khai: n/15"
                state_dir=SettingsLoader.get_app_config_dir(),
            )
        return self._quick_deployer

    # Hàm cũ, đổi tên (giữ nguyên thân hàm): vẫn dùng cho Võ Đường và khi quick deploy không dùng được.
    def _deploy_formation_by_drag(
        self, formation: Formation
    ) -> DeployResult: ...  # toàn bộ code _deploy_formation hiện tại

    def _deploy_formation(self, formation: Formation) -> DeployResult:
        """Xếp đội hình tức thì; rơi về kéo thả nếu không dùng được."""
        if self._layout is BATTLE_LAYOUT:
            try:
                result = self._get_quick_deployer().deploy(formation.units)
                if result.verified:
                    return DeployResult(result.count, result.needed)
                logging.warning(
                    "Quick deploy chưa xác nhận được bộ đếm, xếp lại bằng kéo thả."
                )
            except QuickDeployError as error:
                logging.warning(
                    f"Quick deploy không dùng được ({error}), xếp bằng kéo thả."
                )
        return self._deploy_formation_by_drag(formation)
```

Ghi chú:

* `auto_battle._deploy_current_step` không cần sửa: nó chỉ dùng `result.blocked`, `result.count`,
  `result.complete`, `result.needed`, và `DeployResult` giữ nguyên các trường đó.
* `_deploy_formation_by_drag` bắt đầu bằng việc nhấn nút xóa sân rồi quét khay thẻ. Khi quick deploy
  thành công, các bước quét khay, nhận diện thẻ và "dạy thẻ" **không còn được gọi** cho màn thường.
  Chúng vẫn cần cho Võ Đường và cho đường dự phòng, nên đừng xóa.
* Sau mỗi lần deploy, module trả lại hàm gốc, vì vậy `_quick_deploy(...)` (bấm nút thật khi không có
  đội hình) vẫn dùng thuật toán xếp của game.
* Lần đầu sau khi game mở, module mất ~20 giây để tìm hàm trong bộ nhớ; các lần sau ~2 giây (địa chỉ
  được nhớ theo pid trong `state_dir/quick_formation_state.json`).

## Ánh xạ Tatari của đội hình → loài trong game

File đội hình ghi loài là `"<hệ>-<n>"` (ví dụ `rock-5`). Trong game, đó là **loài thứ n của hệ đó
theo `tid` tăng dần** (mỗi hệ 14 loài). Bảng nằm ở `data/tatari_to_tid.json` (đã kiểm chứng trên cả
70 loài bằng hệ `UnitElement` và tên loài trong game: `rock-5` ↔ `tid 24` Monkey, `fire-9` ↔ `tid 42`
FireTiger...).

* `tid` **không đổi khi Tatari tiến hóa**; game luôn đặt con đó ra sân ở dạng hiện tại, nên không cần
  ảnh hay tier. Phần `evolution_id`/`tier` của file đội hình bị bỏ qua.
* **Sửa tay**: tạo `data/tatari_to_tid.override.json`, ví dụ `{"fire-9": 42}`. File này được ưu tiên
  hơn bảng mặc định và được đọc lại mỗi khi tạo `TatariMap()`. Từ code:
  `deployer.mapping.set_override("fire-9", 42)`.
* **Sau khi game thêm loài mới** quy luật thứ tự có thể lệch. Dữ liệu để dựng lại là
  `{tid: UnitElement}` đọc từ `petConfig` của từng Tatari; gọi
  `mapping.rebuild_mapping(species)` để ghi lại bảng. (Công cụ đọc dữ liệu đó nằm ở
  `research/petcfg.py`, không thuộc gói này.)

## Thử bằng dòng lệnh (không cần AdbAutoPlayer)

Chạy từ thư mục chứa `quick_formation/`, game đang mở **đúng màn chuẩn bị trận**:

```
python -m quick_formation status --adb "C:\...\adb.exe"
python -m quick_formation apply tatari_formations\22\22-30.json --index 0 --adb "C:\...\adb.exe"
python -m quick_formation restore --adb "C:\...\adb.exe"
```

`status` chỉ kiểm tra hàm gốc, không bấm gì. `apply` in `deployed n/15` chỉ khi đọc được bộ đếm;
dòng lệnh không có OCR nên sẽ in "not verified: look at the screen".

## Kiểm thử

```
python -m unittest discover -s quick_formation/tests -t .
```

Các bài kiểm thử chạy offline (thiết bị giả), kiểm tra: tọa độ ô (`x = col`, `y = 6 - row`), bảng
ánh xạ và file ghi đè, các bước nhảy của bytecode, đọc/ghi bộ nhớ theo lô.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| `GameNotRunning` | Game chưa chạy. |
| `RootUnavailable` | `su` không có hoặc cú pháp khác: chỉnh tham số `su=`. |
| `UnsupportedBuild` | Game đã cập nhật, cấu trúc hàm đổi: quay về kéo thả, cần kiểm chứng lại bản mới. |
| `UnsupportedLayout` | Không phải màn thường (ví dụ Võ Đường). |
| `UnknownTatari` | Loài chưa có trong bảng: thêm vào file ghi đè. |
| Kết quả `verified=False` | Game không ở màn chuẩn bị trận hoặc OCR không đọc được bộ đếm. |
| Nút thật của game xếp lạ | Bản vá chưa được trả lại (ví dụ chương trình dừng giữa chừng): chạy `restore` hoặc khởi động lại game. |

## Rủi ro cần biết

Module sửa mã Lua của game đang chạy trên máy của bạn (chỉ trong RAM, chỉ ở màn xếp đội hình trước
trận). Việc can thiệp client của một game online có thể trái điều khoản dịch vụ của nhà phát hành;
dùng với tài khoản của bạn và tự cân nhắc rủi ro.
