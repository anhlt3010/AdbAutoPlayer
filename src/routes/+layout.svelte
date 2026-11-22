<script lang="ts">
  import "../app.css";

  import { ui } from "#lib/stores.svelte.ts";

  let { children } = $props();

  $effect(() => {
    document.documentElement.className = ui.theme;
    document.documentElement.style.setProperty(
      "--accent-h",
      ui.accentHue.toString(),
    );
  });
</script>

{@render children()}
