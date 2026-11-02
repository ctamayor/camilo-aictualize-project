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

Then run `status`, which says whether the output folder already holds a run. A
run in progress means another session is working on it: tell the user and stop,
because two runs on one folder would overwrite each other. An earlier run that
finished, stopped partway, or was made from a corpus that has since changed is
the user's to keep or discard: ask whether to continue it or start over. Continuing
repeats nothing that is done; starting over throws away its results and pays for
every model call again. If you cannot ask, continue it. To start over, run `reset`.

Then run `run` with the longest timeout the shell tool allows. Its last line is
the status. `CONTINUE`: run it again; it resumes where it stopped. `DONE` or
`FAILED <reason>`: report the lines it printed, with the dashboard address, and
stop.
