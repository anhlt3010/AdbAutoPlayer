# Xếp đủ đội hình, setting chờ swipe, log rõ ràng — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Không bấm Chiến Đấu khi đội hình thiếu quân: bù tối đa 5 vòng, vẫn thiếu thì đổi sang đội hình kế tiếp, hết đội hình thì dừng và báo; đưa thời gian chờ tray ngừng trượt vào setting; log rõ hệ, màn, đội hình, tiến độ.

**Architecture:** `DeployMixin._deploy_formation` (`deploy.py`) trả về `DeployResult(count, needed)` thay cho `int` và tự bù các ô chưa đặt được, không xóa sân. `AutoBattleMixin._play_plan_step` (`auto_battle.py`) thấy kết quả thiếu thì nhảy sang bước kế tiếp của plan, hết bước thì log error và dừng. Setting mới nằm trong `AutoBattleSettings`.

**Tech Stack:** Python 3.12, Pydantic, pytest, ruff (`uvx ruff` từ thư mục gốc repo).

**Spec:** `docs/superpowers/specs/2026-11-22-deploy-completeness-design.md`

## Global Constraints

- Số lần bù cố định `_FILL_ATTEMPTS = 5` (hằng số, không phải setting).
- "Số cần" (`needed`) = số placement có `evolution_id`, tối đa `MAX_DEPLOYED` (15). Ô không có tatari không tính là thiếu.
- Quick Deploy không phải phương án thay thế: chỉ đi tiếp các bước còn lại của plan.
- Kết quả `count == 0` vẫn dừng như cũ.
- Setting mới: `tray_settle_poll_seconds`, float, mặc định `0.5`, khoảng `0.1` đến `5`. `_DRAG_SETTLE_SECONDS` giữ nguyên.
- Code Python: ruff line-length 88, docstring Google style cho hàm public, không dùng `time.time`, không số "ma thuật" trong so sánh (dùng hằng số module).
- `Point` luôn bằng nhau trong repo này: test so sánh `(p.x, p.y)`.
- Chỉ chạy các file test liên quan, không chạy cả bộ. Chạy từ `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`.
- Log tiếng Việt cho các dòng mới ở mức info/warning/error, chi tiết từng thẻ giữ ở debug.

## Review Focus

- Bộ đếm "Đã triển khai" không đọc được (`None`): không bù vô hạn, dùng số quân đã đặt thành công. (Task 2)
- Người chơi không có tatari nào của đội hình (`needed == 0`, `count == 0`): vẫn trả về 0 và dừng, không bù. (Task 2)
- Sân đã có nhiều quân hơn `needed` (bộ đếm lớn hơn số cần): tính là đủ. (Task 2)
- Đội hình thiếu rồi nhảy sang đội hình kế: bộ đếm lần đánh (`_plan_fights`) của bước mới bắt đầu từ 0 và bước mới được xếp ngay trong cùng lần gọi, không bấm Chiến Đấu với sân thiếu. (Task 3)
- Đội hình cuối cùng cũng thiếu: dừng bằng log error nêu màn, đội hình và số thiếu, không bấm Chiến Đấu. (Task 3)
- `tray_settle_poll_seconds` ngoài khoảng 0,1 đến 5 bị Pydantic từ chối. (Task 1)

---

### Task 1: Setting `tray_settle_poll_seconds`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/settings.py` (thêm kiểu và field trong `AutoBattleSettings`)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/deploy.py` (`_wait_tray_stable`, bỏ hằng số `_STABLE_POLL_SECONDS`)
- Modify: `src-tauri/settings/ClashOfCritters.toml`
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_auto_battle_settings.py`, `test_deploy.py`

**Interfaces:**
- Produces: `AutoBattleSettings.tray_settle_poll_seconds: float` (mặc định 0.5). `DeployMixin._wait_tray_stable` sleep theo giá trị này qua `self.settings.auto_battle.tray_settle_poll_seconds`.

- [ ] **Step 1: Write the failing tests**

Trong `test_auto_battle_settings.py`: thêm `assert settings.tray_settle_poll_seconds == 0.5` vào `test_defaults`; thêm vào `test_bounds_rejected` hai dòng `AutoBattleSettings(tray_settle_poll_seconds=0.05)` và `AutoBattleSettings(tray_settle_poll_seconds=6)` mỗi dòng trong `pytest.raises(ValidationError)`.

Trong `test_deploy.py`: thêm `test_wait_tray_stable_sleeps_the_configured_interval`. `_DeployBot.settings` hiện raise `NotImplementedError`, nên test gán `bot.settings = SimpleNamespace(auto_battle=SimpleNamespace(tray_settle_poll_seconds=0.2))`. Test cho `get_screenshot` trả hai ảnh đen giống nhau, gọi `bot._wait_tray_stable()` (fixture `bot` đã mock method này, nên tạo bot riêng bằng `object.__new__(_DeployBot)` hoặc dùng `DeployMixin._wait_tray_stable(bot)`), và assert `no_sleep.assert_called_with(0.2)`. Cần đổi `settings` trong `_DeployBot` thành thuộc tính gán được (class attribute `settings = None`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_settings.py src-python/tests/games/clash_of_critters/test_deploy.py -q`
Expected: FAIL (thiếu field `tray_settle_poll_seconds`).

