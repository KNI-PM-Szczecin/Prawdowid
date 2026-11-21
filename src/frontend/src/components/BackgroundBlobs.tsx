import { toneClass, type Tone } from "../lib/presentation";
import "./BackgroundBlobs.scss";

// Decorative colour wash behind the page (Figma): green on the home page, the summary tone on a result.
export function BackgroundBlobs({ tone }: { tone: Tone }) {
  return (
    <div class={`blobs ${toneClass(tone)}`} aria-hidden="true">
      <span class="blobs__blob blobs__blob--top" />
      <span class="blobs__blob blobs__blob--left" />
      <span class="blobs__blob blobs__blob--bottom" />
    </div>
  );
}
