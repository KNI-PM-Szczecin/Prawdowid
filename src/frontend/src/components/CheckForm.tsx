import { useRef, useState } from "preact/hooks";
import { IS_MOCK_MODE } from "../lib/api";
import { MAX_IMAGE_BYTES, MAX_INPUT_LENGTH, SUPPORTED_IMAGE_TYPES } from "../lib/input";
import { MOCK_EXAMPLES } from "../lib/mockResults";
import { texts } from "../lib/texts";
import "./CheckForm.scss";

interface CheckFormProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onSubmitImage: (image: File) => void;
}

export function CheckForm({ value, onChange, onSubmit, onSubmitImage }: CheckFormProps) {
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const length = value.trim().length;

  const submit = () => {
    if (length === 0) {
      setValidationError(texts.form.empty);
      return;
    }
    if (length > MAX_INPUT_LENGTH) {
      setValidationError(texts.form.tooLong(MAX_INPUT_LENGTH));
      return;
    }
    setValidationError(null);
    onSubmit(value);
  };

  // The picture is checked right after it is chosen: one step for a citizen on a phone (brief scenario F).
  const submitImage = (image: File | undefined) => {
    if (!image) return;
    if (!SUPPORTED_IMAGE_TYPES.has(image.type)) {
      setValidationError(texts.form.imageBadType);
      return;
    }
    if (image.size > MAX_IMAGE_BYTES) {
      setValidationError(texts.form.imageTooLarge);
      return;
    }
    setValidationError(null);
    onSubmitImage(image);
  };

  return (
    <div class="check-form">
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <label for="check-input" class="sr-only">
          {texts.form.label}
        </label>
        <textarea
          id="check-input"
          value={value}
          onInput={(event) => onChange(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={texts.form.placeholder}
          rows={5}
          aria-describedby="check-note check-count"
          aria-invalid={validationError !== null}
          aria-errormessage={validationError ? "check-error" : undefined}
          class="check-form__input"
        />
        <div class="check-form__meta">
          <p id="check-count" class={length > MAX_INPUT_LENGTH ? "check-form__count--over" : undefined}>
            {texts.form.charCount(length, MAX_INPUT_LENGTH)}
          </p>
          <p>{texts.form.shortcutHint}</p>
        </div>
        {validationError && (
          <p id="check-error" role="alert" class="check-form__error">
            {validationError}
          </p>
        )}
        <div class="check-form__actions">
          <button type="submit" class="button button--primary button--large check-form__submit">
            {texts.form.submit}
          </button>
          <input
            ref={fileInputRef}
            id="check-image"
            type="file"
            accept={[...SUPPORTED_IMAGE_TYPES].join(",")}
            class="sr-only"
            aria-describedby="check-image-hint"
            onChange={(event) => {
              submitImage(event.currentTarget.files?.[0]);
              event.currentTarget.value = "";
            }}
          />
          <button
            type="button"
            class="button button--secondary button--large check-form__image"
            onClick={() => fileInputRef.current?.click()}
          >
            {texts.form.imageButton}
          </button>
        </div>
        <p id="check-image-hint" class="check-form__note">
          {texts.form.imageHint}
        </p>
        <p id="check-note" class="check-form__note">
          {texts.form.note}
        </p>
      </form>

      {IS_MOCK_MODE && (
        <section aria-labelledby="examples-title" class="check-form__examples">
          <h2 id="examples-title" class="check-form__examples-title">
            {texts.form.examplesTitle}
          </h2>
          <ul class="check-form__example-list">
            {MOCK_EXAMPLES.map((example) => (
              <li key={example.label}>
                <button type="button" onClick={() => onChange(example.input)} class="check-form__example">
                  {example.label}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
