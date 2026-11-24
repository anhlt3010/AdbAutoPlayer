<script lang="ts">
  import { onMount } from "svelte";
  import { listen } from "@tauri-apps/api/event";
  import { getFormationView } from "#pytauri/apiClient.ts";
  import { applySettingsFromFile } from "#lib/utils/settings.ts";
  import { t } from "#lib/i18n/i18n.ts";
  import FormationGrid from "#lib/components/formation/FormationGrid.svelte";
  import UnrecognizedCards from "#lib/components/formation/UnrecognizedCards.svelte";
  import { stepStage } from "#lib/formation/stage.ts";
  import {
    FORMATION_VIEWER_REFRESH_EVENT,
    FORMATION_VIEWER_TAB_EVENT,
    type ViewerMode,
  } from "#lib/formation/viewer.ts";
  import type { FormationView } from "#lib/formation/types.ts";

  // A Võ Đường has 10 stages and a 3 column x 4 row field.
  const DOJO_MAX_STAGE = 10;
  const DOJO_ROWS = 4;
  const DOJO_COLUMNS = 3;
  const ELEMENTS = ["water", "fire", "grass", "rock", "lightning"] as const;

  let profileIndex = $state(0);
  let mode = $state<ViewerMode>("battle");
  // Võ Đường only: the element read from the tray (or picked), kept so that the
  // stage buttons and a typed stage reuse it.
  let element = $state<string | null>(null);
  let elementPickerOpen = $state(false);
  let tab = $state<"formation" | "cards">("formation");
  let unrecognizedCount = $state(0);
  // Bumped to make the unrecognized cards tab load its list again.
  let cardsReload = $state(0);
  // The last answer that has formations; kept while a typed stage is invalid.
  let view = $state<FormationView | null>(null);
  let problem = $state<string | null>(null);
  let errorText = $state("");
  let formationIndex = $state(0);
  let stageInput = $state("");
  let loading = $state(false);
  // Whether the running request reads a typed stage (not the device screen).
  let loadingTyped = $state(false);
  // Stage of the last answer; the "no formation" message names it, not the box.
  let answeredStage = $state("");
  // Only the newest request may update the page (fast +/- clicks).
  let latestRequest = 0;
  // True once the user types in the box while a request runs, so a late answer
  // does not overwrite what they are typing.
  let inputDirty = false;

  const formations = $derived(view?.formations ?? []);
  const current = $derived(formations[formationIndex] ?? null);
  const maxStage = $derived(mode === "dojo" ? DOJO_MAX_STAGE : undefined);
  const canStepDown = $derived(stepStage(stageInput, -1, maxStage) !== null);
  const canStepUp = $derived(stepStage(stageInput, 1, maxStage) !== null);
  // The element row opens by itself when the tray could not tell the element.
  const showElementPicker = $derived(
    mode === "dojo" && (elementPickerOpen || problem === "element_unreadable"),
  );

  const elementLabel = $derived.by(() => {
    const labels: Record<string, string> = {
      water: $t("Water"),
      fire: $t("Fire"),
      grass: $t("Grass"),
      rock: $t("Rock"),
      lightning: $t("Lightning"),
    };
    return (name: string) => labels[name] ?? name;
  });

  const problemText = $derived.by(() => {
    switch (problem) {
      case "no_device":
        return $t("No device found.");
      case "stage_unreadable":
        return $t(
          "Could not read the stage from this screen. Type a stage such as 15-50.",
        );
      case "stage_invalid":
        return $t("Wrong stage format. Use chapter-number, for example 15-50.");
      case "element_unreadable":
        return $t("Could not tell the element from the tray. Pick it below.");
      case "no_formation":
        return $t("No prepared formation for stage {{stage}}.", {
          stage: answeredStage,
        });
      case "error":
        return $t("Could not load the formations: {{error}}", {
          error: errorText,
        });
      default:
        return null;
    }
  });

  /** Load a typed stage, or read the stage from the device screen when null. */
  async function load(stage: string | null) {
    const request = ++latestRequest;
    loading = true;
    loadingTyped = stage !== null;
    inputDirty = false;
    try {
      const result = await getFormationView({
        profile_index: profileIndex,
        stage,
        mode,
        element,
      });
      if (request !== latestRequest) {
        return;
      }
      if (result.status === "stage_invalid") {
        // Keep what is shown; only tell the user the typed stage is wrong.
        problem = result.status;
        return;
      }
      problem = result.status === "ok" ? null : result.status;
      view = result.status === "ok" ? result : null;
      formationIndex = 0;
      answeredStage = result.stage ?? "";
      if (result.stage && !inputDirty) {
        stageInput = result.stage;
      }
      if (result.element) {
        element = result.element;
      } else if (result.status === "element_unreadable") {
        element = null;
      }
    } catch (error) {
      if (request === latestRequest) {
        problem = "error";
        errorText = String(error);
      }
    } finally {
      if (request === latestRequest) {
        loading = false;
      }
    }
  }

  function step(delta: -1 | 1) {
    const next = stepStage(stageInput, delta, maxStage);
    if (next === null) {
      return;
    }
    stageInput = next;
    void load(next);
  }

  /** Võ Đường: the user picks the element the tray did not tell. */
  function pickElement(name: string) {
    element = name;
    elementPickerOpen = false;
    void load(stageInput.trim() || null);
  }

  /** Show another mode: forget what the old one showed and read the screen. */
  function switchMode(next: ViewerMode) {
    mode = next;
    view = null;
    problem = null;
    answeredStage = "";
    stageInput = "";
    element = null;
    elementPickerOpen = false;
  }

  function onStageKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      void load(stageInput.trim());
    }
  }

  onMount(() => {
    const params = new URLSearchParams(window.location.search);
    profileIndex = Number(params.get("profile") ?? "0") || 0;
    if (params.get("mode") === "dojo") {
      mode = "dojo";
    }
    if (params.get("tab") === "cards") {
      tab = "cards";
    }

    let unlisten: (() => void) | undefined;
    let unlistenTab: (() => void) | undefined;
    void (async () => {
      try {
        await applySettingsFromFile();
      } catch (error) {
        console.error(error);
      }
      unlisten = await listen<{ profile_index: number; mode?: ViewerMode }>(
        FORMATION_VIEWER_REFRESH_EVENT,
        (event) => {
          profileIndex = event.payload.profile_index;
          // No mode in the event keeps the current one (automatic events).
          if (event.payload.mode && event.payload.mode !== mode) {
            switchMode(event.payload.mode);
          }
          cardsReload++;
          void load(null);
        },
      );
      unlistenTab = await listen(FORMATION_VIEWER_TAB_EVENT, () => {
        tab = "cards";
        cardsReload++;
      });
    })();
    void load(null);

    return () => {
      unlisten?.();
      unlistenTab?.();
    };
  });
