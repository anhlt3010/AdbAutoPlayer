# Card "Xem Đội Hình" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay cửa sổ xem đội hình (cần build app) bằng một card ở category Battle: bấm thì dựng trang HTML có hình các đội hình của màn rồi mở bằng trình duyệt; gỡ nút và mọi xử lý giao diện của cửa sổ cũ.

**Architecture:** Hàm thuần `render_formation_page(response) -> str` (file mới `formation_page.py`) dựng HTML từ `FormationViewResponse` có sẵn. Lệnh `show_formation` trong `main.py` gọi `load_formation_view()` có sẵn, ghi HTML vào thư mục tạm và mở bằng `webbrowser`. Phần giao diện cũ được gỡ bằng revert hai commit và xóa lệnh PyTauri `get_formation_view`.

**Tech Stack:** Python 3.12, Pydantic, pytest, ruff (`uvx ruff` từ thư mục gốc repo), `pnpm check` cho frontend.

**Spec:** `docs/superpowers/specs/2026-11-22-formation-card-design.md`

## Global Constraints

- Chỉ Python được thêm mới: bản patch là đủ, không được sửa Svelte/Rust/capabilities (chỉ gỡ).
- Sau Task 1, các đường dẫn `src/`, `src-tauri/src/`, `src-tauri/capabilities/`, `src-tauri/tauri.conf.json` phải giống hệt tag `coc-vn-v0.3.5`.
- Giữ nguyên `formation_view.py`, `test_formation_view.py` và thay đổi `formation.py` của commit `366fbb1e`.
- Card: label "Xem Đội Hình", category "Battle". Setting mới `formation_view.stage` (chuỗi, mặc định rỗng).
- Không gửi thao tác vào thiết bị (chỉ chụp ảnh khi `stage` rỗng).
- Mọi chuỗi từ dữ liệu đưa vào HTML phải được escape (`html.escape`).
- Code Python: ruff line-length 88, docstring Google style cho hàm public (trừ trong `games/` và `tests/`), không `time.time`, không số "ma thuật" trong so sánh, dùng `X | None`.
- Chạy từ `src-tauri/` và chỉ chạy các file test liên quan: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`.
- Log tiếng Việt cho các dòng mới ở mức info/warning.

## Review Focus

- Tên tatari có ký tự HTML (`<`, `&`, dấu nháy) không phá trang hoặc chèn thẻ. (Task 2)
- Đội hình thiếu sprite cho một tatari (không có trong `sprites`): vẫn hiện ô với tên, không lỗi. (Task 2)
- Ô trống (đội hình ít hơn 25 quân) hiện đúng 25 ô, và đội hình `level=None` không hiện chữ "None". (Task 2)
- Số màn gõ có dấu gạch en ("15–50") vẫn dùng được; số màn sai thì log báo và không mở trình duyệt. (Task 3)
- Setting `stage` chỉ gồm khoảng trắng được coi như rỗng (tự nhận màn từ ảnh), không báo "màn sai". (Task 3)
- Trình duyệt không mở được (`webbrowser.open` trả False hoặc ném lỗi): log đường dẫn file để người dùng tự mở, task không bị lỗi. (Task 3)

---

### Task 1: Gỡ nút xem đội hình và xử lý giao diện

**Files:**
- Revert: commit `8a06fd12` (nút, cửa sổ, route `formation-viewer`, `window.rs`, capabilities, CSP, i18n, tách layout `(app)`) rồi `0b6fe88f` (client TypeScript).
- Modify: `src-tauri/src-python/adb_auto_player/__main__.py` (xóa `FormationViewBody`, `get_formation_view` và import `FormationViewResponse`, `load_formation_view`).
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (bỏ đoạn "Formation viewer" mô tả cửa sổ, nếu xung đột khi revert thì giữ các đoạn Deploying/Auto Battle mới nhất).
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_formation_view.py` (không đổi, phải vẫn pass).

**Interfaces:**
- Produces: `formation_view.load_formation_view` và `FormationViewResponse` vẫn dùng được (Task 3 dùng), không còn lệnh PyTauri `get_formation_view`.

- [ ] **Step 1: Revert the UI commits**

