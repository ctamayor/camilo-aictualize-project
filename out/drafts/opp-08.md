# Request: automate the nightly El Paso model vs. CARP reconciliation entry

*Email, drafted for opportunity 8: Nightly El Paso (EPE) model vs. CARP reconciliation entry, $216 a month.*

**For:** Real Time Trading Support (from the Portland Real Time desk manager; cc the Real Time night shift traders)

---

To: Real Time Trading Support
Cc: Real Time night shift traders
Subject: Request: nightly job to log the EPE reconciliation automatically

Could you set up a job or macro that runs each night after CARP finishes? It would:
1. Compare the day's El Paso model totals with the CARP report.
2. Write the totals, the result ("no variance" or "variance") and a timestamp into that month's EPE reconciliation file.
3. Email the shift only when there's a variance, listing the hours and deals that differ.

Why: Every night the shift fills in the reconciliation sheet by hand, even when there's nothing to report. Houston reads an empty sheet as a sign that nobody ran CARP. In the first 8 days of July there were no variances at all, but the entry still had to be made each night, and on at least one busy night it was missed. A timestamp written by the job would show Houston that CARP was run, and the traders would only have to explain real variances.

Could you reply with whether this can be done and a rough date? Until the job is running and checked, the shift keeps making the entry by hand as it does now.

Thanks,
Real Time Desk Manager, Portland

---
Background and details (for whoever builds it)

How it works today
- Since July 2001, at the end of each trading day the Real Time shift has to tie out the El Paso model with the CARP report. They log the El Paso totals in the reconciliation spreadsheet on the shared drive and explain any variances.
- The file is kept per month, for example: m://electric/epe/epe01/aug01/epe reconciliation model (with folders like July01, aug01).
- The sheet has to have an entry every night, even when nothing differs. That entry is only there to show that CARP was run.
- The reconciliation itself works well. The July checkout with Settlements took about five minutes, against the five days spent the month before. This request doesn't change the month-end process. It only takes over the nightly manual entry.

What the job should do
- Run after CARP has finished for the trading day.
- Read the day's El Paso model totals and the CARP report, then compare them.
- Write the El Paso totals, the result and a run timestamp into the current month's reconciliation file.
- At month change, create the next month's folder and file following the existing naming pattern.
- If there's a variance, email the shift the hours and deals that differ, leaving a space in the sheet for the trader's explanation.
- If there's no variance, nobody needs to open the sheet.

Questions for Real Time Trading Support
- When does CARP reliably finish each night, so the job can run after it?
- Where are the El Paso model totals and the CARP report read from, and are they in a format a macro can read directly?
- What should happen if the job fails or CARP hasn't run? A suggestion: email the shift so the entry is made by hand and the sheet is never left blank.

Suggested rollout
- For the first couple of weeks, run the job alongside the manual entry and check that the two match.
- After that, the shift stops making the manual entry on no-variance nights and only explains the variances the job flags.

Expected benefit
- About 5 minutes a night, every day: roughly 2.5 hours a month, or about $216 a month. It also removes the risk of a blank sheet caused by a forgotten entry, and the follow-up reminders that come with it.
