# Airline satisfaction: a real pi-rsi experiment

[中文说明](README.zh-CN.md) · [Compact visualization](index.html) · [Full search explorer](tree.html) · [Research Wiki](wiki.html) · [Snapshot summary](SUMMARY.json)

This example records a real, sequential search on the supplied S6E10 airline-satisfaction data using one RTX 2080 Ti. GPT-6.1 Sol performed research, implementation and result analysis; GPT-6 Luna maintained the research wiki and handled audits and diagnostics.

**This is an intermediate snapshot of a running campaign, not a finished 32-node study.** The authoritative snapshot timestamp, node counts and scores are in [SUMMARY.json](SUMMARY.json). The export initially contains 19 allocated nodes: 16 completed, two failed, and one in progress. The campaign's current limit is 32 research nodes, excluding the baseline.

## View the experiment

The interactive pages are also published on the blog: [overview](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/), [full search tree](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/tree/), and [research Wiki](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/wiki/). The [English guide](https://blog.pocketplay.win/en/blog/pi-rsi-airline-20261004/) has the [Chinese version](https://blog.pocketplay.win/zh/blog/pi-rsi-airline-20261004/).

Download or clone this repository and open `index.html` in a browser. It contains the chart, search branches and node details, including D3, and works offline. Click a node to select it; toggle the legend to show or hide the score series. The expanded `tree.html` also works offline and includes hypotheses, handoffs, analyses, audited results, failure records and research knowledge. GitHub's file view displays the HTML source; it does not run the interactive page.

Alternatively, from the repository root:

```sh
python3 -m http.server 8000 --directory examples/airline-s6e10-2080ti-20261004
```

Then open `http://localhost:8000/`. Both pages are archived snapshots; they do not poll the original machine.

![Score progression and search branches](preview.png)

## Recorded results

| Node | Intervention | Search-validation ROC-AUC |
|---|---|---:|
| root | Untouched GPU CatBoost baseline | 0.9572004066 |
| n008 | Depth 8 with stronger L2 regularization | 0.9577204389 |
| n011 | Numeric ratings plus categorical views | 0.9577967297 |
| **n016** | **Raw predictors with Depthwise growth** | **0.9579240131** |
| n017 | Fresh raw SymmetricTree control | 0.9577845706 |
| n018 | Increase raw SymmetricTree depth to 10 | 0.9577366851 |

n016 is the highest valid completed score in this snapshot, **+0.0007236065** above the baseline. Its gain over n014 is only **+0.0001394425**, below the prespecified 0.0002 practical screen. Its quick-set contrast was negative. These are adaptively reused search-validation results, with unknown GPU training variation and no established independent replication. Numerical rank is not evidence of stable superiority, statistical significance, or a causal mechanism.

n001's model artifact changed after evaluation, so its measurement is invalid and cannot improve the best-score curve. n012 exceeded its implementation/trial budget; n013 subsequently completed a repaired implementation without improving the incumbent. Failed outcomes remain visible. The final holdout remains sealed and there were no Kaggle submissions.

## What is included

| File or directory | Purpose |
|---|---|
| `index.html` | Self-contained compact chart and clickable search branches |
| `tree.html` | Self-contained full experiment explorer |
| `wiki.html`, `wiki-data.json` | Offline claim/evidence browser and published knowledge-revision history |
| `SUMMARY.json`, `results.json`, `snapshot.json` | Snapshot status, score ledger and explorer data |
| `metrics/` | Aggregate node metrics with measurement-validity labels |
| `models/root/`, `models/n016/` | Exact committed baseline and current-best candidate source, with provenance |
| `rsi.toml` | Archived campaign configuration with a repository-relative task path |
| `assets/` | Offline dashboard export template and the D3 license |
| `../../pi_rsi/tasks/airline-s6e10-2080ti/` | Original task brief, preparation code, starter, frozen evaluator, public manifest and pinned requirements |

Dataset rows, held-out labels, prediction tables, trained weights, raw model-session logs, authentication material and machine-local paths are not part of the archive. The archived configuration and metric hashes document the run; the snapshot is not a checkpoint from which `rsi run` can resume. The live experiment retains the full recovery state separately.

## Data, compute and reproduction

The frozen stratified split uses seed **20261004**: 489,744 training-pool rows, 104,945 search-validation rows and 104,946 final-holdout rows. Quick development uses 50,000 training rows and 10,000 disjoint development rows. Whole-candidate time limits are 60 seconds for quick, 180 for validation and 240 for final. CPU preprocessing is capped at eight threads; each research node permits at most three development attempts.

The task pack consumes the three original, locally supplied CSVs placed in its `data/raw/` directory. `setup.sh` installs the exact cached requirements offline and runs `prepare.py`; existing splits are verified rather than silently regenerated. The CSVs are not redistributed. See the task pack's [data description](../../pi_rsi/tasks/airline-s6e10-2080ti/docs/DATA.md) and [frozen protocol](../../pi_rsi/tasks/airline-s6e10-2080ti/docs/PROTOCOL.md).

The original evaluator and candidates deliberately verify the exact original RTX 2080 Ti identity and visibility mask. Viewing the archive needs no GPU. Running an exported candidate requires the original prepared data, environment and authorized GPU. An adaptation to another GPU or split is a new protocol and should be reported separately. On the original workstation, run the best candidate's quick development evaluation from the repository root:

```sh
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d
pi_rsi/tasks/airline-s6e10-2080ti/.venv/bin/python \
  pi_rsi/tasks/airline-s6e10-2080ti/eval/eval.py \
  --agent-dir examples/airline-s6e10-2080ti-20261004/models/n016 \
  --seedset quick --out /tmp/airline-n016-quick.json \
  --python pi_rsi/tasks/airline-s6e10-2080ti/.venv/bin/python
```

This command is documented for reproduction; exporting this example does not execute it. Only the harness performs official validation. The final holdout is disabled by default. GPU CatBoost is not bitwise deterministic, so exact score equality on another fit is not guaranteed.

## Update the archive

With the live experiment available and the current development harness installed, first refresh its native explorer, then export it:

```sh
./rsi render airline-s6e10-sol61-2080ti-20261004
python3 scripts/export_airline_example.py \
  --experiment experiments/airline-s6e10-sol61-2080ti-20261004
```

The exporter uses only Python's standard library, reads aggregate results and committed source, and writes the archive outside the live experiment. It launches no agents, jobs or evaluations. It strips machine-local paths and raw execution records, preserves failed nodes, and omits an earlier pilot's stale `final.json` while the continuation is running. It exports the baseline and whichever completed candidate is currently best. Update this narrative and preview after refreshing the data.

## Browse the research Wiki

![Research Wiki claim and evidence browser](wiki-preview.png)

Open `wiki.html` offline. Choose an observation, hypothesis or experience entry to read its statement, recorded status, scope, competing explanations and next test. Supporting and opposing evidence remain separate; selecting a source reveals aggregate experiment metrics or its original documentation URL, with immutable packet hashes. Expand the revision history to inspect actual before/after statuses and recorded revision reasons. The research agenda lists unresolved questions and discriminating experiments.

Wiki statuses are generated, scoped interpretations, not independently verified facts. A supported documentation claim is not experimental confirmation; multiple evidence packets can describe the same experiment or source. The page exports provenance metadata, not full raw evidence packets or private data. It has its own revision timestamp, which can be newer than the experiment snapshot when refreshed separately.

To export the latest published Wiki without running an LLM or evaluation:

```sh
python3 scripts/export_wiki_view.py \
  --memory experiments/_memory/airline-s6e10-2080ti/protocols/3809e829ce612de2b66a
```

Pass `--revision <revision-id>` to pin a historical revision. The experiment exporter automatically pins the Wiki to the revision embedded in its full explorer; the standalone Wiki exporter defaults to `CURRENT.json`. Every exported claim reference is checked against its evidence index, and history follows published revision ancestry rather than treating rejected model drafts as versions.

The recorded sequential research/wiki loop belongs to the current development harness. This example adds the archive and task pack without folding unrelated, pending framework changes into the repository. The candidate CLI and frozen evaluator are supplied independently of those changes.

Project code is MIT licensed. D3 7.9.0 is bundled under its [ISC license](assets/D3-LICENSE.txt).

## Publish the interactive views

The blog build uses PocketPlay Kit v2 and external, same-origin scripts and data. It does not weaken the blog's script policy or embed executable HTML in article Markdown. Build the six English/Chinese pages from this sanitized archive:

```sh
python3 scripts/build_blog_visualizations.py \
  --output work/blog-preview/rsi/interactive/airline-20261004 \
  --kit /path/to/pocketplay-platform/kit/v2
```

The English pages wrap the views in a long-form reading guide (project introduction, how to read each figure, highlights and limits) from `scripts/blog-guide/`. Its prose quotes this snapshot's numbers, so the build stops if a refreshed archive no longer matches them; update the guide text and `GUIDE_FACTS` together. Chinese pages are unchanged.

`scripts/deploy_blog_visualizations.py` installs only this static component inside the existing `pocket` container: a new immutable component release, an atomic link for its fixed URL prefix, a private rollback receipt, and a robots.txt declaration for its six-page sitemap. It does not replace the platform or legacy blog release, modify Nginx routing, touch accounts or call an LLM. Article JSON in `blog/` is published through the existing limited editorial publisher. Refresh the archive and build again to update the visual snapshots; no automatic polling or new scheduled job is added.

Publication checks: all six live pages returned 200 and passed the primary node/evidence/revision interactions; 390px and 1440px layouts fit, with light/dark checks. Public data and sitemap files were accessible in the browser; representative live script assets matched the build. English/Chinese article canonicals, links, RSS and the editorial sitemap were checked. The research sitemap was discovered in the shared index from the robots declaration. Existing Cloudflare telemetry injection is blocked by the site's existing CSP on both old and new pages; it did not affect the application interactions. This is not a claim of Google indexing.
