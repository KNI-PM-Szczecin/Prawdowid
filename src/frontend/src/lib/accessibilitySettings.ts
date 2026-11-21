import { useEffect, useState } from "preact/hooks";

export type ContrastMode = "default" | "high-light" | "high-dark";

export const TEXT_SCALES = [100, 125, 150, 200] as const;
export type TextScale = (typeof TEXT_SCALES)[number];

export interface AccessibilitySettings {
  contrast: ContrastMode;
  textScale: TextScale;
  reduceMotion: boolean;
}

const STORAGE_KEY = "prawdowid.accessibility.v1";
const DEFAULT_TEXT_SCALE: TextScale = 100;

function systemDefaults(): AccessibilitySettings {
  const prefersMoreContrast = window.matchMedia("(prefers-contrast: more)").matches;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  let contrast: ContrastMode = "default";
  if (prefersMoreContrast) {
    contrast = prefersDark ? "high-dark" : "high-light";
  }
  return {
    contrast,
    textScale: DEFAULT_TEXT_SCALE,
    reduceMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  };
}

function loadSettings(): AccessibilitySettings {
  const defaults = systemDefaults();
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored ? { ...defaults, ...(JSON.parse(stored) as Partial<AccessibilitySettings>) } : defaults;
  } catch (error) {
    console.warn("Accessibility settings could not be read, using defaults", error);
    return defaults;
  }
}

function saveSettings(settings: AccessibilitySettings): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.warn("Accessibility settings could not be saved", error);
  }
}

function applySettings(settings: AccessibilitySettings): void {
  const root = document.documentElement;
  root.dataset.contrast = settings.contrast;
  root.dataset.reduceMotion = String(settings.reduceMotion);
  root.style.fontSize = `${settings.textScale}%`;
}

export function useAccessibilitySettings() {
  const [settings, setSettings] = useState<AccessibilitySettings>(loadSettings);

  useEffect(() => {
    applySettings(settings);
    saveSettings(settings);
  }, [settings]);

  const update = (changes: Partial<AccessibilitySettings>) => setSettings((current) => ({ ...current, ...changes }));
  const reset = () => setSettings(systemDefaults());

  return { settings, update, reset };
}
