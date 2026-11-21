import { useEffect, useRef } from "preact/hooks";
import { TEXT_SCALES, type AccessibilitySettings, type ContrastMode } from "../lib/accessibilitySettings";
import { texts } from "../lib/texts";
import { CrossIcon } from "./Icons";

interface AccessibilityPanelProps {
  open: boolean;
  settings: AccessibilitySettings;
  onChange: (changes: Partial<AccessibilitySettings>) => void;
  onReset: () => void;
  onClose: () => void;
}

const CONTRAST_OPTIONS: { value: ContrastMode; label: string }[] = [
  { value: "default", label: texts.accessibility.contrastDefault },
  { value: "high-light", label: texts.accessibility.contrastHighLight },
  { value: "high-dark", label: texts.accessibility.contrastHighDark },
];

const OPTION_CLASS =
  "flex cursor-pointer items-center gap-3 rounded-md border-2 border-line px-4 py-3 text-lg has-[:checked]:border-ink has-[:checked]:font-semibold";

export function AccessibilityPanel({ open, settings, onChange, onReset, onClose }: AccessibilityPanelProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      aria-labelledby="accessibility-title"
      class="m-0 ml-auto h-full max-h-none w-full max-w-md overflow-y-auto bg-page p-6 text-ink backdrop:bg-black/50 sm:p-8"
    >
      <div class="flex items-start justify-between gap-4">
        <h2 id="accessibility-title" class="text-2xl font-semibold">
          {texts.accessibility.title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={texts.accessibility.close}
          class="rounded-md border-2 border-ink p-2 hover:bg-neutral-soft"
        >
          <CrossIcon class="h-6 w-6" />
        </button>
      </div>
      <p class="mt-3 text-lg">{texts.accessibility.description}</p>

      <fieldset class="mt-6">
        <legend class="mb-3 text-xl font-semibold">{texts.accessibility.contrast}</legend>
        <div class="flex flex-col gap-2">
          {CONTRAST_OPTIONS.map((option) => (
            <label key={option.value} class={OPTION_CLASS}>
              <input
                type="radio"
                name="contrast"
                value={option.value}
                checked={settings.contrast === option.value}
                onChange={() => onChange({ contrast: option.value })}
                class="h-5 w-5 accent-current"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset class="mt-6">
        <legend class="mb-3 text-xl font-semibold">{texts.accessibility.textSize}</legend>
        <div class="grid grid-cols-2 gap-2">
          {TEXT_SCALES.map((scale) => (
            <label key={scale} class={OPTION_CLASS}>
              <input
                type="radio"
                name="text-scale"
                value={scale}
                checked={settings.textScale === scale}
                onChange={() => onChange({ textScale: scale })}
                class="h-5 w-5 accent-current"
              />
              {scale}%
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset class="mt-6">
        <legend class="mb-3 text-xl font-semibold">{texts.accessibility.motion}</legend>
        <label class={OPTION_CLASS}>
          <input
            type="checkbox"
            checked={settings.reduceMotion}
            onChange={(event) => onChange({ reduceMotion: event.currentTarget.checked })}
            class="h-5 w-5 accent-current"
          />
          {texts.accessibility.reduceMotion}
        </label>
      </fieldset>

      <button
        type="button"
        onClick={onReset}
        class="mt-8 w-full rounded-md bg-ink px-4 py-3 text-lg font-semibold text-page hover:opacity-90"
      >
        {texts.accessibility.reset}
      </button>
    </dialog>
  );
}
