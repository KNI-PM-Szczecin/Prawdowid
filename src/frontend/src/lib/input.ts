import type { InputType } from "./types";

// Must match the backend limit from CONTRACT.md §1.
export const MAX_INPUT_LENGTH = 5000;
// Upload limits of POST /api/check/image (CONTRACT.md §1).
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const SUPPORTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

const URL_PATTERN = /^https?:\/\/\S+$/i;

export function detectInputType(input: string): InputType {
  return URL_PATTERN.test(input.trim()) ? "url" : "text";
}
