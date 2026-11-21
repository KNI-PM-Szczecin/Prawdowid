import { useEffect, useRef } from "preact/hooks";
import { TEXT_SCALES, type AccessibilitySettings, type ContrastMode } from "../lib/accessibilitySettings";
import { texts } from "../lib/texts";
import "./AccessibilityPanel.scss";
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
    <dialog ref={dialogRef} onClose={onClose} aria-labelledby="accessibility-title" class="accessibility-panel">
      <div class="accessibility-panel__header">
        <h2 id="accessibility-title" class="section-title">
          {texts.accessibility.title}
        </h2>
        <button type="button" onClick={onClose} aria-label={texts.accessibility.close} class="icon-button">
          <CrossIcon />
        </button>
      </div>
      <p class="accessibility-panel__description">{texts.accessibility.description}</p>

      <fieldset class="accessibility-panel__group">
        <legend class="accessibility-panel__legend">{texts.accessibility.contrast}</legend>
        <div class="accessibility-panel__options">
          {CONTRAST_OPTIONS.map((option) => (
            <label key={option.value} class="accessibility-panel__option">
              <input
                type="radio"
                name="contrast"
                value={option.value}
                checked={settings.contrast === option.value}
                onChange={() => onChange({ contrast: option.value })}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset class="accessibility-panel__group">
        <legend class="accessibility-panel__legend">{texts.accessibility.textSize}</legend>
        <div class="accessibility-panel__options accessibility-panel__options--grid">
          {TEXT_SCALES.map((scale) => (
            <label key={scale} class="accessibility-panel__option">
              <input
                type="radio"
                name="text-scale"
                value={scale}
                checked={settings.textScale === scale}
                onChange={() => onChange({ textScale: scale })}
              />
              {scale}%
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset class="accessibility-panel__group">
        <legend class="accessibility-panel__legend">{texts.accessibility.motion}</legend>
        <label class="accessibility-panel__option">
          <input
            type="checkbox"
            checked={settings.reduceMotion}
            onChange={(event) => onChange({ reduceMotion: event.currentTarget.checked })}
          />
          {texts.accessibility.reduceMotion}
        </label>
      </fieldset>

      <button type="button" onClick={onReset} class="button button--primary accessibility-panel__reset">
        {texts.accessibility.reset}
      </button>
    </dialog>
  );
}
