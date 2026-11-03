# Notes

## Running it

In Claude Code, type `/run-pipeline`. This will start the run (or use an existing one), start the dashboard, and print its localhost link.

## How it works

To maintain determinism where it matters, python orchestrates. It handles launching and stopping subagents, parsing and deduplication, verifying quotes, calculating hours and dollars, and displaying the dashboard. Agent tools are constrained to only what is necessary for their task.

The run has three stages of agents. 
1. First, 15 readers each read one batch of the mail to identify leads worth investigating. Together they read every message.
2. Then 8 analysts, each paired with a critic, start from the readers' leads and explore the mail for 22 minutes. They propose opportunities which the critics judge and then either reject, suggest ways to improve, or approve. To avoid performing duplicate work, there is a shared record of already investigated opportunities that agents reference.
3. Finally, 10 drafters write an artifact for each of the top 10 opportunities (ranked by recurring monthly cost). The drafters produce whatever kind of artifact would be most effective for beginning the suggested change.

Context is budgeted to optimize efficiency. A reader's batch has a limit of 100K tokens because after testing a larger limit of 200k tokens, there was noticeable context decay that affected outputs. Furthermore, the shared record of already investigated opportunities is kept brief so that it doesn't use too much agent context.

All of the agents within each stage run in parallel, and a re-run repeats nothing that is finished. When mail is added, only the new batches are read for leads and then exploring starts again.

## My development process

I spent around 6 hours on this project, using Claude Code to brainstorm and develop the architecture. The table below sets out where it went wrong and how I dealt with each problem.

| Where Claude Code got it wrong | How I fixed it |
|---|---|
| It overengineered. | I made sure I understood every suggestion before accepting it. Usually, if I could not understand a change, it was not a good one. |
| Its prompts were unclear and unnecessarily illustrative. | I read every prompt line by line and gave specific feedback for prompt revisions. |
| Its revisions were too specific, constraining the agents' reasoning and overfitting to issues seen in trial runs. | I gave the agents more freedom, looked over each suggested revision myself, and pivoted architectures midway. |
| It did not use key performance indicators to refine the system. | I judged thoroughness with metrics, such as messages opened, the sum of the monthly costs found by a run, and by reading the outputs myself. When the analysts opened only about 650 of the 3,200 messages in a 15-minute run, I added an initial stage to read every message, search for leads, and encourage a more complete analysis. |
| Its dashboard was ineffective at conveying information. | I reviewed the dashboard and corrected for simplicity, conciseness, and relevance. |

## Limitations and future work

The cost estimates are the least certain part of the output. I checked that the estimates were reasonable and matched the evidence, but beyond that I took them on faith, and they are likely somewhat inaccurate and arbitrary.

Also, the pipeline is largely nondeterministic. Runs on the same input produce different estimates and different opportunities. The more estimates/opportunities vary from run to run, the less trust we can have in the cost numbers.

With another week, I would experiment more with the variance to learn how much of an issue it is and how to reduce it. This would help me figure out how to make the set of opportunities more complete and cost estimates more accurate. I would also give the subagents more guidance on writing the drafted artifacts, which are verbose, clearly written by AI, and could be more clear.