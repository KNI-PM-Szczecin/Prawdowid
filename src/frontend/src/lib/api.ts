import { mockCheck, mockImageCheck } from "./mockResults";
import type { CheckResult, InputType } from "./types";

const CHECK_ENDPOINT = "/api/check";
const IMAGE_CHECK_ENDPOINT = "/api/check/image";
const IMAGE_FORM_FIELD = "image";
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
  return postForResult(CHECK_ENDPOINT, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, inputType }),
  });
}

// A screenshot or photo: the backend reads its text (OCR in rag) and checks it like typed text (CONTRACT.md §1).
export async function checkImage(image: File): Promise<CheckResult> {
  if (IS_MOCK_MODE) {
    return mockImageCheck();
  }
  const form = new FormData();
  form.append(IMAGE_FORM_FIELD, image, image.name);
  return postForResult(IMAGE_CHECK_ENDPOINT, { body: form });
}

async function postForResult(endpoint: string, init: { headers?: Record<string, string>; body: BodyInit }): Promise<CheckResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: init.headers,
      body: init.body,
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
