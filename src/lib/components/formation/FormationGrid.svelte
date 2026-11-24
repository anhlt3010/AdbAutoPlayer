<script lang="ts">
  import { t } from "#lib/i18n/i18n.ts";
  import type { ViewUnit } from "#lib/formation/types.ts";

  interface Props {
    units: ViewUnit[];
    // Sprite data URI of each evolution_id.
    sprites: Record<string, string>;
    // Size of the field: only these cells are drawn (auto battle 5x5, Võ Đường 3x4).
    rows?: number;
    columns?: number;
  }

  const BATTLE_FIELD_SIZE = 5;

  let {
    units,
    sprites,
    rows = BATTLE_FIELD_SIZE,
    columns = BATTLE_FIELD_SIZE,
  }: Props = $props();

  const cells = $derived(
    Array.from({ length: rows * columns }, (_, i) => ({
      row: Math.floor(i / columns) + 1,
      col: (i % columns) + 1,
    })),
  );

  const unitAt = $derived(
    new Map(units.map((unit) => [`${unit.row},${unit.col}`, unit])),
  );
</script>

<div class="grid" style:--columns={columns}>
  {#each cells as cell (`${cell.row},${cell.col}`)}
    {@const unit = unitAt.get(`${cell.row},${cell.col}`)}
    <div class="cell" class:filled={unit !== undefined}>
      {#if unit}
        {#if sprites[unit.evolution_id]}
          <img
            class="sprite"
            src={sprites[unit.evolution_id]}
            alt={unit.name}
          />
        {:else}
          <span class="fallback">{unit.name}</span>
        {/if}
        <span class="tier">T{unit.tier}</span>
        {#if unit.glitter}
          <span class="glitter" title={$t("Glitter")}>✨</span>
        {/if}
        {#if sprites[unit.evolution_id]}
          <span class="name">{unit.name}</span>
        {/if}
      {/if}
    </div>
  {/each}
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--columns), 1fr);
    gap: 4px;
    width: 100%;
    /* A narrower field keeps the cell size of the 5 column one. */
    max-width: calc(var(--columns) / 5 * 100%);
  }

  .cell {
    position: relative;
    aspect-ratio: 1;
    border-radius: 8px;
    background: var(--bg-1);
    border: 1px solid var(--line-soft, var(--line));
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }

  .cell.filled {
    background: var(--bg-2);
    border-color: var(--line);
  }

  .sprite {
    width: 80%;
    height: 80%;
    object-fit: contain;
  }

  .fallback {
    font-size: 10px;
    text-align: center;
    padding: 2px;
    color: var(--text-2, inherit);
  }

  .tier {
    position: absolute;
    top: 2px;
    left: 2px;
    font-size: 10px;
    font-weight: 700;
    line-height: 1;
    padding: 2px 4px;
    border-radius: 4px;
    color: white;
    background: var(--accent);
  }

  .glitter {
    position: absolute;
    top: 1px;
    right: 2px;
    font-size: 11px;
    line-height: 1;
  }

  .name {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    font-size: 9px;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0 2px 1px;
    color: var(--text-3);
    background: color-mix(in oklab, var(--bg-2) 80%, transparent);
  }
</style>
