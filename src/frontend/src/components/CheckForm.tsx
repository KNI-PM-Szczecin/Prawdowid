import { useState } from "preact/hooks";
import { IS_MOCK_MODE } from "../lib/api";
import { MAX_INPUT_LENGTH } from "../lib/input";
import { MOCK_EXAMPLES } from "../lib/mockResults";
import { texts } from "../lib/texts";
import "./CheckForm.scss";

interface CheckFormProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
}

export function CheckForm({ value, onChange, onSubmit }: CheckFormProps) {
  const [validationError, setValidationError] = useState<string | null>(null);
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
        <button type="submit" class="button button--primary button--large check-form__submit">
          {texts.form.submit}
        </button>
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