Run: `git revert --no-edit 8a06fd12 0b6fe88f` (từ gốc repo, sạch working tree). Nếu `CLAUDE.md` của game xung đột, giải quyết bằng cách giữ nội dung Deploying/Auto Battle hiện tại và bỏ đoạn "Formation viewer".
Expected: hai commit revert được tạo, không còn xung đột.

- [ ] **Step 2: Remove the PyTauri command in `__main__.py`**

Xóa `FormationViewBody`, `get_formation_view` và hai import liên quan; không đổi gì khác.

- [ ] **Step 3: Verify**

- `git diff coc-vn-v0.3.5 --stat -- src src-tauri/src src-tauri/capabilities src-tauri/tauri.conf.json`
  Expected: không có dòng nào (giống hệt tag).
- Grep `get_formation_view|formation-viewer|openFormationViewer` trong `src`, `src-tauri` (trừ `docs` và `tests`).
  Expected: không có kết quả.
- `pnpm check`
  Expected: không có lỗi mới.
- `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py src-python/tests/games/clash_of_critters/test_formation_load.py -q`
  Expected: PASS (ghi số test pass).

- [ ] **Step 4: Commit**

```bash
git add -u src-tauri src
git commit -m "refactor: remove the formation viewer window and its command"
```

### Task 2: Trang HTML các đội hình

**Files:**
- Create: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation_page.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_formation_page.py`

**Interfaces:**
- Consumes: `formation_view.FormationViewResponse`, `ViewFormation`, `ViewUnit` (`row`, `col` từ 1 đến 5, `evolution_id`, `name`, `tier`, `glitter`), `sprites: dict[str, str]` khóa theo `evolution_id`.
- Produces: `render_formation_page(response: FormationViewResponse) -> str` trả về một tài liệu HTML đầy đủ (tự chứa, không tải gì từ ngoài) với tiêu đề có số màn và mỗi đội hình một lưới 5x5.

- [ ] **Step 1: Write the failing tests** (`test_formation_page.py`, tự dựng `FormationViewResponse`)

- `test_page_has_the_stage_and_a_grid_per_formation`: hai đội hình, trang chứa số màn (ví dụ "15-50") và đúng `2 * 25` phần tử ô (đếm theo class `cell`).
- `test_unit_cell_shows_sprite_name_and_tier`: ô có `<img src="data:image/png;base64,...">`, tên và cấp (ví dụ "T2"), dấu glitter khi `glitter=True`.
- `test_unit_without_a_sprite_still_shows_its_name`: `sprites={}`, không lỗi, có tên, không có thẻ `<img` của ô đó.
- `test_names_are_escaped`: tên `<script>alert(1)</script>&"` không xuất hiện nguyên văn; xuất hiện dạng escape.
- `test_level_none_does_not_print_none`: `level=None` không sinh chuỗi "None".
- `test_empty_cells_are_blank`: đội hình 1 quân cho 24 ô trống.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_formation_page.py -q`
Expected: FAIL (thiếu module).

- [ ] **Step 3: Implement `render_formation_page`** trong `formation_page.py`

Chuỗi f/`html.escape`, CSS gọn trong thẻ `<style>`, `<meta charset="utf-8">`. Lưới 5 hàng 5 cột theo `row`, `col` (hàng 1 ở trên). Mỗi ô có class `cell`; ô có quân thêm class `unit`. Tiêu đề: `Màn {stage}` và với mỗi đội hình `Đội hình {i}/{n}` kèm `Lv {level}` khi có. Docstring Google style.

- [ ] **Step 4: Run tests to verify they pass**

Run: lệnh ở Step 2. Expected: PASS (ghi số test pass).

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src-python
git commit -m "feat: render the prepared formations of a stage as an HTML page"
```

### Task 3: Card `show_formation` và setting

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/settings.py` (class `FormationViewSettings` với field `stage`, và field `formation_view` trong `Settings`)
- Modify: `src-tauri/settings/ClashOfCritters.toml` (thêm `[formation_view]` với `stage = ""`)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/main.py` (lệnh `show_formation`)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (mô tả card, giới hạn, và việc patch đủ)
- Test: `test_auto_battle_settings.py` (hoặc file settings mới), `test_auto_battle_command.py`, và file mới `test_show_formation.py`

