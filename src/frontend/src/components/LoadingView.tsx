import { texts } from "../lib/texts";

export function LoadingView() {
  return (
    <div class="mx-auto max-w-3xl px-4 py-24 text-center sm:px-8" role="status" aria-live="polite">
      <span
        class="mx-auto block h-16 w-16 animate-spin rounded-full border-8 border-line border-t-ink"
        aria-hidden="true"
      />
      <h1 class="mt-8 text-3xl font-semibold">{texts.loading.title}</h1>
      <p class="mt-3 text-xl">{texts.loading.description}</p>
    </div>
  );
}
