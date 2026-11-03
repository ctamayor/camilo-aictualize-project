---
name: run-pipeline
description: Run the pipeline over the email archive and report the result. Invoke as /run-pipeline.
---

The pipeline is driven by `py -m pipeline <command>` on Windows, or
`python3 -m pipeline <command>` on macOS and Linux. Run only the commands named
here.

Start with `dashboard`. It starts the dashboard, which follows the run while it
works and shows the ranked results once they exist, and prints its address. Give
the user that address before anything else, so they can watch from the start.

Then run `status`. Its first word says what the output folder holds.

- NONE: there is no earlier run. Go on to `run`.
- RUNNING: another session is running the pipeline on this folder. Tell the user
  and stop, because two runs on one folder would overwrite each other.
- DONE: the earlier run finished, and the dashboard you just started shows its
  results. Tell the user, and ask whether they want a new run. If they don't, or
  you cannot ask, stop.
- STOPPED or CHANGED: the earlier run stopped partway, or the corpus has changed
  since it ran. Ask whether to continue it or start over. Continuing repeats
  nothing that is done. If you cannot ask, continue.

A new run or a fresh start throws away the earlier results and pays for every
model call again, so say so when you ask. Before either, run `reset`.

Then run `run` in the background, since it takes about half an hour, longer than
a shell call may last, and wait until it ends without checking on it. Its last
line is the status, `DONE` or `FAILED <reason>`. When it ends, tell the user in a
sentence whether it finished or failed, with the reason if it failed, give the
dashboard address, and stop.
