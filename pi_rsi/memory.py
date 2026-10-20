"""Research wiki: immutable evidence, versioned synthesis, bounded recall, shared across runs.

Only the harness writes this store. A file lock serializes publication; model calls run outside
the lock and stale results cannot overwrite a newer revision. Readers follow one atomic pointer.
"""
from __future__ import annotations

import dataclasses
import difflib
import fcntl
import hashlib
import json
import re
import time
from contextlib import contextmanager
from pathlib import Path

from .util import atomic_write_json, atomic_write_text, now_iso, read_json, read_text


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9_]{2,}", text.lower()))
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    return words | set("".join(chars[i:i + 2]) for i in range(len(chars) - 1))


# A failed compilation is retried with bounded backoff, then isolated, never skipped forever:
# evidence captured behind a failing batch must still reach the wiki.
REFLECT_BACKOFF_S = (300, 3600)   # first retry delay and cap; doubles per consecutive failure
QUARANTINE_AFTER = 2              # failures before a packet that also fails alone is set aside
QUARANTINE_RETRY_S = 6 * 3600     # a set-aside packet gets one isolated retry this often



def _known_id(ref, known):
    """An evidence ID as cited, or the single close match among the supplied IDs (a truncated or mistyped copy)."""
    if ref in known:
        return ref
    close = difflib.get_close_matches(ref, list(known), n=1, cutoff=0.85)
    return close[0] if close else ref

