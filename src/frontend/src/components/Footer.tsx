import { texts } from "../lib/texts";
import "./Footer.scss";
import { ExternalIcon } from "./Icons";
import { MszLogo } from "./MszLogo";

const LINKS = [
  { label: texts.footer.repository, href: texts.footer.repositoryUrl },
  { label: texts.footer.sources, href: texts.footer.sourcesUrl },
  { label: texts.footer.sourcesCatalog, href: texts.footer.sourcesCatalogUrl },
];

export function Footer() {
  return (
    <footer class="footer">
      <div class="footer__inner">
        <div class="footer__about">
          <p>{texts.footer.about}</p>
          <MszLogo variant="footer" />
        </div>
        <ul class="footer__links">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a href={link.href} target="_blank" rel="noopener noreferrer" class="footer__link">
                {link.label}
                <ExternalIcon class="footer__link-icon" />
                <span class="sr-only"> {texts.panel.opensInNewTab}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