**Interfaces:**
- Consumes: `formation_view.load_formation_view(stage_text: str | None, grab=..., data_root=None) -> FormationViewResponse`, `formation_page.render_formation_page`.
- Produces: `FormationViewSettings.stage: str` (mặc định `""`); `ClashOfCritters.show_formation(self) -> None`; `ClashOfCritters._open_formation_page(self, response: FormationViewResponse) -> None` (ghi file, mở trình duyệt).

- [ ] **Step 1: Write the failing tests**

- Settings: `FormationViewSettings().stage == ""`; `"formation_view" in Settings.model_fields`.
- Command: `COMMAND_REGISTRY["clash_of_critters"]["clash_of_critters.show_formation"]` có `label == "Xem Đội Hình"` và `category == "Battle"` (cùng kiểu với `test_auto_battle_is_registered_in_the_battle_category`).
- `test_show_formation.py` (bot dựng bằng `object.__new__(ClashOfCritters)`, patch `main.load_formation_view`, `main.webbrowser.open`, và thư mục tạm bằng `tmp_path`):
  - `stage` rỗng hoặc chỉ khoảng trắng: `load_formation_view` được gọi với `None`; có số màn: được gọi với chuỗi đã `strip`.
  - Status `ok`: file HTML được ghi (tên có số màn), `webbrowser.open` được gọi với đường dẫn file, log info có đường dẫn.
  - Mỗi status `no_device`, `stage_unreadable`, `stage_invalid`, `no_formation`: không ghi file, không mở trình duyệt, log warning bằng tiếng Việt khác nhau cho từng status.
  - `webbrowser.open` trả `False` hoặc ném `webbrowser.Error`: không ném lỗi ra ngoài, log có đường dẫn file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_show_formation.py src-python/tests/games/clash_of_critters/test_auto_battle_command.py src-python/tests/games/clash_of_critters/test_auto_battle_settings.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `settings.py`: `FormationViewSettings(BaseModel)` với `stage: str = Field(default="", title="Stage", description="Stage to show, for example 15-50. Leave empty to read the stage from the screen (preparation and fight screens only).")`; trong `Settings`: `formation_view: FormationViewSettings = Field(default_factory=FormationViewSettings, title="Xem Đội Hình")`.
- `ClashOfCritters.show_formation` với `@register_command(gui=GUIMetadata(label="Xem Đội Hình", category="Battle", tooltip=...))`: lấy `stage = self.settings.formation_view.stage.strip() or None`, gọi `load_formation_view(stage)` (dùng `grab_screenshot` mặc định khi `stage` là None), rồi theo `status`.
- `_open_formation_page`: ghi `render_formation_page(response)` vào `Path(tempfile.gettempdir()) / f"coc_formation_{stage}.html"` (UTF-8), mở bằng `webbrowser.open(path.as_uri())`; bắt `webbrowser.Error` và kết quả `False`.
- Bảng log theo `status` là hằng số module (ví dụ `_VIEW_STATUS_LOG: dict[str, str]`).
- `ClashOfCritters.toml`: thêm `[formation_view]` và `stage = ""`.
- `CLAUDE.md` của game: thay mô tả cửa sổ bằng mô tả card (file HTML trong thư mục tạm, setting `stage`, chỉ đọc màn ở màn chuẩn bị và đang đánh, patch đủ, setting mới chỉ hiện sau khi reset hoặc sửa settings). Ghi kết quả kiểm tra việc chạy khi auto battle đang chạy (xem Step 5).

- [ ] **Step 4: Run tests to verify they pass**

Run: lệnh ở Step 2, cộng `test_formation_page.py` và `test_formation_view.py`. Expected: PASS (ghi số test pass từng file).

- [ ] **Step 5: Check running next to the auto battle**

Đọc `__main__.py` (`start_task`, `run_task`): tìm xem app có chặn chạy hai task cùng lúc không, rồi ghi kết luận một câu vào `CLAUDE.md` của game. Không viết test cho việc này.

- [ ] **Step 6: Lint and commit**

Từ gốc repo: `uvx ruff check --fix` và `uvx ruff format` trên `src-tauri/src-python`. Expected: không còn lỗi.

```bash
git add src-tauri
git commit -m "feat: add the Xem Đội Hình card that opens the formations of a stage"
```
