"""Recover failed editorial phases of already measured nodes, without rerunning research."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import gitops
from .evidence import comparison
from .measurement import validated_measurement, metrics_path
from .research import _strings, _text
from .util import atomic_write_json, atomic_write_text, read_json, read_text, now_iso
from .worker import _record_audit


_STRING = {"type":"string"}
_LIST = {"type":"array", "items":_STRING, "maxItems":12}
ANALYSIS_SCHEMA = {"type":"object", "properties":{
    **{key:_LIST for key in ("observations","belief_revisions","competing_explanations","limitations","next_experiments")},
    **{key:_STRING for key in ("interpretation","noise_assessment","reason")},
    "recommendation":{"type":"string","enum":["continue","saturated"]}},
    "required":["observations","belief_revisions","competing_explanations","limitations","next_experiments",
                "interpretation","noise_assessment","reason","recommendation"]}


def recover(orch, node_ids=None, *, seconds=600):
    if not 1<=seconds<=1800:
        raise ValueError("closeout seconds must be between 1 and 1800")
    cfg,tree=orch.cfg,orch.tree
    state=read_json(cfg.dir/"state.json",{}) or {}
    if state.get("status") in ("running","finishing"):
        import os
        pid=state.get("pid")
        if pid and Path(f"/proc/{pid}").exists() and pid!=os.getpid():
            raise ValueError("Stop the active controller before closeout")
    nodes=[tree.get(nid) for nid in node_ids] if node_ids else [
        n for n in tree.non_root() if n.worker.get("evaluation_validated") and
        (n.status=="incomplete" or (n.status=="failed" and
         ("timeout" in (n.failure or "") or "wall-clock budget" in (n.failure or ""))))]
    orch._closeout_deadline=time.monotonic()+seconds
    recovered=[]
    for node in nodes:
        if node.status=="done":
            continue
        metrics=validated_measurement(orch,node)
        parent=tree.get(node.parent)
        pm=read_json(metrics_path(cfg,parent)) or parent.metrics
        noise=orch.noise_level(metrics,pm)
        assessment=comparison(metrics,pm,score=node.score,parent_score=parent.score,
                              higher_is_better=tree.higher_is_better(),fallback=noise)
        nd=cfg.nodes_dir/node.id
        backup=nd/"closeout.original.json"
        if not backup.exists():atomic_write_json(backup,node.to_dict())
        handoff=read_text(nd/"HANDOFF.md")
        snapshot={k:v for k,v in metrics.items() if k not in ("bootstrap_samples","per_item","per_seed","_eval")}
        prompt=("You are pi-rsi's result-analysis agent. This is closeout of a COMPLETED, validated experiment. "
            "The original analysis timed out or was blocked by the search wall clock, not by training/scoring failure. "
            "Return only the analysis JSON; no tools, implementation, training, inference, new experiment, or protocol change. "
            "Separate measured outcomes, noise, mechanism hypotheses and applicability. "
            "Compare with root AND the prior best when present; beating root does not mean beating the prior head. "
            "Do not inspect or claim a new expert-label result. This follow-up is selection-only. "
            "A completed score and a incomplete handoff are distinct facts.\n\n"
            f"NODE {node.id}: {node.title}\nHYPOTHESIS {node.hypothesis}\n"
            f"TRUSTED METRICS {json.dumps(snapshot,ensure_ascii=False)}\n"
            f"COMPARISON {json.dumps(assessment,ensure_ascii=False)}\n"
            f"EXISTING HANDOFF (interpretation, not independent measurement)\n{handoff[:18000]}\n"
            f"RESEARCH MEMORY\n{orch.memory.context(node.title)[:8000]}\n"
            "Recommend future work only; the current search is over. Output full JSON matching the schema.")
        remaining=orch._closeout_deadline-time.monotonic()
        if remaining<=0:raise RuntimeError("closeout time budget exhausted")
        orch.log("closeout_analysis",node=node.id,model=orch.research.runner.model)
        if metrics.get('_eval',{}).get('monitor'):
            from .monitor import TaskMonitor
            TaskMonitor(Path(metrics['_eval']['monitor'])).begin_analysis()
        data,res=orch.research.runner.ask_json(prompt,cwd=nd,log_path=nd/"closeout.analysis.jsonl",
                                            schema=ANALYSIS_SCHEMA,timeout_s=min(300,remaining))
        orch.add_cost("research_analysis",res)
        if not res.ok or not isinstance(data,dict):
            raise RuntimeError(f"{node.id}: closeout analysis failed: {res.error}")
        out={k:_strings(data.get(k),k) for k in ("observations","belief_revisions","competing_explanations","limitations","next_experiments")}
        if not out["observations"] or data.get("recommendation") not in ("continue","saturated"):
            raise ValueError("closeout analysis lacks observations/recommendation")
        out.update({k:_text(data.get(k),k) for k in ("interpretation","noise_assessment","reason")})
        out["recommendation"]=data["recommendation"]
        if handoff and not (nd/"HANDOFF.before_closeout.md").exists():
            atomic_write_text(nd/"HANDOFF.before_closeout.md",handoff)
        lines=[f"# Handoff {node.id}: {node.title}","","## Hypothesis",node.hypothesis,"",
               "## What I did","Implementation and development details are preserved in HANDOFF.before_closeout.md. "
               "This closeout reused the exact evaluated code/checkpoint/predictions; no training or scoring was repeated.","",
               "## Result",*['- '+x for x in out['observations']],"","## Mechanism",out['interpretation'],"",
               "## Noise assessment",out['noise_assessment'],"","## Belief revisions",*['- '+x for x in out['belief_revisions']],"",
               "## Competing explanations",*['- '+x for x in out['competing_explanations']],"",
               "## Limitations",*['- '+x for x in out['limitations']],"","## Next experiments",*['- '+x for x in out['next_experiments']],"",
               "## Stop or continue",out['recommendation']+': '+out['reason'],"","## Harness measurement record",
               f"Official {cfg.task.score_key}: {node.score}; code: `{node.commit}`.",
               '```json',json.dumps(assessment,ensure_ascii=False,indent=2),'```','']
        atomic_write_text(nd/"HANDOFF.md",'\n'.join(lines))
        atomic_write_json(nd/"analysis.json",{**out,"harness_comparison":assessment,"closeout":True})
        validated_measurement(orch,node)  # publishing still requires unchanged scientific artifacts
        audit=orch.utility.audit(node,metrics,gitops.log_oneline(cfg.worktrees_dir/node.id,node.base_commit),
                                 gitops.diff_stat(cfg.worktrees_dir/node.id,node.base_commit),noise)
        audit['comparison']=assessment
        recovery={'at':now_iso(),'original_failure':node.failure,'operation':'analysis-only closeout'}
        documentation={"state":"complete","phase":"complete","analysis_complete":True,"pending":False}
        if getattr(orch,'executions',None):
            orch.executions.document(node,documentation)
        tree.complete(node,summary=audit['summary'],verdict=audit['verdict'],audit=audit,failure=None,diagnosis={},
                      documentation=documentation,
                      worker={**node.worker,'analysis':out,'closeout':recovery})
        _record_audit(orch,node,audit,gitops.log_oneline(cfg.worktrees_dir/node.id,node.base_commit),
                      gitops.diff_stat(cfg.worktrees_dir/node.id,node.base_commit))
        if metrics.get('_eval',{}).get('monitor'):
            from .monitor import TaskMonitor
            TaskMonitor(Path(metrics['_eval']['monitor'])).consumed()
        recovered.append(node.id);orch.log('closeout_done',node=node.id,score=node.score)
    if recovered:
        orch.memory.sync(tree)
        if time.monotonic()<orch._closeout_deadline:
            try:orch.memory.reflect(orch.maintainer,force=True)
            except Exception as e:orch.log('memory_failed',error=str(e))
        final=read_json(cfg.dir/'final.json',{}) or {}
        final.update(best=tree.best_id(),closeout={'at':now_iso(),'recovered':recovered,'new_experiments':0})
        atomic_write_json(cfg.dir/'final.json',final)
        from .orchestrator import _write_report
        _write_report(orch,final)
        orch._status='finished';orch._stop_reason=final.get('stop_reason');orch.render()
    return recovered
