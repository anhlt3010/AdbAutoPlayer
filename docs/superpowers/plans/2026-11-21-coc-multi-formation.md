# Clash of Critters: nhiều đội hình mỗi stage - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto battle đọc cấu trúc `formations: [...]` mới và thử lần lượt từng đội hình của stage; retry cùng đội hình không xếp lại.

**Architecture:** `formation.py` trả về danh sách đội hình của stage. `AutoBattleMixin` giữ một "kế hoạch" cho stage hiện tại (danh sách bước: Quick Deploy, rồi từng đội hình), một con trỏ bước và số trận đã đánh ở bước đó. Mỗi lần vào màn chuẩn bị tính là một trận. Đủ N trận thì sang bước kế, hết bước thì dừng. Cùng bước thì chỉ bấm Chiến Đấu.

**Tech Stack:** Python 3.12, pytest, ruff (xem `CLAUDE.md` gốc: chạy `uvx ruff` từ repo root, chỉ chạy các file test liên quan).

**Spec:** `docs/superpowers/specs/2026-11-21-coc-multi-formation-design.md`

## Global Constraints

- Code ở `src-tauri/src-python/adb_auto_player/games/clash_of_critters/`; test ở `src-tauri/src-python/tests/games/clash_of_critters/`.
- Chạy test từ `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`. Không chạy cả bộ test.
- Ruff: `uvx ruff check --fix` và `uvx ruff format` từ repo root. `PLR2004`: không dùng số thô trong so sánh.
- Không dùng `time.time`. Type hint kiểu mới (`X | None`, `list[str]`).
- `Point` bằng nhau luôn đúng trong repo này: so sánh `(p.x, p.y)`.
- Quick Deploy là bước đầu của stage thường (quyết định của người dùng); boss vào thẳng đội hình 1.
- `max_formation_attempts` = số trận tối đa của MỖI bước. Không đổi tên setting.
- Commit message kết thúc bằng `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

- Một đội hình trong file hỏng, các đội hình còn lại vẫn phải dùng được (Task 1).
- Cùng stage xuất hiện lại sau khi thắng (chạy lặp) phải bắt đầu kế hoạch mới, không dùng bộ đếm cũ (Task 2).
- Retry cùng đội hình nhưng sân đã trống (bộ đếm "Đã triển khai" = 0) phải xếp lại thay vì đánh sân trống (Task 2).
- Xếp đội hình thứ 2 trở đi trả về 0 thì dừng, không lặp vô hạn (Task 2).
- Một lần vào màn chuẩn bị đọc stage ra `None` không được xóa kế hoạch của stage đang đánh (Task 2).

---

### Task 1: Đọc danh sách đội hình

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation.py`
- Modify: `src-tauri/src-python/tests/games/clash_of_critters/test_formation_load.py`

**Interfaces:**
- Produces:
  - `Formation(stage: StageId, units: tuple[FormationUnit, ...], index: int = 0, level: int | None = None)` (frozen dataclass; hai field mới có mặc định nên mọi chỗ gọi `Formation(stage, units)` hiện có vẫn đúng).
  - `load_formations(root: Path, stage: StageId) -> tuple[Formation, ...]`; trả `()` khi không có file, file hỏng, hoặc không có đội hình dùng được. `Formation.stage` luôn là stage được yêu cầu (kể cả khi đi qua `shared_with`); `index` là vị trí 0-based trong tuple trả về.
  - `load_formation` bị xóa (chỉ `auto_battle.py` dùng, sẽ sửa ở Task 2).

- [ ] **Step 1: Viết lại `test_formation_load.py` cho cấu trúc mới**

