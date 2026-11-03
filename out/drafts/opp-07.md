# Request: fill origination schedule entries from TAGG by deal number

*Email, drafted for opportunity 7: Daily origination schedule entries on the gas desks, $246 a month.*

**For:** From the gas desks' origination schedule coordinator to the person who supports TAGG reporting and the desk spreadsheets, with the lead book administrators on each gas desk copied

---

To: TAGG reporting / desk spreadsheet support
Cc: Lead book administrators, gas desks
Subject: Request: fill origination schedule entries from TAGG by deal number

Can you build two things for the gas desks' origination schedule?

1. A lookup keyed on deal number. When a book administrator types a deal number, it fills in Book, Date originated, Customer, B/S, Term, Price and Pub code from TAGG. It can be a spreadsheet macro or a TAGG extract, whichever is easier for you.
2. A daily extract of the Middle Market (NYMEX) group's TAGG deals. It adds any deal that isn't on the schedule yet, with $0 origination.

Why: Since January every entry needs 11 fields. Seven of them describe the deal and are already in TAGG, but admins type them in again by hand. Admins also have to type in every Middle Market deal just to record $0. We estimate the change saves about 8 minutes a working day, which is roughly 2.9 hours or $245 a month across the desks. It also cuts down on retyping errors in a schedule that feeds a daily report and is checked against each book's P&L every day.

Could you tell me by the end of the week whether this can be done, and which way (macro or extract) you'd go?

Lead book administrators: please reply with roughly how many entries your desk makes on a typical day. The estimate above assumes about five a day across all desks, and we have no actual count.

---------------------------------------------
Background and details (for whoever builds it)

How the schedule is filled in today
- Book administrators on each gas desk record every originated deal by hand in the origination schedule (the "origination file").
- From 9 January 2001, the Middle Market (NYMEX) group has received a daily report built from the schedule. That raised the fields per entry from seven to eleven:
  - Original fields: Book, Deal #, Date originated, Customer, Origination Group, Origination Value, Originator
  - Added fields, in this order: B/S, Term, Price, Pub code
- From 10 January 2001, every deal that group does must be on the schedule, including deals with no origination granted. Those get $0.
- Origination requests come in by deal number (for example, "The deal is HS Energy and the Deal number is V58190"). The admin then looks up the deal details and types them in.
- The schedule is kept up daily, and each book's P&L is checked against it every day. Past breaks include one desk recognizing origination that wasn't on the schedule, and another not recognizing part of an amount it had been granted.

What the admin would do after the change
1. Type the deal number. Book, Date originated, Customer, B/S, Term, Price and Pub code fill in from TAGG.
2. Type Origination Value, Origination Group and Originator.
3. Check the filled fields against the deal.
4. For Middle Market deals added by the daily extract, change the $0 to the granted amount on any row where origination is granted.

Where each field comes from
- From TAGG via the lookup: Book, Date originated, Customer, B/S, Term, Price, Pub code
- Typed by the admin: Deal #, Origination Value, Origination Group, Originator
- Added by the daily extract (Middle Market group only): any group deal not already on the schedule, with Origination Value set to $0

Requirements
- Keep the current column order, so the daily report built from the schedule doesn't change.
- Don't add an extract row for a deal that's already on the schedule.
- Let admins overwrite filled values if TAGG and the deal confirmation disagree.

Open questions
- How many entries are made per day on each desk? (Lead book administrators, see above.)
- Does the Middle Market (NYMEX) group's daily report need to change in any way once the $0 rows come from the extract instead of being typed in?

How the savings were estimated
8 minutes saved per working day × 21.67 working days a month = 2.89 hours, or $245.65 a month. This uses the stated rate of one round of entries per working day and an assumed volume of about five entries a day. The desk counts requested above will confirm or correct it.
