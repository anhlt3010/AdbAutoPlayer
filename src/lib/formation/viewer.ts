import { emitTo } from "@tauri-apps/api/event";
import { get } from "svelte/store";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { t } from "#lib/i18n/i18n.ts";
import { showErrorToast } from "#lib/toast/toast-error.ts";

export const FORMATION_VIEWER_LABEL = "formation-viewer";
export const FORMATION_VIEWER_REFRESH_EVENT = "formation-viewer:refresh";

const WINDOW_WIDTH = 420;
const WINDOW_HEIGHT = 560;
// Give up waiting for the new window after this long, so the button never stays
// locked if Tauri answers neither "created" nor "error".
const CREATE_TIMEOUT_MS = 5000;

let opening: Promise<void> | null = null;

/**
 * Open the formation viewer window, or bring the open one to the front and ask
 * it to read the device screen again. Only one viewer window exists.
 *
 * A second click while the first one is still opening the window is ignored,
 * otherwise both would try to create the same window label.
 */
export function openFormationViewer(profileIndex: number): Promise<void> {
  opening ??= open(profileIndex).finally(() => {
    opening = null;
  });
  return opening;
}

async function open(profileIndex: number): Promise<void> {
  const tr = get(t);
  const failTitle = tr("Failed to open the formation viewer");
  try {
    const existing = await WebviewWindow.getByLabel(FORMATION_VIEWER_LABEL);
    if (existing !== null) {
      await existing.unminimize();
      await existing.show();
      await existing.setFocus();
      await emitTo(FORMATION_VIEWER_LABEL, FORMATION_VIEWER_REFRESH_EVENT, {
        profile_index: profileIndex,
      });
      return;
    }
    const created = new WebviewWindow(FORMATION_VIEWER_LABEL, {
      url: `/formation-viewer?profile=${profileIndex}`,
      title: tr("Formation viewer"),
      width: WINDOW_WIDTH,
      height: WINDOW_HEIGHT,
      resizable: true,
    });
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, CREATE_TIMEOUT_MS);
      const done = () => {
        clearTimeout(timer);
        resolve();
      };
      void created.once("tauri://created", done);
      void created.once("tauri://error", (event) => {
        done();
        void showErrorToast(event.payload, {
          title: failTitle,
          logToLogDisplay: false,
        });
      });
    });
  } catch (error) {
    void showErrorToast(error, { title: failTitle, logToLogDisplay: false });
  }
}
