import { useRef, useState } from "preact/hooks";
import { AccessibilityPanel } from "./components/AccessibilityPanel";
import { BackgroundBlobs } from "./components/BackgroundBlobs";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Landing } from "./components/Landing";
import { LoadingView } from "./components/LoadingView";
import { ResultView } from "./components/ResultView";
import { StatusView, statusCopy } from "./components/StatusView";
import { useAccessibilitySettings } from "./lib/accessibilitySettings";
import { IS_MOCK_MODE, checkImage, checkInput } from "./lib/api";
import { detectInputType } from "./lib/input";
import { SUMMARY_TONE, type Tone } from "./lib/presentation";
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

  // What "try again" repeats: the last typed input or the last picture.
  const lastRunRef = useRef<(() => Promise<CheckResult>) | null>(null);

  const runRequest = async (request: () => Promise<CheckResult>) => {
    lastRunRef.current = request;
    setView({ kind: "loading" });
    window.scrollTo({ top: 0 });
    try {
      setView({ kind: "result", result: await request() });
    } catch (error) {
      console.error("Check request failed", error);
      setView({ kind: "connection_error" });
    }
  };

  const runCheck = (input: string) => {
    setSubmittedInput(input);
    return runRequest(() => checkInput(input.trim(), detectInputType(input)));
  };

  const runImageCheck = (image: File) => {
    setSubmittedInput("");
    return runRequest(() => checkImage(image));
  };

  const retryLastRun = () => {
    if (lastRunRef.current) {
      void runRequest(lastRunRef.current);
    }
  };

  const goHome = () => setView({ kind: "form" });
  const startNewCheck = () => {
    setDraft("");
    goHome();
  };

  // Home is green like the Figma landing; a result takes its summary colour; other screens stay neutral.
  let blobTone: Tone = "neutral";
  if (view.kind === "form") {
    blobTone = "positive";
  } else if (view.kind === "result" && view.result.summary) {
    blobTone = SUMMARY_TONE[view.result.summary.level];
  }

  return (
    <div class="app">
      <BackgroundBlobs tone={blobTone} />
      <a href="#main" class="skip-link">
        {texts.skipToContent}
      </a>
      <Header
        onHome={goHome}
        onOpenAccessibility={() => setAccessibilityOpen(true)}
        notice={IS_MOCK_MODE ? texts.demoBanner : null}
      />
      <main id="main">
        {view.kind === "form" && (
          <Landing value={draft} onChange={setDraft} onSubmit={runCheck} onSubmitImage={runImageCheck} />
        )}
        {view.kind === "loading" && <LoadingView />}
        {view.kind === "connection_error" && (
          <StatusView
            title={texts.connectionError.title}
            message={texts.connectionError.description}
            onRetry={retryLastRun}
            onBack={goHome}
          />
        )}
        {view.kind === "result" && view.result.status !== "ok" && (
          <StatusView
            title={statusCopy(view.result).title}
            message={view.result.message ?? texts.status.fallbackMessage}
            note={statusCopy(view.result).note}
            onRetry={statusCopy(view.result).retryable ? retryLastRun : undefined}
            onBack={goHome}
          />
        )}
        {view.kind === "result" && view.result.status === "ok" && (
          <ResultView result={view.result} submittedInput={submittedInput} onNewCheck={startNewCheck} />
        )}
      </main>
      <Footer />
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
