import { useState } from "preact/hooks";
import { texts } from "../lib/texts";
import "./MszLogo.scss";

// The official file comes from the organizer (it is not drawn here: the logo contains the state emblem).
// Without public/msz-logo.svg the slot stays empty instead of showing a broken image.
const LOGO_SRC = "/msz-logo.svg";

export function MszLogo({ variant }: { variant: "header" | "footer" }) {
  const [missing, setMissing] = useState(false);
  if (missing) return null;
  return (
    <img
      src={LOGO_SRC}
      alt={texts.mszLogoAlt}
      class={`msz-logo msz-logo--${variant}`}
      onError={() => setMissing(true)}
    />
  );
}
