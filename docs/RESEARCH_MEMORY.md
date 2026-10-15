# Research memory

The research wiki accumulates scoped observations, hypotheses, and experience across experiment
branches and runs. It maintains an explicit research agenda: motivation, method rationale, changes
in understanding, open questions, and experiments that distinguish competing explanations.

This adapts the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
using the harness's existing Python/Markdown infrastructure. It does not require a wiki plugin,
an embedding service, or a particular coding-agent runtime.

## Behavior

New experiments enable memory by default. Existing rsi.toml files without a memory section remain
disabled until explicitly enabled. Node handoffs, official evaluation, retry handling, original
INSIGHTS.md/DEADENDS.md ledgers, and score reporting remain available.

1. The coordinator captures completed/failed nodes as immutable evidence packets. Official selection
   metrics, code identity, worker interpretations, and audit results have distinct fields.
2. Every three pending records by default, a bounded utility call synthesizes relevant knowledge.
   It also runs at a score plateau and at normal finish, before final evaluation. Interruptions and
   an exhausted wall-clock budget do not start another reflection call. Remaining records can be
   compiled explicitly later.
3. The harness validates IDs, scope, statuses, and evidence references. Counterevidence cannot silently
   disappear from an existing claim; support plus opposition produces mixed status. Prior revisions
   are retained. Invalid/model-failed compilations leave the published revision and pending evidence
   intact. A failed batch is retried with exponential backoff (5 min doubling to 1 h, persisted in
   `reflection_status.json` and shared by runs on the same wiki), halving the batch after each failure;
   a packet that still fails alone is set aside (quarantined) so later evidence keeps compiling. It
   gets an isolated retry every 6 h, is listed in the memory context, and `rsi memory reflect`
   retries it immediately.
   Incorrect historical evidence relations are corrected by superseding the old claim and writing a
   successor, keeping the old references in history. Any automatic mixed-status reconciliation is
   explicitly recorded in the agenda rather than silently disagreeing with the model's summary.
4. Planners receive the current agenda and relevant knowledge with both supporting and opposing
   references. Workers receive a bounded snapshot saved beside their node notes.
5. An unused proposal queue from an older compiled revision is re-planned before expansion. Previous
   proposals and their indices remain in the tree as history.
6. Every third expansion prefers an available ablate/debug proposal that names a research question,
   prediction, and falsifier, even on a lower-scoring branch. Root breadth, human focus, depth/width,
   retries, and hard budgets still apply. Score patience gets a bounded two-node grace window;
   generated prose never resets patience or changes the incumbent.

The research slot is a preference among available proposals, not a guarantee that every third node
is scientifically informative. A model's labels do not establish causality; reviewers should inspect
the intervention, predicted outcomes, and actual evidence.

## Layout and ownership

The default base is experiments/_memory/<task-name>/. Different compatible runs share it.
Each evaluator/config/data-version fingerprint has an isolated protocols/<fingerprint>/ directory:

    SCHEMA.md                          # editable research conventions
    raw/e-<hash>.json                   # immutable captured source/evaluation packets
    CURRENT.json                       # atomically published revision pointer
    INDEX.md                           # human navigation to current revision
    revisions/<revision>/
        state.json                     # complete authoritative state for this revision
        INDEX.md
        AGENDA.md
        wiki/<claim-id>.md

Node notes also contain MEMORY.md (exact supplied text) and memory.json (revision, protocol,
context hash). The code tree tracks code inheritance; wiki pages integrate evidence across branches.
The archive is outside candidate code worktrees, so checking out old code does not roll back knowledge.

A process file lock serializes evidence writes and publication across runs. Model calls happen
outside the lock. A compilation based on an obsolete revision cannot overwrite another run's new
revision. All revision files are written before CURRENT.json switches readers to them.
Generated Markdown is a view of state.json. Edit SCHEMA.md or import a source to change knowledge;
manual edits to generated pages do not change the state used by the planner.

## Commands

    rsi init my-run --task kaggriculture --runner grok --model grok-4.6
    rsi memory status my-run

Enable and backfill an existing run without starting workers or evaluating any candidate:

    rsi memory enable kag-grok-46
    rsi memory sync kag-grok-46
    rsi memory reflect kag-grok-46 --batches 3

sync is deterministic and makes no model calls. reflect uses the configured utility runner/model,
records normal usage/cost logs, and makes at most the requested number of calls (default one, max ten).
Repeated sync is idempotent; changed measurements/notes get a new record instead of overwriting evidence.
Multiple versions of the same experiment are not independent replications.

Use `rsi memory review <exp>` for a bounded model review of existing knowledge, even when no new
evidence is pending. It revisits unsupported causal claims, scope, counterevidence, and the agenda;
it does not count as a new experiment or an independent replication.

Import a local UTF-8 paper excerpt, observation, or research note with a useful citation:

    rsi memory ingest my-run --source /absolute/path/paper-notes.md --label "Paper title, section 4, URL"
    rsi memory reflect my-run