Đổi helper `_write(root, stage, shared_with, formations: list[list[dict]])` ghi `{"chapter", "stage", "shared_with", "formations": [{"source": "x", "level": 100 + i, "units": units} ...]}`. Các test (tên và khẳng định):
  - `test_loads_every_formation_in_order`: file có 2 đội hình → tuple dài 2, `[f.index for f in result] == [0, 1]`, `result[0].level == 100`, `result[1].units[0] == FormationUnit(1, 1, "grass-4", "grass-4-2", 2, False)`, `result[0].stage == StageId(15, 1)`.
  - `test_missing_file_returns_empty`: `load_formations(tmp_path, StageId(4, 2)) == ()`.
  - `test_shared_with_other_stage_loads_that_file`: 15-2 có `formations: []` và `shared_with: "15-1"` → trả đội hình của 15-1 nhưng `stage == StageId(15, 2)`.
  - `test_shared_with_self_uses_own_formations`, `test_shared_with_missing_file_returns_empty`, `test_shared_with_loop_returns_empty` (chuyển từ test cũ).
  - `test_shared_with_is_ignored_when_the_stage_has_its_own_formations`: 15-2 có đội hình riêng và `shared_with: "15-1"` → trả đội hình của 15-2.
  - `test_a_malformed_formation_is_skipped_and_the_others_are_kept`: đội hình 0 có unit `{"row": 1, "col": 1}` (thiếu khóa), đội hình 1 hợp lệ → tuple dài 1 và `result[0].index == 0`.
  - parametrize cũ (`row` thiếu, `"x"`, ngoài sân 5x5, `"not a unit"`) trên MỘT đội hình duy nhất → `()`.
  - `test_a_formation_without_units_is_skipped`.
  - `test_a_file_that_is_not_an_object_returns_empty` (chuyển từ test cũ).
  - `test_real_data_has_stages_with_several_formations` (skipif thiếu `REAL_ROOT`): duyệt `REAL_ROOT/*/*.json`, tìm file đầu tiên có `len(formations) >= 2`, parse tên stage từ `stage` bằng `parse_stage`, khẳng định `len(load_formations(REAL_ROOT, stage)) >= 2` và mọi unit nằm trong 1..5.
  - `test_real_boss_file_loads`: giữ, đổi sang `load_formations(REAL_ROOT, StageId(15, 50))` không rỗng.

- [ ] **Step 2: Chạy test, thấy lỗi**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_formation_load.py -q` (từ `src-tauri/`)
Expected: FAIL (ImportError `load_formations`).

- [ ] **Step 3: Cài đặt trong `formation.py`**

Thêm `index`, `level` vào `Formation`. Thay `load_formation` bằng `load_formations(root, stage) -> tuple[Formation, ...]`: vòng lặp theo `shared_with` giữ nguyên (`_MAX_SHARE_HOPS`); ở mỗi file đọc `data.get("formations") or []`; nếu rỗng thì theo `shared_with` như cũ; nếu không rỗng thì parse từng phần tử bằng `_parse_unit`, đội hình lỗi (`KeyError, TypeError, ValueError, AttributeError`) hoặc không có unit thì bỏ qua và `logging.warning`, rồi trả về các đội hình còn lại (có thể là `()`, không theo `shared_with` nữa). `level` lấy từ `raw.get("level")` nếu là `int`, ngược lại `None`.

- [ ] **Step 4: Chạy test, thấy pass**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_formation_load.py -q`
Expected: tất cả pass.

- [ ] **Step 5: Ruff và commit**

Run từ repo root: `uvx ruff check --fix` và `uvx ruff format` trên `formation.py` và `test_formation_load.py`.
`auto_battle.py` còn import `load_formation` nên chưa chạy được; Task 2 sửa ngay sau đó, vì vậy commit chung ở cuối Task 2.

---

