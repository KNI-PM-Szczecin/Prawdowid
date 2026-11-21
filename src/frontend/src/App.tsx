import { useState } from "preact/hooks";
import { AccessibilityPanel } from "./components/AccessibilityPanel";
import { CheckForm } from "./components/CheckForm";
import { Header } from "./components/Header";
import { LoadingView } from "./components/LoadingView";
import { ResultView } from "./components/ResultView";
import { StatusView, statusCopy } from "./components/StatusView";
import { useAccessibilitySettings } from "./lib/accessibilitySettings";
import { IS_MOCK_MODE, checkInput } from "./lib/api";
import { detectInputType } from "./lib/input";
import { texts } from "./lib/texts";
import type { CheckResult } from "./lib/types";

type View =
  | { kind: "form" }
  | { kind: "loading" }
  | { kind: "result"; result: CheckResult }
  | { kind: "connection_error" };

export function App() {
  const [view, setView] = useState<View>({ kind: "form" });
  const [draft, setDraft] = useState("");
  const [submittedInput, setSubmittedInput] = useState("");
  const [accessibilityOpen, setAccessibilityOpen] = useState(false);
  const accessibility = useAccessibilitySettings();

  const runCheck = async (input: string) => {
    setSubmittedInput(input);
    setView({ kind: "loading" });
    window.scrollTo({ top: 0 });
    try {
      const result = await checkInput(input.trim(), detectInputType(input));
      setView({ kind: "result", result });
    } catch (error) {
      console.error("Check request failed", error);
      setView({ kind: "connection_error" });
    }
  };

  const goHome = () => setView({ kind: "form" });
  const startNewCheck = () => {
    setDraft("");
    goHome();
  };

  return (
    <div class="min-h-screen bg-page text-ink">
      <a
        href="#main"
        class="sr-only rounded-md bg-ink px-4 py-2 text-page focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
      >
        {texts.skipToContent}
      </a>
      <Header onHome={goHome} onOpenAccessibility={() => setAccessibilityOpen(true)} />
      {IS_MOCK_MODE && (
        <p class="border-b-2 border-warning-line bg-warning-soft px-4 py-3 text-center text-lg font-semibold">
          {texts.demoBanner}
        </p>
      )}
      <main id="main" data-tone={view.kind === "result" ? view.result.summary?.level : undefined} class="page-glow">
        {view.kind === "form" && <CheckForm value={draft} onChange={setDraft} onSubmit={runCheck} />}
        {view.kind === "loading" && <LoadingView />}
        {view.kind === "connection_error" && (
          <StatusView
            title={texts.connectionError.title}
            message={texts.connectionError.description}
            onRetry={() => runCheck(submittedInput)}
            onBack={goHome}
          />
        )}
        {view.kind === "result" && view.result.status !== "ok" && (
          <StatusView
            title={statusCopy(view.result).title}
            message={view.result.message ?? texts.status.fallbackMessage}
            note={statusCopy(view.result).note}
            onRetry={statusCopy(view.result).retryable ? () => runCheck(submittedInput) : undefined}
            onBack={goHome}
          />
        )}
        {view.kind === "result" && view.result.status === "ok" && (
          <ResultView result={view.result} submittedInput={submittedInput} onNewCheck={startNewCheck} />
        )}
      </main>
      <AccessibilityPanel
        open={accessibilityOpen}
        settings={accessibility.settings}
        onChange={accessibility.update}
        onReset={accessibility.reset}
        onClose={() => setAccessibilityOpen(false)}
      />
    </div>
  );
}