class ResearchMemory:
    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = cfg.memory.enabled
        task = dataclasses.asdict(cfg.task)
        for key in ("dir", "reference_scores", "objective"):   # objective only steers prompts
            task.pop(key, None)
        files = {}
        # This fingerprints the declared protocol, not an unversioned external dataset.
        for p in sorted((cfg.task_dir / cfg.task.eval_dir).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".json", ".toml"):
                files[str(p.relative_to(cfg.task_dir))] = hashlib.sha256(p.read_bytes()).hexdigest()
        self.protocol = _hash({"task": task, "eval_files": files, "data_version": cfg.memory.protocol_id})[:20]
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", cfg.task.name) or "task"
        base = Path(cfg.memory.path).expanduser() if cfg.memory.path else cfg.dir.parent / "_memory" / name
        if not base.is_absolute():
            base = cfg.dir / base
        self.root = base.resolve() / "protocols" / self.protocol
        self._seen = {}

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / ".lock", "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                if not (self.root / "SCHEMA.md").exists():
                    atomic_write_text(self.root / "SCHEMA.md",
                                      read_text(Path(__file__).parent / "prompts" / "memory_schema.md"))
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def state(self) -> dict:
        if not self.enabled:
            return self._empty()
        pointer = read_json(self.root / "CURRENT.json")
        if not pointer:
            return self._empty()
        state = read_json(self.root / "revisions" / pointer["revision"] / "state.json")
        state.setdefault("topics", {})  # revisions compiled before direction pages existed
        return state

    def _empty(self):
        return {"revision": "", "claims": {}, "agenda": {}, "topics": {}, "consumed": [], "protocol": self.protocol}

    @property
    def revision(self) -> str:
        return self.state()["revision"]

    def packets(self) -> list[dict]:
        return sorted((read_json(p) for p in (self.root / "raw").glob("*.json")),
                      key=lambda p: (p.get("observed_at", ""), p["id"]))

    def evidence_fingerprint(self):
        """Hash observations/primary-source content, excluding AI/document/index revisions."""
        identities = set()
        for packet in self.packets():
            if packet.get("kind") == "experiment":
                metrics = {k: v for k, v in packet.get("metrics", {}).items() if k != "_eval"}
                identities.add(_hash({"protocol": packet.get("protocol"), "role": packet.get("role"),
                                      "commit": packet.get("commit"), "metrics": metrics}))
            elif packet.get("kind") == "source":
                identities.add(_hash({"sha256": packet.get("sha256") or _hash(packet.get("text", "")),
                                      "source_url": packet.get("source_url")}))
        return _hash(sorted(identities))

    def _capture(self, packet: dict) -> str:
        # Identity excludes capture time: restart/import is idempotent; changed evidence gets a new ID.
        identity = {k: v for k, v in packet.items() if k not in ("id", "captured_at")}
        packet["id"] = "e-" + _hash(identity)[:24]
        packet["captured_at"] = now_iso()
        with self._lock():
            p = self.root / "raw" / (packet["id"] + ".json")
            if not p.exists():
                atomic_write_json(p, packet)
        return packet["id"]

    def sync(self, tree) -> int:
        if not self.enabled:
            return 0
        count = 0
        with tree.lock:
            nodes = [n.to_dict() for n in tree.nodes.values() if n.status in ("done", "failed", "incomplete")]
        for n in nodes:
            nd = self.cfg.nodes_dir / n["id"]
            paths = [nd / name for name in ("HANDOFF.md", "PROGRESS.md", "FAILURE.md")]
            from .measurement import metrics_path as measurement_path
            metrics_path = measurement_path(self.cfg, tree.get(n["id"]))
            paths.append(metrics_path)
            sig = _hash([n, [(str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.exists()]])
            if self._seen.get(n["id"]) == sig:
                continue
            # No final.json, reports, test/confirmation metrics, or submission ledgers are ingested.
            node = tree.get(n["id"])
            valid_measurement = node.measurement_valid
            metrics = read_json(metrics_path, n["metrics"]) if valid_measurement else {}
            packet = {
                "kind": "experiment", "protocol": self.protocol, "role": "selection",
                "experiment": str(self.cfg.dir), "node": n["id"], "parent": n["parent"],
                "observed_at": n["finished_at"] or n["created_at"], "status": n["status"],
                "title": n["title"], "hypothesis": n["hypothesis"], "commit": n["commit"],
                "score": n["score"] if valid_measurement else None,
                "measurement_status": "validated" if valid_measurement else (
                    "skipped" if node.measurement.get("state") == "skipped" else "unavailable"),
                "selection_eligible": valid_measurement,
                "hypothesis_id": node.hypothesis_key,
                "documentation_status": n.get("documentation", {}).get("state", "complete" if n["status"] == "done" else "pending"),
                "metric": self.cfg.task.score_key, "level": self.cfg.task.official_seedset,
                "metrics": metrics, "worker_interpretation": {
                    p.name: {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                             "text": read_text(p)} for p in paths[:-1] if p.exists()
                },
                "audit": n["audit"], "failure": n["failure"],
                "result_analysis": n["worker"].get("analysis", {}),
                "research_cycle": n["worker"].get("research", {}),
            }
            if n["worker"].get("postprocess"):
                packet["completion"] = n["worker"]["postprocess"]
            self._capture(packet)
            self._seen[n["id"]] = sig
            count += 1
        return count

    def ingest(self, path: Path, label: str = "", *, source_url: str = "",
               attribution: str = "user-supplied source; claims need assessment") -> str:
        if not self.enabled:
            raise ValueError("enable memory before importing a source")
        path = path.expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        if len(text) > 200000:
            raise ValueError("source exceeds 200,000 characters; import a bounded text excerpt with its citation")
        return self._capture({"kind": "source", "protocol": self.protocol, "role": "research",
                              "title": label or path.name, "path": str(path), "text": text,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "observed_at": "", "source_url": source_url, "attribution": attribution})

    def pending(self, state=None) -> list[dict]:
        consumed = set((state or self.state())["consumed"])
        return [p for p in self.packets() if p["id"] not in consumed]

    def context(self, query: str, state=None) -> str:
        """Bounded, layered recall: L0 the agenda; L1 every research direction (topic page summaries, most
        relevant first, each bounded); L2 the claims that fit the query and its directions; L3 raw evidence by ID."""
        if not self.enabled:
            return ""
        state = state or self.state()
        memory = self.cfg.memory
        limit = memory.context_chars
        rev = self.root / "revisions" / state["revision"]
        lines = [
            "# Research memory",
            f"Revision: {state['revision'] or 'uncompiled'}; protocol: {self.protocol}.",
            f"Evidence packets (L3): {self.root / 'raw'} (read by cited ID when needed).",
            f"Generated knowledge (L2): {rev / 'wiki'}; direction pages (L1): {rev / 'topics'}.",
            f"Navigation index: {rev / 'index'} (not evidence).",
            "Evidence and interpretations are distinct. Scope is mandatory; failed implementations do not refute a method.",
            "Use supporting AND opposing evidence. Legacy insights/dead ends are provisional, conditional notes.",
        ]
        if state["agenda"]:
            lines += ["## Current research agenda (L0)",
                      json.dumps(state["agenda"], ensure_ascii=False)[:min(getattr(memory, "agenda_chars", 3000), limit // 3)]]
        terms = _tokens(query)

        def overlap(obj):
            return len(terms & _tokens(json.dumps(obj, ensure_ascii=False)))

        topics = sorted(state.get("topics", {}).values(),
                        key=lambda t: (-overlap(t), t.get("status") == "closed", t["id"]))
        matched = {t["id"] for t in topics[:3] if overlap(t)}
        if topics:
            lines += ["## Research directions (L1; every direction, most relevant first; a topic page has the detail)"]
            budget, used = min(getattr(memory, "topic_chars", 4000), limit // 3), 0
            for i, t in enumerate(topics):
                block = json.dumps({k: t.get(k) for k in ("id", "title", "status", "best", "why_stalled", "summary")},
                                   ensure_ascii=False)
                if len(block) > 700:
                    block = block[:699] + "…"
                if used + len(block) + 1 > budget:
                    lines.append(f"... {len(topics) - i} more directions in {rev / 'topics'}")
                    break
                lines.append(block)
                used += len(block) + 1
        claims = sorted(state["claims"].values(), key=lambda c: (
            -(overlap(c) + (3 if c.get("topic") in matched else 0)),
            c["status"] == "superseded", c["status"] not in ("mixed", "untested"), c["id"]))
        lines += ["## Relevant knowledge (L2, including counterevidence)"]
        for claim in claims:
            block = json.dumps(claim, ensure_ascii=False)
            if len("\n".join(lines)) + len(block) > limit - 1600:
                continue
            lines.append(block)
        quarantined = sorted(self.reflection_status()["quarantined"])
        if quarantined:
            block = (f"{len(quarantined)} evidence packets could not be compiled after repeated attempts; "
                     "read them directly in raw/ by ID: " + ", ".join(quarantined[:10]))
            if len("\n".join(lines)) + len(block) < limit:
                lines.append(block)
        # Recent uncompiled evidence remains visible; summaries are explicitly provisional.
        for p in self.pending(state)[-3:]:
            block = f"Pending {p['id']}: {p['title']}; status={p.get('status', 'source')}; "
            block += f"official score={p.get('score')}; interpretation not yet synthesized."
            block += " " + p.get("hypothesis", p.get("text", ""))[:400]
            if len("\n".join(lines)) + len(block) < limit:
                lines.append(block)
        return "\n".join(lines)[:limit]

    def snapshot(self, node) -> dict:
        state = self.state()
        text = self.context(node.title + " " + node.hypothesis, state)
        info = {"revision": state["revision"], "protocol": self.protocol,
                "context_sha256": hashlib.sha256(text.encode()).hexdigest()}
        nd = self.cfg.nodes_dir / node.id
        atomic_write_text(nd / "MEMORY.md", text)
        atomic_write_json(nd / "memory.json", info)
        return info

    def reflection_status(self) -> dict:
        """Compilation retry bookkeeping, shared by every run that uses this wiki."""
        status = read_json(self.root / "reflection_status.json", {}) or {}
        for key, default in (("failures", {}), ("quarantined", {}), ("streak", 0), ("retry_after", 0)):
            status.setdefault(key, default)
        return status

    def _next_batch(self, state, *, force, retry_now) -> list[dict]:
        status, now = self.reflection_status(), time.time()
        quarantined = status["quarantined"]
        pending = self.pending(state)
        due = [p for p in pending if p["id"] in quarantined
               and (retry_now or quarantined[p["id"]].get("retry_at", 0) <= now)]
        if due:
            return due[:1]  # a set-aside packet is retried alone, on its own slow schedule
        if not retry_now and now < status["retry_after"]:
            return []  # bounded paid retries after a failed compilation
        queue = [p for p in pending if p["id"] not in quarantined]
        if not queue or (not force and len(queue) < self.cfg.memory.reflect_every):
            return []
        # Shrink the batch after each failure of its head, isolating a packet that cannot be compiled.
        head = status["failures"].get(queue[0]["id"], 0)
        return queue[:max(1, self.cfg.memory.batch_size >> head)]

    def _record_outcome(self, status, batch, error=None) -> dict:
        ids = [p["id"] for p in batch]
        if error is None:
            for pid in ids:
                status["failures"].pop(pid, None)
                status["quarantined"].pop(pid, None)
            return {**status, "streak": 0, "retry_after": 0}
        now = time.time()
        status["last_error"] = {"at": now_iso(), "error": str(error)[:2000], "batch": ids}
        retry = [pid for pid in ids if pid in status["quarantined"]]
        for pid in retry:
            status["quarantined"][pid].update(attempts=status["quarantined"][pid].get("attempts", 0) + 1,
                                              error=str(error)[:2000], retry_at=now + QUARANTINE_RETRY_S)
        if retry:
            return status  # an isolated retry does not delay the healthy queue
        for pid in ids:
            status["failures"][pid] = status["failures"].get(pid, 0) + 1
        if len(ids) == 1 and status["failures"][ids[0]] >= QUARANTINE_AFTER:
            status["quarantined"][ids[0]] = {"at": now_iso(), "error": str(error)[:2000],
                                             "attempts": status["failures"].pop(ids[0]),
                                             "retry_at": now + QUARANTINE_RETRY_S}
        status["streak"] += 1
        status["retry_after"] = now + min(REFLECT_BACKOFF_S[1], REFLECT_BACKOFF_S[0] * 2 ** (status["streak"] - 1))
        return status

    def reflect(self, utility, *, force=False, review=False, retry_now=False) -> bool:
        """Compile pending evidence into a new wiki revision. A failure is recorded and retried later
        with a smaller batch (see REFLECT_BACKOFF_S/QUARANTINE_*); `retry_now` is for a human."""
        if not self.enabled:
            return False
        state = self.state()
        if review:
            batch = self.packets()[-self.cfg.memory.batch_size:]
        else:
            batch = self._next_batch(state, force=force, retry_now=retry_now)
        if not batch:
            return False
        try:
            validated = self._compile(utility, state, batch, review)
        except Exception as error:
            if not review:
                with self._lock():
                    atomic_write_json(self.root / "reflection_status.json",
                                      self._record_outcome(self.reflection_status(), batch, error))
            raise
        with self._lock():
            if self.revision != state["revision"]:
                return False  # another run published first; rebuild from its revision next time
            new = {**state, "claims": {**state["claims"], **validated["claims"]},
                   "topics": {**state.get("topics", {}), **validated.get("topics", {})},
                   "agenda": validated["agenda"], "updated_at": now_iso(),
                   "consumed": sorted(set(state["consumed"]) | {p["id"] for p in batch}),
                   "previous_revision": state["revision"]}
            new["changes"] = [{"claim": cid, "before": state["claims"].get(cid, {}).get("status"),
                               "after": c["status"], "reason": c.get("revision_reason") or validated["agenda"]["what_changed"],
                               "supersedes": c.get("supersedes", "")}
                              for cid, c in validated["claims"].items()
                              if {k:v for k,v in c.items() if k != "updated_at"} !=
                                 {k:v for k,v in state["claims"].get(cid, {}).items() if k != "updated_at"}]
            new["revision"] = _hash(new)[:24]
            dest = self.root / "revisions" / new["revision"]
            atomic_write_json(dest / "state.json", new)
            self._render(dest, new)
            atomic_write_json(self.root / "CURRENT.json", {"revision": new["revision"]})
            atomic_write_text(self.root / "INDEX.md",
                              f"# Research wiki\n\nProtocol: {self.protocol}\n\n"
                              f"[Current wiki](revisions/{new['revision']}/INDEX.md)\n\n"
                              f"[Knowledge index](revisions/{new['revision']}/index/INDEX.md)\n\n"
                              f"[Belief revisions](revisions/{new['revision']}/CHANGES.md)\n")
            if not review:
                atomic_write_json(self.root / "reflection_status.json",
                                  self._record_outcome(self.reflection_status(), batch))
        return True

    def _compile(self, utility, state, batch, review) -> dict:
        from .memory_prompts import reflection_prompt, REFLECTION_SCHEMA
        prompt, allowed_claims = reflection_prompt(self, state, batch)
        if review:
            prompt += ("\nREVIEW PASS\nRevisit the existing knowledge for unsupported causal claims, "
                       "over-broad scope, inconsistent statuses, and obsolete recommendations. "
                       "Observations must describe interventions and measured outcomes only. "
                       "Move causal explanations to separate hypotheses with appropriate uncertainty. "
                       "Prioritize corrections over new pages; no new experiment occurred in this review.\n")
        data = utility._ask("memory_reflection", prompt, REFLECTION_SCHEMA, "_memory")
        try:
            return self._validate(data, state, batch, allowed_claims)
        except ValueError as error:
            # A single bounded editorial correction; never publish the rejected draft.
            if "changing claim scope" in str(error):
                name, why = "memory_scope_repair", ("The draft was rejected because an existing ID changed scope. "
                    "For existing IDs copy the EXACT old scope, including punctuation, when the proposition still fits. "
                    "For a materially different scope, mark the predecessor superseded and create a NEW scoped ID "
                    "with supersedes and revision_reason. ")
            else:
                name, why = "memory_repair", (f"The draft was rejected by validation: {error}. Fix exactly that "
                    "problem and keep everything else. ")
            correction = (prompt + "\nVALIDATION REPAIR\n" + why + "Preserve all evidence and causal uncertainty. "
                "Return the full corrected JSON, not a patch. No new experiment occurred.\nREJECTED DRAFT\n" +
                json.dumps(data, ensure_ascii=False)[:24000])
            data = utility._ask(name, correction, REFLECTION_SCHEMA, "_memory")
            return self._validate(data, state, batch, allowed_claims)

    def _validate(self, data, state, batch, allowed_claims) -> dict:
        if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
            raise ValueError("reflection must return claims and an agenda")
        # References may point to this batch or sources already cited in supplied knowledge.
        known = {p["id"] for p in batch}
        for cid in allowed_claims:
            c = state["claims"][cid]
            known.update(c["supports"] + c["opposes"])
        updates = {}
        reconciled = []
        if len(data["claims"]) > 12:
            raise ValueError("reflection exceeds 12 claim updates")
        for c in data["claims"]:
            if not isinstance(c, dict):
                raise ValueError("invalid claim")
            cid = c.get("id", "")
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", cid):
                raise ValueError("invalid claim ID")
            if cid in updates or (cid in state["claims"] and cid not in allowed_claims):
                raise ValueError("duplicate or unseen claim update")
            if c.get("kind") not in ("observation", "hypothesis", "experience"):
                raise ValueError("invalid claim kind")
            if c.get("status") not in ("untested", "supported", "mixed", "refuted", "superseded"):
                raise ValueError("invalid claim status")
            for key in ("title", "statement", "scope", "next_test"):
                if not isinstance(c.get(key), str) or not c[key].strip() or len(c[key]) > 2000:
                    raise ValueError(f"claim requires bounded {key}")
            for key in ("supports", "opposes", "alternatives"):
                if not isinstance(c.get(key), list) or any(not isinstance(x, str) for x in c[key]):
                    raise ValueError(f"invalid {key}")
            for key in ("supports", "opposes"):
                c[key] = [_known_id(x, known) for x in c[key]]
            if not set(c["supports"] + c["opposes"]) <= known:
                raise ValueError("claim cites evidence absent from its input")
            if c["status"] in ("supported", "mixed", "refuted") and not (c["supports"] or c["opposes"]):
                raise ValueError("tested claims require evidence")
            if c["status"] == "refuted" and not c["opposes"]:
                raise ValueError("refutation requires opposing evidence")
            if c["status"] == "supported" and not c["supports"]:
                raise ValueError("support requires supporting evidence")
            old = state["claims"].get(cid, {})
            if old and c["scope"] != old["scope"]:
                raise ValueError("changing claim scope requires an explicit successor with a new ID")
            c = {k: c[k] for k in ("id", "title", "kind", "status", "statement", "scope",
                                  "supports", "opposes", "alternatives", "next_test")}
            original = next(x for x in data["claims"] if x["id"] == cid)
            topic = original.get("topic") if isinstance(original.get("topic"), str) else ""
            topic = (topic or old.get("topic", "")).strip()[:64]
            if topic:
                c["topic"] = topic  # the direction page it belongs to; checked below
            predecessor = original.get("supersedes", old.get("supersedes", ""))
            reason = original.get("revision_reason", old.get("revision_reason", ""))
            if predecessor:
                if predecessor == cid or predecessor not in allowed_claims:
                    raise ValueError("successor must cite a supplied predecessor claim")
                if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
                    raise ValueError("superseding a claim requires a bounded revision reason")
                c.update(supersedes=predecessor, revision_reason=reason)
            # Never silently erase older counterevidence; narrow/retract in a new revision.
            for key in ("supports", "opposes"):
                c[key] = sorted(set(c[key]) | set(old.get(key, [])))
            if c["supports"] and c["opposes"] and c["status"] != "superseded":
                if c["status"] != "mixed":
                    reconciled.append(f"{cid}: requested {c['status']}, retained as mixed because both "
                                      "supporting and opposing references remain. No historical reference was removed.")
                c["status"] = "mixed"
            c["updated_at"] = now_iso()
            updates[cid] = c
        for c in updates.values():
            if c.get("supersedes"):
                previous = updates.get(c["supersedes"], state["claims"][c["supersedes"]])
                if previous["status"] != "superseded":
                    raise ValueError("retire the predecessor explicitly before publishing its successor")
        combined = {**state["claims"], **updates}
        for cid in updates:
            seen, current = set(), cid
            while current:
                if current in seen:
                    raise ValueError("claim succession cannot contain a cycle")
                seen.add(current)
                current = combined.get(current, {}).get("supersedes", "")
        topic_updates = self._validate_topics(data.get("topics") or [], state, set(state["claims"]) | set(updates))
        known_topics = set(state.get("topics", {})) | set(topic_updates)
        for c in updates.values():
            if c.get("topic") and c["topic"] not in known_topics:
                c.pop("topic")  # an unknown direction is not a reference
        agenda = data.get("agenda")
        if not isinstance(agenda, dict):
            raise ValueError("missing agenda")
        for key in ("motivation", "method", "what_changed"):
            if not isinstance(agenda.get(key), str) or not agenda[key].strip() or len(agenda[key]) > 4000:
                raise ValueError(f"agenda requires bounded {key}")
        agenda = dict(agenda)
        for key in ("open_questions", "next_experiments"):
            if not isinstance(agenda.get(key), list):
                raise ValueError(f"invalid agenda {key}")
            if any(not isinstance(x, str) for x in agenda[key]):
                raise ValueError(f"invalid agenda {key} item")
            # Most important first (the prompt asks for that); a longer list is cut, not rejected.
            agenda[key] = [x[:1500] for x in agenda[key][:6]]
        if reconciled:
            agenda = {**agenda, "what_changed": "Stored evidence status: " + " ".join(reconciled)
                      + "\n\nDraft interpretation (subject to the corrections above): " + agenda["what_changed"]}
        if self.cfg.research.enabled:
            agenda = {**agenda, "next_experiments": []}  # plans live in NEXT.md / DECISION.md
        return {"claims": updates, "topics": topic_updates, "agenda": {k: agenda[k] for k in (
            "motivation", "method", "what_changed", "open_questions", "next_experiments")}}

    @staticmethod
    def _validate_topics(topics, state, known_claims) -> dict:
        """Direction pages (L1): one per research direction. Earlier claim references and explored nodes are
        retained; a reference to an unknown claim is dropped rather than invented."""
        if not isinstance(topics, list) or len(topics) > 8:
            raise ValueError("reflection exceeds 8 topic updates")
        out = {}
        for t in topics:
            if not isinstance(t, dict):
                raise ValueError("invalid topic")
            tid = t.get("id", "")
            if not isinstance(tid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", tid) or tid in out:
                raise ValueError("invalid or duplicate topic ID")
            if t.get("status") not in ("active", "stalled", "closed"):
                raise ValueError("invalid topic status")
            for key, cap in (("title", 200), ("summary", 1500)):
                if not isinstance(t.get(key), str) or not t[key].strip() or len(t[key]) > cap:
                    raise ValueError(f"topic requires bounded {key}")
            old = state.get("topics", {}).get(tid, {})
            best = t.get("best") if isinstance(t.get("best"), dict) else {}
            score = best.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                score = (old.get("best") or {}).get("score")
            tried = {x for x in (t.get("tried") or []) if isinstance(x, str) and x in known_claims}
            subtree = {str(x)[:64] for x in (t.get("subtree") or []) if isinstance(x, str)}
            out[tid] = {"id": tid, "title": t["title"].strip(), "status": t["status"],
                        "scope": str(t.get("scope") or old.get("scope") or "")[:1000],
                        "summary": t["summary"].strip(), "why_stalled": str(t.get("why_stalled") or "")[:1000],
                        "tried": sorted(tried | set(old.get("tried", []))),
                        "best": {"node": str(best.get("node") or (old.get("best") or {}).get("node") or "")[:64],
                                 "score": score},
                        "subtree": sorted(subtree | set(old.get("subtree", [])))[:24], "updated_at": now_iso()}
        return out

    def ledger_views(self):
        """INSIGHTS.md / DEADENDS.md as views of the wiki: supported claims and refuted ones."""
        state = self.state() if self.enabled else {"claims": {}, "revision": ""}
        head = (f"Generated from research wiki revision {state.get('revision') or '(none)'}; do not edit. "
                "Each line cites its wiki claim; the claim page cites the evidence.")
        views = []
        for title, status in (("Insights", "supported"), ("Dead ends", "refuted")):
            lines = [f"# {title} (generated)", "", head, ""]
            lines += [f"- {c['title']}: {c['statement'][:300]} [wiki: {c['id']}]"
                      for c in state["claims"].values() if c.get("status") == status]
            views.append("\n".join(lines) + "\n")
        return tuple(views)

    def _render(self, dest, state):
        lines = ["# Research wiki", "", f"Revision: {state['revision']}", "",
                 "[Research agenda](AGENDA.md)", "", "## Knowledge"]
        for c in state["claims"].values():
            lines.append(f"- [{c['title']}](wiki/{c['id']}.md) — {c['kind']}, {c['status']}")
            body = [f"# {c['title']}", "", f"Type: {c['kind']}; status: {c['status']}",
                    "", c["statement"], "", "## Scope", c["scope"], "", "## Supporting evidence"]
            for key, heading in (("supports", None), ("opposes", "Opposing evidence")):
                if heading:
                    body += ["", "## " + heading]
                body += [f"- [{eid}](../../../raw/{eid}.json)" for eid in c[key]] or ["- None"]
            body += ["", "## Competing explanations", *["- " + x for x in c["alternatives"]],
                     "", "## Next discriminating test", c["next_test"]]
            if c.get("supersedes"):
                body += ["", "## Revises earlier knowledge",
                         f"[Previous claim]({c['supersedes']}.md)", c["revision_reason"]]
            atomic_write_text(dest / "wiki" / (c["id"] + ".md"), "\n".join(body) + "\n")
        topics = state.get("topics", {})
        if topics:
            lines += ["", "## Research directions"]
        for t in topics.values():
            lines.append(f"- [{t['title']}](topics/{t['id']}.md) — {t['status']}")
            best = t.get("best") or {}
            best_line = ((f"node {best['node']}" + (f", official score {best['score']}" if best.get("score") is not None else ""))
                         if best.get("node") else "(none recorded)")
            body = [f"# {t['title']}", "", f"Status: {t['status']}", "", t["summary"], "", "## Scope",
                    t.get("scope") or "(unstated)", "", "## Best measured result", best_line,
                    "", "## Why it stalled", t.get("why_stalled") or "(not stalled)",
                    "", "## Claims in this direction",
                    *([f"- [{cid}](../wiki/{cid}.md)" for cid in t.get("tried", [])] or ["- None"]),
                    "", "## Explored at nodes", ", ".join(t.get("subtree", [])) or "(none recorded)"]
            atomic_write_text(dest / "topics" / (t["id"] + ".md"), "\n".join(body) + "\n")
        atomic_write_text(dest / "INDEX.md", "\n".join(lines) + "\n")
        agenda = ["# Research agenda", "", "This is a revisable synthesis, not independently verified fact."]
        for key, value in state["agenda"].items():
            if value == []:
                continue
            agenda += ["", "## " + key.replace("_", " ").title(),
                       "\n".join("- " + x for x in value) if isinstance(value, list) else value]
        atomic_write_text(dest / "AGENDA.md", "\n".join(agenda) + "\n")
        # Third layer: navigation projections. Measurements remain exclusively in raw/.
        index = {"revision": state["revision"], "protocol": self.protocol,
                 "claims": [{"id": c["id"], "title": c["title"], "kind": c["kind"],
                             "status": c["status"], "scope": c["scope"],
                             "page": f"../wiki/{c['id']}.md", "supports": c["supports"],
                             "opposes": c["opposes"], "supersedes": c.get("supersedes", ""),
                             "topic": c.get("topic", "")}
                            for c in state["claims"].values()],
                 "topics": [{"id": t["id"], "title": t["title"], "status": t["status"],
                             "page": f"../topics/{t['id']}.md", "tried": t.get("tried", []),
                             "best": t.get("best", {}), "subtree": t.get("subtree", [])}
                            for t in state.get("topics", {}).values()],
                 "changes": state.get("changes", [])}
        atomic_write_json(dest / "index" / "index.json", index)
        navigation = ["# Knowledge index", "", "Navigation only; follow source links to assess evidence.", "",
                      "[Research agenda](../AGENDA.md)", "[Belief revisions](../CHANGES.md)", ""]
        if state.get("topics"):
            navigation += ["## Directions", ""]
            navigation += [f"- [{t['title']}](../topics/{t['id']}.md) — {t['status']}" for t in state["topics"].values()]
            navigation.append("")
        for kind in ("observation", "hypothesis", "experience"):
            navigation += ["## " + kind.title(), ""]
            navigation += [f"- [{c['title']}](../wiki/{c['id']}.md) — {c['status']}"
                           for c in state["claims"].values() if c["kind"] == kind]
            navigation.append("")
        atomic_write_text(dest / "index" / "INDEX.md", "\n".join(navigation))
        changes = ["# Belief revisions", "", "Prior revisions and raw evidence are retained.", ""]
        changes += [f"- **{c['claim']}**: {c['before'] or 'new'} → {c['after']}. {c['reason']}"
                    for c in state.get("changes", [])]
        atomic_write_text(dest / "CHANGES.md", "\n".join(changes) + "\n")


def research_context(cfg, query: str) -> str:
    if not cfg.memory.enabled:
        return ""
    try:
        return ResearchMemory(cfg).context(query)
    except (OSError, ValueError, KeyError):
        return "Research memory could not be read. Use original node evidence; do not invent missing knowledge."
