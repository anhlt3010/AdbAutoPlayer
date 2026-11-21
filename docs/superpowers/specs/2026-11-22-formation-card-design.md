# Card "Xem Đội Hình" thay cho cửa sổ xem đội hình (thiết kế ngắn)

## Mục đích

Cửa sổ xem đội hình (nút trên card Tự Động Chiến Đấu) cần build app mới, trong khi người dùng chỉ cập nhật bằng patch Python. Thay nó bằng một card trong danh sách card hiện tại (category Battle) mà bản patch là đủ: bấm card thì mở trang HTML có hình các đội hình của màn.

## Mục tiêu

- Một card mới ở category Battle, dưới "Tự Động Chiến Đấu". Không cần build app.
- Bấm card: lấy màn (gõ trong setting, hoặc tự nhận từ một ảnh màn hình), dựng một trang HTML tự chứa (lưới 5x5 cho từng đội hình, sprite từng tatari, tên và cấp tiến hóa), lưu vào thư mục tạm và mở bằng trình duyệt mặc định.
- Gỡ nút xem đội hình và mọi xử lý giao diện liên quan, đưa phần giao diện về như bản `coc-vn-v0.3.5`.

## Không làm

- Không đưa hình vào bên trong card hay cửa sổ app (cần build app).
- Không thêm trường nào vào `MenuOption` hay `GUIMetadata`.
- Không gửi thao tác vào game (chỉ chụp ảnh).

## Các cách đã cân nhắc

- **Card + trang HTML mở bằng trình duyệt (đã chọn):** chỉ cần patch, có hình.
- Card chỉ ghi log chữ: không có hình.
- Card mở cửa sổ app: cần build app mới, nên đi ngược mục đích.

## Thiết kế

### Card mới

- Lệnh `show_formation` trong game Clash of Critters, `@register_command(gui=GUIMetadata(label="Xem Đội Hình", category="Battle", tooltip=...))`.
- Setting mới `formation_view.stage` (chuỗi, mặc định rỗng): số màn như "15-50" (dấu gạch en được chấp nhận). Rỗng thì tự nhận màn từ một ảnh màn hình.
- Dùng lại `formation_view.load_formation_view(stage_text)` (đã có test) để lấy `FormationViewResponse`: `status` (`ok`, `no_device`, `stage_unreadable`, `stage_invalid`, `no_formation`), `stage`, `formations` (mỗi đội hình có `level` và `units` gồm `row`, `col`, `name`, `tier`, `glitter`) và `sprites` (data URI PNG 96 px).
- Trạng thái khác `ok`: ghi log một câu tiếng Việt nêu lý do (ví dụ "Không đọc được màn: hãy mở màn chuẩn bị chiến đấu hoặc gõ số màn trong cài đặt") và không mở trình duyệt.
- Trạng thái `ok`: dựng HTML, ghi vào thư mục tạm (tên có số màn), mở bằng `webbrowser.open`, ghi log đường dẫn file.

### Trang HTML

- Mô-đun mới `formation_page.py` với hàm thuần `render_formation_page(response) -> str` (không gọi thiết bị, dễ test): tiêu đề có số màn, mỗi đội hình một lưới 5x5, ô có sprite, tên, cấp (và dấu glitter), ô trống để trống. Mọi chuỗi đưa vào HTML phải được escape.

### Gỡ giao diện

- Revert commit `8a06fd12` (nút, cửa sổ, route `formation-viewer`, `window.rs`, capabilities, CSP, i18n, tách layout `(app)`) và `0b6fe88f` (client TypeScript tạo lại), vì cả hai chỉ phục vụ cửa sổ.
- Xóa lệnh PyTauri `get_formation_view` và `FormationViewBody` trong `__main__.py` (chỉ cửa sổ dùng).
- Giữ nguyên `formation_view.py`, `test_formation_view.py` và thay đổi trong `formation.py` (card dùng lại).
- Cập nhật CLAUDE.md của game: bỏ đoạn mô tả cửa sổ, thêm đoạn mô tả card.

## Ràng buộc

- Chỉ Python: bản patch là đủ, không cần build app.
- Bản `coc-vn-v0.4.0` đã đẩy lên có release note mô tả cửa sổ xem đội hình ở mục App. Sau thay đổi này note đó sai, nên cần phát hành bản patch mới (số version hỏi khi đóng gói).

## Để người xây quyết định

- Lấy ảnh màn hình bằng `self.get_screenshot()` của game hay `grab_screenshot` có sẵn trong `formation_view.py`.
- Có chạy được khi auto battle đang chạy không (cơ chế task của app). Kiểm tra khi làm và ghi lại trong CLAUDE.md.
- Cách đặt tên file tạm và dọn file cũ.
- Test: `render_formation_page` (escape, số ô, ô trống), nhánh từng `status`, lệnh không mở trình duyệt khi không `ok`, setting mới (mặc định, giá trị rỗng), và test hồi quy cho phần gỡ giao diện (không còn `get_formation_view` trong `__main__.py`).
