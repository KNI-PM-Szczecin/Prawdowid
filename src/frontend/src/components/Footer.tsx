import { texts } from "../lib/texts";
import "./Footer.scss";
import { ExternalIcon } from "./Icons";

export function Footer() {
  return (
    <footer class="footer">
      <div class="footer__inner">
        <p class="footer__about">{texts.footer.about}</p>
        <a href={texts.footer.repositoryUrl} target="_blank" rel="noopener noreferrer" class="footer__link">
          {texts.footer.repository}
          <ExternalIcon class="footer__link-icon" />
          <span class="sr-only"> {texts.panel.opensInNewTab}</span>
        </a>
      </div>
    </footer>
  );
}
