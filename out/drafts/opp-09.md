# Request: set up new ERMS curves in RisktRAC and TAGG automatically, with a nightly gap report

*Email, drafted for opportunity 9: Setting up new forward curves in RisktRAC and TAGG, $202 a month.*

**For:** From the RAR manager to the IT application owners for ERMS and RisktRAC and to the TAGG administrator, cc the desk risk managers

---

To: ERMS application owner; RisktRAC application owner; TAGG administrator
Cc: Desk risk managers

Subject: Request: set up new ERMS curves in RisktRAC and TAGG automatically, with a nightly gap report

What we're asking: Please help us replace the paper curve set-up form, the TAGG request emails and RAR's weekly manual check with one automated job. ERMS would be the master list of curves. When a curve is created in ERMS, the job would create the matching curve in RisktRAC and in TAGG, or queue it for RAR or the TAGG administrator to approve with one click. Each night the job would report any ERMS curve still missing from RisktRAC or TAGG.

Why: Right now a skipped step leaves positions out of V@R. In our first weekly check we "noted numerous curves in ERMS" that were not in RisktRAC. As things stand, "If the curve is not set up in RisktRAC the positions are not captured in the" V@R. The change also frees about 2.4 staff hours a month (about $200 a month).

Next step: Please reply with the person on each system who can say whether a nightly read of new ERMS curves is possible, and whether that read could either load RisktRAC and TAGG directly or feed an approval queue. Once we have those names, we'll set up a short working session to agree on the scope.

---

Background, for whoever needs it

How it works today
1. A desk risk manager builds a new curve in ERMS.
2. To get it into RisktRAC, the risk manager fills in a paper curve set-up request form and sends it to Risk Analysis and Reporting (RAR). RAR then keys the curve into RisktRAC by hand.
3. Separately, the risk manager emails the TAGG administrator to add the curve to TAGG and waits for a reply. Recent examples: "I have added two curves in Publ Names: WY/WELLHEAD and WY/MKTZONE. They are in curveview. Please add them to Tagg." and "I set up these new curves this morning and need them added to Tagg". The reply was "Done."
4. Because steps get skipped, RAR now compares ERMS with RisktRAC by hand every week: "Risk Analysis and Reporting has implemented a new process in which on a weekly basis new curves set up in ERMS are reviewed to ensure that these have been set up in RisktRAC."

What changes
- Risk managers create the curve once in ERMS and send no form and no email.
- The curve is created automatically in RisktRAC and TAGG, or it waits in a queue for one-click approval by RAR (RisktRAC) or the TAGG administrator (TAGG).
- A nightly exception report lists every ERMS curve not yet in RisktRAC or TAGG. RAR and the TAGG administrator only work the items on that report.
- RAR stops the weekly manual comparison.

Points to settle in the working session
- Should new curves load directly, or go to the approval queue first? Is the answer different for RisktRAC and TAGG?
- Which ERMS fields RisktRAC and TAGG need for each curve (the fields the paper form captures today).
- Who receives the nightly exception report, and who clears each item on it.
- Until the job is live, keep the current form and email steps and RAR's weekly check, so no curves are missed in the meantime.

How we estimated the savings
- About 33 minutes each time across the form, re-keying, the TAGG email round trip and the check. The weekly frequency stated by RAR is 4.33 times a month, which comes to about 2.38 hours, or $202.30, a month.
- The mail itself shows this work three times between October and December 2000. We used the stated weekly rate because it is the higher of the two.
- The larger benefit is risk control: positions no longer drop out of V@R because a curve was never set up.