Import captures a source assertion, not a verified fact. PDF parsing/web discovery remain separate;
use a text/Markdown excerpt with attribution. No source network access occurs inside workers.

For a separate wiki or an isolated comparison:

    rsi init trial --task kaggriculture --memory-dir /absolute/path/trial-wiki
    rsi init control --task kaggriculture --no-memory
    rsi memory enable old-run --path /absolute/path/shared-wiki
    rsi memory disable old-run

## Configuration

    [memory]
    enabled = true
    path = ""                  # relative paths are relative to the experiment directory
    protocol_id = ""           # set to the dataset/split/seed manifest version when data is external
    reflect_every = 3
    batch_size = 8
    context_chars = 12000
    research_every = 3         # 0 disables reserved research turns
    patience_grace = 2         # set to 0 for unchanged score patience

The automatic fingerprint covers task evaluation configuration and evaluator .py/.json/.toml files.
It does NOT fingerprint arbitrary external datasets or linked model weights. Set protocol_id to
their manifest/version when they change. Cross-protocol knowledge transfer is deliberately not
automatic in this version: such transfer requires re-scoping a claim as a hypothesis.

## Evidence boundaries and limitations

- The automatic importer reads the official selection metrics, HANDOFF.md, PROGRESS.md, FAILURE.md,
  and node audit. It does not ingest final.json, reports, confirmation metrics, or submission ledgers.
  Notes remain author-supplied text: manually copying test/leaderboard results into them or importing
  such a source can expose feedback. This is provenance separation, not a semantic leakage detector.
- Original notes and packets are preserved. Model input uses bounded excerpts, marked as truncated;
  claim retrieval uses lexical overlap plus uncertainty-aware ordering, not semantic retrieval.
- Numeric validation is inherited from the evaluator/auditor. Synthesis validation verifies structure
  and references, not that a causal claim follows from its evidence.
- The current agenda is a working interpretation. Literature significance/novelty is unknown until
  relevant external sources are supplied. No autonomous literature search or cross-project
  generalization is claimed.
- Reflection calls are serial in the coordinator; already-running workers continue. Calls consume
  time and tokens and can delay new dispatch. Tune reflect_every/batch_size for expensive models.
- Evidence packets contain the captured full selected metrics/notes; generated prompts are bounded.
  Back up the entire wiki base, including raw packets and revisions.

## Validation

tests/test_memory.py covers restart/import idempotency, re-evaluation versioning, cross-run sharing,
protocol isolation, final-metric exclusion, counterevidence retention, context snapshots, malformed
outputs, stale concurrent publication, stale-proposal replacement, lower-score research selection,
bounded patience, and an end-to-end scripted run with failed workers, retries, and wiki compilation.

To evaluate scientific benefit, compare (A) disabled memory, (B) memory with research_every=0 and
patience_grace=0, and (C) the full loop under equal total model/compute budgets. Use isolated empty
wiki directories, or replay only the historical prefix available at each decision. A wiki backfilled
from the full run must not be used to claim a causal improvement in that run. Measure repeat mistakes,
conditional conclusion recall, discrimination quality of new experiments, and blind human assessment
of the motivation/method evidence chain, in addition to benchmark score.

## Replicated Kaggriculture campaign

`scripts/memory_campaign.py` prepares and executes a bounded A/B/C comparison from an existing duel
task pack. It snapshots the current harness (including local changes), isolates empty per-run wikis,
uses two disjoint search panels, and keeps a 48-seed confirmation panel outside the worker task packs.
All six selection winners are locked before any confirmation result is computed. It does not submit.

    python3 scripts/memory_campaign.py init experiments/my-memory-study --template experiments/kag-duel-memory-20260913
    python3 experiments/my-memory-study/harness/scripts/memory_campaign.py run experiments/my-memory-study
    python3 scripts/memory_campaign.py status experiments/my-memory-study

The fixed campaign defaults are 24 non-root nodes and six hours of scheduling per run, 20 minutes per
worker, three concurrent runs in each of two balanced waves. At six million reported input+output
tokens per run the driver requests a graceful stop; unfinished work may exceed that threshold while
draining. Reflection and audit usage count toward it. These are equal resource ceilings, not equal
realized token consumption; timeouts can also leave usage incomplete. The driver does not silently
restart interrupted runs or replace failed replications, because doing so would reset budgets or bias
the comparison. Use a durable service for long runs and inspect `FAILED.json` if a wave fails.

`PROTOCOL.md` records the comparison and limitations before launch. `STATUS.md` tracks progress;
`RESULTS.md`, `TRAJECTORIES.json`, and arm-masked `review/` packets are generated afterward. Whole-run
review packets retain parent relationships and memory revisions, permitting examination of whether
counterevidence affected later decisions. The program does not grade its own scientific quality.
Two independent runs per arm support an exploratory comparison, not a strong significance claim;
game seeds must not be treated as independent replications of the memory system.
