import { useState } from "preact/hooks";
import { IS_MOCK_MODE } from "../lib/api";
import { MAX_INPUT_LENGTH } from "../lib/input";
import { MOCK_EXAMPLES } from "../lib/mockResults";
import { texts } from "../lib/texts";

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
    <div class="mx-auto max-w-4xl px-4 py-12 sm:px-8 sm:py-20">
      <h1 id="main-heading" tabIndex={-1} class="text-center text-4xl font-medium leading-tight sm:text-6xl">
        {texts.form.title}
      </h1>

      <form
        class="mt-10"
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
          class="block w-full resize-y rounded-2xl border-2 border-line bg-page p-4 text-xl text-ink placeholder:text-ink-soft focus:border-ink"
        />
        <div class="mt-2 flex flex-wrap items-start justify-between gap-2">
          <p id="check-count" class={length > MAX_INPUT_LENGTH ? "font-semibold text-negative-strong" : "text-ink-soft"}>
            {texts.form.charCount(length, MAX_INPUT_LENGTH)}
          </p>
          <p class="text-ink-soft">{texts.form.shortcutHint}</p>
        </div>
        {validationError && (
          <p id="check-error" role="alert" class="mt-2 text-lg font-semibold text-negative-strong">
            {validationError}
          </p>
        )}
        <button
          type="submit"
          class="mt-4 w-full rounded-xl bg-ink px-6 py-4 text-xl font-semibold text-page hover:opacity-90 sm:w-auto"
        >
          {texts.form.submit}
        </button>
        <p id="check-note" class="mt-4 text-lg text-ink-soft">
          {texts.form.note}
        </p>
      </form>

      {IS_MOCK_MODE && (
        <section aria-labelledby="examples-title" class="mt-10">
          <h2 id="examples-title" class="text-2xl font-medium">
            {texts.form.examplesTitle}
          </h2>
          <ul class="mt-4 flex flex-wrap gap-3">
            {MOCK_EXAMPLES.map((example) => (
              <li key={example.label}>
                <button
                  type="button"
                  onClick={() => onChange(example.input)}
                  class="rounded-full border-2 border-line px-4 py-2 text-lg hover:border-ink"
                >
                  {example.label}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="how-title" class="mt-14">
        <h2 id="how-title" class="text-3xl font-medium">
          {texts.howItWorks.title}
        </h2>
        <ol class="mt-4 list-decimal space-y-2 pl-6 text-lg">
          {texts.howItWorks.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
    </div>
  );
}
