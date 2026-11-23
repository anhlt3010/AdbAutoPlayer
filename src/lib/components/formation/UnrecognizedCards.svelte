<script lang="ts">
  import { getUnrecognizedCards, teachCard } from "#pytauri/apiClient.ts";
  import { t } from "#lib/i18n/i18n.ts";
  import type {
    CardChoice,
    WaitingCards,
    WaitingCard,
  } from "#lib/formation/types.ts";

  interface Props {
    profileIndex: number;
    // Bumped by the page (refresh button, refresh event) to load the list again.
    reloadToken: number;
    onCountChange: (count: number) => void;
  }

  let { profileIndex, reloadToken, onCountChange }: Props = $props();

  let data = $state<WaitingCards | null>(null);
  let selectedCard = $state<string | null>(null);
  let selectedChoice = $state<string | null>(null);
  let loading = $state(false);
  let saving = $state(false);
  let errorText = $state("");

  const card = $derived<WaitingCard | null>(
    data?.cards.find((c) => c.id === selectedCard) ?? null,
  );

  // One row per tatari: normal tiers, then glitter tiers (the order the server sends).
  const rows = $derived.by(() => {
    const choices: CardChoice[] = card
      ? (data?.choices[card.element] ?? [])
      : [];
    const byTatari = new Map<string, CardChoice[]>();
    for (const choice of choices) {
      const row = byTatari.get(choice.tatari_id) ?? [];
      row.push(choice);
      byTatari.set(choice.tatari_id, row);
    }
    return [...byTatari.entries()];
  });

  async function load() {
    loading = true;
    errorText = "";
    try {
      data = await getUnrecognizedCards({ profile_index: profileIndex });
      onCountChange(data.cards.length);
      if (!data.cards.some((c) => c.id === selectedCard)) {
        selectedCard = data.cards[0]?.id ?? null;
        selectedChoice = null;
      }
    } catch (error) {
      errorText = String(error);
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!card || !selectedChoice) {
      return;
    }
    saving = true;
    errorText = "";
    try {
      const result = await teachCard({
        profile_index: profileIndex,
        crop_id: card.id,
        evolution_id: selectedChoice,
      });
      if (result.status !== "ok") {
        errorText = $t("Could not save: {{status}}", { status: result.status });
      }
      selectedChoice = null;
      await load();
    } catch (error) {
      errorText = String(error);
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    void reloadToken;
    void load();
  });
</script>

{#if loading && !data}
  <p class="note">{$t("Loading...")}</p>
{/if}
{#if errorText}
  <p class="problem">{errorText}</p>
{/if}

{#if data && data.cards.length === 0}
  <p class="note">{$t("No unrecognized cards.")}</p>
{:else if data}
  <div class="cards">
    {#each data.cards as waiting (waiting.id)}
      <button
        class="card"
        class:selected={waiting.id === selectedCard}
        onclick={() => {
          selectedCard = waiting.id;
          selectedChoice = null;
        }}
      >
        <img src={waiting.image} alt={waiting.element} />
      </button>
    {/each}
  </div>

  {#if card}
    <p class="note">{$t("Pick the tatari of this card")}</p>
    <div class="choices">
      {#each rows as [tatariId, choices] (tatariId)}
        <div class="row">
          <span class="tatari">{tatariId}</span>
          {#each choices as choice (choice.evolution_id)}
            <button
              class="choice"
              class:selected={choice.evolution_id === selectedChoice}
              title={choice.evolution_id}
              onclick={() => (selectedChoice = choice.evolution_id)}
            >
              {#if choice.sprite}
                <img src={choice.sprite} alt={choice.evolution_id} />
              {/if}
              <span class="tier"
                >T{choice.tier}{choice.glitter ? "✨" : ""}</span
              >
            </button>
          {/each}
        </div>
      {/each}
    </div>
    <button
      class="save"
      disabled={!selectedChoice || saving}
      onclick={() => void save()}>{$t("Save")}</button
    >
  {/if}
{/if}

<style>
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

  .cards {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .card,
  .choice {
    padding: 2px;
    border-radius: 6px;
    background: var(--bg-2);
    border: 2px solid var(--line);
    cursor: pointer;
  }

  .card img {
    display: block;
    width: 80px;
  }

  .selected {
    border-color: var(--accent);
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: 4px;
    overflow-y: auto;
    max-height: 60vh;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .tatari {
    width: 72px;
    font-size: 12px;
    color: var(--text-2, var(--text-1));
  }

  .choice {
    position: relative;
    width: 52px;
    height: 52px;
    display: grid;
    place-items: center;
  }

  .choice img {
    max-width: 46px;
    max-height: 46px;
  }

  .tier {
    position: absolute;
    right: 2px;
    bottom: 1px;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-1);
  }

  .save {
    align-self: flex-end;
    padding: 4px 16px;
    border-radius: 6px;
    background: var(--accent);
    color: var(--bg-0, #fff);
    border: none;
    cursor: pointer;
  }

  .save:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
