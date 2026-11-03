# Request: make the prompt-month roll-off a scheduled setting in the gas risk calc

*Email, drafted for opportunity 3: Month-end basis and index roll-off in the gas risk books, $468 a month.*

**For:** From the gas risk lead to whoever maintains the gas risk calc (risk systems). Cc the gas book administrators and the regional risk leads.

---

To: Risk systems lead (owner of the gas risk calc)
Cc: Gas book administrators; Regional risk leads
Subject: Request: make the prompt-month roll-off a scheduled setting in the gas risk calc

**My request:** Please add a roll-off calendar to the gas risk calc. On roll-off nights, one calc run should write two results:
- the 100% prompt-month basis to the TDS post ID
- the rolled-off basis to the Benchmark/V@R post ID

Please reply with whether this can be done and a date we could test it. If possible, test it before the next prompt-month roll-off.

**Why:** On each roll-off night, every administrator now calculates and officializes basis twice. They follow an email I send each month, and the sequence depends on people remembering it. In November, a missed reminder meant several traders' basis was not rolled off on the Benchmark, so V@R was wrong. The double calc also costs about 5.5 hours of administrator time a month (about $467.50).

---

**Details, for whoever builds or tests it**

What to build:
1. **Roll-off calendar setting, kept by the risk group.** It holds the roll-off dates and percentages for:
   - basis
   - Gas Daily and physical index (roll-off and roll-in)

   The current pattern runs over two nights: 50% of basis rolls off on the first night and 50% on the second. 50% of Gas Daily and physical index positions roll off and roll in each night.
2. **One calc, two post IDs.** On a roll-off night, a single calc writes the 100% prompt-month basis to the TDS post ID and the rolled-off basis to the Benchmark/V@R post ID. Administrators then calculate and officialize once, as on any other night.
3. **Exception check.** After the roll-off night's calc, a list of any book whose Benchmark basis was not rolled, sent to the gas risk lead and the relevant regional lead for follow-up.

What this removes:
- my monthly instruction email to the book administrators
- the second basis calc on each roll-off night
- the steps of unofficializing and officializing again between the two calcs
- relying on reminders between leads and administrators

Today's sequence, which each administrator repeats on both roll-off nights:
1. Calc the 100% basis calc.
2. Officialize.
3. Load positions into TDS.
4. Unofficialize.
5. Calc the 50% basis calc.
6. Officialize (this is the Benchmark used for V@R).

**Until the change is live:** Administrators should keep following the sequence above, and I will keep sending the monthly email. Regional leads: on each roll-off night, please confirm with every administrator in your region that the second calc was done. That step is the one missed in November.

**Savings basis:** about 330 minutes of administrator time per monthly roll-off. That is 5.5 hours a month, or about $467.50.

Thanks,
Gas risk lead
