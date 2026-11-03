# Request: have SPI tag "no data yet" zeros in the MIPS nightly file as incomplete

*Email, drafted for opportunity 5: Overriding MIPS zero volumes in POPS by hand, $307 a month.*

**For:** Measurement manager (owner of MIPS and the SPI vendor relationship); cc POPS team lead, Pipeline Operations scheduling lead, desk accountant (UA4/P&L)

---

To: Measurement Manager
Cc: POPS Team Lead; Pipeline Operations Scheduling Lead; Desk Accountant
Subject: Request: have SPI tag "no data yet" zeros in the MIPS nightly file as incomplete

What we're asking: Please have SPI change the MIPS nightly file so that a zero sent only because no volume has arrived yet is tagged (i) incomplete. Measurement already named this as the only possible fix. Please ask SPI for a cost and a date this week, and open a work order if one is needed.

Why: Right now these zeros replace Gas Control's estimate in POPS. That takes purchase expense out of the desk P&L and leaves it in UA4 until a scheduler finds the zero and overrides it by hand. This happens about once every working day, about 3.6 hours (around $307) of scheduler time a month. That doesn't count the P&L being wrong or the escalation emails.

Reply needed: whether you'll approve the change, and SPI's cost and date once you have them.

Thanks,
Pipeline Operations Scheduling Lead

---

Background, for anyone who needs it

How it works today
- MIPS gets no volume for outside-measured and bidirectional meters until month-end. Until then its nightly file sends POPS a zero ("systematically, no information equals zero").
- POPS takes that zero as the best available volume (BAV). It overwrites the estimate Gas Control sends, and POPS passes the zero to Sitara.
- If scheduling doesn't catch it, the desk's purchase expense is understated. The volumes "have not been picked up in [the desk's] P&L and are, instead, sitting in UA4."
- To fix it, schedulers find the zeroed meters, get Gas Control's volumes, override POPS and re-allocate the meter.
- A later nightly roll can put the zero back. On 3/21/2000 a meter that had been correct the night before was reset to zero from day 14 onward when the 14th rolled from MIPS, so it had to be fixed again.
- This affects "various bidirectional meters," not just one.

Where it stalls
- The POPS team reported the bug to MIPS and was told it was not a priority, so the hand work goes on.
- Missed zeros have to be escalated by email. Four people wrote about one on 3/21/2000. On 4/4/2000 an override request for Enron Methanol had to be sent twice because the first one, a sticky note, wasn't read as a request. The zero stayed in POPS for an extra day.

What changes after the fix
- POPS keeps Gas Control's estimate as the BAV until a real measured volume arrives.
- Schedulers no longer search for zeroed meters, retype estimates, re-allocate, or redo the work after a nightly roll.
- The desk P&L and UA4 stay correct during the month, and the escalation emails stop.

Savings estimate
- About 10 minutes each time, about once a working day (21.67 times a month) = 3.61 hours = $306.85 a month.
- This is a conservative figure. It doesn't include the time spent correcting the P&L or UA4, or the escalations.

Until the fix is live (Scheduling Lead and POPS team)
1. After each nightly MIPS roll, check the outside-measured and bidirectional meters in POPS for zero volumes.
2. Override any zeros with Gas Control's volumes and re-allocate the meter. Re-check meters you've already corrected, because a later roll can zero them again.
3. Send override requests by email with the meter, the days and "please override" in the subject line. Don't use sticky notes or verbal requests.