- [ ] **Step 3: Implement**

- `settings.py`: thêm `TrayPollSeconds = Annotated[float, Field(ge=0.1, le=5)]` và field `tray_settle_poll_seconds: TrayPollSeconds = Field(default=0.5, title="Tray Settle Check Interval (seconds)", description="After swiping the tray, how often it is checked for having stopped moving. A slow emulator may need a longer interval.")`.
- `deploy.py`: `_wait_tray_stable` dùng `self.settings.auto_battle.tray_settle_poll_seconds` thay cho `_STABLE_POLL_SECONDS` (xóa hằng số, sửa comment đầu khối cho đúng).
- `ClashOfCritters.toml`: thêm `tray_settle_poll_seconds = 0.5` dưới `keep_formation_after_win`.
- `CLAUDE.md` của game: thêm một câu vào mục "Deploying" nói về setting này và rằng setting mới chỉ hiện sau khi reset hoặc sửa settings profile.

- [ ] **Step 4: Run tests to verify they pass**

Run: lệnh ở Step 2. Expected: PASS (ghi lại số test pass).

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src-python src-tauri/settings docs
git commit -m "feat: make the tray settle check interval a setting"
```

### Task 2: Bù quân cho đủ trong `_deploy_formation`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/deploy.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_deploy.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class DeployResult` với `count: int` (quân trên sân: bộ đếm, hoặc số đã đặt nếu bộ đếm không đọc được), `needed: int`, và property `complete -> bool` (`count >= needed`).
- Produces: `DeployMixin._deploy_formation(self, formation: Formation) -> DeployResult`. Kết quả `DeployResult(0, 0)` khi không đọc được dữ liệu tatari.
- Produces: `DeployMixin._place_wanted(self, wanted: dict[str, FormationUnit]) -> dict[str, FormationUnit]` trả về các thẻ chưa đặt được (không thấy trong tray hoặc kéo hỏng), thay cho số đã đặt.
- Consumes: `_scan_owned`, `_select_element`, `_read_deployed_count`, `plan_deployment` như hiện tại.

- [ ] **Step 1: Write the failing tests** (trong `test_deploy.py`, dùng fixture `bot`)

- `test_complete_formation_reports_complete`: hai thẻ sở hữu đủ, kết quả `DeployResult(2, 2)`, `complete` là True.
- `test_missing_unit_is_filled_in_a_later_round`: `_drag_card` hỏng lần đầu cho một thẻ (sân không tăng), lần sau thành công. Kết quả `complete` và không gọi lại `CLEAR_FIELD_POINT` lần hai.
- `test_gives_up_after_five_fill_rounds`: thẻ luôn hỏng. Kết quả `complete` False, `count < needed`, và số vòng bù bằng `deploy._FILL_ATTEMPTS` (5). Dùng `bot._scan_owned.call_count` hoặc số lần `_select_element` để assert số vòng.
- `test_unowned_units_are_not_needed`: đội hình 3 ô nhưng chỉ sở hữu 2: `needed == 2`, kết quả `complete`, không có vòng bù.
- `test_unreadable_counter_does_not_loop_forever`: `_read_deployed_count` luôn trả `None`, một thẻ không đặt được: kết thúc sau tối đa `_FILL_ATTEMPTS` vòng, `count` bằng số đã đặt.
- `test_nothing_owned_returns_zero`: không sở hữu thẻ nào: `DeployResult(0, 0)`, không có vòng bù.
- `test_count_above_needed_is_complete`: bộ đếm đọc lớn hơn `needed`: `complete` True.
- `test_element_logs` (dùng `caplog`): có dòng log chứa tên hệ và `đủ`/`thiếu`, và dòng tổng `Đã xếp {count}/{needed}`.

Sửa các test hiện có đang so kết quả `int` sang `result.count`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_deploy.py -q`
Expected: FAIL (chưa có `DeployResult`).

- [ ] **Step 3: Implement**

- Thêm `DeployResult` và hằng số `_FILL_ATTEMPTS = 5` trong `deploy.py`.
- `_place_wanted` trả về dict các thẻ chưa đặt (giữ nguyên thứ tự duyệt và việc dò tray về đầu).
- `_deploy_formation`: với mỗi hệ, `owned = self._scan_owned()`, tính plan, rồi log `Hệ {element}: nhận diện {len(owned)} tatari trong tray, đủ {n}/{n} tatari cần` hoặc `thiếu {danh sách evolution_id}` (warning khi thiếu); `needed` cộng số placement có `evolution_id`; `missing[element] = self._place_wanted(wanted)`; log `Hệ {element}: đã xếp x/y`. Sau tất cả hệ: đọc bộ đếm; nếu bộ đếm nhỏ hơn `needed` (hoặc, khi bộ đếm là `None`, số đã đặt nhỏ hơn `needed`) và còn `missing`, lặp tối đa `_FILL_ATTEMPTS` vòng: với mỗi hệ còn thiếu, `_select_element`, `_scan_owned()` (để tray về cuối), `missing[element] = self._place_wanted(missing[element])`, rồi đọc lại bộ đếm; log `Bù quân lần {n}/{_FILL_ATTEMPTS}: còn thiếu {m}`. Kết thúc `_select_element(None)`, log tổng `Đã xếp {count}/{needed} quân` rồi trả `DeployResult`.
- `_scan_owned`: đổi log "Recognized ..." sang mức debug (log theo hệ đã chuyển lên `_deploy_formation`).
- Giữ nguyên nhánh `try: self._get_recognizer()` (trả `DeployResult(0, 0)`), và việc xóa sân + xóa lại một lần.

- [ ] **Step 4: Run tests to verify they pass**

Run: lệnh ở Step 2. Expected: PASS (ghi lại số test pass).

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src-python
git commit -m "feat: fill the missing units of a formation before fighting"
```

