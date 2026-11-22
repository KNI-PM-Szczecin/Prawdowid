import { texts } from "../lib/texts";
import type { CaseNotice, CaseStatus } from "../lib/types";
import "./CaseNoticeBox.scss";

// Most advanced first: a forwarded case is the news, a logged one the default.
const STATUS_ORDER: CaseStatus[] = ["forwarded", "recommended", "logged"];
const CASE_NUMBER_LENGTH = 8;

// One box for all claims of a check. The text follows the backend status only: nothing says "forwarded"
// unless the moderator really received the case.
export function CaseNoticeBox({ notices }: { notices: CaseNotice[] }) {
  if (notices.length === 0) return null;
  const statuses = STATUS_ORDER.filter((status) => notices.some((notice) => notice.status === status));
  const mostReports = Math.max(...notices.map((notice) => notice.reports));
  return (
    <section aria-labelledby="cases-title" class="case-notice">
      <h2 id="cases-title" class="case-notice__title">
        {texts.cases.title(notices.length)}
      </h2>
      <p>{mostReports > 1 ? texts.cases.repeated(mostReports, notices.length) : texts.cases.firstReport(notices.length)}</p>
      {statuses.map((status) => (
        <p key={status}>{texts.cases.status[status](notices.filter((notice) => notice.status === status).length)}</p>
      ))}
      <p class="case-notice__id">
        {texts.cases.caseNumbers(notices.length)}:{" "}
        {notices.map((notice) => notice.caseId.slice(0, CASE_NUMBER_LENGTH)).join(", ")}
      </p>
    </section>
  );
}
