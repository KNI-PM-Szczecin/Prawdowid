import { mockCheck } from "./mockResults";
import type { CheckResult, InputType } from "./types";

const CHECK_ENDPOINT = "/api/check";
// Backend budget is 25 s (CONTRACT.md §2); the rest covers the network.
const REQUEST_TIMEOUT_MS = 40_000;
// 503 and 429 carry a CheckResult with status technical_error (CONTRACT.md §1).
const HTTP_STATUSES_WITH_RESULT = new Set([200, 429, 503]);

export const IS_MOCK_MODE = import.meta.env.MODE === "mock";

export class CheckRequestError extends Error {}

export async function checkInput(input: string, inputType: InputType): Promise<CheckResult> {
  if (IS_MOCK_MODE) {
    return mockCheck(input, inputType);
  }
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(CHECK_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, inputType }),
      signal: controller.signal,
    });
    if (!HTTP_STATUSES_WITH_RESULT.has(response.status)) {
      throw new CheckRequestError(`Unexpected HTTP status ${response.status}`);
    }
    const body: unknown = await response.json();
    if (!isCheckResult(body)) {
      throw new CheckRequestError("Response body is not a CheckResult");
    }
    return body;
  } catch (error) {
    if (error instanceof CheckRequestError) {
      throw error;
    }
    throw new CheckRequestError("Check request failed", { cause: error });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function isCheckResult(body: unknown): body is CheckResult {
  if (typeof body !== "object" || body === null) {
    return false;
  }
  const candidate = body as Partial<CheckResult>;
  return typeof candidate.status === "string" && Array.isArray(candidate.claims);
}
