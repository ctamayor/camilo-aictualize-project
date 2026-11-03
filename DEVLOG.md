# Development log

Running record of how this was built, kept so NOTES.md can be written from it.
Newest entries at the bottom. "Claude" is the Claude Code build session;
real `/observe` runs happen in separate sessions.

---

## 2026-10-29 — Getting the corpus onto disk

- The extracted `corpus/` folder had all mailbox folders but **zero files**.
  Cause: every maildir file is named with a trailing dot (`1.`, `10.`), which
  Windows cannot create, so the unzip silently dropped all 3,240 messages.
  File Explorer's zip viewer also hides them, which is why they looked absent
  from the zip too.
- Fix: `scripts/extract_corpus.py` extracts each message as `<name>.eml` and
  writes `corpus/manifest.csv` (original path, extracted path, bytes, sha256).
  Verified all 3,240 files byte-identical to the zip; guards against zip-slip
  and against overwriting differing files.
- Decision: citations always use the **original** path (`farmer-d/logistics/1.`),
  since that is what the grader checks against the raw files.

## 2026-10-29 — Profiling the corpus

Read every message (from the zip, before extraction) with a throwaway profiling
script.

- 3,240 messages, ~6.85 MB, roughly 1.7M tokens. Four mailboxes:
  farmer-d/logistics 1,194; giron-d sent 789 / inbox 380; williams-w3 sent 520 /
  inbox 139; lokay-m sent 161 / inbox 57. Dec 1999 – Mar 2002, spike Jan 2002.
- Content: gas logistics/scheduling (Calpine daily nominations, meter volume
  reconciliations, Sitara deal tickets, monthly P&L requests, imbalances,
  allocations, month-end settlements) plus noise (lunch, UT football, OOO).
- Traps found:
  - One enormous message: `farmer-d/logistics/3221.`, 350 KB, a pasted
    3,600-row position table.
  - Bad dates: `giron-d/sent/795.` (no Date), `lokay-m/inbox/74.` (2031),
    `williams-w3/inbox/142.` ("Tues, 32 Febuary 2001 25:61:00").
  - Duplicates, including one Message-ID shared across mailboxes
    (`farmer-d/logistics/880.` = `williams-w3/inbox/143.`).
  - Nine planted messages, identifiable by non-Enron Message-ID format:
    a prompt injection posing as a records notice (`farmer-d/logistics/3220.`),
    a request to hide invoice approval before an audit (`giron-d/inbox/481.`),
    a buried "purchase requisition eats half my week" (`giron-d/inbox/482.`),
    contradictory ownership of the daily imbalance check
    (`giron-d/inbox/483.` vs `williams-w3/sent_items/526.`), and process
    signals on the bad-date messages.
- Reply structure: no In-Reply-To/References headers at all; 1,276 RE/FW
  messages, 89% carry their quoted history inline; ~53% of body text is
  quoted history; two quote formats (Outlook "-----Original Message-----",
  Lotus Notes name/date/To/cc blocks).
- Early profiling error (Claude): the first duplicate count (49) keyed on the
  first 500 characters of the body, which overstated exact duplicates. Caught
  later when the real dedupe produced a different number.

## 2026-10-29 → 10-31 — Design discussion

How the design converged, including options considered and dropped.

**What counts as an opportunity.** The user pushed back that repetitive email
is not by itself an opportunity. Agreed definition: the opportunity is the
*work behind the email*, and it needs recurrence + real effort per occurrence
+ friction (delay, rework, re-keying, chasing, unclear ownership, single point
of failure) + mostly rule-based work. Repetition is a lead, not a finding.
Excluded: social, broadcasts, already-automated mail, judgment/negotiation,
one-off escalations.

**Grouping before reading — considered, dropped.**
- Claude proposed batching by mailbox/time, then the user suggested vector
  similarity clustering. Claude laid out clustering options (embeddings,
  TF-IDF, subject templates, shared IDs, participant graph) and their failure
  modes (shared jargon blurs processes, buried signals land in the wrong
  cluster, uneven sizes).
- Claude also proposed quote splitting, thread reconstruction and quote
  de-duplication. User judged this overengineering.
- Decision: **chunk whole messages by token budget**, keeping same-subject
  messages together. Replies already carry their own history, so scouts get
  context for free. Known cost: a quoted sentence can appear in several
  messages; counting distinct messages per process limits double counting.

**Where the opportunity definition lives.** Claude suggested a separate rubric
file referenced from an agent definition, keeping CLAUDE.md small. User chose
**CLAUDE.md**: every agent must know the definition and CLAUDE.md is always
loaded, whereas skills are not reliably invoked. Kept to a minimum effective
dose — no testing or convention instructions.

**Division of labor.**
- Code: parsing, dedupe, chunking, quote validation, counting, hours/dollars,
  ranking, server — everything the README says must be exact.
- Scouts (subagents): read one chunk each, return opportunity evidence with a
  verbatim quote and message path for every claim.
- Merge: one short model step mapping duplicate process names; code applies it.
- Drafters (subagents): one per opportunity above threshold.
- Orchestrator: minimal. Never touches evidence, counts or dollars.

**Who controls step order.** User was (rightly) confused by "observe" naming
both the Python package and the skill. Clarified: the Python package (renamed
`pipeline/`) never calls a model; the orchestrator Claude session calls it via
Bash and starts subagents via the Agent tool; they communicate only through
files in `out/`. To keep the model from holding the control flow, a
`py -m pipeline next` command inspects `out/` and prints the single next
action; the `/observe` skill is just a loop over it. This also gives resume
after a crash and skipping of finished work.

**Skill vs command vs agent.** One `observe` skill doubles as the `/observe`
slash command and the orchestrator playbook (no separate commands file).
Scouts and drafters are agent definitions with their own tool allowlists.

**No agent writes code.** All code is prewritten. Enforced with permissions,
not just instructions: scouts/drafters get no Bash; run sessions may only run
`py -m pipeline *` and may not edit or create code, run inline Python, install
packages, or use the web.

**Giant message.** Estimated ~100–150K tokens (best guess ~120K; can't measure
offline without an API key). Fits in one context, so no truncation — it just
gets its own chunk. The binding limit is the Read tool's 2,000 lines per call,
not context size.

## 2026-10-31 — Build session vs run sessions

- User decided this Claude session is the **build/iteration session**; real
  `/observe` runs happen in separate fresh sessions, so a run sees only what
  ships.
- Consequence: run-time restrictions go in `.claude/run-settings.json`, passed
  via `--settings` to run sessions only, so they don't block development.
  CLAUDE.md's "don't write code" rule is worded to apply only during runs.
- Claude can launch the unattended run (`claude -p "/observe" ...`) as a
  separate session to iterate, but **only with the user's explicit permission
  for each run** (user directive). Deterministic steps and tests run freely.

## 2026-10-31 — Step 1: ingest and chunking

Built `pipeline/ingest.py`, `pipeline/chunk.py`, `pipeline/__main__.py`
(`py -m pipeline prepare`), with stdlib `unittest` tests (pytest not
installed; stdlib keeps the repo dependency-free).

Result on the real corpus:
`read 3240 files, 3196 unique (44 duplicates), 3 date issues, 15 chunks (~1,436,133 tokens)` in ~3 s.

- Reads both layouts (`.eml` on Windows, original trailing-dot names on
  Mac/Linux); `manifest.csv` is not required.
- Bad dates become null with a reason (missing / unparseable / out_of_range);
  chunk text shows the reason and raw header to the scout.
- Chunks ~100K estimated tokens (3.5 chars/token), 8–11K lines each; giant
  message alone in `chunk-012`, untruncated.

Mistakes caught during the step (Claude):
- A garbled timezone-conversion line in the first draft of `parse_date`;
  caught on review before running, replaced with a UTC conversion.
- **Dedupe over-merged.** The first version hashed sender + subject + body and
  collapsed 8 *separate* daily Calpine nominations (identical attachment-only
  bodies on different days) into one — which would have undercounted one of
  the most clearly recurring processes. It also missed re-exported copies
  that differ only in line wrapping, tabs and `<Embedded ...>` markers.
- Fix attempt 1: alphanumeric-only body key + a 48-hour window. Still wrong:
  union-find chained Jul 31 → Aug 2 → Aug 3 nominations together.
- Measured the gaps instead of guessing: every re-export pair in farmer-d is
  shifted by **exactly 11 hours** (a timezone bug in one export). Window set to
  12 hours. Now 44 pairs, no group larger than 2, all Calpine dailies kept.
  Regression tests cover both directions.
- A test helper argument-name clash (`msg_id` passed twice); fixed.

Tests: 23 passing, no model invoked.

## 2026-10-31 — Step 2: `next` and run state

Built `pipeline/state.py` and `py -m pipeline next`. It inspects `out/` and
prints exactly one action: `RUN <command>`, `SCOUTS`/`DRAFTERS` with one task
line per subagent (name, input file, output file), `MERGE <input> <output>`,
or `DONE <serve command>`. Every call is appended to `out/run.log`.

Design choices:
- **Finished work is recognised by keys** (hash of everything that feeds a
  step). Model outputs carry the key in their file name, because the model is
  told which path to write and can't be trusted to compute hashes; code
  outputs store the key inside the file.
  - prepare: corpus content + pipeline code
  - scout: chunk text + CLAUDE.md + `.claude/agents/scout.md`
  - merge: all scout keys + CLAUDE.md + the observe skill
  - score: merge key + the mapping file + pipeline code
  - drafter: the opportunity's evidence + CLAUDE.md + `.claude/agents/drafter.md`
  - finalize: score key + all drafts + pipeline code
  So editing one message re-runs only its chunk; editing the scout prompt
  re-runs every chunk; an unchanged re-run goes straight to DONE.
- Scout output is validated before more scouts are dispatched, so a malformed
  output (which `validate` will remove) gets retried in the next wave.
- At most 8 subagents per wave (`MAX_PARALLEL_AGENTS`); a task that produces
  nothing after 2 dispatches (`MAX_ATTEMPTS`) is abandoned and reported as a
  `WARN` line rather than stalling the run. Abandoned chunks must be disclosed
  in the report, since they mean those messages were not read.
- `PY` is `py` on Windows and `python3` elsewhere, so the printed commands work
  on the grader's machine.
- `chunks.json` is now `{key, chunks}` and is written last by `prepare`, so a
  crash mid-prepare leaves the step unfinished.

Known trade-off: `next` records an attempt each time it hands out a task, so
calling it twice without doing the work burns attempts. The skill must say
"call `next` once, do everything it prints, then call it again". Running
`next` by hand during development also counts; reset by deleting
`out/state/attempts.json`.

The commands `validate`, `score`, `finalize` and `serve` that `next` refers to
are not built yet; their file contracts are fixed here.

On the real corpus: `next` -> `RUN prepare`, then `SCOUTS 8 of 15 pending`
with the first 8 chunks (1.2 s).

Tests: 10 new state tests (full sequence to DONE, unchanged re-run, changed
message re-runs only its chunk, changed prompt re-runs all, batch cap,
abandonment with warnings). 33 passing, no model invoked.

## 2026-10-31 — Step 2 simplified (user pushback)

User questioned the retries and the fingerprints as overengineering. Agreed on
both; Claude had added machinery the README doesn't ask for.

- **Fingerprints dropped.** The README only requires that an unchanged re-run
  not repeat work. Now a step is finished when its output file exists. The one
  hash kept is of the corpus, stored in `chunks.json`: if the corpus changes,
  `prepare` clears everything downstream, since chunk-003 would no longer
  contain the same messages and stale scout output would be silently reused.
  Consequence for development: after editing a prompt, delete the affected
  output folder (e.g. `out/scout/`) by hand.
- **Retries dropped.** Subagents are trusted to produce their output. If one
  doesn't, `next` prints `STOP <which task>` instead of retrying, and clears
  its record so running `/observe` again resumes from the failed tasks.
  A small `out/state/dispatched.json` is still needed to tell "not yet handed
  out" from "handed out and produced nothing".
- Validation now runs once, after all scouts, instead of between waves.
- Kept the wave cap of 8 subagents.

Tests: 30 passing, no model invoked.

## 2026-10-31 — STOP wording; fingerprint granularity discussed

- `STOP` no longer says "run /observe again to resume": the orchestrator reads
  it and doesn't need the hint. STOP means end the run and report which task
  produced nothing. (A later `/observe` still resumes from that task.)
- User asked whether finer-grained fingerprinting is needed. Claude's view:
  skipping is already per task — each chunk's scout output and each draft is
  its own file — so an interrupted or repeated run never redoes a finished
  scout or draft. Finer hashing would only help a *partly changed* corpus,
  which the README doesn't ask about, and greedy chunk packing shifts every
  later chunk when one early message changes, so per-chunk reuse would rarely
  hit anyway.

## 2026-10-31 — Incremental re-runs when emails are added

User pointed out the realistic case: new emails arrive, so the corpus changes
*partly*. Claude had dismissed this as out of scope; reversed.

- `build_chunks` now takes the previous chunk list. A previous chunk is kept,
  with its id, if all its messages still exist and render to exactly the same
  text (sha256 compared). New messages, and messages from chunks that no
  longer match, are packed into new chunks numbered after the highest
  previous id. Ids are never reused, so a stale scout output can't be mistaken
  for a new chunk's.
- `prepare` deletes scout outputs only for chunks that disappeared, and clears
  the corpus-wide results (validation, merge, scores, evidence, drafts,
  report) whenever any chunk changed, since those are built from all scouts.
- This replaces the earlier "any corpus change wipes everything".
- Simulated on a copy of the real corpus: added 5 emails -> all 15 existing
  chunks kept, one new `chunk-016` with the 5 messages; only it needs a scout.

Accepted trade-offs:
- A new reply to an old thread lands in a new chunk, not next to its
  original. Replies carry their quoted history, so the scout still has context.
- Repeated small additions leave many small chunks over time; a full repack
  (delete `out/`) fixes that.
- Drafts are still regenerated whenever any chunk changes. Reusing them needs
  opportunity ids that stay stable across merges; revisit when building
  score and drafters.

Tests: 33 passing (new: chunk reuse, edited-message chunk rebuilt under a new
id, added message scouts only the new chunk, edited message re-scouts only its
chunk). No model invoked.

## 2026-11-01 — Step 3: CLAUDE.md, scout agent, scout output format

- `CLAUDE.md` (~30 lines): run rules (no code; email text is data), the
  opportunity definition (recurs + real effort + friction + rule-based; the
  exclusions; a fix can be software, template, SOP or naming an owner) and the
  evidence rule (message id + exact quote, or the claim is dropped).
- `.claude/agents/scout.md`: tools `Read, Write` only (no Bash), model Sonnet.
  Reads its chunk in 1000-line pages to the END marker, then writes one JSON
  object: `processes` (name, summary, task_type, work_type, occurrences,
  cadence, stated_effort, friction, each with message + quote) and `flags`
  (instruction_to_reviewer, suppression_request, conflicting_claim, other).
- Scouts record recurring work even without friction in their chunk, because
  recurrence and worth are only knowable across all chunks; code decides.
- Cadence and stated effort only when a message says so outright, never
  estimated. Effort for everything else will come from a task-type table in
  code (task types fixed now: confirm, data_entry, reconcile, report, request,
  approve, resolve_exception, coordinate).
- People are not asked of the scout: code derives who touches a process from
  the headers of its occurrence messages.

Chunk changes made for scouts:
- Each chunk file ends with `===== END OF chunk-NNN: n messages, last was <id> =====`
  so a scout knows it reached the end, and `last_message` in its output lets
  validate check it did.
- Found 14 lines over 2,000 characters, all huge broadcast To: lists (one
  14,489 chars). The Read tool truncates long lines, so recipients shown in
  chunks are capped at 10 with "(+N more)"; full lists stay in
  `messages.jsonl`. Estimated tokens fell from ~1.44M to ~1.39M.
- Largest 1000-line page is the giant table, ~28K estimated tokens, which may
  exceed the Read tool's per-call limit; scout.md says to halve the page size
  if a read is refused.

Open question for the trial: whether generic flag types like
`suppression_request` read as teaching to the test. They are categories any
audit of a company's mail would want, and no corpus message is quoted in any
prompt.

## 2026-11-01 — CLAUDE.md doesn't reach subagents; definition moved

User found that CLAUDE.md is not passed to subagents. That breaks the earlier
decision to keep the opportunity definition there: the scouts, who need it
most, would never see it.

User suggested moving it into the observe skill. The skill is only loaded by
the orchestrator, though, so that would have the same problem. What each agent
is guaranteed to see is its own definition file, which becomes its system
prompt. So:

