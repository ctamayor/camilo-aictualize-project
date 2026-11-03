# Request: macro to tie out the El Paso model against CARP each night and fill in the EPE reconciliation sheet

*Email, drafted for opportunity 4: Nightly El Paso Electric model-vs-CARP tie-out, $388 a month.*

**For:** Real Time Trading Support (from the Portland Real Time desk lead; cc the shift traders who market El Paso Electric)

---

To: Real Time Trading Support
Cc: Real Time shift traders (EPE)
Subject: Request: nightly El Paso model vs. CARP tie-out macro

The ask: please add a comparison tab or macro to the El Paso model. Each night it should read the day's CARP report, compare it with the model, highlight any differences, and write the day's El Paso totals plus a "no variance" or "variance" entry into the monthly EPE reconciliation workbook.

Why: right now the shift trader checks the two by eye and types an entry every night, including nights with nothing to report. Entries get skipped on busy nights, so Houston has no proof the CARP was run, and any differences we miss only show up at the monthly checkout with El Paso and Settlements. Sorting out June 2001 at checkout took five days. Once the macro is in place, the trader only has to explain the items it flags. We estimate this saves about 4.5 hours of trader time a month, and it should also shorten month-end.

Could you reply with a rough date for a first version we can try on one night's data?

---

WHAT THE MACRO NEEDS TO DO

1. Read the day's CARP report and the matching day in the El Paso model.
2. Compare them. The test is the one we already use: the CARP report must EXACTLY match the El Paso model. Highlight every line where they differ.
3. Write a row for the day into the monthly EPE reconciliation workbook with:
   - the date
   - the day's El Paso totals
   - "No variance" or "Variance"
   - an empty explanation cell, which the trader fills in only when the row says "Variance"
4. On a night with no variance, write the row anyway. Houston takes an empty sheet to mean nobody ran the CARP, so every night needs an entry.

Monthly workbook: please set it up as a template with the file path already filled in, so whoever opens a new month doesn't have to re-point the macro. The El Paso models are kept in a folder for each month (for example M:/Electric/EPE/EPE 2002/Models/February02/), so the path will need to change month by month.

Before you build it, please let us know whether the CARP report can be read straight into the spreadsheet or has to be pasted in. Also tell us whether the current totals columns in the reconciliation workbook can stay as they are.

---

THE NIGHTLY STEPS FOR THE SHIFT TRADER (once the macro is live)

1. When the trading day is done, open the El Paso model and run the tie-out.
2. If it reports no variance, you're finished. The entry is already in the monthly workbook.
3. If it flags a variance, check the flagged lines, fix anything in the model that needs fixing (check the spreadsheet formulas), and run it again.
4. For any variance that is still there, type an explanation in that day's row of the reconciliation workbook.

Reconciling the CARP is still a basic requirement of the position. The macro just makes it quicker and makes sure the entry gets written.

---

BACKGROUND (for anyone who needs it)

- How it works today: after the trading day, the EPE shift trader compares the El Paso model and the CARP report by eye. They then log the El Paso totals in a separate monthly EPE reconciliation workbook and explain every variance. The sheet has to be filled in even when nothing differs.
- What we've seen: a review of the first 8 days of July 2001 found no variances at all, but each of those nights still needed an entry typed by hand. On at least one busy night the reconciliation sheet was not done.
- Cost of missed differences: the June 2001 checkout with El Paso and Settlements took about five days to sort out. After the July reconciliation was kept up, the checkout took about five minutes.
- Estimated saving: about 9 minutes a night × 30.42 nights a month = 4.56 hours, or about $387.60 a month. This doesn't count time saved at the month-end checkout.
