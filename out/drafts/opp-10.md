# Request: nightly report of ERMS curves missing from RisktRAC (to replace our weekly hand check)

*Email, drafted for opportunity 10: Weekly check that new ERMS curves exist in RisktRAC, $215 a month.*

**For:** From the head of Risk Analysis and Reporting to the IT team that supports ERMS, RisktRAC and TAGG, with a copy to the risk leads of the commodity desks

---

Subject: Request: nightly report of ERMS curves missing from RisktRAC

To: IT support for ERMS / RisktRAC / TAGG
Cc: Risk leads, commodity desks

The ask: Please set up a nightly job that compares the curves in ERMS with the curves in RisktRAC and the TAGG mapping. It should email any ERMS curve that has no match to Risk Analysis and Reporting and to the risk lead of the desk that owns the curve.

Why: If a curve isn't set up in RisktRAC, its positions are left out of VaR, so VaR is wrong until someone notices. Right now we only notice through a weekly check done by hand, so a gap can last up to a week. A nightly report would show it the next morning.

Please reply with:
1. Whether this can be done, and who in IT will own it
2. A rough date for a first test run
3. Anything you need from us, such as how to tell which desk owns a curve

Desk risk leads: you don't need to do anything yet. Once the report is running, you'll get an email only when one of your desk's curves is missing from RisktRAC or TAGG. When that happens, please send the curve set-up request form for it.

---

Background, for whoever needs it

How it works today
- When a trader needs a new price curve, the desk's risk management team builds it in ERMS.
- They fill in a curve set-up request form so Risk Analysis and Reporting can set the curve up again in RisktRAC, the system that calculates VaR.
- Separately, they email IT to add the curve to TAGG.
- In the past few months, not everyone has followed this procedure, and forms haven't always been sent. That's why Risk Analysis and Reporting started checking by hand every week that every new ERMS curve is also in RisktRAC. The first check found many ERMS curves that weren't in RisktRAC, and each one has to be worked out with the desk.

What the nightly job should do
- Compare all ERMS curves with the curves in RisktRAC, and with the TAGG mapping.
- List every ERMS curve that has no match in RisktRAC, TAGG or both, and say which system is missing it.
- Send the list each morning to Risk Analysis and Reporting and to the risk lead of the desk that owns each curve.
- If nothing is missing, the email can be skipped or can simply say "no exceptions", whichever is easier.

What changes for us
- Risk Analysis and Reporting stops doing the weekly comparison by hand. We'll work from the short exception list instead.
- Missing curves will show up the next morning rather than up to a week later, so VaR isn't left wrong in the meantime.
- The weekly check takes about 35 minutes each time, which is roughly 2.5 hours a month. This doesn't count the time spent on forms or TAGG requests.

A possible later step (not part of this request)
When a new curve is created in ERMS, it could automatically create the RisktRAC set-up request, filled in from the ERMS curve definition, so nobody has to fill in the form by hand. We'd like to talk about this once the nightly report is running.
