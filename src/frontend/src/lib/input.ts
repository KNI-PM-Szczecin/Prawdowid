import type { InputType } from "./types";

// Must match the backend limit from CONTRACT.md §1.
export const MAX_INPUT_LENGTH = 5000;

const URL_PATTERN = /^https?:\/\/\S+$/i;

export function detectInputType(input: string): InputType {
  return URL_PATTERN.test(input.trim()) ? "url" : "text";
}
