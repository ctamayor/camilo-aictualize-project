# Request: book all ECC counterparty deals to FT-US/CAND-ERMS automatically and run a nightly exception report

*Email, drafted for opportunity 4: Monthly search of Houston books for Enron Canada (ECC) deals, $365 a month.*

**For:** EnronOnline contact who set up the automatic ECC booking for TransCanada Energy and Dynegy Canada, and the Tagg reporting owner. Copy: Calgary settlements (ECC) and the Houston book administrators' lead.

---

Subject: Book all ECC counterparty deals to FT-US/CAND-ERMS automatically, plus a nightly exceptions report

To: EnronOnline contact for automatic deal booking; Tagg reporting owner
Cc: Calgary settlements (ECC); Houston book administrators' lead

I have two requests. Together they would end the monthly search of every Houston book for ECC deals, which currently holds up NYMEX invoicing for both ECC and ENA.

1. EnronOnline: EOL already books TransCanada Energy and Dynegy Canada deals to settle with ECC. Please apply the same rule to every counterparty ECC has a master agreement with, starting with Duke Energy Marketing and Aquila Canada Corp, so those deals go into FT-US/CAND-ERMS when they are booked. I'll send the full counterparty list separately.

2. Tagg: Please save the calc we already use to find these deals as a query that runs every night. It should email Calgary settlements and the administrator of the book involved a list of any deal with ECC or a listed Canadian counterparty that is sitting outside FT-US/CAND-ERMS. That includes deals booked as ENA. The book administrator moves the deal the next morning.

Could you each reply by the end of this week with whether this can be done and a likely start date? We'd like it working before the next NYMEX close.

Thanks,
[Name], [Role]

---

Background, for anyone who needs it

How it works today
- Before each month's NYMEX invoicing, Calgary settlements searches the Houston books, makes a list of the ECC deals it finds there and emails 6 to 8 Houston staff. The email asks them to go through all their books and move ECC deals to FT-US/CAND-ERMS. That request is then forwarded to 5 to 7 book administrators, and each of them searches their own books.
- Invoicing for both ECC and ENA waits until this is finished: "Invoicing for November should start today, and both ECC and ENA are held back from invoicing until these deals are fixed."
- Most of the misplaced deals come from EnronOnline: "These are all EnronOnline deals so they were put into this book automatically." That's why a booking rule fixes the cause.

Why searching by hand still misses deals
- Only TransCanada Energy and Dynegy Canada are covered by the EOL rule today. Setting up the same rule for Duke was discussed with EOL but hasn't happened yet.
- Deals booked as ENA with a Canadian counterparty don't show up in Tagg as ECC deals, so they're missed by the search and need a second round of requests. In March: "I'm missing at least 10 deals from the April 2001 Nymex invoice." This is why the nightly query has to check the counterparty, not just whether a deal is marked ECC.
- A calc that finds these deals already exists, but people pass it around one at a time. Running it nightly for everyone replaces all the separate manual searches.

What changes
- No more month-end request asking everyone to search their books. Any deal that slips past the booking rule is caught within a day and fixed by the administrator of its book.
- NYMEX invoicing for ECC and ENA can start on time.
- Estimated saving: about 220 minutes per round, about 1.17 rounds a month (8 rounds between October 2000 and March 2001). That's roughly 4.3 hours, or about $365, a month, not counting the time saved by not delaying invoicing.

Before go-live
- Calgary settlements confirms the full list of ECC master-agreement counterparties.
- EOL confirms the rule covers every counterparty on the list.
- Tagg reporting confirms the nightly email goes to Calgary settlements and to the right administrator for each book.
- Book administrators confirm they'll move flagged deals the next morning.
