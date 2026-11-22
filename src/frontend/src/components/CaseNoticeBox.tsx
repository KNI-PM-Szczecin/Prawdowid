import { texts } from "../lib/texts";
import type { CaseNotice } from "../lib/types";
import "./CaseNoticeBox.scss";

// The text follows the backend status only: nothing says "forwarded" unless the moderator really received the case.
export function CaseNoticeBox({ notices }: { notices: CaseNotice[] }) {
  if (notices.length === 0) return null;
  return (
    <section aria-labelledby="cases-title" class="case-notice">
      <h2 id="cases-title" class="case-notice__title">
        {texts.cases.title}
      </h2>
      <ul class="case-notice__list">
        {notices.map((notice) => (
          <li key={notice.caseId + notice.claimId} class="case-notice__item">
            <p>{texts.cases.reports(notice.reports)}</p>
            <p>{texts.cases.status[notice.status]}</p>
            <p class="case-notice__id">
              {texts.cases.caseNumber}: {notice.caseId.slice(0, 8)}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