</script>

<svelte:head>
  <title>{$t("Formation viewer")}</title>
</svelte:head>

<main class="viewer">
  <nav class="tabs">
    <button
      class="tab"
      class:active={tab === "formation"}
      onclick={() => (tab = "formation")}>{$t("Formation")}</button
    >
    <button
      class="tab"
      class:active={tab === "cards"}
      onclick={() => (tab = "cards")}
      >{$t("Unrecognized cards ({{n}})", {
        n: String(unrecognizedCount),
      })}</button
    >
  </nav>

  <header class="bar">
    <div class="stage-box">
      <button
        class="icon-btn"
        disabled={!canStepDown}
        onclick={() => step(-1)}
        aria-label="-">-</button
      >
      <input
        class="stage-input"
        bind:value={stageInput}
        oninput={() => (inputDirty = true)}
        onkeydown={onStageKeydown}
        placeholder={mode === "dojo" ? "4-2" : "15-50"}
        aria-label={$t("Stage")}
      />
      <button
        class="icon-btn"
        disabled={!canStepUp}
        onclick={() => step(1)}
        aria-label="+">+</button
      >
    </div>
    {#if mode === "dojo"}
      <button
        class="element-badge"
        onclick={() => (elementPickerOpen = !elementPickerOpen)}
        title={$t("Element")}
        aria-label={$t("Element")}
        >{element ? elementLabel(element) : $t("Element")}</button
      >
    {/if}
    {#if current?.level != null}
      <span class="level">Lv {current.level}</span>
    {/if}
    <div class="spacer"></div>
    <button
      class="icon-btn"
      disabled={formationIndex <= 0}
      onclick={() => formationIndex--}
      title={$t("Previous formation")}
      aria-label={$t("Previous formation")}>◀</button
    >
    <button
      class="icon-btn"
      disabled={formationIndex >= formations.length - 1}
      onclick={() => formationIndex++}
      title={$t("Next formation")}
      aria-label={$t("Next formation")}>▶</button
    >
    <button
      class="icon-btn"
      onclick={() => {
        cardsReload++;
        void load(null);
      }}
      title={$t("Refresh (read the screen)")}
      aria-label={$t("Refresh (read the screen)")}>⟳</button
    >
  </header>

  {#if showElementPicker && tab === "formation"}
    <div class="elements">
      {#each ELEMENTS as name (name)}
        <button
          class="chip"
          class:active={element === name}
          onclick={() => pickElement(name)}>{elementLabel(name)}</button
        >
      {/each}
    </div>
  {/if}

  <!-- Kept mounted so the tab label shows the count from the start. -->
  <div class="cards-tab" class:hidden={tab !== "cards"}>
    <UnrecognizedCards
      {profileIndex}
      reloadToken={cardsReload}
      onCountChange={(count) => (unrecognizedCount = count)}
    />
  </div>

  {#if tab === "formation"}
    {#if formations.length > 0}
      <p class="counter">
        {$t("Formation {{current}}/{{total}}", {
          current: String(formationIndex + 1),
          total: String(formations.length),
        })}
      </p>
    {/if}

    {#if loading}
      <p class="note">
        {loadingTyped ? $t("Loading...") : $t("Reading the screen...")}
      </p>
    {/if}
    {#if problemText}
      <p class="problem">{problemText}</p>
    {/if}

    {#if current}
      {#if mode === "dojo"}
        <FormationGrid
          units={current.units}
          sprites={view?.sprites ?? {}}
          rows={DOJO_ROWS}
          columns={DOJO_COLUMNS}
        />
      {:else}
        <FormationGrid units={current.units} sprites={view?.sprites ?? {}} />
      {/if}
    {/if}
  {/if}
</main>

<style>
  :global(body) {
    background: var(--bg-0, var(--bg-1));
    color: var(--text-1);
  }

  .viewer {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
    min-height: 100vh;
    box-sizing: border-box;
  }

  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--line);
  }

  .tab {
    padding: 4px 10px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-3);
    cursor: pointer;
  }

  .tab.active {
    color: var(--text-1);
    border-bottom-color: var(--accent);
  }

  .cards-tab {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .hidden {
    display: none;
  }

  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .stage-box {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .stage-input {
    width: 76px;
    text-align: center;
    font-weight: 600;
    padding: 3px 6px;
    border-radius: 6px;
    background: var(--bg-1);
    border: 1px solid var(--line);
    color: var(--text-1);
  }

  .icon-btn {
    min-width: 26px;
    height: 26px;
    border-radius: 6px;
    display: grid;
    place-items: center;
    background: var(--bg-2);
    color: var(--text-2, var(--text-1));
    border: 1px solid var(--line);
    cursor: pointer;
  }

  .icon-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .icon-btn:not(:disabled):hover {
    color: var(--text-1);
  }

  .level {
    font-size: 12px;
    color: var(--text-3);
  }

  .element-badge,
  .chip {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 12px;
    background: var(--bg-2);
    color: var(--text-2, var(--text-1));
    border: 1px solid var(--line);
    cursor: pointer;
  }

  .chip.active {
    color: var(--text-1);
    border-color: var(--accent);
  }

  .elements {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .spacer {
    flex: 1;
  }

  .counter,
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--text-3);
  }

  .problem {
    margin: 0;
    font-size: 13px;
    color: var(--accent);
  }
</style>
