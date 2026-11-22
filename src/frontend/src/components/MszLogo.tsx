import { useState } from "preact/hooks";
import { texts } from "../lib/texts";
import "./MszLogo.scss";

// Current MFA logotype (2022), public domain, from Wikimedia Commons:
// https://commons.wikimedia.org/wiki/File:Ministerstwo_Spraw_Zagranicznych_logo_2022.png
// Commons has no SVG of this version (the SVG there is the logotype used before 2022).
const LOGO_SRC = "/msz-logo.png";

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