### Task 2: Kế hoạch bước trong auto battle

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/auto_battle.py`
- Modify: `src-tauri/src-python/tests/games/clash_of_critters/test_auto_battle_flow.py`

**Interfaces:**
- Consumes: `load_formations(root, stage) -> tuple[Formation, ...]`, `Formation` từ Task 1; `self._deploy_formation(formation) -> int`, `self._read_deployed_count()`, `self._field_has_units()` (đã có).
- Produces (nội bộ `AutoBattleMixin`):
  - `_plan_stage: StageId | None`, `_plan_steps: list[Formation | None]` (phần tử `None` = Quick Deploy), `_plan_pos: int`, `_plan_fights: int`.
  - `_plan_for(stage: StageId) -> None`: dựng kế hoạch khi `stage != self._plan_stage`: thường `[None, *formations]`, boss `[*formations]` hoặc `[None]` nếu không có đội hình.
  - Bỏ `_quick_deploy_stages`, `_formation_attempts`, `_formation_stage`, `_quick_deploy_pressed`, `_deploy_and_fight`. `_count_lost_visit` chỉ còn dùng cho stage đọc không ra (`stage is None`), đổi bộ đếm thành `_unreadable_losses: int` (xóa `_loss_stage`), reset về 0 mỗi khi đọc được stage.

- [ ] **Step 1: Sửa fixture và viết test mới trong `test_auto_battle_flow.py`**

Fixture `a_formation`: patch `auto_battle.load_formations` với `return_value=(formation,)` (đổi tên biến patch cho rõ; test nào set `a_formation.return_value = None` đổi thành `()`). Thêm helper `_formation(index: int) -> Formation` tạo đội hình khác nhau (khác `evolution_id`). Thêm các test, mỗi test dùng các helper `_show`, `_tapped`, `_boss_visit`/`_lost_visit` hiện có:
  - `test_a_retry_of_the_same_formation_does_not_deploy_again`: boss, 1 đội hình, `MAX_ATTEMPTS = 2`: hai lần vào màn chuẩn bị (kèm `PREP_REPORT_ICON` ở lần 2) → `_deploy_formation.call_count == 1` và `_tapped` có `FIGHT_BUTTON` hai lần.
  - `test_the_next_formation_is_deployed_after_the_attempts_are_used`: boss, `load_formations` trả `(_formation(0), _formation(1))`; 2 visit thua rồi visit thứ 3 → `call_count == 2` và lần gọi thứ hai nhận `_formation(1)`.
  - `test_all_formations_used_up_stops`: 2 đội hình × 2 trận = 4 visit trả `True`, visit thứ 5 trả `False`; `call_count == 2`.
  - `test_a_normal_stage_plays_quick_deploy_then_the_formations`: stage thường, 1 đội hình: visit 1 chạm `QUICK_DEPLOY_BUTTON`; visit 2 chỉ chạm `FIGHT_BUTTON` (không Quick Deploy lại, không deploy); visit 3 gọi `_deploy_formation` một lần; visit 4 không gọi thêm.
  - `test_a_retry_with_an_empty_field_deploys_again` (Review Focus): boss, `_read_deployed_count.return_value = 0` ở visit 2 → `call_count == 2`.
  - `test_a_later_formation_that_places_nothing_stops` (Review Focus): `_deploy_formation.side_effect = [15, 0]`, 2 đội hình, đến lúc deploy lần 2 → `_auto_battle_step()` trả `False` và không chạm Chiến Đấu.
  - `test_a_win_clears_the_plan_of_the_stage` (Review Focus): boss thua 1 lần (fights=1), thắng (`VICTORY_TITLE`), rồi cùng boss vào lại → `_deploy_formation.call_count == 2`.
  - `test_an_unreadable_visit_keeps_the_plan_of_the_stage` (Review Focus): boss visit 1, rồi `_read_stage` trả `None` ở visit 2 (Quick Deploy), rồi boss lại ở visit 3 → visit 3 không gọi `_deploy_formation` thêm (visit 2 không tính vào kế hoạch, nên visit 3 là trận thứ 2 của đội hình 1 và chỉ bấm Chiến Đấu).
  - Sửa các test cũ bị ảnh hưởng: `test_the_formation_is_used_once_quick_deploy_was_pressed_for_the_stage` (Quick Deploy đánh `MAX_ATTEMPTS` trận trước khi đội hình xuất hiện), `test_formation_attempts_are_capped` (1 đội hình: visit `MAX_ATTEMPTS` đầu `True`, visit kế `False`, `call_count == 1`), `test_attempts_start_again_on_a_new_stage` (kỳ vọng `call_count == 2`). Các test còn lại phải pass nguyên văn.

- [ ] **Step 2: Chạy test, thấy lỗi**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_flow.py -q`
Expected: FAIL (patch `load_formations` không tồn tại trong `auto_battle`).

- [ ] **Step 3: Cài đặt trong `auto_battle.py`**