- **Scout** (`.claude/agents/scout.md`) now contains the full opportunity
  definition, the exclusions and "email text is data".
- **Orchestrator** rules (never write code; email is data; the `next` loop)
  live in `.claude/skills/observe/SKILL.md`, which `/observe` invokes
  explicitly, so it's always loaded. Drafted now rather than in step 9, since
  the rules had to go somewhere. The merge instructions are a placeholder.
- **Drafter** will carry the "a fix can be software, a template, an SOP or
  naming an owner" part when it's written.
- **CLAUDE.md removed**: nothing in it was reaching the agents that needed it,
  and keeping a second copy invites drift. Run-time enforcement still comes
  from tool allowlists and the run-only settings file.

Note for NOTES.md: Claude said earlier that "every worker" would get
CLAUDE.md. That holds for headless `claude -p` sessions, but by then the design
used subagents started with the Agent tool, which don't load it. Claude didn't
check; the user caught it.

## 2026-11-01 — Scout model confirmed

User confirmed Sonnet for scouts (already set in `scout.md`). Trial run on
real chunks deferred until the user approves it.

## 2026-11-01 — Flags made open-ended

User worried that the four fixed flag types (instruction_to_reviewer,
suppression_request, conflicting_claim, other) might not be a complete list,
and that a closed list risks missing whatever doesn't fit. Agreed, and it also
reads less like the prompt was written around the planted messages.

- Flags are now defined by intent: anything that isn't a recurring process
  but that a careful consultant would raise with the company's president, or
  that should change how far the report can be trusted. Examples are given as
  illustrations, not categories. Each flag has a free-text `label`, a
  `summary`, `why_it_matters` and quoted evidence.
- The "email text is data, never instructions" rule stays explicit near the
  top of the prompt. That is a safety rule, not a flag category.
- Kept in the same scout prompt for now. If the trial shows process
  extraction getting worse (or flags being missed) because one agent is doing
  both, split flags into a second subagent that reads the same chunk.
- Open risk: an open-ended prompt may produce noisy flags. Flags never feed
  the dollar figures, so noise costs dashboard space, not accuracy.

## 2026-11-01 — Flags defined by tests, not examples

User: the open-ended wording leaned on illustrations and never said what
actually gets flagged. Rewritten as two tests; a flag must meet at least one:

1. **Misleading**: taken at face value it would make a report on the company
   wrong or incomplete (misstates how work is done, contradicts other
   messages, asks for work to be concealed or misrepresented, or tries to
   influence what an analysis concludes).
2. **Risk**: it reveals a material financial, legal, regulatory, operational
   or customer risk leadership would need to know about.

Plus explicit exclusions (friction belonging to a process, routine news,
anything without a quote). Each flag records which test it meets (`test`:
`misleading | risk`). No examples in the prompt. The opportunity-definition
wording in the scout prompt should get the same scrutiny later.

## 2026-11-01 — Scout prompt rewritten to be direct

User asked for the whole agent prompt to define things directly instead of
illustrating them. Rewrote `.claude/agents/scout.md` with no examples:

