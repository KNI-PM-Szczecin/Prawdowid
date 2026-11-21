import { texts } from "../lib/texts";
import "./LoadingView.scss";

export function LoadingView() {
  return (
    <div class="loading-view" role="status" aria-live="polite">
      <span class="loading-view__spinner" aria-hidden="true" />
      <h1 class="loading-view__title">{texts.loading.title}</h1>
      <p class="loading-view__text">{texts.loading.description}</p>
    </div>
  );
}