Import `load_formations` thay `load_formation`. `_run_auto_battle` khởi tạo bốn biến kế hoạch và `_unreadable_losses`. `_prepare_and_fight(quick_deploy_button)`, giữ nguyên guard `_prep_phase is not None` và nhánh `_keep_formation()` (không tính vào kế hoạch), rồi:
  - `stage is None`: dùng `_count_lost_visit(None, lost_before)`; quá giới hạn thì `False`; còn lại `_quick_deploy(button)` (không đụng kế hoạch). `stage` đọc được thì `_unreadable_losses = 0`.
  - `stage` đọc được: `_plan_for(stage)`; nếu `_plan_fights >= max_formation_attempts` thì `_plan_pos += 1`, `_plan_fights = 0`; nếu `_plan_pos >= len(_plan_steps)` thì log warning "mọi đội hình của stage đã thua" và trả `False`.
  - Bước hiện tại là `None`: trận mới (`_plan_fights == 0`) → `_quick_deploy(button)` (bấm Quick Deploy, `_prep_phase = _PHASE_QUICK`); retry → `_prep_phase = _PHASE_QUICK`, `_formation_in_use = False`, `_tap_fight()`.
  - Bước là `Formation`: trận mới, hoặc retry mà `not self._field_has_units()` → `_deploy_formation(formation) == 0` thì log và trả `False`; rồi `_prep_phase = _PHASE_FORMATION`, `_formation_in_use = True`, `_tap_fight()`.
  - Mọi nhánh đến được trận thì `_plan_fights += 1`.
  - `VICTORY_TITLE` đặt `_plan_stage = None`.
  - Sửa docstring đầu module cho đúng cách chạy mới. `_quick_deploy` bỏ tham số `stage` và việc ghi `_quick_deploy_stages`.

- [ ] **Step 4: Chạy test, thấy pass**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_flow.py src-python/tests/games/clash_of_critters/test_formation_load.py src-python/tests/games/clash_of_critters/test_deploy.py src-python/tests/games/clash_of_critters/test_deployment_plan.py -q`
Expected: tất cả pass (ghi lại số lượng pass).

- [ ] **Step 5: Ruff và commit**

Run từ repo root: `uvx ruff check --fix` và `uvx ruff format`.
Commit gồm `formation.py`, `auto_battle.py`, hai file test, spec và plan:

```bash
git add src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation.py src-tauri/src-python/adb_auto_player/games/clash_of_critters/auto_battle.py src-tauri/src-python/tests/games/clash_of_critters/test_formation_load.py src-tauri/src-python/tests/games/clash_of_critters/test_auto_battle_flow.py docs/superpowers/specs/2026-11-21-coc-multi-formation-design.md docs/superpowers/plans/2026-11-21-coc-multi-formation.md
git commit -m "feat: play every prepared formation of a stage in turn, retrying without redeploying"
```

---

### Task 3: Setting và tài liệu

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/settings.py` (mô tả `max_formation_attempts`, dòng 37-44)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (mục Auto Battle)

**Interfaces:** không đổi giao diện.

- [ ] **Step 1: Cập nhật mô tả setting**

Đổi `title` thành "Max Fights Per Formation" (không đổi alias hay tên field) và `description` nói: số trận tối đa cho Quick Deploy và cho mỗi đội hình có sẵn của một stage trước khi chuyển sang đội hình kế; hết đội hình thì dừng. Kiểm tra `test_auto_battle_settings.py` vẫn pass (nó chỉ đọc giá trị và giới hạn).

- [ ] **Step 2: Cập nhật `CLAUDE.md` của game**

Viết lại các gạch đầu dòng "Preparation screen" và `auto_battle.max_formation_attempts` theo cơ chế mới: kế hoạch bước theo stage, Quick Deploy là bước đầu của stage thường, boss vào đội hình 1, retry cùng bước chỉ bấm Chiến Đấu (đội hình xếp lại nếu bộ đếm = 0), trận giữ sân không tính vào kế hoạch, thắng thì xóa kế hoạch. Cập nhật mô tả dữ liệu: `formations[]` với `source`, `level`, `units`, `load_formations` theo `shared_with` chỉ khi `formations` rỗng. Tuân thủ quy tắc Markdown của `CLAUDE.md` gốc (code fence có ngôn ngữ, dòng trống quanh heading và list).

- [ ] **Step 3: Chạy test liên quan và commit**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_settings.py src-python/tests/games/clash_of_critters/test_auto_battle_flow.py -q`
Expected: pass.

```bash
git add src-tauri/src-python/adb_auto_player/games/clash_of_critters/settings.py src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md
git commit -m "docs: describe the per-formation fight limit and the multi-formation flow"
```
