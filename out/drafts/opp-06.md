# Request: book Canadian-settled EnronOnline deals straight to FT-US/CAND-ERMS, plus a nightly exceptions report

*Email, drafted for opportunity 6: Monthly hunt for Enron Canada (ECC) deals in Houston books before NYMEX invoicing, $298 a month.*

**For:** To: EnronOnline booking-rules owner and the risk systems/reporting owner. Cc: Calgary settlements lead, Houston risk controllers and book administrators.

---

Hello,

I'm asking for two changes so we can stop the monthly search of every Houston book for ECC deals before NYMEX invoicing:

1. **EnronOnline booking rule (booking-rules owner):** We already have a rule that books TransCanada Energy and Dynegy Canada deals to settle with ECC. Please extend it so these deals go straight into FT-US/CAND-ERMS:
   - every deal where ECC is the settling Enron entity, and
   - every deal with a counterparty on a list of Canadian-settled parties that we will keep up to date. The list starts with Duke Energy Marketing LP and Aquila Canada Corp.
2. **Nightly exceptions report (reporting owner):** Please build a standard report that runs every night. It should list any of these deals sitting in a book other than FT-US/CAND-ERMS, grouped by book owner, and go to each book owner and to Calgary settlements.

**Why:** EnronOnline deals land in Houston books automatically, so the same mistake comes back every month. Invoicing for both ECC and ENA waits until every controller has searched and moved ("flipped") their deals. Deals the search misses are left off the Canadian invoice. In March, at least 10 deals were missing from the April 2001 NYMEX invoice.

**What I need back:** a yes or no on each item, who will own it, and a rough date. Please also tell us who should keep the counterparty list up to date.

Thanks,
[Houston risk controller]

---

**Background, for anyone who needs it**

**How it works today**
- Around each NYMEX close, Calgary settlements emails 5 to 8 Houston risk controllers. The email asks them to search all their books for deals that settle between ECC and an outside counterparty and flip them to FT-US/CAND-ERMS, usually by end of day.
- The request is then forwarded to 5 to 7 book administrators, and each one checks their own books.
- Some deals with Canadian parties are entered as ENA deals, and the search misses them completely. One email said these should have been "TAGG as ECC deals."
- One controller built a private calc to find these deals, and others have asked to copy it. Item 2 would turn that calc into a report everyone gets.

**What changes**
- Most Canadian-settled deals would be booked correctly from the start (item 1).
- Each night, book owners would get a short list of any deals that still land in the wrong book, and they move those as they appear (item 2).
- The monthly all-books request, the forwarding chain and the end-of-day rush at NYMEX close would all go away. ECC and ENA invoicing would no longer wait on the search.

**What it saves**
- This request went out 8 times between October 2000 and March 2001, which works out to about 1.17 times a month.
- Each round takes about 180 minutes, so the total is about 3.51 hours a month, or roughly $298.35 a month.
- That figure doesn't count delayed invoicing or deals missing from the Canadian invoice.

**Open points to settle**
- Who owns the Canadian-settled counterparty list, and how parties get added to it.
- Whether the nightly report should also flag ENA-entered deals with counterparties on the list. These are the ones today's search misses.
