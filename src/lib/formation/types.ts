import type {
  getFormationView,
  getUnrecognizedCards,
} from "#pytauri/apiClient.ts";

// Derived from the generated client so the viewer follows the Python models.
export type FormationView = Awaited<ReturnType<typeof getFormationView>>;
export type ViewFormation = FormationView["formations"][number];
export type ViewUnit = ViewFormation["units"][number];

export type WaitingCards = Awaited<ReturnType<typeof getUnrecognizedCards>>;
export type WaitingCard = WaitingCards["cards"][number];
export type CardChoice = WaitingCards["choices"][string][number];
