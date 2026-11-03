# Request: one scheduled batch for the month-end basis roll-off calcs (100% for TDS and 50% for V@R)

*Email, drafted for opportunity 9: Month-end basis and index roll-off double calc, $255 a month.*

**For:** Risk system team lead (cc: gas risk lead who sets the roll-off percentages, and the gas desk leads)

---

To: Risk system team lead
Cc: Gas risk lead; gas desk leads

Subject: Request: one scheduled batch for the month-end basis roll-off calcs (100% for TDS and 50% for V@R)

The ask: Please add a roll-off batch job that runs both month-end basis calcs for each gas book in one pass:
1. A 100% prompt-basis calc under a TDS post ID, loaded to TDS automatically.
2. A 50%/50% roll-off calc under the official V@R post ID.
The gas risk lead would enter the roll-off and roll-in percentages once a month as parameters.

Why: On every roll-off night, every gas book administrator now calcs and officializes their book twice. They do it by switching official status by hand, in a fixed order. The batch would end that repeat work. It would also remove the risk of V@R being fed from the wrong post ID.

Could you reply with whether this is feasible and roughly when, so we can run it before the next roll-off? I can walk through the current steps whenever suits you.

---

Background, for whoever builds or reviews this

What book administrators do today, on every roll-off night until indexes are set:
1. Calc the 100% basis calc.
2. Officialize it.
3. Load positions into TDS.
4. Unofficialize.
5. Calc the 50% basis calc.
6. Officialize it.

The 100% calc feeds the TDS download and reports. The 50% calc is the V@R benchmark. For V@R we roll 50% of basis off on one night and 50% the next. We keep running two calcs until indexes are set, so this happens on at least two nights a month and often more. The steps are complex enough that the desk leads have planned classroom training on the roll-off, the curve shift tied to it, where that shows up on the P&L, and which days we roll in index at which percentages.

What changes for book administrators once the batch exists:
- They review the two results the batch produced for their book.
- They run reports off the 100% calc.
- They no longer recalc, officialize, unofficialize or re-officialize by hand.

What the job needs, in short:
- Inputs: the list of gas books, plus the roll-off and roll-in percentages for the month, entered by the gas risk lead.
- For each book: a 100% prompt-basis calc saved under a TDS post ID and loaded to TDS, then a roll-off calc at the set percentages saved under the official V@R post ID.
- Schedule: every roll-off night until indexes are set.

Estimated saving: about 3 hours a month of book administrator time, roughly $255 a month. That is a low estimate. It counts one occurrence a month, while the double calc actually repeats on every roll-off night across all the gas books.

Thanks,
[Gas risk lead]