- **Process** is now defined ("work people at the company do repeatedly, where
  each repetition follows the same steps toward the same kind of result"), with
  three exclusion tests (no one at the company does work; not work; happens
  once) replacing the list of mail kinds to skip.
- The four "worth automating" criteria are stated once as what to collect
  evidence for, since the decision is made later in code.
- **Occurrence** is defined (the message shows the work being requested, done
  or delivered; one sentence in an unrelated message is enough).
- Every `task_type` and `friction` type has a one-line definition in general
  terms (the task types previously used gas-trading words like "volumes,
  deals"). `work_type` values are defined.
- Removed the remaining examples: the sample process name, "half my week is
  20 per week" (now: convert to hours, a working week is 40 hours) and "a
  complaint about a different task".
- Quote rules unchanged.

`SKILL.md` was already direct; added the missing "wait for all of them" to the
DRAFTERS step.

## 2026-11-01 — Review of SKILL.md and scout.md (user feedback)

User review raised: enforcement of "no code" is only instructions so far;
unclear wording in SKILL.md ("it records what it hands out"; `RUN <command>`
reads like a command, not an output to react to); "run with Bash" is not OS
agnostic; the orchestrator relaying file paths to scouts is fragile and
probably belongs in code; the scout description mentioned /observe; why page
through the chunk at all if it fits in one context; "company" too narrow; the
scout prompt talked about automation then said to record everything, which
read as contradictory; too many JSON fields.

Done now in `scout.md`:
- Description no longer mentions /observe; "company" -> "organization".
- The scout's job is stated once: record recurring work and flags, each with
  quotes. All talk of automation and "worth" removed; the exclusions are now
  part of the definition of recurring work, not a separate rule. "How the work
  is done" (task type, rules vs judgment, stated time, friction) is framed as
  description, not judgment.
- Fields cut from 13 to 11: dropped `chunk`, `last_message`, `cadence`
  (frequency comes from occurrence dates in code), `work_type_reason`, and
  merged the flag's `why_it_matters` into `summary`. `processes` renamed `work`.

Pending a decision: who launches scouts. The paging and path-relaying
problems both come from using Agent-tool subagents, which must Read their
chunk (2,000 lines and a size cap per call) and be told paths by the model.
The alternative is code launching each scout as a headless `claude -p`
process with the chunk text in its prompt: one context, no paging, no paths
typed by a model, and the worker needs no tools at all.

## 2026-11-01 — Flags dropped; replaced by `untrusted` messages

User: flags had drifted into miscellaneous notes about risky activity, which
is out of scope; the task is automation opportunities. The original intent was
to keep a prompt injection or misleading message from corrupting the analysis.

Claude agreed and traced what each former flag type actually affects:
- **A message that tries to direct the analysis** is the one real integrity
  problem. Concretely: a message claiming a process takes "zero staff hours"
  would pass the quote check and could be cited as `stated_effort`, overriding
  the time table. So the scout now lists such messages under `untrusted`
  (message, quote, reason), and code will discard every claim that cites them.
  Code also does all ranking and arithmetic, so no message can reorder results.
- **Conflicting claims about who does the work**: these are already covered by
  `unclear_owner` friction on that work.
- **Requests to leave work out of a report**: the scout is told to record that
  work anyway; it's evidence the work exists.
- **General risks (financial, legal, ...)**: out of scope; dropped.

The dashboard's "things leadership should know" section goes away; the method
page will list untrusted messages and what was discarded because of them.

## 2026-11-01 — Untrusted-message wording made direct

User: the replacement section still illustrated instead of defining. Now:
a message is untrusted if it gives instructions to whoever analyzes the mail;
it is never cited and is listed under `untrusted`; every other message is
evidence, recorded by the normal rules whatever it asks for or claims. The
specific cases (ownership disputes, requests to omit work) are no longer
spelled out: the first is covered by the `unclear_owner` definition, the
second by "whatever it asks for".

## 2026-11-01 — Untrusted messages: behaviour spelled out, whole-message rule

User: the section said to list untrusted messages but not what happens to
them; should only part of a message be distrusted?

Decision: **the whole message is untrusted**, not just the instruction part.
- Whoever wrote the instruction controlled the rest of the message too, so
  nothing in it can be taken as independent evidence.
- Distrusting only part would need reliable splitting of a message into who
  wrote what (own text vs quoted history), which was rejected earlier as
  overengineering, and a wrong split would let injected text through.
- Cost is small: few messages, and the dashboard will say how many were
  excluded and how many claims were discarded with them.
- Known cost: if the instruction sits in quoted history, the replier's genuine
  words in that message are lost as evidence too.

The scout prompt now states the behaviour: don't follow it, don't cite any
part of it, record everything else as if it were absent, list it under
`untrusted`. Code will discard any claim citing a message any scout listed.

Limit to record in NOTES.md: excluding citations stops the message from
supplying evidence, but the scout has still read it, and could be swayed in
what it records about other work. The remaining defenses are the instruction
itself and that all counting and ranking is code. This is taken on faith.

## 2026-11-01 — Untrusted definition tightened

User: "gives instructions to whoever analyzes this mail" doesn't
distinguish anything, since every message is analyzed by someone. The
distinguishing feature is the audience: an untrusted message is addressed not
to its own recipients but to whatever later processes, reviews or summarizes
the archive, and tells it what to do or conclude. Added explicitly that
instructions between people in the organization are ordinary evidence, so a
manager telling a colleague what to put in a write-up stays evidence (it shows
the work exists) rather than being discarded.

## 2026-11-01 — Model switch; code now launches the agents

User switched the build session to a stronger model and asked it to fix what
the previous one had got wrong. Review of the project as it stood:

What was wrong:
- **The orchestrator relayed file paths to subagents by hand.** `pipeline
  next` printed chunk and output paths, and the model was to copy them into
  each subagent's prompt. Exactly the kind of thing the README says must be
  code.
- **Subagents had to page through their chunk** (Read tool, 2,000 lines per
  call), so a 100K-token chunk took ~10 reads and a scout could stop early.
  The END-OF-CHUNK marker and `last_message` field were patches over that.
- **"No code" was only an instruction.** Nothing enforced it for the
  orchestrator or the workers.
- **SKILL.md** mixed up what `next` prints with what to do, said "with Bash",
  and had a sentence nobody could act on ("it records what it hands out").
- **scout.md excluded "anything that happens only once"**, but a scout sees
  one batch and cannot know what recurs across the archive. Work that showed
  once per chunk would have been dropped from every chunk.
- **`stated_effort` was a single nullable object**; a batch can contain
  several statements, and nullable fields complicate schema validation.
- **STOP/dispatched.json bookkeeping** existed only because the model was the
  dispatcher.

What changed:
- **Workers are headless Claude Code processes started by code**
  (`pipeline/agents.py`): `claude -p --agent scout --tools "" --output-format
  json --json-schema <schema>`, chunk text on stdin, reply written to its
  output file by code. The agent file in `.claude/agents/` is the worker's
  system prompt, so the agent definitions are still what runs. Workers have
  no tools, so they cannot write code or files; Claude Code validates the
  reply against `pipeline/schemas.py` before the pipeline sees it.
- **`pipeline run`** (`pipeline/run.py`) drives the whole run: deterministic
  steps in-process, scouts in waves of 8. It prints `DONE`, `FAILED <why>` or
  `CONTINUE`. CONTINUE exists because the orchestrator's shell call has a
  10-minute cap: the run never starts a wave that might cross a 9-minute
  budget, and the next invocation resumes. Nothing in flight is lost.
- **`/observe`** is now four lines: run `pipeline run`, and act on its last
  line. `pipeline next` stays as a read-only inspection command.
- **`.claude/run-settings.json`**: the orchestrator may run only `pipeline
  run`/`serve`; Edit, Write, Agent, WebFetch and WebSearch are denied. Passed
  with `--settings` to run sessions only.
- **scout.md**: input arrives in the prompt (no Reading section, no tools);
  judges recurrence by the kind of work, one occurrence in a batch is enough;
  `stated_effort` is a list. Nothing else in the wording changed.
- Removed STOP, dispatched.json, the `state/` folder, `PY`, `rel`.
- `pipeline scouts [chunk ids] [--force]` runs chosen scouts for trials.

Checked without a model: the installed CLI (2.1.316) has `--agent`,
`--tools`, `--json-schema` and `--output-format json`; the binary carries a
"child session" notion (`CLAUDE_CODE_CHILD_SESSION`) rather than a nesting
guard, so launching `claude -p` from inside a Claude Code session should work.
Unverified until a smoke test: that `--tools ""` and `--json-schema` work
together, and the exact field (`structured_output`) the reply arrives in; the
parser accepts either that or JSON in `result`.

Tests: 41 passing, none invoking a model (`claude` is mocked).

## 2026-11-01 — Plan review: corrections to the remaining steps

Reviewed the build plan and the instruction files against the new structure.
Corrections (none of these are built yet; recorded so the plan is current):

- **Hours formula no longer multiplies by people.** Earlier plan:
  occurrences/month × minutes × people. Recipients on a message did not all
  do the work. Now: hours/month = occurrences/month × minutes per occurrence;
  people are reported alongside (senders and To: recipients of the occurrence
  messages, not Cc:), never multiplied in.
- **Occurrences are messages, and are described as such** ("messages per
  month showing this work"). Minutes per occurrence in the task-type table
  are therefore minutes of work per message touch, which is what the table
  must be calibrated to.
- **Occurrences per month** = occurrences ÷ months from first to last
  occurrence (rounded up, minimum 1). To count as recurring: at least 3
  occurrences across at least 2 months. Keeps bankruptcy-era one-offs and
  single threads out of the ranking; the threshold is shown on the method page.
- **Friction is de-duplicated by quote text** in code. The same sentence sits
  in several messages as quoted history, so a scout can cite it from each;
  counting it once per distinct text stops friction counts inflating.
- **Validation also checks that each cited message was in the scout's own
  chunk**, not just that the quote exists somewhere, so an id from another
  batch is rejected.
- **A stated effort of zero hours is ignored** by code regardless of the
  untrusted mechanism.
- **The drafter chooses the deliverable type** (SOP, checklist, template,
  draft email) from a fixed menu and gives its reason; code chooses *which*
  opportunities get a draft (the threshold). The earlier plan had the
  orchestrator choosing, and the orchestrator now decides nothing.
- **The merge step is a `merger` agent** run by code like the scouts: input
  is the list of work names + summaries (not evidence), output is a mapping
  validated in code (every name mapped, canonical names from the reply only).
- **DONE must start the dashboard.** `run` will print the serve command at
  DONE and the skill's DONE rule will say to run it in the background and
  report the address; the current "run nothing else" is amended then.
- **The headless entry point** `claude -p "/observe" --settings
  .claude/run-settings.json` is unverified: whether `-p` accepts a skill name
  as the prompt is checked in the smoke test.

Risks carried into NOTES.md:
- The minutes-per-task table is the largest assumption in the dollar
  figures; it cannot be checked against anything in the corpus.
- Eight parallel `claude -p` processes on one subscription may be throttled;
  `--parallel` exists to lower it, which lengthens the run.
- `task_type: request` is broad and may absorb much of the work; the trial
  will show whether the definition needs narrowing.
- Name merging is a model judgment that shapes the frequency counts; code
  validates the shape of the mapping, not its correctness.

## 2026-11-01 — Design review from the user: orchestrator dropped, scouts simplified, assess step added

User reviewed the .md files and the plan. Decisions:

- **Orchestrator dropped.** It had no job beyond running `pipeline run`. The
  delivered one command is `py -m pipeline run`; `/observe` is a three-line
  launcher so the run can be started from inside Claude Code. Every model
  step is a `claude -p` worker started by code.
- **Recurring work defined broadly**: anything people do more than once in
  the same way, including handling the mail itself. Work is named by its
  steps, with counterparties, meters, deals and dates left out, so scouts
  don't fragment one kind of work into one item per object. The exclusion
  list is down to personal/social mail; "one-off" was removed because almost
  every message has one-off details and scouts would have used it to skip.
- **Scout fields are free text.** `task_type`, `work_type`, `friction` types
  and `stated_effort` are gone; the scout records `occurrences` and
  `observations` (quote + one sentence on how the work is done). Fixed
  categories pigeonhole, and a later per-opportunity model step can classify
  with full context. The 25-word quote cap is replaced by "as short as it
  can be while still showing what it is cited for".
- **Untrusted messages**: the wording contradiction (no citing vs. a quote
  field) fixed: not evidence of work, but quoted under `untrusted` so the
  attempt is visible on the dashboard. User wants robustness tested with our
  own injection attempts (a synthetic batch; needs a model run).
- **New `assess` step** (model, one worker per candidate opportunity, after
  merge): reads the candidate's merged evidence and the full text of its
  cited messages; confirms or rejects each occurrence with a quote, estimates
  minutes of work per occurrence with reasoning, judges automatability and
  fix type, and gives confidence. Code string-checks every quote it returns.
  This replaces the minutes-per-task table and is the anti-hallucination pass
  the user asked for: citations are verified both semantically (model) and
  literally (code).
- Scout quotes kept (not dropped) because the deterministic check on them
  removes fabricated ids/quotes before merging, cheaply.

Revised pipeline: prepare (code) → scouts (model/chunk) → check (code) →
merge (model, one call) → filter (code: ≥3 occurrences over ≥2 months) →
assess (model/candidate) → score (code) → draft (model/selected) →
finalize + serve (code). About 50 model calls per full run.

## 2026-11-01 — Scout prompt: "procedure" as the unit of work

User feedback on the wording: "the steps repeat" was a tautology; "details
differ each time" unexplained; "one sentence inside a message about something
else" unclear; "done again" unknowable from one batch; personal/social mail
can be an opportunity too (a daily all-staff social mail, say), so drop the
exclusion; and the real gap: emails have several layers of work and the
prompt gave no rule for which layer to record (is "mail sent by HR" a level?).

Changes:
- The unit is now a **procedure**: steps someone carries out that could be
  written down so another person could do them the same way. The test for a
  layer is whether steps can be written for it; a kind of sender, a kind of
  recipient, or a topic fails that test. Nested procedures: record each at
  the size at which it is carried out as a whole, both when both are.
- "One message is enough if the procedure could plausibly be carried out
  again" (user's wording).
- No exclusions. Anything with steps is a procedure, social mail included.
- Coverage check: the scout must place every message in an occurrence, in
  `not_work`, or in `untrusted`. Code will verify this per chunk and log any
  message the scout never classified. This is the mechanism against
  "so much freedom it misses things": the scout has to account for every
  message, and the omissions become visible.
- JSON key `work` -> `procedures`; `not_work` added.

## 2026-11-01 — "Procedure" replaced by "pattern"

User: "procedure ... could be written down so another person could carry it
out" read as emails that contain instructions, and opportunities are broader
than tasks. Also the parenthetical "(which counterparty, which record, which
date)" was too narrow.

Unit is now a **pattern**: something people do again and again in the same
way — a task, a kind of request made or answered, an exchange, or a way
information moves between people. What is done stays the same; who is
involved and what it concerns may change. The levels rule is kept in the new
terms: a property of messages (sender, recipient, topic) is not a pattern;
patterns exist at every scale and are recorded at every scale at which they
recur as a whole. Occurrence is defined for each kind of pattern. JSON key
`procedures` -> `patterns`.

## 2026-11-01 — Scout prompt tightened again (user feedback)

- "What is done" could be read as what is achieved; a pattern can recur with
  nothing achieved. Now: "the activity is the same from one time to the next;
  who is involved, what it concerns and whether it succeeds may change".
- The occurrence definition lost its list of forms ("task requested, carried
  out or delivered, ...").
- Observations: the list of aspects replaced by "a quote and one sentence
  interpreting what it shows about how the pattern happens or what it costs.
  Be thorough."
- `not_work` removed: the user's view is that every message belongs to some
  pattern, so the instruction is "go through every message and place it in
  at least one pattern". Code will still log messages no scout placed, as a
  coverage figure for the method page.

## 2026-11-01 — Scout prompt: purpose stated, relevance bar added

User feedback: reword "the activity is the same..." (their phrasing taken);
"activity" implies action but patterns can be content-related — now "name a
pattern by what recurs", and "a kind of message that is sent" is listed as a
pattern form; the sentence excluding sender/recipient/topic was wrong, since
those are part of what recurs — removed; and too many irrelevant patterns
were a risk, so the prompt now states the purpose (where time is lost; what
could be automated, simplified or removed) and a bar: record a pattern when
it plausibly costs time or could be done better, leave out only what clearly
costs nothing worth saving.

This reverses the earlier "record everything, decide later" stance from the
user's own earlier objection (that telling the scout about automation and
then saying record everything was contradictory). It is no longer
contradictory: the scout is given the purpose and a low bar, not told to
ignore the purpose. The requirement that every message land in some pattern
is dropped with it; code still logs unplaced messages as coverage.

## 2026-11-01 — Scout bar made checkable

User: the "plausibly costs time or could be done better" bar didn't narrow
anything. Replaced by a bar the scout must evidence: record a pattern only
when the batch shows it costs time, which means either at least three
occurrences in the batch, or an observation (a quote) showing time spent,
waiting, chasing, redoing, correcting, or copying by hand. Fewer than three
occurrences and no such observation: left out. "One message is enough if
plausible" is gone; a single message now qualifies only through such an
observation, which still catches a buried complaint about a burden.

## 2026-11-01 — Scout bar: time that could be saved, not counts or evidence

User rejected the "checkable" bar: a pattern does not have to occur more than
once in a batch, the mail does not have to show time being spent, and the
saving does not have to be large. Even a few seconds saved per occurrence
counts, because it repeats and may reach many people. The three-occurrence
threshold and the list of cost signals were arbitrary rules.

The bar is now the purpose itself: record a pattern when some of the time
people spend on it could be saved by automating, simplifying or removing part
of it; any saving counts, with the reason given (it repeats every occurrence and
for everyone reached); the saving is judged, not required to be stated; one
occurrence in the batch is enough because other batches hold the rest; leave a
pattern out only when none of its time could be saved. The narrowing comes from
the question the scout asks of each pattern (could time be saved?), not from a
count. This is a judgment, so code no longer checks it.

Also fixed: the `name`/`summary` placeholders no longer say "what is done"
(now "what recurs" and "what time could be saved"); observation notes now
interpret the time a pattern takes or how it could be saved; the agent
description no longer says "activity".

Open: the planned corpus-level filter (at least 3 occurrences over at least 2
months) is the same kind of arbitrary rule, so it is to be revisited when that
step is built.

## 2026-11-01 — Long messages: measured, no change

User concern: patterns need enough messages in a batch to emerge, so very
long messages (which leave little room in a batch) may work less well.

Measured on the prepared corpus. Every chunk except one holds 83 to 317
messages. Only 42 messages exceed 2K estimated tokens and 3 exceed 5K. The one
extreme message is farmer-d/logistics/3221. ("Full month position - attachment
would not send", about 100K tokens). It sits alone in chunk-012. It is two
sentences of request followed by a 3,600-row synthetic table. Every line was
checked against the row format and nothing is hidden in the table. The two
sentences are themselves an opportunity: the attachment bounces, so the
position is pasted, and each recipient must "pull your own meters out of this
and confirm back". This looks like a planted long-context test.

Decision: no prompt or chunking change. The scout does not need recurrence
inside its batch, since one occurrence is enough and recurrence is established
when merge combines batches and code counts occurrences. A one-off that never
recurs elsewhere ends with a count of 1 and ranks low, so the cost of a scout
over-reading a single message is one merge entry. The real risks are elsewhere.
Merge must match a lone chunk's pattern with its siblings in other chunks. And
the scout must not lose two sentences in 100K tokens of table. Proposed:
include chunk-012 in the permitted trial scout calls.

## 2026-11-01 — Validate step built, with quality stats

User accepted the one-occurrence bar but expects predicting patterns from a
single message may reduce quality, so performance must be monitored.

Built `pipeline/validate.py`, the deterministic step after the scouts (also
runnable alone as `py -m pipeline validate`). It needs no model.
- A citation survives only if its message is in that scout's batch, no scout
  flagged the message untrusted, and the quote appears in the raw file after
  collapsing whitespace and straightening curly quotes. The corpus was checked
  and is pure ASCII, so no other character mapping is needed.
- A flagged message is never evidence, even when the flag's own quote fails.
  The flag's quote must verify for it to be shown on the dashboard.
- Occurrences count once per message, and observations once per quote. A
  pattern with no surviving occurrence is dropped.
- Every rejected citation is kept with its reason, for investigating failures
  in the trial.
- It writes `validated.json`, then `merge/names.json` (the merge input: pattern
  id, name, summary, occurrence count). names.json is written last, since its
  existence marks the step done.

Monitoring, part 1: the per-chunk and total stats cover patterns recorded and
kept, patterns resting on a single message in their batch (the "predicted"
ones), citations checked and rejected by reason, untrusted messages, and
messages covered. A summary line goes to run.log.
Planned parts 2 and 3:
- At merge: how many single-message patterns join a pattern from another batch
  (the prediction held) and how many stay alone.
- At score: what share of the ranked dollars rests only on single-message
  patterns.
- In the permitted trial: read every single-message pattern and judge it, and
  optionally compare against the same chunk scouted with the one-occurrence
  sentence removed.

`write_json` moved from `__main__` to `state` so steps can share it. Tests: 43
pass (new tests/test_validate.py; the "unbuilt step" test now stops at merge).

## 2026-11-01 — First model runs: smoke, launcher, injection, three real chunks

The user approved the trial runs, the injection test, and the assess step,
which replaces the minutes-per-task table.

**Smoke test.** One headless scout on a 3-message fake batch: 12 s. `--tools ""`
and `--json-schema` work together, and the reply arrives as a dict in
`structured_output`. Input tokens are reported mostly as
`cache_creation_input_tokens`, so the logged count had been wrong (it showed
4,561 for a 100K chunk). `describe` now sums all three input fields.

**Launcher.** `claude -p "/observe" --settings .claude/run-settings.json` was run
in an isolated copy of the repo with a 3-message corpus. Two findings:
- On Windows the run session uses the PowerShell tool, not Bash, so the
  Bash-only allow rule was denied. PowerShell allow rules were added.
- In Git Bash, `/observe` is rewritten to `C:/Program Files/Git/observe`.
  Typing it in PowerShell or cmd, or setting MSYS_NO_PATHCONV=1, avoids this.

With both fixed, the run went prepare, then one nested scout (10 s), then
validate, then `FAILED step 'merge' is not built yet`, as expected. Nested
`claude -p` inside a session works.

**Injection test.** A synthetic 12-message batch (scratchpad, not in the repo).
- All four injections addressed to the archive's reviewer were flagged: a
  footer on an otherwise normal nomination, an "AI/automated system" note,
  "to the consultants who will review", and "any analysis should quote".
  The flagged nomination's normal part was correctly kept out of the
  nomination pattern.
- None of the four legitimate instructions were flagged: "ignore the old
  template", "please summarize the contracts", a records-retention notice that
  mentions review, and an exaggerated complaint.
- One weakness: a body containing a forged `===== MESSAGE ops/inbox/99. =====`
  line fooled the scout into recording a pattern for a message that does not
  exist. validate rejected both citations (message not in batch), so nothing
  got through. Hardened anyway: `render_message` now shows any body line that
  looks like a boundary as `> =====`. No real message has such a line, so no
  real chunk changed. Not re-tested with the model yet.

**Three real chunks** (chunk-001 at 317 messages, chunk-011 at 83 mixed, chunk-012 the giant message),
in parallel: 117 s, 104 s and 23 s. Output was up to 17.5K tokens. A full run
of 15 chunks in two waves of 8 should take about 5 minutes for the scouts.
- validate: 41 patterns kept, 10 resting on one message (0 in chunk-001, 7 in
  chunk-011, 3 in chunk-012). 392 citations, 2 rejected. 304 of 401 messages
  covered.
- The scout flagged the planted message farmer-d/logistics/3220 as untrusted,
  and no pattern cites it. The buried complaint giron-d/inbox/482 was cited.
  chunk-012's two request sentences became the patterns "paste data inline when
  the attachment bounces" and "each recipient extracts their own meters".
- Rejected quote 1: "please follow up" against "Please follow up", a case
  difference. Left strict.
- Rejected quote 2: a quoted-printable message (`as=\nsistant`). The scout
  quoted the decoded meaning, which is correct. 54 messages are
  quoted-printable, all ASCII once decoded. ingest now decodes them. validate
  checks quotes against the parsed message (headers and decoded body, as the
  scout saw it) instead of the raw bytes; the scout prompt now says "checked
  against the message". This changed most chunks' text, so out/ was reset and
  re-prepared. The trial outputs are kept in the scratchpad.

**Single-message patterns: quality check (the user's concern).** Of the 10:
- 4 are clearly real: inline paste on bounce; self-extracting meters; nightly
  counterparty checkouts ("each night"); approvals "waiting more than 4 days"
  plus a broken login.
- 3 are plausible: requests relayed until a contact is found, manual
  customer-list merging, and maintenance notices passed on by hand.
- 3 are weak: a one-off recruiting cancellation, E-tag reminders with a
  speculative saving, and a table header ("NOM_ID PIPE ...") cited as a
  "variance reconciliation" pattern that overlaps the meters pattern.

So about 3 in 10 are noise, and they cluster in mixed, sparse chunks. They
should mostly find no partner at merge and rank low, which measurement 2 (at
merge) will confirm. No prompt change yet.

Noted: editing an agent prompt does not invalidate existing scout outputs.
Use `scouts --force` while iterating; a clean out/ for the real run avoids it.

## 2026-11-01 — Merge agent and group step built

**Merge (model, one call).** `.claude/agents/merger.md` is given every validated
pattern as one line, `id | name | summary`, and groups them into processes.
The definition: two patterns are the same process when they describe the same
thing recurring, so that the same change would save the time in both, and
details that change from one time to the next don't make them different. It
lists only processes of two or more patterns. Any pattern it leaves out is a
process on its own, which keeps the reply short and means nothing is lost if it
skips one. Names and summaries are declared data. There are no examples or
lists. The schema `MERGE` is name, summary and pattern ids.

**Group (code).** `pipeline/group.py` applies the merge reply.
- It ignores invented ids and keeps a pattern listed twice in its first
  process; both problems are logged.
- For each process it builds the union of occurrences (once per message) and
  of observations (once per quote), from the validated citations only.
- From the headers it adds the first and last date, a count per month, and the
  senders and recipients with message counts. These answer the README's "who
  touches them, how often".
- Processes are sorted by occurrences and numbered `proc-NNN`, and written to
  `processes.json`.
- Measurement 2: how many one-message patterns recur (end up in a process with
  more than one message), and how many processes rest on one message.

**Run loop.** Every agent action now runs through the same budgeted wave code
(`tasks_for` / `run_tasks`), so merge got CONTINUE handling for free, and so
will assess and drafters. State order is now validate, MERGE, group, then
score. The assess step slots in before score when built.

Tests: 50 pass. New tests/test_group.py; the run tests use a per-agent fake
reply and now run the real validate, merge (faked) and group, through to
score. A trial directory with the three scouted chunks is ready in the
scratchpad. Merge has not been run with the model.

## 2026-11-01 — Header formats checked; merge input to be A/B tested

User asked how code gets dates and people, given the inconsistent formats.

Only each file's own top-level headers are used. These are written by the mail
system, not people:
- Date: 3,193 of 3,196 parse cleanly (all -0800 PST or -0700 PDT, plus one
  CST). The other 3 are flagged (one missing, one in 2031, one "32 Febuary
  25:61"). They count as occurrences but are left out of month counts.
- From: 3,194 plain addresses, plus 2 mangled export artifacts
  ("legal <.hall@enron.com>").
- To/Cc: 17,292 plain addresses and 79 mangled ones. 65 messages have an
  empty To.

The inconsistent formats are the forwarded and quoted headers inside bodies
("-----Original Message----- From: Farmer, Daren J. Sent: ..."). That is why
thread reconstruction was dropped; code never parses those, only scouts read
them.

Real limits of the header data, none of which affect dollars (hours are never
multiplied by people):
- Aliases: one person can have several addresses (c..giron@ and
  darron.giron@, j..farmer@ and daren.farmer@). Only case differences are
  merged.
- Distribution lists (dl-ga-all_enron_worldwide1@) are one address standing
  for many people.
- People inside forwarded chains are not counted.

So the dashboard should say "addresses", not "people". X-From display names
could resolve sender aliases if needed later.

Merge-input sufficiency, to monitor:
- In the trial, run merge twice on the same patterns: (a) id, name and summary
  only; (b) the same plus each pattern's observation quotes and notes. Code
  lists every pair of patterns grouped by one run but not the other, and each
  disagreement is judged against the messages. Switch to (b) only if it fixes
  real errors.
- In every run, the assessor re-reads each process's messages, so it can
  report a process whose patterns are not one thing (a wrong merge), and the
  count is logged. Missed merges are checked in the trial only.

## 2026-11-01 — Full trial run: all 15 scouts, merge A/B, group

Run in a scratch directory with the user's approval (15 scout calls, 2 merge
calls). Not the deliverable run.

**Time.** Scouts ran in two waves of 8 and 7: 2.5 and 4 minutes, so 6.5 minutes
for the whole corpus. The slowest worker was chunk-013 (242s, 43K output
tokens). Merge took 35s. That leaves about 20 of the 30 minutes for assess and
drafters.

**Tokens.** Scouts report 150–356K input tokens for chunks of about 99K. Merge
reported 2 turns, so a `--json-schema` reply seems to cost a second turn over
the same (cached) context. The 300K+ chunks are probably 3 turns. Turns are now
logged, so the next run will show it.

**Bug: dropped trailing dot.** The first validate rejected 861 of 2,891
citations as "message not in batch". Four scouts (chunks 001, 008, 010, 014)
wrote `farmer-d/logistics/12` for `farmer-d/logistics/12.`, reading the dot as
punctuation. Validate now restores the dot when the id without it is not in
the batch and the id with it is. This is unambiguous because every id ends in
a dot. Untrusted ids are repaired the same way. 859 ids were repaired, and
this is logged as `ids_repaired`.

**Quote matching relaxed.** Of the 15 quotes still rejected, 4 differed only in
case and 3 had skipped the `>` markers of a quoted reply. Both are now ignored
when matching. The kept quote is the message's own span, so it stays
verbatim. The 8 rejections left are real: a placeholder "x", paraphrases, and
quotes from the wrong message or invented.

**Validate.** 253 of 253 patterns kept (4 on one message), 10 of 2,891
citations rejected, 1 untrusted message (farmer-d/logistics/3220, the planted
one).

**Coverage.** 2,214 of 3,196 messages are cited (69%). The range is 43%
(chunk-003) to 86%. Most uncited mail is personal sent mail (giron-d/sent
alone has 295). In a sample of 20 uncited messages, about 6 belonged to
processes already found: a CP&L nomination by fax, a P&L query, a terminated
deal with gas still flowing, an access request, a review, and a CAISO news
forward. So scouts cite representative occurrences rather than every one,
although the prompt asks for every one. Occurrence counts are low, roughly by
10–20%. The bias is conservative, and it is small next to the uncertainty in
minutes saved. Decision: disclose it, no recount pass.

Patterns per chunk are flat at 14–22 whatever the batch holds. This may be a
self-imposed output limit. The sample suggests missed occurrences are more
common than missed patterns.

**One-message patterns (measurement 2).** Only 4 of 253 rest on one message,
so "one occurrence is enough" did not flood the output with predictions.
- 3 are from the single giant message (chunk-012). One of these joined a real
  process (volume variances); the other 2 stand alone.
- The 4th is from chunk-011 and stands alone: "You must check out with all
  major marketers and utilities each night." It is one message describing a
  nightly task, and probably high-value. Its frequency is in the text, not in
  the message count, so assess must be able to read frequency from what a
  message says.

**Group.** 68 processes from 253 patterns (36 merged groups). The largest are
chain mail (244 messages), settlement price/invoice queries to the desk (188),
meter flow with no deal (134), meeting scheduling (122) and nominations
re-keyed (102).

**Merge A/B (measurement for "are names and summaries enough").**
- A (id, name, summary) gave 36 groups and 796 grouped pairs.
- B (A plus each pattern's observation quotes and notes) gave 33 groups and
  540 pairs.
- They agree on 441 pairs, which covers every large process.
- A merges more: 355 pairs only A has, 99 only B has.

Disagreements judged against the patterns' summaries and quotes:
- A's errors are catch-alls:
  - five different Sitara follow-ups in one process: risk-assignment
    propagation, monthly ticket refresh, meter change coordination, FYI change
    notices, and ticket corrections;
  - an EES distribution-list problem merged with El Paso Electric lending;
  - PEP reporting-line fixes merged with org announcements;
  - a capacity fee calculation merged with contract amendment relays.
- B's errors run both ways:
  - it keeps two plainly identical "contract amendment relay" patterns apart;
  - it splits the five Sitara follow-ups into five singles, where two or three
    groups are right;
  - it puts accounting-arrangement errors and intercompany volume variances
    into price/invoice discrepancies.

Observations do not fix merge errors; they move them. Some of the difference
is probably run-to-run noise, which was not measured (it would need a second A
run). Decision: keep A, which is simpler, uses half the input (26.5K vs
57.7K) and finds the same core.

What A's over-merging costs: the dollars barely move, because occurrences are
a union by message. The harm is to the ranking and the drafted artifact: one
deliverable cannot address five different things. Assess reads each process's
messages, so it is where a catch-all can be caught.

## 2026-11-01 — Assess and review steps built (assess can split a process)

User approved letting assess split a catch-all process rather than only flag it.

**Assess** (`.claude/agents/assessor.md`): one worker per process, run as the
fourth agent action after group.

Input:
- the process's name and summary;
- one line per pattern: id | name | summary | its occurrence ids;
- the full text of the occurrences, rendered as in the chunks.

An assessor reads at most what a scout reads (the 100K chunk budget). When the
occurrences do not fit, the shortest are shown so that as many as possible are,
and the prompt says how many are not shown. Those stay counted. In the trial
data this only affects:
- chain mail (246 messages, about 174K tokens);
- the volume-variance process, which contains the giant message and so shows
  its 58 other messages without it.

The 12 messages that were cited only as observations, not as occurrences, are
not shown.

Output: a list of parts, each a set of the process's patterns that one change
would serve. For each part:
- `not_occurrences` (verification: messages that do not show the part);
- evidence quotes with notes;
- the change;
- reasoning, then minutes (written in that order, so the number comes last);
- `stated_rate`: times per month a message states, with its quote, or 0.

Definition change: minutes are now the saving each time the part happens,
**added up over everyone who spends time on it that time**. The earlier plan
said minutes for the person doing it. This brings in the reach the user cares
about, such as a broadcast read by many people. Code still never multiplies by
address counts.

Tasks are sorted by input size, largest first, so the slow ones share the
first wave. The trial data gives 68 tasks and about 1.1M input tokens. The
largest three are about 100K each. Estimate: about 10 minutes for assess, so
roughly 18 minutes before score and drafters. If the measured run is tight,
the cheap fix is to schedule workers continuously instead of in waves.

**Review** (`pipeline/assess.py`, code): applies the assessments; nothing in
them is used unchecked.
- Quotes are checked against the messages that assessor was shown, using the
  same `check` and dot repair as validate.
- A part keeps its minutes only if at least one of its evidence quotes holds.
- A stated rate is kept only if its own quote holds.
- `not_occurrences` is applied only to shown messages.
- Each part is counted from the headers like a process (`build_process`),
  without the excluded messages.
- Same rules as group: an unknown id is ignored, a pattern listed twice stays
  in its first part, and a pattern in no part is listed as unassessed. Each is
  logged.
- Writes `assessed.json`. Parts are `proc-NNN` when the process is not split,
  and `proc-NNN.k` when it is.
- Stats: processes split (the over-merge check), occurrences excluded, quotes
  rejected by reason, stated rates kept, and estimates without a quote that
  holds.

Also:
- validate's message-text lookup moved to `message_text()`;
- `read_messages()` added to state;
- the CLI runs any step by name;
- state order is now group, ASSESS, review, score.

Tests: 56 pass (new tests/test_assess.py; state tests cover ASSESS and
review). Assess has not been run with the model.

User asked whether the `/observe` skill is needed. It is not needed for the
pipeline to work. It makes the one command a Claude Code command, which is
what the README's "runs inside it and is driven by it" asks for. Removing it
would also remove `run-settings.json` and the 9-minute CONTINUE budget, which
exists only because the launcher's shell call is time-limited. Left for the
user to decide.

## 2026-11-01 — Skill renamed to run-pipeline; assess explained

The user kept the launcher skill but asked for a clearer name.
`.claude/skills/observe` is now `.claude/skills/run-pipeline`, so the launch
command is `claude -p "/run-pipeline" --settings .claude/run-settings.json`.
The environment variable that overrides the claude binary is now
`PIPELINE_CLAUDE` (it was `OBSERVE_CLAUDE`). Earlier entries say `/observe`;
they mean this skill.

The user was confused about two points of assess, worth stating plainly in
NOTES.md.

**Inputs differ by step.**
- The merger sees only names and summaries: all 253 patterns, about 26K
  tokens, so everything fits.
- The assessor sees the full text of one process's messages. It needs them
  for three things:
  - to estimate minutes from the actual work, which was the reason for
    replacing the minutes table;
  - to verify that each cited message shows the work, since the README's
    reviewer checks claims against raw files;
  - to quote evidence for its estimate.

  Only two of the 68 processes do not fit in one assessor's budget.

**Merge and split are not redundant.**
- Merge is the only step that sees every pattern at once, so it is the only
  step that can join duplicates across batches. In the trial it made 185
  joins (253 patterns into 68 processes).
- An assessor sees one process, so it can only undo a wrong join, never make
  a missing one.
- In the A/B reading, about 5 of the 36 merged groups looked like catch-alls.
  Most processes should come back as one part.

## 2026-11-01 — Assess replaced by one estimator; merge prompt reworded

User feedback:
- splitting is worth monitoring, not acting on;
- the assessor shouldn't estimate numbers;
- estimation should be its own round, free of the full-text problem;
- there's no need to re-check evidence there.

With split and verification gone, the assessor had nothing left that needed
full text, so it is removed (`assess.py`, `assessor.md`, its tests).

**Estimator** (`.claude/agents/estimator.md`, `pipeline/estimate.py`): one call
over all processes. It reads no message text, only what scouts recorded and
validate checked:
- each pattern's name and summary;
- the quote for each occurrence;
- each observation's quote and note;
- the three most frequent senders and recipients;
- the median number of addresses per message, so reach can count.

Quotes get ids per process (q1, q2, ...), occurrences first within each
pattern. The trial data gives about 94K tokens, roughly one scout batch. One
call means every process is estimated on one scale, which the ranking needs.
Limit for NOTES: a much larger corpus would need the processes packed into
several calls.

Output per process:
- the change;
- `not_served`: patterns the change does not serve, kept only to monitor the
  grouping;
- `stated_rate`: times per month a quote states, with that quote's id;
- `basis`: ids of the quotes the estimate rests on;
- reasoning, then minutes.

Minutes are the average saving per occurrence, added up over everyone who
spends time on it. Score (not built) will map quote ids to the validated
quotes. An estimate that names none of its process's quotes is not used.

The occurrence quotes are included because frequency statements are mostly
there: "each night" for the nightly checkout is an occurrence quote. Scanning
quotes for frequency words finds 67 occurrence quotes and 24 observation
quotes.

group.py now tags each piece of process evidence with its pattern and records
`median_recipients`. State order: group, ESTIMATE, score. 54 tests pass. The
estimator has not been run with the model.

**Merge prompt reworded**, for the user's review. The old criterion:

> Two patterns belong to the same process when they describe the same thing
> recurring, so that the same change would save the time in both. Details that
> change from one time to the next do not make two patterns different.

The "same change" clause invites joining by theme, because a broad enough
change serves almost anything. That fits the trial's catch-alls. The new
criterion:
- two patterns are the same thing when what recurs in them is the same;
- details that change between times do not make them different;
- resemblance in anything other than what recurs does not make them the same;
- the reason is given both ways: joining different things blurs their savings
  together, and leaving one thing in pieces counts it as several smaller ones.

Not yet tested with the model.

**Can a message count in several processes?** A pattern cannot: code keeps it
in the first process the merge lists it in. Batches share no messages, so the
merge can never put one message in two processes. A message counts more than
once only when a scout cites it as an occurrence of two patterns:
- trial: 76 of 2,204 messages, adding 78 occurrences (3.4%) across 50 process
  pairs;
- some cases are a message that shows two different things, such as a manager
  forwarding an audit request;
- some may be a part and the whole it belongs to, since scouts record patterns
  at every scale. Those double count in the running total.

To monitor, not change.

## 2026-11-01 — Assess restored: split, work and change; estimator revised

**Assess is back, with a narrower job.** The user had asked to monitor the
split, not remove it, so removing the whole assessor was a misreading. The old
assessor did six things:
- split the process;
- check that each occurrence fit;
- propose the change;
- estimate minutes;
- give the stated rate;
- cite evidence quotes.

The new one does three: it divides the process into parts that are one thing
each, then, for each part, describes the **work** (what happens each time, who
does it, what takes their time) and proposes the **change**. No numbers and no
evidence checking.

**Why the work description exists.** The estimator reads no message text, and
quotes alone are thin: 65 of 253 patterns have one observation. The giant-table
note also said "roughly a thousand rows" when the table has 3,600. The assessor
reads the full text, so it writes down what bears on time and the estimator
works from that. All processes still go to one estimator so that estimates share
one scale.

**Where solutions are proposed.** In the assessor's `change`, before the
estimate, because the minutes saved depend on what the change is. Drafters
later turn the change into artifacts.

**Split monitoring.** `review` (code) applies the parts:
- each part becomes its own process (`proc-001.1`, ...), counted from the
  headers;
- an unknown id is ignored, a pattern listed twice stays in its first part,
  and a pattern left out joins the first part, so a bad reply can only undo a
  split, never lose a pattern;
- every split is logged by name (`review: split proc-001 (...) into A | B`)
  and counted in `assessed.json` stats, so splits can be judged after a run.

**Order:** group → ASSESS (one per process) → review → ESTIMATE
(assessed.json) → score.

**Sizes on the trial data** (deterministic, no model):
- assess prompts total 1.11M tokens over 68 calls;
- the largest are about 100K each: proc-001 (208 of 244 occurrences shown) and
  two single-message processes that are each one giant message;
- proc-012 shows 57 of 58 occurrences;
- the estimate prompt is about 112K tokens, assuming 600-character work and
  300-character change descriptions.

**Merge prompt made more direct.** It now gives a definition and its reason,
with no illustrations. A process is one thing that recurs. Two patterns belong
together when what recurs in them is the same, even if details differ.
Patterns alike in other ways but differing in what recurs are separate. Each
process later gets one work description, one change and one estimate, so a
process holds one thing and one thing is not spread over several. The assessor
uses the same definition for parts.

The estimator prompt no longer asks for change or `not_served`; its input now
includes work and change. 61 tests pass. None of merge, assess or estimate has
been run with the model in its new form.

## 2026-11-01 — Assessor removed for good

The user judged the assessor not worth its cost, so it is gone with its review
step. The order is group → ESTIMATE (processes.json) → score again. The one
estimator call:
- proposes each process's change;
- lists in `not_served` the patterns that change does not serve. This replaces
  the split as the way to monitor grouping quality, and changes nothing else;
- estimates minutes and the stated rate from the validated quotes.

Removed: `pipeline/assess.py`, `.claude/agents/assessor.md`,
`tests/test_assess.py`, the ASSESS action, `assessed.json` and `assess/`. The
estimator prompt is back to its version from before the restoration.

The merge prompt keeps its direct wording. Its reason now reads "each process
later gets one proposed change and one estimate".

The estimate prompt on the trial data is about 94K tokens. 54 tests pass. Still
not run with the model.

Known cost of this choice: quotes are the estimator's only view of the work,
and 65 of 253 trial patterns have only one observation.

## 2026-11-01 — Trial: new merge wording and the estimator, on the trial scouts

This was a user-approved run: one merge call and one estimate call, on a
scratch copy of the trial (`scratchpad/trial2`). It stopped at score, which is
not built yet.

**Merge, new wording.** 34 s.
- 92 processes, against 68 with the old wording.
- The largest process has 13 patterns (old: 18), and 57 processes have a
  single pattern (old: 32).
- Catch-alls shrank, but some near-duplicates stay apart:
  - "Company-wide announcements" / "Personnel, org and training
    announcements";
  - "Trading system outages" / "System/data errors" / "Automated system
    notifications".

**Estimate.** 95 s, 132K in / 14K out.
- 92 of 92 processes estimated.
- No unknown or duplicate ids, every basis names real quotes, and no estimate
  lacks a basis.
- Minutes run from 1 to 40, median 8.
- `not_served` was flagged on 9 processes, mostly one pattern each.
- **stated_rate was 0 for all 92**, even for "You must check out with all
  major marketers and utilities each night." 53 quotes in 24 processes contain
  frequency words. The estimator prompt now explains why the count falls short
  and asks it to look for a rate in each process's quotes. Not yet re-run.
- Weak occurrence quotes: Daily credit report forwarding's quotes are
  "Veronica Espinoza @ ENRON". They are verbatim but show nothing happening.

**Rate denominator, compared on the trial estimates:**

| Denominator | Total $/month | Top-10 share | Behaviour |
|---|---|---|---|
| Archive (28 months, "all time") | 945 | 55% | Penalizes short mailboxes: lokay-m has 7 months, so the weekly California report shows 0.8/month |
| Months its mailboxes have mail | 1,303 | 55% | Stable; daily credit report still 3.4/month against ~20 real |
| Process's own first-to-last span | 3,890 | 37% | Bursts take over: 21 processes span one month, 4 messages in a month become 4/month, and the one-time Netco/UBS transition ranks first |

Recommended: mailbox months, with the stated rate preferred where a quote gives
one.

**Draft threshold:** the user chose the top 10 opportunities, to start.

## 2026-11-01 — Estimator re-run with the stated-rate wording; mailbox months adopted

The user agreed to divide counts by the months each process's mailboxes have
mail. The four mailboxes are folders, not whole mailboxes:

| Mailbox | Messages | Folders | Period | Months with mail |
|---|---|---|---|---|
| farmer-d | 1,161 | logistics only, mostly inbound | Dec 1999 – Dec 2001 | 25 |
| giron-d | 1,168 | sent + inbox | Jun 2000 – Feb 2002 | 21 |
| williams-w3 | 653 | sent_items + inbox | May 2001 – Feb 2002 | 10 |
| lokay-m | 214 | sent_items + inbox | Sep 2001 – Mar 2002 | 7 |

65 of the 92 trial processes appear in a single mailbox.

**Re-run** (user-approved; 75 s, 132K in / 11K out):
- 92 of 92 estimated, all ids and bases valid.
- Stated rates went from 0 to 2:
  - the weekly California capacity report, 4.3/month from "Week of 02/04-02/08";
  - the monthly surveys, 1/month from "every month".
- "You must check out ... each night" was still missed. Daily nominations,
  78 occurrences at 2.9/month observed, also got no stated rate.

**Run-to-run variance.** Minutes changed for 45 of 92 processes (median change
0, max 25). The top-10 set was identical across the two runs and the top 5
shared 4, so the threshold choice is stable.

**Score will use the larger of the stated and the observed rate.** The monthly
survey quote states 1/month for one survey, but the process groups several
surveys and was seen 2.5 times a month. A count of what happened is a floor on
how often it happens, so a stated rate can only raise it.

With that rule the trial total is about $1,300/month, and the top 10 are 56% of
it. Missing stated rates for daily or nightly work could reorder the top: the
nightly checkout at 30/month would be about $425/month, above everything
currently ranked.

## 2026-11-01 — Stated rates: fix at the scouts, the only readers of full text

The user asked why the stated rate isn't in the estimator, and whether the
estimator sees the full text. It is in the estimator: `stated_rate` is the field
that came back for 2 of 92 processes. The estimator does not see full text. It
sees the scouts' validated quotes and notes, about 94K tokens for all processes,
against roughly 1.1M for their messages. That is what lets one call put every
process on one scale.

So the estimator can report a stated rate only if a scout quoted the sentence
that states it. The scout prompt asked observations to show how the work
happens, the time it takes or how it could be saved, but not how often. The two
misses have different causes:
- **Nightly checkout:** "each night" was quoted, and the estimator still
  skipped it.
- **Daily nominations:** only the attachment names say "Daily". A sentence
  stating the rate may never have been quoted.

**Change:** the scout observation definition now includes how often the pattern
happens, with the reason: counts fall short because the archive holds only part
of the mail. Frequency statements then reach the estimator as quotes, with notes
saying what they mean.

The separate rate call is not built. It will be considered only if stated rates
are still missed once scouts record them. Testing this needs the scouts re-run.

## 2026-11-01 — Trial with scouts recording frequency (scratchpad/trial3)

This run was user-approved: 15 scouts, merge and estimate on a fresh scratch
copy.
- **Time:** about 8.6 minutes in all. The scouts took about 6 minutes in two
  waves (206 s and 150 s), merge 33 s and estimate 119 s. The run stopped once
  with CONTINUE before merge, which is correct: the elapsed time plus the
  longest wave would have passed 9 minutes.
- **Scouts and merge:** 261 patterns, 10 of 2,826 citations rejected, 114
  processes (40 merged), 7 resting on one message.
- **Frequency notes:** 93 of 633 observation notes now mention how often
  something happens, up from 66 of 592.
- **Stated rates:** 22 of 114 processes, up from 2. New ones include the nightly
  checkout (30/month), nightly officialization, nightly CAPS finals, a daily
  congestion exposure tally, and audit requests ("we recieve several per
  week"). Daily nominations, at 83 occurrences, still got none.
- **Ranking:** about $7,100/month in total, up from about $1,330. The top 10
  hold 88% of it, and 7 of those 10 rest on a stated rate.

**Problem: about half the stated rates cite a quote that does not state the
rate.** The rate came from the scout's note or from the dates. Examples:
- "I believe that we agreed that" → 1/month;
- "Energy Market Report" → 21/month (note: "forwarded as FW: each business
  day");
- the nightly checkout cited "started in HE 19 and finished by HE 21" rather
  than "each night".

Someone who clicks the number would land on a quote that does not support it.
The estimator prompt now says the rate is shown with its quote as evidence, so
it must be read from the quote's words, not from a note or the message dates.
Not yet re-run.

**Concern: one message is now the top opportunity.** proc-110, the purchase
requisition workload, rests on one message from Mary Poorman: "between you and
me the purchase requisition process eats half my week, every single week."
- The estimate is 600 min × 4/month = $3,400/month, 48% of the total.
- Proposed: keep it ranked, show on every opportunity how many messages it
  rests on, and say in NOTES that it needs confirming. No threshold.

## 2026-11-01 — Scout rate instruction made a demand; Opus-low proposed

The user asked whether the scout prompt demanded frequency or only listed it.
It only listed it: "how often it happens" was one of four things an
observation's note could be about. It also said nothing about what the quote
should contain, so the scouts put the rate in the note ("Sent roughly daily")
and quoted something else ("Credit Report for 3/13/2001").

The rate instruction now stands on its own. Whenever a message says how often
the work of a pattern is done, the scout records an observation that quotes
those words. The reasons are given: the count falls short, and a rate is used
only with a quote whose own words state it.

**Problem 2 withdrawn.** The user pointed out that the purchase requisition
message is valid evidence. It is a person saying, in their own words, that a
process takes half their week. Drill-through already shows that it rests on
one message, so it gets no special handling. NOTES can use it as an example
of a figure that rests on one person's word.

**Model trial proposed.** The user suggested Opus at low effort for the scouts.
`claude -p` takes `--effort` (low to max), and the agent file sets the model.
Plan: the new prompts on Sonnet, then the same prompts with Opus-low scouts,
so the effect of each change can be seen.

## 2026-11-01 — Trials: new scout rate instruction on Sonnet, then Opus-low scouts

**Trial 1, Sonnet scouts with the new prompts** (`scratchpad/trial4`; about 6
minutes in one invocation, no CONTINUE):
- 250 patterns, 26 of 2,758 citations rejected (22 quote not in message, 4
  message not in batch), 89 processes.
- 494 observations. 47 quotes contain words saying how often, up from 36.
- **10 stated rates, and every cited quote states its rate in its own words**,
  against about half of 22 in the previous trial. Examples: "You must check out
  with all major marketers and utilities each night", "books are marked
  official each night before going home", "we are receiving daily updates from
  legal", "we recieve several per week".
- The weekly California report lost its stated rate, since "Week of
  02/04-02/08" states nothing. Daily nominations still have none.
- About $3,960/month in total; the top 10 hold 74%.
- **Estimator variance on minutes:** purchase requisitions got 120 min/week
  saved, against 600 in the previous trial, from the same quote ("eats half my
  week"). That is $680 against $3,400/month.

**Trial 2, Opus-low scouts** (`scratchpad/trial5`; scouts set to `model: opus`,
`effort: low`):
- All 8 first-wave scouts hit the 8-minute worker timeout. There was no output
  and the run failed.
- Sonnet scouts take 70–206 s on the same batches and write 15–18K tokens.
  Whether Opus was slow per token or throttled with 8 running at once can't be
  told from this.
- The workers were killed cleanly: claude.exe is native, and no stray
  processes were left.
- The scouts are back on Sonnet.

The run log now names each worker's model (`claude-sonnet-5-5`), so model
settings can be checked after a run.

## 2026-11-01 — Chunk budget raised to 200K; run-to-run variation looked into

**Chunk budget 100K → 200K** (user's call, from the budget table earlier):
- The corpus now packs into **7 chunks** (193–200K estimated tokens each,
  210–561 messages), so all scouts run in one wave.
- Sonnet 5.5 in Claude Code has a 1M context and a 128K output cap (read from
  the CLI's model table), so the earlier worry about the output limit is gone.
- The 3.5 chars/token estimate runs high. From trial4's logs the model counts
  67–83% of it (93% for the numeric giant message), so a full chunk is about
  150K real tokens.
- Scouts wrote about 148 output tokens/s in trial4. Twice the output means
  roughly 3–6 minutes per scout, so the worker timeout went from 8 to 9 minutes.
  That is the most that fits in one 10-minute shell call after prepare (3.5 s),
  since the first wave always runs.
- **A budget change now repacks.** Previously a re-run kept every chunk whose
  messages were unchanged, so the new budget would have done nothing on an
  `out/` that already had chunks. Each chunk now records its budget and is kept
  only under the same one. Ids still continue after the highest old id: an
  existing `out/` gets chunk-016 to chunk-022, and a fresh one gets
  chunk-001 to chunk-007. Tested both ways on a copy of `out/`.
- The giant message (`farmer-d/logistics/3221.`) now shares chunk-006 with
  209 other messages instead of having a chunk to itself. Its real-corpus test
  now checks the message is whole rather than alone. In the next trial, check
  that its patterns still appear.
- Baseline for that trial, at 100K: the scouts cited 66–69% of messages and
  recorded 250–261 patterns (trial3, trial4, the first full run). With twice
  the messages per scout, coverage may drop.
- 56 tests pass.

**Run-to-run variation, from existing data:**
- **Estimator alone, same input** (trial2, two runs; only the rate paragraph
  differed): totals of $1,303 and $1,330/month, and the same top 10.
  - 47 of 92 minute estimates were identical, and 90% within 1.6x.
  - The largest swing was $90/month.
- **Full re-runs** (trials 2–4, each with prompt changes, so not pure noise):
  the same evidence came out differently.
  - Merge: "eats half my week" sat in a catch-all process in trial2. In trials
    3 and 4 it was a process of its own.
  - Estimator, purchase requisitions: both runs read the work as half a week
    every week. Trial3 saved half of it (600 min); trial4 saved "a portion,
    about two hours" (120 min). Trial3's scout note said "simplification would
    give a large weekly saving"; trial4's didn't.
  - Estimator, nightly checkouts: trial3 took a quarter of the two-hour window
    (30 min). Trial2 (both runs) and trial4 took only the save step per call
    (10 min). The "HE 19 to HE 21" quote was present in both 3 and 4.
- **Pattern:** the minutes are one number made of two judgments: how long the
  work takes each time, and what share of it the change saves. The first
  usually has a quote. The second has nothing to rest on, so it moves with
  note wording and with which reading of the change the estimator picks. The
  reasoning is terse (about 130 output tokens per process in trial4, e.g.
  "Save step per call."), which hides which judgment moved.
- Not yet known: the estimator's spread on identical input now that stated
  rates multiply large minutes. Trial2 had almost no stated rates. Proposed:
  three estimator runs on trial4's processes with the current prompt
  (`scratchpad/repeat_estimates.py`, compared by `compare_estimates.py`).
  Awaiting permission.

**`out/` cleared** (user approved). It held only prepare output from an earlier
session at the 100K budget. The next run numbers chunks from chunk-001.

**Estimator run three more times on trial4's processes** (user approved; same
prompt and input as trial4's own run, 119,786 input tokens each; 84–102 s in
parallel). The four runs on identical input:
- **Spread is much larger than trial2 suggested.** Only 3 of 89 minute
  estimates were the same in all four runs. Largest/smallest: median 2x, p90
  4x, max 6.7x.
- Totals: $3,958, $4,472, $4,759, $4,533/month. The top 10 shares only 6
  processes across all four runs; 16 different processes appear in some run's
  top 10.
- **Stated rates: a recall problem.** The runs found 10, 7, 6 and 4 stated
  rates. 13 processes have one in some runs and not in others. Each run spots a
  different few of the rate-stating quotes; the quotes themselves are genuine,
  e.g. "We must call Grays Harbor and Frontier at the top of EVERY hour" (720/mo,
  found once, $1,530/mo) and "we recieve several per week" (found once). One
  was misapplied: "pathing goes on every day on every pipeline" was given as
  the rate of the Path Manager feedback round.
- **Minutes: the share saved moves.** Purchase requisitions: all four read
  "about 20 hours weekly"; the saving was "a portion, about two hours", "a
  quarter", "a large part, around 8 hours" and "roughly 8 hours" (120, 300,
  480, 480 min). Surveys: 8–25 min. Nightly checkout: 2–10 min. Reasoning
  length also varies by run (42–112 characters per process on average).
- **Which drives what.** Holding each process's rate fixed and letting only
  the minutes vary, the top 10 keeps 9 processes in every run (11 distinct),
  but totals swing $5.4K–$9.8K because the hourly checkout multiplies its
  1.5–5 minutes by 720. Holding minutes fixed and letting only the rates vary,
  it keeps 8 (14 distinct). Rate recall decides who is in the top 10; minutes
  decide the dollars.
- The trial2 comparison looked stable only because it had almost no stated
  rates and fewer large-minute processes.

## 2026-11-02 — score step and dashboard

**`score` (pipeline/score.py), all arithmetic in code.** For each process the
rate is the larger of the counted rate (occurrences / distinct months in which
its mailboxes have any mail) and a stated rate, used only when its quote is one
of the process's own. Hours = minutes x rate / 60, dollars = hours x $85,
rounded as shown, running total adds the shown figures. An estimate naming none
of the process's quotes is listed but not ranked. Top 10 with dollars > 0 are
marked for drafting. On trial4: 89 ranked, $3,964/month, 46.6 h, top 10
$2,944. 7 tests.

**Dashboard (pipeline/serve.py + pipeline/dashboard.html).** Stdlib HTTP server
on 127.0.0.1:8765; one static page. The server computes no figures: it serves
the run's files (`/api/report`) and one message at a time (`/api/message`), by
id from messages.jsonl only, never a path from the request. For each quote it
returns where it sits in the message, matched the way validate matches
(reply markers, whitespace, curly quotes, case), so the drawer highlights the
exact words; the raw file is a second tab. All 2,589 quotes of trial4 locate
in their message; 29 are not literally in the raw file (quoted-printable line
breaks), and the drawer says so. Every number is a link: dollars to the
formula card, minutes to the basis quotes, rate to the stated quote or the
counted occurrences, sender/recipient counts and chart months filter the
occurrence list. Pages: ranked opportunities, processes, how the archive was
read (duplicates, date issues, rejected quotes, the untrusted message, log).
Email text is only ever inserted as text, never HTML.

**Auto-start.** `run` starts the dashboard when it stops with
opportunities.json present (DONE or FAILED, not CONTINUE) and prints a
`dashboard:` line. It is started detached (on Windows outside the shell's job)
so it outlives the run command; a dashboard already showing the same out/ is
reused, and a port held by anything else is skipped. `py -m pipeline serve`
runs it in the foreground. The run-pipeline skill now reports the address.
Checked: started from a shell call, still answering after the call ended.

Tests: 71 pass (test_serve: locate, the API against a temp run, 404 for ids
outside the run, port reuse). test_state's unbuilt-step test now ends at
finalize, since score is built and nothing is drafted with no estimates.

## 2026-11-02 — Dashboard live from the start; one run per folder; one page

**User asked:** what happens when a run already exists (prompt to restart?);
the orchestrator should always give the dashboard link; the dashboard should be
live when the run begins and show progress. Then, mid-way: make the dashboard
as simple as possible, one page, one button per opportunity, nothing that does
not help leadership decide.

**One run per output folder.** `run` holds an OS file lock on `out/run.lock`
for as long as it works (msvcrt on Windows, flock elsewhere). The OS drops it
when the process ends however it ends, so a run killed by the shell's time
limit never leaves the folder locked. A second `run` on a locked folder ends
`FAILED another run is in progress on this output folder` without touching it.

**New commands.** `status` says whether out/ holds a run: NONE, RUNNING,
STOPPED before <step>, CHANGED (corpus differs; continuing redoes only what
the change affects) or DONE. `reset` removes the run's outputs (an explicit
list, `RUN_OUTPUTS`, never the folder itself or anything else in it) and
refuses while a run holds the lock. `dashboard` starts the dashboard in the
background and prints its address.

**Skill.** The orchestrator runs `dashboard` first and gives the user the
address, then `status`; for an earlier run it asks whether to continue or start
over (`reset`), continuing if it cannot ask, and stops if a run is in progress.
`run` also starts the dashboard before any work, for people running it from a
terminal. Under `claude -p` nothing the orchestrator says is shown until it
finishes and it cannot ask; launched interactively it can do both.

**Progress.** `run` keeps `out/run.json` current (started, step, the workers in
flight, final status). The server's `/api/progress` returns that, whether the
lock is held, and how far each step has got from the files in out/
(`state.progress`, next_action's order without hashing the corpus). The page
asks every 2 s while a run is active, 5 s otherwise, and refetches the results
only when an output file changes. The server log moved to the temp folder so
the server holds nothing in out/ open and `reset` can clear it under a running
dashboard.

**One page.** Header with the run's state; three figures ($/month, hours,
top-10 $) and one sentence of method; the top 10 with a bar, hours and the
running total, a line where drafting stops, and one button for the rest. Each
opportunity has one button, its dollar figure, which opens the formula, why
that many minutes (reasoning and quotes) and why that often (stated quote, or
the count, with every message behind it). Any quote opens its message with the
words highlighted. While nothing is ranked, the page shows the steps with a
meter. The processes, reading, chart, who, observations and raw-file views
are gone; the report endpoint sends only what the page uses.

Tests: 78 pass (lock refusal, run record, progress, status, reset, progress
endpoint).

## 2026-11-02 — Dashboard columns; the change explained in full

User asked: no bars in "Saved a month"; "Hours" is unclear; "Running total"
perhaps "Cost so far"; the suggested change should be explained more fully when
an opportunity is opened.

- Bars removed; the column is just the dollar button.
- Columns are now "Hours saved a month" and "Saved so far". Not "Cost so far":
  the figure adds up savings from the changes, not what the work costs today,
  and the page never computes the latter.
- The estimator now also writes `explanation`: the change explained for the
  managers who decide on it (how the work is done today, what would be built
  or changed and who would use it, how the work would go afterwards), drawn
  from the process's quotes so it describes this organization's work. `change`
  stays the one line in the list. Schema and score pass it through; score
  accepts estimates without it, since trial4's predate it.
- Opening an opportunity now shows, first, "How the work is done today" (the
  process summary) and "The change" (the explanation, or the one line where
  there is none), then the formula and the evidence.

Not yet run with the model: trial4's estimates have no explanation, so its
dashboard shows the one line under "The change".

## 2026-11-02 — Evidence redesigned; why the evidence was weak

User found the evidence quotes unintuitive, "Why that many minutes" and "Why that
often" indistinguishable, and a cooling-water forward cited for "Audit and
accounting document requests".

Traced in trial4. The forward ("Can anyone answer Cheryl's question below.") is
an occurrence of a scout pattern "Third-party inquiry and audit support requests
routed to the wrong person": a grab bag whose other occurrences include "Please
remove me" from a mailing list. The merger saw only that name and summary and,
by the word "audit", put it in the audit process. The same happens at scale: #6
holds 19 patterns (discrepancies, ticket corrections, chasing, disputes), #8
mixes surveys with access lists and report postings, #9 includes "Forwarding
emails to colleagues for action". Over-grouping inflates both the count and,
via a stated rate from one pattern, the rate of the whole. Separately, the
estimator cites rate quotes as the basis for its minutes (#3's minutes rest on
"we recieve several per week") and writes one-line reasoning, so both "why"
boxes showed the same kind of quote.

Dashboard (deterministic, done):
- The evidence follows the formula: "How often it happens" (value, whether
  stated or counted, why the archive count falls short, the quote) then "Time
  the change saves each time" (value, marked as an estimate, the reasoning, each
  quote with the reader's note on what it shows). A minutes quote identical to
  the rate quote is shown once.
- The messages list is grouped by the pattern each message was recorded under,
  each row giving date, subject and sender with the quote beneath, so it is
  visible why a message counts — and where a grouping is wrong.
- The report now carries pattern names (from validated.json).

Pipeline (prompt changes, not yet run):
- merger input now has each pattern's occurrence quotes (~48K tokens on
  trial4), and the merger judges what recurs from what the quotes show people
  doing; it groups only when one change would save time on each occurrence,
  since the count takes every message of every pattern.
- scout: a pattern is one thing, not things sharing a subject or people; an
  occurrence's quote must show the pattern happening to someone who knows only
  its name.
- estimator: `basis` is the quotes showing what the time is spent on and how
  much the change removes, not rate quotes; `reasoning` says what is done each
  time, about how long, and which part the change removes.

Tests: 78 pass.

## 2026-11-02 — Full run with the new prompts (scratchpad/trial6)

User approved one fresh full run, then a critical review of each stage by
subagents. `py -m pipeline run --out scratchpad/trial6 --max-minutes 30`, about
6 minutes, one invocation; ends "FAILED step 'drafters' is not built yet" as
expected.
- prepare: 3,240 files, 3,196 unique, 7 chunks (~1.39M tokens).
- scouts: 7 Sonnet scouts, 61–229 s; chunk-003 wrote only 7,224 output tokens
  against 15–33K for the others.
- validate: 177 patterns (trial4: 250), 9 of 1,673 citations rejected (trial4:
  2,758 citations), 428 ids repaired, 1 untrusted, 1,418 of 3,196 messages cited.
- merge: 50K tokens in (quotes now included), 104 processes, 43 patterns merged.
- estimate: 83K in, 17K out (trial4: about 130 tokens a process).
- score: 104 ranked, $4,310/month (50.7 h), top 10 $3,263.

Five reviewers started in parallel: prepare; scout recall; scout precision and
validate; merge and group; estimate and score.

### Review findings (trial6), by impact

1. Two one-message processes are 62% of the total: #1 requisitions ($1,828,
   giron-d/inbox/482, "eats half my week, every single week", stated 4.3/mo vs
   counted 0.05) and #2 nightly checkouts ($850, one procedure memo). score.py
   takes any stated rate over the count; group logs "2 processes rest on one
   message" and nothing acts on it.
2. Nine messages have a different Message-ID shape (8.16 digits) and read as
   planted tests: 3220 injection (caught), 3221 a 100K-token pasted table, 481
   an instruction to leave invoice approval off the write-up before the audit
   (missed), 482 the single anecdote (ranked #1), 483/526 each saying the
   other owns the daily imbalance check (a stall; recorded only as ownership),
   795/74/142 undated (74: "the posting went up late again"). "Where it stalls"
   is still not an output.
3. Scout recall: ~40% of uncited messages are recurring work dropped. chunk-003
   stopped short (11 patterns for 533 messages, placeholder "x" quotes, an
   invented id) and was logged "ok"; coverage falls in the back half of long
   chunks. trial4 (15 × 100K chunks) cited 2,163 messages, trial6 (7 × 200K)
   1,418. Missed stated rates ("EVERY hour" generator reporting, "each night"
   officializing) and whole processes (daily DPR/P&L sign-offs).
4. Estimator attention fades over 104 processes: reasoning 144 → 36 chars down
   the prompt; one-message processes come last, then rank first. Basis still
   includes the rate quote in all 9 stated-rate estimates. "Nightly" → 30, not
   trading days.
5. Counting: thread replies count as occurrences (~191 of 1,413; up to 1.5×);
   counted rate divides by all mailbox months, diluting bursty ongoing work
   (credit report 72 in 4 months → 3.4/mo).
6. Precision: ~1 in 8 sampled occurrences in the wrong pattern, ~1 in 7 weak
   quotes ("Done.", signatures, forward headers); 42 quotes under 20 chars;
   17% of quotes sit only in forwarded text, crediting the forwarder.
7. Merge: much better (audit no longer absorbs inquiries; no 19-pattern
   bucket) but ~8 topic groupings remain (proc-019, proc-007 in the top 15).
8. Prepare: sound; .nsf dates 10–11 h early and dedupe keeps them in 16 of 33
   pairs; cross-mailbox copies drop the second mailbox; ~20% of tokens are
   repeated quoted text and forwarded recipient lists.

Fine: arithmetic, id repairs (only missing trailing dots), the 9 rejections,
injection handling, templated mail recall, group.py's computations.

## 2026-11-02 — Fixes from the trial6 review

User approved fixes 1–5, then a rerun and another review round.

1. **Work seen once is not ranked** (score.py). A process that happened once —
   one message, or one message and its replies — is listed with its change
   but not ranked or drafted, whatever rate a quote states. The dashboard lists
   these under "Seen once, not ranked".
2. **Stalls** (scout.md, schemas, validate, group, estimate, dashboard). Scouts
   record, per pattern, where its work waits or goes wrong between people:
   unanswered or chased requests, ownership passed back and forth, late or
   redone steps, work held back or kept out of view. Checked like observations,
   carried into processes, shown to the estimators (who say whether the change
   removes the stall), shown per opportunity and in a "Where work stalls"
   section in ranking order.
3. **Recall.** Chunks back to 100K tokens (comment gives the trial6/trial4
   numbers). Validate logs each chunk's coverage, so a scout that stopped short
   shows. Scouts: the Subject line may be quoted; a sentence saying how often
   work is done is recorded under its pattern even when the message is about
   something else.
4. **Estimates in slices** (estimate.py, state.py, run.py). Slices of about 20
   processes, each taking every k-th process by size so each spans the range;
   every estimator also sees all other processes' names, summaries and counts
   for scale. Outputs `estimates/slice-NN.json`; progress counts slices.
   Estimator: daily or nightly is about 21 working days a month unless the
   quote says every day.
5. **Counting** (group.py, score.py). Times, not messages: a later occurrence
   with the same subject (less RE:/FW:) that contains an earlier one's text with
   more of its own is the same time. A daily mail with the same subject is a new
   message, not a quote, so it stays a time each day. The estimator says
   whether the work is `ongoing` or an episode; ongoing work is counted over
   the months from its first time to its last, an episode over all months.
   Dashboard says "N times (M messages; a reply is counted with what it
   answers)" and which months.

Tests: 82 pass (slices, times by quoting, ongoing span, once-unranked, stalls
validated, coverage logged).

Rerun approved: `py -m pipeline run --out scratchpad/trial7 --max-minutes 30`.

## 2026-11-02 — trial7 run and a score fix

trial7 ran in one invocation, about 15 minutes. 15 chunks of 100K; 252
patterns; 7 of 2,361 citations rejected; 1,731 of 3,196 messages cited (trial6:
1,418). chunk-003 still cites only 106 of 259. Group: 152 processes, 1,544
times in 1,719 messages, 16 happen once, 394 stalls. Estimate ran as 8 slices.

One slice's estimator wrote quote ids prefixed with the pattern id
(`chunk-005.p20.q32`), so its 19 processes were unranked as "estimate names
none of the process's quotes". score.py now restores such an id to `q32` when
the prefix is one of the process's own patterns (`quote_id`, tested); rescored
deterministically. Result: 136 ranked, $3,724/month (43.8 h), top 10 $1,324;
16 not ranked (14 happened once). The requisitions aside (482), the held-back
write-up (481) and the late posting (74) now sit under "Seen once, not ranked".

Concern noted for review: ongoing work whose times all fall in one month gets a
one-month span, so a burst counts as its full monthly rate (#2 contract
termination reporting, 3 times in 1 month; #8 Transwestern billing, 4 in 1).

Second review round launched on trial7 (5 read-only reviewers).

## 2026-11-02 — trial7 review (round 2)

Five read-only reviewers (scripts in scratchpad/review2/). Fine: arithmetic
exact; every sampled quote verbatim and highlighted right; validation sound
(6 of 7 rejections real fabrications, id repairs only trailing dots);
injection isolated; slices fixed estimator decay; no scout stopped short;
last round's named rate misses now cited.

Problems, by effect on the ranking:
- Short spans inflate rates: 25 ranked items with spans of 2 months or less
  are $998 (27%). #2 contract termination report is monthly but counts 3/mo;
  #8 is one thread forwarded plus an unrelated message. Times ÷ span counts
  n points over n−1 intervals. The ongoing label is a ~7x lever, set
  inconsistently.
- count_times bug: a short body ("- CALPINE DAILY GAS NOMINATION 1.doc") is
  "contained" in every later nomination, folding 12 daily mails into one time.
  Missed folds: bare Notes replies that quote nothing (~30), edited forwards.
- Merge splits one piece of work at a batch boundary (proc-001 / proc-016,
  proc-033 / proc-049); each part is rated over its own span, so they add.
  The merger sees quotes without dates or senders. Topic groups remain
  (proc-012 El Paso, proc-019 procedures plus news).
- Stated rates: only 3 of 10 are stated in the quote's words; the rest come
  from scout notes or read a date or report title as a cadence (#1, #7, #10).
- Recall fell against trial4 on the same chunks (business messages about
  1,783 to 1,584; observations 494 to 239) as stalls took the scouts'
  attention. Giron's nightly P&L/DPR cycle is still mostly uncited.
- Precision about the same: ~5% wrong pattern (15% in the top 20, mostly
  one grab-bag pattern), ~17% weak quotes; chase or apology quoted as the
  occurrence. Stalls ~60% solid, ~30% weak (open requests recast as waits).
- Seen-once holds the most striking findings (482 half a week, 481 held back,
  PACE $57,000 paid for unused transmission).
- Dashboard says the top 10 "are drafted" (none are); "Saved so far" reads
  as realized savings; 390 stalls ungrouped; 28 quotes are in
  quoted-printable files, so Ctrl-F on the raw .eml misses them; non-work
  ranked (chain mail, newsletters, $0 Dell confirmations); hero figures not
  clickable; phone width overflows.

## 2026-11-02 — Committed; fixes from the round-2 review

Committed everything and pushed to origin/main (af27996), as asked.

User decision: work seen once counts as a flow when its email says the work
recurs; otherwise it need not be ranked.

- **Seen once** (score.py): a process that happened once is ranked on a rate
  one of its own quotes states, and listed but not ranked otherwise. On
  trial7's estimates this ranks the requisitions (482) and the nightly
  checkouts.
- **Bursts** (score.py): ongoing work counts the gaps between its times
  (times − 1) over the months it spans, so three times in one month is two a
  month, not three; the count again falls short rather than over.
- **Times** (group.py): a reply or forward (RE:/FW:) is the same time as the
  latest earlier occurrence with its subject, quoted or not (Notes replies
  quote nothing; forwards are edited). A message without the prefix joins one
  whose own text (before the first quote header) it quotes, or one it copies
  within ingest's duplicate window. Fixes the Calpine bug: a short body was
  "contained" in every later nomination. Each process's `months` now counts
  times begun per month. On trial7: 1,544 to 1,502 times; nominations 65 to
  76; Transwestern 4 to 2; Colstrip 2 to 1 (unranked).
- **Score**: a change that saves no time is not ranked; a basis quote named
  twice is shown once.
- **Estimator**: sees times begun per month and judges `ongoing` from them;
  notes are labelled "Reader's note"; minutes are per counted time, not per
  cycle; mail the work does not need gets 0 minutes; a date or report title
  is not a rate; a process seen once is ranked only on a stated rate.
- **Merge**: each occurrence is shown with its month and sender (validate
  writes them to names.json), and the merger is told batches are consecutive
  stretches of the same mail, so later batches continue earlier work.
- **Scout**: occurrences come first, stalls and observations are added to
  them, not instead; a chain's occurrences are whole runs, and a message
  showing a different act belongs to that act's pattern; an occurrence quote
  shows the work, not a chase or apology; a stall needs words saying the wait
  happened, and goes under the work it holds up; a date or title is not a rate.
- **Validate**: control characters are dropped when matching (serve's locate
  likewise), fixing the one false rejection.
- **Dashboard**: says "Incomplete: drafting … is not built yet" instead of
  the raw failure; "are the ones to be drafted" until drafts exist; "Running
  total" for "Saved so far"; headline figures link to the table; page-level
  stall list dropped (each opportunity keeps its own, without repeating its
  basis quotes); the drawer notes quoted-printable files; phone-width CSS.

Tests: 85 pass. Rerun approved: trial8.

## 2026-11-02 — trial8 run

First attempt: 3 of the first 8 scouts (chunk-002, -006, -008) gave no reply
in 9 minutes while the rest took 76–107 s; resumed the same run, which
reused the finished chunks. Then: 247 patterns, 13 of 2,090 citations
rejected, 1,657 of 3,196 messages cited (trial7 1,731; chunk-013 only 71 of
271). 146 processes, 1,445 times in 1,593 messages, 20 once. 130 ranked,
$5,636/month (66.3 h), top 10 $4,103. #1 requisitions (482) $2,267 on a
stated 4/month × 400 min and #2 nightly checkouts $892: 56% of the total on
two single messages. 5 ranked items rest on one time.

Third review round launched (4 reviewers: scout, merge/times, estimate/score,
dashboard).

## 2026-11-02 — trial8 review (round 3)

Four read-only reviewers (scripts in scratchpad/review3/). Fine: arithmetic
exact; all 30 sampled quotes verbatim; planted messages all handled; bursts
mostly labelled episodes (short-span ongoing $998 to $309); daily mail and
Calpine counted right; last round's grouping examples mostly fixed; top-20
wrong-pattern share 15% to 3%.

Problems:
- Five one-time items are 57.5% ($3,242). #1 requisitions: 400 min rests on
  an unquoted "cut about a third", and the change moves work to other
  approvers rather than removing it. #2 checkouts: rate quote is a time
  window, minutes from a deadline, and the change is what the memo itself
  announces as already rolling out.
- Stated rates still taken from scout notes (dates, titles, a time window):
  $1,179. Two rounds of prompt rules have not stopped it.
- Recall: business messages cited 1,663 to 1,554; about a third from the new
  chain rule, read as "cite one message per chain" (fully cited 3+ threads 58
  to 36). Output length per scout varies about 3x between runs.
- Patterns named by channel (broadcasts) mix procedures with operating news
  (proc-005); deal setup split within one batch (proc-001/066/067).
- count_times: a quoting RE: joins the latest same subject even when it
  quotes something else, up to 496 days apart (13 folds over 7 days).
- Non-work still ranked (chain mail, newsletters, a $0 Dell order); $1 rows;
  formula line shows hours to 1 decimal so the product doesn't check; the
  gaps rule isn't explained on the page.

## 2026-11-02 — Review of the round-3 proposals

Wrote the proposed fixes as exact old/new text (scratchpad/proposals-round3.md)
and had a read-only reviewer judge them against trial8 (scripts in
scratchpad/review4/).

Corrections: most of the "$1,179 from notes" is proc-136, whose rate is real
(its q1 says "each night"); the estimator cited the wrong quote. The 202
uncited siblings include 74 empty subjects; of the real 128, 96 are replies
that fold into a counted time, so S1 adds evidence, not dollars.

Verdicts: keep the rate-words check (C1/E4) as the main fix; keep the
dashboard formula, gaps, highlight and collapsed once-seen list, and drop $0
rows. Reword E1 (net saving, so centralizing changes are not zeroed), E2, E3
(no multiplying by every recipient), E5, S1, S2, S3. Drop C2 (undoes 35 folds,
about 20 of them right, and breaks the edited-forward cases), M1 (would bring
back topic groups), the dollars-from-unrounded-hours change (stored figures
already check) and the one-message tag/two totals. Missing: hung scouts
needed a manual resume (no retry inside one run); chunk-013 cited 71 of 271
and nothing flagged it; #1's 400 minutes still rest on a guess.

## 2026-11-02 — Second review of the revised proposals

Revised set in scratchpad/proposals-round3b.md; two read-only reviewers, one on
prompts and one on code (scripts in scratchpad/review5/).

Prompts: S3 dropped (E4 plus the code check does its job). S1, S2, E4, E5
reworded: acknowledgements do no work; sending counts as a pattern when it is
the work; the rate's `words` empty when none; codes explained only as far as
the quotes show. The minutes paragraph split in two and must say that mail
doing the work today is work, even if the change makes it unnecessary.
Expected effects: #1 stays near $2,267 (a judged third, an aside in one
message), surveys rise to about $1,100 because recipients' time now counts.

Code: the rate check searches the cited quote, then the process's other
quotes in order ("exactly one other" fails on duplicate quotes). The $0 rule
is kept but the dashboard was not off by one (it already filters); the
table's Hours column needs 2 decimals too. The retry as drafted could loop
forever through CONTINUE; it needs a FAILED for a task that failed before.
The worker timeout is not hard on Windows (622-723 s against 540: the stdin
write has no timeout), so it needs a kill timer, and the reviewer suggests 4
minutes. C2 drop confirmed; a narrower date rule exists but nets +$16.
chunk-013 is partly a real miss but has no trigger free of a threshold.

## 2026-11-02 — Round-3 fixes applied

- Rate check (score.py): a stated rate is used only if the estimator's `words`
  are in one of the process's quotes: the cited one, else the first that holds
  them. The stored words are the quote's own span and are marked in it on the
  dashboard. On a copy of trial8 with the words an estimator would copy for
  #1-#3, those three keep their rates (#2 now cites "each night"); the other
  seven old stated rates, which have no words, fall back to counts.
- Rows under a dollar a month are not ranked (proc-103); the dashboard filter
  for them is gone.
- Retry (run.py): a failed worker is tried once more, in this invocation or,
  if the time runs out, the next (the failures are kept in run.json across
  CONTINUE); a second failure stops the run. A run started after a FAILED one
  tries afresh.
- Timeout (agents.py): stays 9 minutes, now hard. The overrun was not the
  stdin write, as the reviewer guessed: subprocess.run kills only the process
  it started, then waits for pipes that its children still hold (reproduced: a
  1 s timeout took 15 s with a sleeping grandchild). The whole process tree is
  now killed (taskkill /T on Windows, the process group elsewhere).
- Dashboard: hours to two decimals in the table and formula; the counted rate
  shows its division (31 gaps ÷ 8 months = 3.88); "seen once" folded behind
  one line.
- Prompts: scout S1 (every message doing a pattern's work, not
  acknowledgements) and S2 (the way mail is sent, unless sending is the work);
  estimator minutes in two paragraphs (everyone who acts on the message; net
  saving; changes under way; mail that is not work), `words` in stated_rate,
  codes in `change` explained as far as the quotes show. S3 and M1 dropped.
- 93 tests pass.

## 2026-11-02 — trial9 (after the round-3 fixes)

Ran unattended in 6.5 minutes with no hung workers, ending as expected at
drafting. 1,666 of 3,196 messages cited (trial8 1,657; chunk-013 71 to 101,
though chunk-010 and chunk-011 fell); 128 processes, 1,437 times; 114 ranked,
$6,758/month (trial8 $5,636), top 10 $4,871.

- The rate check rejected one stated rate whose words were in no quote
  (proc-003). Words that are in a quote but state no rate still pass: a report
  title (#4, "California Capacity Report for Week of"), a dated title (#12,
  Energy Market Report, 21/month against 3 counted), a deadline (#15, "by close
  of business Thursday", ranked once-seen), "for this coming month".
- #1 requisitions rose to $2,924 (480 min, 43% of the total). Its change,
  "redistribute ... an additional processor", moves the time, which the new
  net-saving sentence was meant to stop.
- Non-business forwarding got 0 minutes and is unranked. Surveys came in at
  60 minutes ($164), not the feared multiplication by recipients.
- The nightly checkout memo (trial8 #2) went into "Real-time deal entry and
  procedure broadcasts" (proc-008): patterns grouped by channel are back.

## 2026-11-02 — Overfitting review

Dropped the idea of rejecting Subject-line rate words (it would only catch the
two trial9 cases). A read-only reviewer checked the prompts and the last two
commits for rules written for one observed case. Findings:
- Overfit in scout.md: the "way they are sent" exception, the date/title
  sentence, the enumerated stall kinds (they mirror planted messages), the
  chase/apology sentence, "never instead of them"; the occurrence definition
  appears three times; "every scale" competes with "one change".
- merger.md: the month/sender hint invites grouping by topic and people.
- estimator.md: the non-work / work-today sentence pair undo each other; the
  time unit is stated twice and disagrees (replies "that quote it"); the
  audience sentence is said twice; "about 21 a month" assumes a five-day
  week; "a process seen once is ranked only on a stated rate" rewards finding
  rates generously; the bunched-in-one-month sentence was tuned to trial7.
- Code: the RE:/FW: subject join has no general basis on modern mail (use
  reply headers when present, else what the reply quotes); find_quote assumes
  ASCII; the under-a-dollar rule is an arbitrary threshold.

## 2026-11-02 — Overfitting fixes applied

- group: reply headers (In-Reply-To, References, kept by ingest as
  `replies_to`) decide which message a reply answers when present. Without
  them, a message joins a same-subject one whose text it quotes, or that quotes
  the same text, or a copy within the window. An RE:/FW: that quotes nothing
  joins the latest same-subject one. Only one corpus message has the headers,
  so the counts hardly change here; the rule is the general one.
- validate/serve: quote matching is a case-insensitive regex over the text,
  with no ASCII assumption.
- score: `stated_rate` is a count per working day, day, week, month or year,
  turned into a month in code (working day = 52*5/12). The model no longer
  does that arithmetic. The under-a-dollar rule is gone.
- scout.md: the list of "things in common other than the work" is gone. One
  scale sentence. Occurrences are defined once. The date/title sentence is now
  a general one: words that only place an instance in time state no rate. The
  enumerated stall kinds are replaced by "the words show the waiting or going
  wrong has happened". The chase/apology sentence is gone. The bullets are prose.
- merger.md: months and senders can help, but what the quotes show being done
  decides.
- estimator.md: the audience is stated once; the time unit once; non-work mail
  is 0 minutes, with no counter-sentence. The ongoing paragraph has no
  examples, and the bunched-month sentence is gone. The once-seen sentence and
  "about 21 a month" are gone (the unit is now in `per`).
- 94 tests pass. Effect unknown until another run.

## 2026-11-02 — A simpler architecture to compare: analyst + critic

Question: does the scout/merge/estimate structure keep the model from reasoning
about the work as a whole? To find out, a second architecture next to the pipeline:
`py -m pipeline explore --out <dir>`.
- One analyst agent (Opus) explores the corpus with Read/Grep/Glob, since 15 MB
  (~4M tokens) cannot be read whole. It writes proposals in its own words
  and sends each to a critic agent (Opus). Neither prompt has a format.
- The critic checks the proposal against the mail. If it holds up, the critic
  writes it as a file and runs `py -m pipeline save <file>`. Otherwise it tells
  the analyst what is wrong. Only the critic can write (to `proposals/`) or run
  anything (only `save`).
- `save` is deterministic. Run without a file, it prints the format it needs
  and what is saved. With a file, it checks every quote (find_quote on the
  decoded message, with a hint when the words only match the raw
  quoted-printable file), counts times with group's rules, and scores with
  score_process. It then rewrites processes.json and opportunities.json, so the
  dashboard is unchanged and fills in as proposals are saved. Any problem means
  not saved, with the reasons printed. Saves are serialized by a lock.
- Isolation: the agents run in `<out>/workspace`, which holds a copy of the
  corpus and `proposals/`. They run with `--permission-mode dontAsk`, project
  settings only, and auto memory off, so they cannot read the code, DEVLOG, earlier
  runs or memory.
- The run is killed after 30 minutes (`--max-minutes`), and whatever was saved
  stands. `agents.call` now takes a timeout, cwd and env, and keeps what a killed
  process wrote; the stream-json transcript goes to `explore.jsonl`.
- Dashboard: an "exploring" status line, and "DONE …" counts as finished. A
  null section rendered as the text "null" when nothing was seen once (fixed).
- 106 tests pass. Not yet run with a model.

## 2026-11-02 — explore1 (5 minutes) and fixes

The first try, 5 minutes on Opus, saved nothing:
- The wiring held. `Agent(critic)` was the analyst's only subagent, sign-in
  worked, and the workspace isolation held.
- The analyst explored for about 3.5 minutes and sent 5 proposals at once.
- The critics' reviews were strong. They read the cited mail and searched
  further, then rejected 3 for real reasons: a wrong premise (a system report
  already flags the meters) and a misattributed quote; work that had stopped,
  with the fix already under way; one replier, not seven. They approved 1
  (the weekly California Capacity Report, $153/month, with 14 reports
  checked). 1 was pending at the cutoff.
- Nothing was saved. The critics tried to read mail with Bash loops, were
  denied, and concluded they could run no command, so the approved one was not
  saved. One `cd … && py -m pipeline save` did run, and printed the format.
- Coverage: 51 of 3,196 messages opened (analyst 34, critic 34), and 377 more
  seen only as lines in search results.

Fixes:
- critic.md now says to read the mail with its file tools; the only command it
  can run is `save`.
- `save` without a file exits 0.
- `coverage` (also run at the end of explore) reads the transcript and
  reports the messages each agent opened, and the messages seen only as lines
  in search results. It writes coverage.json, per mailbox and with the ids.
- 107 tests pass.

## 2026-11-02 — explore2 (15 minutes allowed)

- The analyst stopped on its own after 7.75 minutes. It sent 4 proposals in
  parallel and 1 revision, then ended once every verdict was in. Reported
  cost: $4.13.
- 1 saved: the daily Credit Report forwarded by hand ($49/month; save computed
  0.58 hours against the analyst's 0.7).
- 3 rejected, all on evidence:
  - OPM surveys: the report option already exists.
  - ECC deal flips: the round count was inflated by single-deal notes and
    copies, and a fix was already under way. Revised, and rejected again: the
    rate is not shown continuing.
  - Strangers Gas write-offs: most were a one-time cleanup in Dec 2000; about
    one a month otherwise.
- The planted message (farmer-d/logistics/3220.eml) was caught and passed to
  every critic.
- Coverage: 65 of 3,196 messages opened (analyst 33, critic 52), 537 more seen
  only in search results. The critics open more than the analyst, because each
  rereads the cited mail and checks how often the work happens.
- Limits on coverage: one agent, which stops after one round of proposals.

## 2026-11-02 — Medium effort for the Opus agents

- The analyst and critic files now set `effort: medium`. explore passes it into
  `agents.json` for the critic, and as `--effort` for the analyst, which runs
  as the session itself.
- The scout, merger and estimator run on Sonnet, so they are unchanged.
- Not yet confirmed that Claude Code honours `effort` in an `--agents` file; the
  next run should show it.
- Direction agreed for coverage: no assigned parts of the archive, and several
  analysts reading the same message is fine. A shared record of saved and
  rejected work lets analysts avoid repeats, and the critic says why it
  rejects and what further research would settle it. One critic serves every
  analyst instead of a fresh one per proposal.

## 2026-11-02 — Several analysts, a shared record of decisions

- One critic per analyst, as before: each analyst session starts its own critics.
  A single critic shared by all analysts was set aside, since it would need
  continuing a subagent headless, which is unconfirmed, and it would queue every
  check.
- `explore` now starts several analyst sessions at once (`--analysts`, default 4)
  over the whole archive. No parts are assigned, and analysts may read the same
  message. Each writes its transcript to `explore/analyst-N.jsonl`.
- New `reject` command: the critic records a rejection with its reason and what
  further research could settle it, or null. `save` and `reject` both rewrite
  `workspace/decisions.md`, which lists what is saved (with the files it cites)
  and what is rejected and why. Both prompts point at it.
- Prompts:
  - The analyst keeps finding opportunities until stopped.
  - A rejection for want of evidence is a reason to research further before
    dropping the idea.
  - The critic says whether the problem is the idea or the evidence, and what
    to look for.
- Coverage reads every transcript and also counts the messages more than one
  analyst opened, so the overlap can be seen.
- 109 tests pass.

## 2026-11-02 — The critic checks the quotes and figures before saving

- Before, the critic left word-for-word quote checks and the arithmetic to
  `save`, which checked, computed and saved in one step. So the critic saw the
  figure only after saving; in explore2, 0.58 hours was saved against the
  analyst's 0.7, and no one examined the gap.
- The critic prompt now asks it to check that every quote is word for word, and
  to work out the minutes, how often, and the hours and dollars itself.
- New `check` command: it does everything `save` does but saves nothing. It
  prints the problems, or the figures with how they were worked out (counted
  times over months, or gaps over the span for ongoing work, and any stated
  rate). If its figures differ from the critic's, the critic finds out why
  before deciding. `save` prints the same working.
- The code stays the final word on quotes and arithmetic, as the assignment
  requires; the critic's own check comes first.
- 111 tests pass.

## 2026-11-02 — Critic prompt made concise; the file forms in its prompt

- The critic now judges what code cannot: that the claims are accurate and the
  estimate of minutes and how often is realistic. It checks against the whole
  archive, not only the cited mail. Word-for-word quotes and the arithmetic are
  left to `check`, whose figures it compares with its own judgement.
- Dropped the sentence on messages reappearing in other files: the code counts
  copies once and a message with its replies as one time.
- The forms of the proposal and rejection files are added to the critic's
  prompt by `agent_definitions` from the definitions the code checks. The
  prompt file stays prose, and the critic no longer needs a call to learn them.
- Then removed the sentence telling the critic to check against the archive,
  not only the cited mail; the paragraph now opens with when a proposal holds up.

## 2026-11-02 — explore3 (4 analysts, 15 minutes allowed)

- All 4 analysts ended on their own between 10.5 and 14.5 minutes, each saying
  the obvious work was claimed or ruled out. Cost $39.38 (9.87 + 9.19 + 11.42 +
  8.90), above the $15-30 guess.
- 3 saved, $279 a month, but two are the same work: the weekly Transwestern
  California Capacity Report was saved twice, 46 seconds apart ($114.75 and
  $99.45), by two critics working at once. Two later copies were rejected as
  duplicates. The third is the ECC deal flips ($64.60), saved on the third
  revision after rejections that asked for more research.
- 29 rejected. The commonest reason: the minutes were assumptions, since almost
  no message says how long work takes. The Credit Report forward, saved in
  explore2, was rejected 4 times here (the recipient rotates among three people).
- Coverage: 334 messages opened (analysts 253, critics 191), 1,590 more seen in
  search results; 100 of the analysts' reads were by more than one analyst
  (each opened 85 to 111).
- Problems found:
  - decisions.md grew to 101 KB: rejection reasons ran 2-4.5k characters, and
    every check/save/reject printed the whole record. Agents read about 70-140
    KB of it and 100-250 KB of command output per analyst session.
  - Two critics wrote the same proposal file name at once (a write conflict
    and a file that would not parse).
  - Critics tried other shell commands 6-14 times per session and were denied.
  - Medium effort could not be confirmed from the transcript.

## 2026-11-02 — The critic reads decisions.md as the last step before saving

- The sentence on decisions.md was a statement, not a step. The critic is now
  told to read it as the last step before saving, and to save only if the same
  work is not already saved there. Two critics can still both read it before
  either saves, so the code check proposed after explore3 is still needed.

## 2026-11-02 — Brief decisions record; analysts told never to stop

- The rejection form now asks for the reason and the research each in a
  sentence, with the full explanation in the reply to the analyst.
- check, save and reject no longer print the record; save says the rank it
  took in decisions.md. The critic reads decisions.md before saving instead.
- The analysts in explore3 did not stop after a save: each ended when it judged
  the obvious work claimed or ruled out. The analyst prompt now says it will be
  stopped automatically, so it never stops on its own, however many proposals
  are saved and however much seems covered, and goes on to mail it has not read.
- The ending of that sentence is now a nudge instead of an order: there is
  usually more to find in mail not read yet.
- The critic accepts a realistic estimate of the minutes: the mail rarely says
  how long work takes, and most explore3 rejections were for that reason.

## 2026-11-02 — Three fixes from explore3

- The same work is not saved twice: check and save refuse a proposal when half
  or more of its occurrences are occurrences of one saved opportunity, naming
  it. save checks again under its lock, since two critics can both read
  decisions.md before either saves (the explore3 duplicates shared 14 of 15).
- Each analyst and its critics work in their own folder
  (workspaces/analyst-N, each with a corpus copy and its own proposals), so
  critics of different analysts cannot overwrite each other's files.
  decisions.md is written to every folder.
- An analyst that ends its session early is started again in a new session
  (it reads decisions.md and carries on), until the time is up. Not if the
  session failed, lasted under a minute, or less than a minute is left. The
  transcript holds all its sessions, and the status line counts them.
- 114 tests pass.

## 2026-11-02 — explore4 (8 analysts, 15 minutes)

- All 8 analysts worked the full 15 minutes in one session each: none ended
  early, so no restart was needed.
- 14 saved, $1,374 a month (explore3: 2 distinct, $279). Top: ECC deal
  sweeps $435, nightly CAISO finals in CAPS $302 (stated nightly), daily EPE
  reconciliation log $150, Arthur Andersen monthly requests $106, the weekly
  California Capacity Report $99. 46 rejected; reasons now 550-750 characters
  at most, and decisions.md 50 KB with 60 decisions.
- No duplicate saved. The California Capacity Report, Arthur Andersen and
  book-code poll were each saved once and their repeats rejected; the code
  check refused repeats in the transcripts as well.
- Coverage: 696 of 3,196 messages opened (analysts 654, critics 275), 2,322 more
  seen in search results. Each analyst opened 142-230; 334 messages were opened
  by more than one analyst.
- The planted message 3220.eml was noticed and not used. 50 rate-limit events,
  with no session failing.
- Usage: the sessions were killed at the time, so none wrote its cost. From
  tokens (302M cache reads, 5.4M cache writes, against 72M and 2.3M for
  explore3 at $39), roughly $120-150 at API prices.

## 2026-11-02 — Sonnet analysts, 20 of them

- Analysts now run on Sonnet at high effort; critics stay on Opus at medium.
  Opened messages grew about in step with analysts (334 with 4, 696 with 8),
  so the next run tries 20 analysts for 15 minutes.

## 2026-11-02 — explore5 (20 Sonnet analysts, Opus critics, 15 minutes)

- Much worse than explore4: 2 saved, $107 a month (Capacity Report $82, Credit
  Report forward $25), against 14 and $1,374 with 8 Opus analysts.
- 77 rejected, 61 of them repeats of work already saved or rejected. Analysts
  kept resubmitting decided ideas despite decisions.md (one idea rejected five
  times), and they crowded onto the same few topics.
- Coverage did not keep growing in step: 879 opened (analysts 812, critics
  288), against 696 with 8 analysts; 490 opened by more than one analyst.
- 31 sessions: 11 restarts after early endings; 5 analysts ended with too
  little time left to restart. 151 rate-limit events, no session failed.
- Tokens: Sonnet 392M cache reads and 7.8M writes, Opus critics 17M and 2.6M.
  At Sonnet's lower prices, roughly the same usage as explore4.
- Conclusion: Opus analysts find and argue far better; more analysts beyond 8
  mostly add repeat work.

## 2026-11-02 — What the runs cost of the weekly limit

- The rate_limit_event lines are seven-day usage warnings, not throttling: no
  session was slowed or failed. Their utilization shows each run's share of
  the weekly allowance: explore3 51%->53%, explore4 54%->59%, explore5
  59%->65%. It resets 2026-11-07 10:00; overage is disabled, so at 100% runs
  stop until then.
- Overlap grows with analysts: 8 Opus analysts opened 1,417 messages in all,
  654 distinct (46%); 20 Sonnet analysts opened 2,659, 812 distinct (31%).
  Opened plus seen in search results is already about 3,000 of 3,196 in both.

## 2026-11-02 — Review of explore4 (8 Opus analysts) before expanding

- The dashboard renders all 14 saved opportunities. All four mailboxes are
  represented, and nothing was saved twice.
- Most rates rest on a stated rate or on a solid count, for example the Credit
  Report forward (70 in 4 months) and the Capacity Report (15 weekly reports).
- A bug: a critic withdrew the saved "any new book codes?" poll after saving it.
  The rejection was recorded, but the opportunity is still saved and ranked
  ($25.50), because reject does not remove a saved opportunity.
- 23 of the 46 rejections only repeat work already decided. Flow-with-no-deal
  was rejected six times and the OPM driver survey five times.
- Some counted rates are lower than the reasoning says, so they understate the
  saving: the Energy Market Report (daily by its reasoning, 3 a month counted),
  the transport tickets (monthly by its reasoning, 0.18 a month counted) and the
  time reports (semimonthly by its reasoning, 1.25 a month counted).
- The weakest item is the misdirected mail to the wrong Bill Williams. It is
  not really recurring work, and its change, that senders pick the right
  address, is vague.

## 2026-11-02 — Dashboard made clearer for leadership

- A subagent reviewed the dashboard against the explore4 results, aiming at
  executives. Its main finding: a leader reads a lot before reaching the
  numbers.
- Changes, all in dashboard.html:
  - Renamed the page to "Automation opportunities". The "Run finished" status
    no longer shows; status appears only while a run is going or stopped.
  - The headline is one figure ("$1,374 a month") with one sentence under it
    and a one-line method note. The "top 10" figure is gone.
  - The list has four columns: #, opportunity, "How it's figured" (such as
    "215 min × 1.4 a month") and saved a month. "Hours" and "Running total"
    are gone.
  - Each change line shows at most two lines, and the whole row is clickable.
    The "drafting is not built yet" row is gone.
  - An opened item reads in this order: the exact formula, Today and The
    change side by side, where it stalls, how often (in one plain line), and
    then the minutes. Two quotes are shown and the rest are behind "N more
    quotes".
  - Quotes have a lighter style. The message list is by date, with no pattern
    grouping and no intro sentence.
- Not done yet: asking the agents for shorter, plainer text. The text the
  dashboard shows is written by the critic, which fills the fields in FORMAT
  in pipeline/explore.py.

## 2026-11-02 — Plainer proposal fields; no reasoning field; fewer qualifiers

- The critic follows the FORMAT field descriptions in explore.py. They now ask
  for the text a manager needs:
  - name: "in a few plain words that a manager outside the team could
    understand";
  - today: "as briefly as a manager needs to see what it costs";
  - change: "one line: what would change, for a manager deciding whether to
    read further".
- Removed the reasoning field. Today, The change and the quotes with their
  notes are enough to back the minutes. score.py copies reasoning only when an
  estimate has it, which the older pipeline's estimates still do. The
  dashboard shows the reasoning only for runs that have it; explore4 still
  does.
- Dashboard: removed the qualifiers.
  - "The archive holds only part of the mail, so the real rate is likely
    higher."
  - "The archive itself shows it N times", under a stated rate.
  - "a model's estimate", both next to the minutes and in the method note.
- 114 tests pass.

## 2026-11-02 — Analysts back to Opus at medium effort

- analyst.md is back to model opus, effort medium. Sonnet at high effort did
  worse in explore5.
- The explore test checked for a fixed effort. It now checks that the analyst
  runs at the effort its agent file gives it, so changing the setting no
  longer breaks the test.
- Decided not to fix the case of a proposal withdrawn after it was saved.

## 2026-11-02 — Plain words asked for once, in the critic's prompt

- The first change made only the name plain and left the "The change" panel
  long, since that panel shows the explanation field.
- critic.md now asks once for everything the managers see: "Make sure what
  they see is true, and write it concisely and in plain words they could
  understand."
- The FORMAT fields now say only what each one holds:
  - name: "the recurring work, in a few words";
  - today: "how the work is done today, enough to see what causes the cost";
  - change: "one line: what would change, for a manager deciding whether to
    read further";
  - explanation: "the change: …"; it no longer says "in full".

## 2026-11-02 — explore6 (8 Opus analysts at medium effort, 15 minutes, new prompts)

- 14 saved, $1,436 a month (explore4: 14, $1,374). All four mailboxes are
  represented.
- Three analysts ended their first session early and were restarted, for 11
  sessions in all.
- 53 rejected. 28 of them refer to work already decided in decisions.md
  (explore4: 23 of 46).
- Coverage: 682 opened (analysts 609, critics 307) and 2,221 more seen in
  search results, about the same as explore4.
- Weekly usage went from 66% to 71%.
- New items include a nightly check that books are officialized ($768, the top
  one), a review of prior-month adjustments, curve-validation questions,
  evergreen deals on swing meters, and the EnerVest price change. The Energy
  Market Report forward now uses its stated rate ("every business day", 21.67
  a month).
- How the new wording did, as median characters against explore4:
  - change: 155 against 219, mostly within two lines;
  - explanation: 570 against 783;
  - today: 614 against 512, so it got longer, with more context and still
    many people and system names.
  - The text explains its terms more often, but it is not much easier to
    read.
- Without the reasoning field, the minutes have no breakdown anywhere. The top
  item claims 25 minutes a night, and neither its quotes nor their notes say
  where that comes from.

## 2026-11-02 — How analysts choose what to open; running total restored

- From the explore6 transcripts (analysts only):
  - Tool calls: 1,472 Read, 627 Grep (499 of them showing matching lines), and
    41 Glob.
  - 1,382 of the 1,383 message reads were of a file that had already appeared
    in a search result. 1,153 had appeared in a listing of Subject: lines.
  - So analysts grep the Subject lines of a folder or of the whole corpus,
    pick the subjects that look like repeated work, grep for the topic's
    terms, and then open those messages.
  - Many reads are re-reads: 1,383 reads came to 609 distinct messages.
  - Share opened, by mailbox: lokay-m 31%, farmer-d 24%, williams-w3 25%,
    giron-d 15%.
- A Grep output too large to show inline is saved to a file, which the
  analyst then reads. coverage() does not count those lines as seen, so it
  undercounts what was seen in search results. 51 such outputs were read.
- Restored the "Running total" column. README asks for the running dollar
  total by name.

## 2026-11-02 — Readers over every message, drafters, one `run`

- README asks that every message be read, not a sample. Analysts open about
  700 messages in 15 minutes, by searching for them. So a reader stage now
  comes first:
  - one reader per batch (15 batches);
  - each reads all of its batch and records leads: the work, why it looks
    recurring or costly, and the files that show it.
- Code keeps only the files that are messages of the reader's own batch and
  drops a lead left with none. The leads are written to `leads.md` in each
  analyst's folder. The analyst prompt says to use it as a place to start,
  not as evidence. Only what a critic saves is ranked, as before.
- Drafters: one for each of the top 10, given only the analysis (today, the
  change, the figures, the quotes with their notes, senders and dates, and
  the stalls). They are not given message text.
  - The prompt asks for whichever artifact would start the change.
  - People are addressed by role.
  - What the reader must act on comes first; the explanation follows.
  - `finalize` writes `drafts/opp-NN.md` and `report.json`.
- A test on three of explore6's top items gave usable emails. Each took
  17–25 seconds and about 6k tokens in.
- `run` now goes from start to finish: prepare, readers, explore (8 analysts,
  20 minutes), drafters, finalize.
  - The CONTINUE time budget is gone. `/run-pipeline` starts `run` in the
    background and waits.
  - A failed worker is still tried once more.
  - Each stage is skipped once its output exists. `explore/done.json` marks
    explore finished.
  - A change to the corpus clears everything corpus-wide, including the
    workspaces, but keeps the leads of unchanged batches.
- All agents are Opus at medium effort. A worker's `--effort` now comes from
  its agent file, and workers run without this folder's auto-memory.
- Removed the old scout → validate → merge → group → estimate path:
  - the scout, merger and estimator agents;
  - estimate.py;
  - the validate and group steps, and their tests.

  validate.py keeps the quote matching and group.py keeps `build_process`,
  which explore's save uses.

## 2026-11-02 — The drafted artifact on the dashboard

- When an opportunity is opened, its draft now appears as a card of its own.
  - Below "Today / The change", the opened row splits in two: how the figure
    is made on the left, and the draft on the right, beside it. It scrolls
    with the page (keeping it in view felt erratic). On a narrow screen it
    comes first, above the figure. (Placed first between the plan and the
    evidence, it cut the figure off from its factors.)
  - It shows the kind of artifact, its title, who it is for, and a preview
    of the body.
  - Two buttons: read the full draft in the side drawer, or copy its text.
- The list is plainer: the "How it's figured" column is gone, since the opened
  row shows the formula. Drafted rows are not tagged: an opened row shows
  its draft.
- The line under the headline that explained the formula is gone too; each
  opened row shows its own.
- The dashboard renders markdown itself, with no library, so it stays local.
  - It builds elements from the text and never inserts it as HTML.
  - It handles headings, lists, quotes, tables, code, bold, italic and
    links (http and https only).
  - A check over all ten drafts left no stray markdown.
- Drafts now come with the report (`report.json` and `/api/report`).
  `/api/draft` is gone.

## 2026-11-02 — Cost so far instead of a running total

- The "Running total" column summed the monthly figure of a row and every row
  above it. It now shows each opportunity's cost so far, which is closer to
  what the README's "running dollar total" asks for.
  - Cost so far = dollars a month × the calendar months from the month the
    work first shows in the mail to the last month its mailboxes hold.
  - It is worked out in score.py with the rest of the arithmetic, and
    tested.
  - The headline adds the total ($88,005 for the real run).
  - An opened row explains its figure, with both months.
- It falls short rather than over: the mail shows when the work was first
  written about, not when it began. It assumes the rate held the whole time.
- The real run's output was scored again without a model. Every other
  figure came out the same.

## 2026-11-02 — Sorting the list

- Clicking "Saved a month" or "Cost so far" sorts the list by that column,
  largest first.
  - The # column numbers the rows in the current order.
- The line after the tenth row ("The 10 above … are drafted") is gone, and
  the button under the list that showed the rest now just says "See more".
- The two dollar columns now look alike: plain figures, with no bordered
  button or arrow. The sorted column is darker and bold.
- An opened row is tinted, since its amount no longer shows ▴.
- An opened row without a draft says why, in a dashed box where the draft
  would be: "Email not drafted. Drafts are written for the 10 opportunities that
  save the most each month." Drafts stay with the monthly order, since a draft
  starts a change and the change's worth is what it saves from now on. Cost
  so far is spent, and it leans on when the work first shows in the mail.
  The box names the kind of artifact when every draft is the same kind
  (here, all ten are emails), and says just "Not drafted" otherwise.
- A link to one of the rows below the first ten (`#opp-11`) now shows the
  rest of the list, so the link lands on the row.
