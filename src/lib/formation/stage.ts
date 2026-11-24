const STAGE_PATTERN = /^\s*(\d{1,2})\s*-\s*(\d{1,3})\s*$/;
// En dash, em dash and minus sign: what a phone keyboard or a paste brings.
const DASHES = /[\u2013\u2014\u2212]/g;
const MAX_STAGE_NUMBER = 999;

/**
 * Step a stage such as "15-50" by one inside its chapter.
 *
 * @param maxStage the last stage of the chapter (a Võ Đường has 10).
 * @returns the new stage, or null when the text is not a stage or the result
 * would leave the chapter (below 1, or above `maxStage`).
 */
export function stepStage(
  stage: string,
  delta: -1 | 1,
  maxStage: number = MAX_STAGE_NUMBER,
): string | null {
  const match = STAGE_PATTERN.exec(stage.replace(DASHES, "-"));
  if (match === null) {
    return null;
  }
  const next = Number(match[2]) + delta;
  if (next < 1 || next > maxStage) {
    return null;
  }
  return `${Number(match[1])}-${next}`;
}
