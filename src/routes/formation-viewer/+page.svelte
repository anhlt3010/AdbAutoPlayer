<script lang="ts">
  import { onMount } from "svelte";
  import { listen } from "@tauri-apps/api/event";
  import { getFormationView } from "#pytauri/apiClient.ts";
  import { applySettingsFromFile } from "#lib/utils/settings.ts";
  import { t } from "#lib/i18n/i18n.ts";
  import FormationGrid from "#lib/components/formation/FormationGrid.svelte";
  import { stepStage } from "#lib/formation/stage.ts";
  import { FORMATION_VIEWER_REFRESH_EVENT } from "#lib/formation/viewer.ts";
  import type { FormationView } from "#lib/formation/types.ts";

  let profileIndex = $state(0);
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
  const canStepDown = $derived(stepStage(stageInput, -1) !== null);
  const canStepUp = $derived(stepStage(stageInput, 1) !== null);

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
    const next = stepStage(stageInput, delta);
    if (next === null) {
      return;
    }
    stageInput = next;
    void load(next);
  }

  function onStageKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      void load(stageInput.trim());
    }
  }

  onMount(() => {
    const profile = new URLSearchParams(window.location.search).get("profile");
    profileIndex = Number(profile ?? "0") || 0;

    let unlisten: (() => void) | undefined;
    void (async () => {
      try {
        await applySettingsFromFile();
      } catch (error) {
        console.error(error);
      }
      unlisten = await listen<{ profile_index: number }>(
        FORMATION_VIEWER_REFRESH_EVENT,
        (event) => {
          profileIndex = event.payload.profile_index;
          void load(null);
        },
      );
    })();
    void load(null);

    return () => unlisten?.();
  });
</script>

<svelte:head>
  <title>{$t("Formation viewer")}</title>
</svelte:head>

<main class="viewer">
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
        placeholder="15-50"
        aria-label={$t("Stage")}
      />
      <button
        class="icon-btn"
        disabled={!canStepUp}
        onclick={() => step(1)}
        aria-label="+">+</button
      >
    </div>
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
      onclick={() => load(null)}
      title={$t("Refresh (read the screen)")}
      aria-label={$t("Refresh (read the screen)")}>⟳</button
    >
  </header>

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
    <FormationGrid units={current.units} sprites={view?.sprites ?? {}} />
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