### Task 3: Đổi đội hình hoặc dừng khi vẫn thiếu, log tiến độ

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/auto_battle.py` (`_play_plan_step`, import `DeployResult`)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (mục Auto Battle và Deploying)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_auto_battle_flow.py`

**Interfaces:**
- Consumes: `DeployMixin._deploy_formation(formation) -> DeployResult` (Task 2), `StageId`, `Formation.index`, `self._plan_steps`, `self._plan_pos`, `self._plan_fights`.
- Produces: `AutoBattleMixin._deploy_current_step(self, stage: StageId) -> bool` trả về False khi phải dừng (không bấm Chiến Đấu). Triển khai bước hiện tại; nếu thiếu thì tăng `_plan_pos`, đặt `_plan_fights = 1` và triển khai bước kế, cho tới khi đủ hoặc hết bước. Bước `None` (Quick Deploy) không bao giờ xuất hiện sau vị trí 0 nên không cần xử lý.

- [ ] **Step 1: Write the failing tests** (trong `test_auto_battle_flow.py`)

Đổi fixture: `game._deploy_formation = MagicMock(return_value=DeployResult(15, 15))`. Cập nhật `test_nothing_placed_means_no_fight_and_stop` (`return_value = DeployResult(0, 0)`) và `test_a_later_formation_that_places_nothing_stops` (`side_effect = [DeployResult(15, 15), DeployResult(0, 0)]`). Test mới (dùng `a_formation`, `_visit`, `_formation` đã có):

- `test_an_incomplete_formation_moves_on_to_the_next_one`: hai đội hình, lần đầu trả `DeployResult(10, 15)`, lần hai `DeployResult(15, 15)`. Sau một lần gọi `_auto_battle_step` trên màn chuẩn bị: `_deploy_formation.call_count == 2`, đối số lần hai là `_formation(1)`, và đúng một lần bấm `FIGHT_BUTTON`.
- `test_incomplete_formation_never_presses_fight_when_none_is_left`: một đội hình, trả `DeployResult(10, 15)`: `_auto_battle_step()` là False, `_tapped(bot) == []`, và `caplog` có dòng error chứa số stage, `1`, và `5` (số thiếu).
- `test_the_next_formation_starts_with_a_fresh_fight_count`: sau khi chuyển đội hình do thiếu, tổng số lần bấm Chiến Đấu cho đội hình mới đúng bằng `MAX_ATTEMPTS` trước khi sang bước tiếp.
- `test_progress_is_logged` (`caplog`): có dòng chứa stage, `đội hình 1/2` và `lần đánh 1/`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_flow.py -q`
Expected: FAIL (chưa nhảy bước, chưa log).

- [ ] **Step 3: Implement**

- `_play_plan_step`: khối `if not retry or not self._field_has_units():` gọi `self._deploy_current_step(stage)`, trả False nếu hàm đó False (giữ nhánh cũ: kết quả `count == 0` log `No tatari could be deployed, stopping.` rồi dừng).
- `_deploy_current_step`: log `Stage {stage}: đội hình {step.index + 1}/{số đội hình trong plan}, lần đánh {self._plan_fights}/{max_formation_attempts}` trước khi triển khai. Nếu `result.count == 0` dừng. Nếu `not result.complete`: log warning `Stage {stage}: đội hình {i} chỉ có {count}/{needed} quân, đổi đội hình khác`, rồi chuyển bước. Khi hết bước: log error `Stage {stage}: không đội hình nào xếp đủ quân (đội hình {i}: {count}/{needed}), dừng.` và trả False.
- Cập nhật `CLAUDE.md` của game (mục Auto Battle và Deploying): thiếu quân thì bù tối đa 5 vòng, không đủ thì đổi bước, hết bước thì dừng.

- [ ] **Step 4: Run tests to verify they pass**

Run: lệnh ở Step 2, cộng `test_deploy.py` và `test_auto_battle_settings.py`.
Expected: PASS. Báo số test pass của từng file.

- [ ] **Step 5: Lint and commit**

Từ thư mục gốc repo: `uvx ruff check --fix` và `uvx ruff format`. Expected: không còn lỗi.

```bash
git add src-tauri/src-python docs
git commit -m "feat: switch to the next formation when one cannot be filled"
```
