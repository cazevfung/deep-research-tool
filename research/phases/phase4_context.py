"""Phase 4 context assembly utilities.

This module builds a structured context bundle for the synthesis phase,
making upstream artifacts (role charter, research goals, phase 3 evidence)
available in a consistent schema for prompts and validators.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from research.prompts.context_formatters import format_phase3_for_synthesis, format_synthesized_goal_for_context


def _truncate(text: Optional[str], limit: int = 200) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


@dataclass
class EvidenceRecord:
    """Evidence item extracted from Phase 3 findings."""

    evidence_id: str
    step_id: int
    goal: str
    category: str
    summary: str
    detail: Optional[str] = None
    source_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload

    def to_prompt_lines(self) -> str:
        lines = [
            f"[{self.evidence_id}] 步骤 {self.step_id} · {self.goal or '未匹配目标'} · {self.category}"
        ]
        if self.summary:
            lines.append(f"  - 摘要：{self.summary}")
        if self.detail:
            lines.append(f"  - 引述：{self.detail}")
        if self.source_hint:
            lines.append(f"  - 来源线索：{self.source_hint}")
        return "\n".join(lines)


@dataclass
class StepSynopsis:
    """Summarised view of a Phase 3 step for Phase 4 prompts."""

    step_id: int
    goal: str
    summary: str
    insights: str
    confidence: Optional[float]
    key_claims: List[str] = field(default_factory=list)
    counterpoints: List[str] = field(default_factory=list)
    surprises: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)

    def to_prompt_lines(self) -> str:
        label = f"步骤 {self.step_id}"
        if self.goal:
            label += f" · {self.goal}"
        confidence_text = ""
        if isinstance(self.confidence, (float, int)) and self.confidence > 0:
            confidence_text = f"（信心 ≈ {round(float(self.confidence) * 100)}%）"
        lines = [f"- {label}{confidence_text}"]
        if self.summary:
            lines.append(f"  摘要：{self.summary}")
        if self.key_claims:
            lines.append("  关键论点： " + "; ".join(self.key_claims[:3]))
        if self.counterpoints:
            lines.append("  反对观点： " + "; ".join(self.counterpoints[:3]))
        if self.surprises:
            lines.append("  意外洞察： " + "; ".join(self.surprises[:2]))
        if self.evidence_ids:
            lines.append("  证据： " + ", ".join(self.evidence_ids[:6]))
        if self.open_questions:
            lines.append("  待补： " + "; ".join(self.open_questions[:3]))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class GoalAlignmentRow:
    """Mapping between component questions and Phase 3 outputs/evidence."""

    question: str
    related_steps: List[int] = field(default_factory=list)
    related_evidence_ids: List[str] = field(default_factory=list)
    summary: str = ""

    def to_prompt_lines(self) -> str:
        steps_text = ", ".join([f"步骤{sid}" for sid in self.related_steps]) or "未匹配"
        evidence_text = ", ".join(self.related_evidence_ids) or "待补充"
        lines = [
            f"- {self.question}",
            f"  - 对应步骤：{steps_text}",
            f"  - 关联证据：{evidence_text}",
        ]
        if self.summary:
            lines.append(f"  - 摘要：{self.summary}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class Phase4ContextBundle:
    """Structured container for all context needed in Phase 4."""

    selected_goal: str
    research_role: Dict[str, Any]
    synthesized_goal: Dict[str, Any]
    synthesized_goal_context: Dict[str, str]
    component_questions: List[str]
    phase3_text_blocks: Dict[str, str]
    steps: List[StepSynopsis]
    evidence: List[EvidenceRecord]
    goal_alignment: List[GoalAlignmentRow]
    scratchpad_digest: str
    user_initial_guidance: str
    user_priority_notes: str
    research_plan: List[Dict[str, Any]]
    enable_auxiliary_artifacts: bool = False
    phase3_full_payload: str = ""

    def component_questions_text(self) -> str:
        if not self.component_questions:
            return "（未提供组成问题）"
        return "\n".join(f"{idx + 1}. {question}" for idx, question in enumerate(self.component_questions))

    def goal_alignment_text(self) -> str:
        if not self.goal_alignment:
            return "（尚未匹配组成问题与Phase 3步骤，生成文章时需自行确保覆盖。）"
        return "\n".join(row.to_prompt_lines() for row in self.goal_alignment)

    def evidence_catalog_text(self) -> str:
        if not self.evidence:
            return "（暂无显式证据条目；撰写时需引用Phase 3 摘要内容并标注来源。）"
        return "\n".join(record.to_prompt_lines() for record in self.evidence)

    def component_alignment_context_text(self) -> str:
        text = self.goal_alignment_text().strip()
        if text:
            return text
        return "（尚未匹配组成问题与Phase 3步骤，撰写时需手动确认覆盖。）"

    def component_questions_context_text(self) -> str:
        text = self.component_questions_text().strip()
        if text:
            return text
        return "（无组成问题列表；请根据研究主题自行拆解核心问题。）"

    def source_mix_context_text(self) -> str:
        hints = [record.source_hint.strip() for record in self.evidence if record.source_hint and record.source_hint.strip()]
        if hints:
            counts = Counter(hints)
            sorted_items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            lines = [f"- {hint} × {count}" for hint, count in sorted_items[:12]]
            if len(sorted_items) > 12:
                lines.append(f"- 其余来源 {len(sorted_items) - 12} 个（详见 evidence_catalog_json）")
            return "来源覆盖统计：\n" + "\n".join(lines)
        evidence_highlights = (self.phase3_text_blocks.get("phase3_evidence_highlights") or "").strip()
        if evidence_highlights:
            return "来源概览：\n" + evidence_highlights
        return "（Phase 3 输出未提供明确的来源分布；撰写时需在引用证据时补充来源类型与出处。）"

    def user_amendment_context_text(self) -> str:
        guidance = []
        if self.user_initial_guidance:
            guidance.append(f"- 初始指导：{self.user_initial_guidance.strip()}")
        if self.user_priority_notes and self.user_priority_notes.strip() not in self.user_initial_guidance:
            guidance.append(f"- 后续优先事项：{self.user_priority_notes.strip()}")
        if not guidance:
            return "（用户未提供额外指导，可根据研究发现自主组织结构。）"
        return "\n".join(guidance)

    def step_overview_text(self) -> str:
        if not self.steps:
            return "（Phase 3 没有可用步骤摘要。）"
        return "\n".join(step.to_prompt_lines() for step in self.steps)

    def to_prompt_context(self) -> Dict[str, Any]:
        """Render base context dictionary for prompt templates."""
        role_display = self.research_role.get("role") or "资深管理咨询顾问"
        context = {
            "selected_goal": self.selected_goal,
            "title": self.selected_goal,  # Alias for title placeholder (report title)
            "system_role_title": role_display,
            "system_role_description": role_display,  # Required by Phase 4 system prompt
            "research_role_display": self.research_role.get("role", ""),
            "research_role_rationale": self.research_role.get("rationale", ""),
            "synthesized_goal_topic": self.synthesized_goal_context.get("synthesized_topic", ""),
            "synthesized_goal_scope": self.synthesized_goal_context.get("research_scope", ""),
            "component_questions_text": self.component_questions_text(),
            "goal_alignment_table": self.goal_alignment_text(),
            "phase3_overall_summary": self.phase3_text_blocks.get("phase3_overall_summary", ""),
            "phase3_step_overview": self.phase3_text_blocks.get("phase3_step_overview", ""),
            "phase3_key_claims": self.phase3_text_blocks.get("phase3_key_claims", ""),
            "phase3_counterpoints": self.phase3_text_blocks.get("phase3_counterpoints", ""),
            "phase3_surprising_findings": self.phase3_text_blocks.get("phase3_surprising_findings", ""),
            "phase3_evidence_highlights": self.phase3_text_blocks.get("phase3_evidence_highlights", ""),
            "phase3_open_questions": self.phase3_text_blocks.get("phase3_open_questions", ""),
            "phase3_storyline_candidates": self.phase3_text_blocks.get("phase3_storyline_candidates", ""),
            "phase3_step_synopsis": self.step_overview_text(),
            "evidence_catalog": self.evidence_catalog_text(),
            "component_alignment_context": self.component_alignment_context_text(),
            "component_questions_context": self.component_questions_context_text(),
            "source_mix_context": self.source_mix_context_text(),
            "user_amendment_context": self.user_amendment_context_text(),
            "scratchpad_digest": self.scratchpad_digest or "暂无结构化发现。",
            "user_initial_guidance": self.user_initial_guidance or "",  # Keep for backward compatibility
            "user_priority_notes": self.user_priority_notes or "",  # Keep for backward compatibility
            "user_guidance": self.user_initial_guidance or "",  # New: unified field
            "user_context": self.user_priority_notes or "",  # New: unified field
            "enable_auxiliary_artifacts": "yes" if self.enable_auxiliary_artifacts else "no",
            "phase3_full_payload": self.phase3_full_payload or "",
            # JSON payloads for downstream prompts
            "component_questions_json": json.dumps(self.component_questions, ensure_ascii=False),
            "phase3_steps_json": json.dumps([step.to_dict() for step in self.steps], ensure_ascii=False),
            "evidence_catalog_json": json.dumps([record.to_dict() for record in self.evidence], ensure_ascii=False),
            "goal_alignment_json": json.dumps([row.to_dict() for row in self.goal_alignment], ensure_ascii=False),
            "research_plan_json": json.dumps(self.research_plan or [], ensure_ascii=False),
        }
        return context

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_goal": self.selected_goal,
            "research_role": self.research_role,
            "synthesized_goal": self.synthesized_goal,
            "component_questions": self.component_questions,
            "phase3_text_blocks": self.phase3_text_blocks,
            "steps": [step.to_dict() for step in self.steps],
            "evidence": [record.to_dict() for record in self.evidence],
            "goal_alignment": [row.to_dict() for row in self.goal_alignment],
            "scratchpad_digest": self.scratchpad_digest,
            "user_initial_guidance": self.user_initial_guidance,
            "user_priority_notes": self.user_priority_notes,
            "research_plan": self.research_plan,
            "enable_auxiliary_artifacts": self.enable_auxiliary_artifacts,
            "phase3_full_payload": self.phase3_full_payload,
        }


def build_phase4_context_bundle(
    session: Any,
    phase1_5_output: Dict[str, Any],
    phase3_output: Optional[Dict[str, Any]],
    *,
    enable_auxiliary_artifacts: bool = False,
) -> Phase4ContextBundle:
    """Assemble the full context bundle used by Phase 4."""

    synthesized_goal = phase1_5_output.get("synthesized_goal") if isinstance(phase1_5_output, dict) else None
    if not synthesized_goal and isinstance(phase1_5_output, dict):
        # backward compatibility where Phase 1.5 output itself is the goal
        synthesized_goal = {
            key: phase1_5_output.get(key)
            for key in ("comprehensive_topic", "component_questions", "unifying_theme", "research_scope")
            if key in phase1_5_output
        }
    synthesized_goal = synthesized_goal or session.get_metadata("synthesized_goal", {}) or {}
    synthesized_goal_context = format_synthesized_goal_for_context(synthesized_goal)

    selected_goal = synthesized_goal.get("comprehensive_topic") or session.get_metadata("selected_goal", "")
    component_questions = list(synthesized_goal.get("component_questions") or [])

    research_role = session.get_metadata("research_role", {}) or {}
    if not research_role:
        role_artifact = session.get_phase_artifact("phase0_5", {}) or {}
        if isinstance(role_artifact, dict):
            research_role = role_artifact.get("research_role") or {}

    research_plan = []
    try:
        plan_meta = session.get_metadata("research_plan", [])
        if isinstance(plan_meta, list):
            research_plan = plan_meta
    except Exception:
        research_plan = []

    scratchpad_digest = session.get_scratchpad_summary()

    user_initial_guidance = session.get_metadata("phase_feedback_pre_role", "") or phase1_5_output.get("user_initial_input", "") if isinstance(phase1_5_output, dict) else ""
    user_priority_notes = session.get_metadata("phase_feedback_post_phase1", "")
    if not user_priority_notes and isinstance(phase1_5_output, dict):
        user_priority_notes = phase1_5_output.get("user_input", "")

    phase3_text_blocks, structured_steps = format_phase3_for_synthesis(phase3_output, research_plan)
    steps, evidence_records = _extract_phase3_structures(phase3_output, structured_steps, research_plan)

    goal_alignment = _align_component_questions(component_questions, steps, evidence_records)

    phase3_full_payload = ""
    try:
        if phase3_output is not None:
            phase3_full_payload = json.dumps(phase3_output, ensure_ascii=False, indent=2)
    except Exception:
        phase3_full_payload = str(phase3_output) if phase3_output is not None else ""

    bundle = Phase4ContextBundle(
        selected_goal=selected_goal,
        research_role=research_role if isinstance(research_role, dict) else {"role": str(research_role)},
        synthesized_goal=synthesized_goal,
        synthesized_goal_context=synthesized_goal_context,
        component_questions=component_questions,
        phase3_text_blocks=phase3_text_blocks,
        steps=steps,
        evidence=evidence_records,
        goal_alignment=goal_alignment,
        scratchpad_digest=scratchpad_digest,
        user_initial_guidance=user_initial_guidance or "",
        user_priority_notes=user_priority_notes or "",
        research_plan=research_plan,
        enable_auxiliary_artifacts=enable_auxiliary_artifacts,
        phase3_full_payload=phase3_full_payload,
    )

    return bundle


def _extract_phase3_structures(
    phase3_output: Optional[Dict[str, Any]],
    structured_steps: List[Dict[str, Any]],
    research_plan: List[Dict[str, Any]],
) -> Tuple[List[StepSynopsis], List[EvidenceRecord]]:
    """Extract step synopses and evidence catalog from raw Phase 3 output."""

    if not isinstance(phase3_output, dict):
        return [], []

    plan_lookup: Dict[int, Dict[str, Any]] = {}
    for plan_step in research_plan or []:
        if isinstance(plan_step, dict):
            step_id = plan_step.get("step_id")
            if isinstance(step_id, int):
                plan_lookup[step_id] = plan_step

    steps: List[StepSynopsis] = []
    evidence_records: List[EvidenceRecord] = []
    evidence_index = 1

    findings_entries = phase3_output.get("findings") or []
    if not isinstance(findings_entries, list):
        findings_entries = []

    structured_lookup: Dict[int, Dict[str, Any]] = {}
    for entry in structured_steps or []:
        if isinstance(entry, dict) and isinstance(entry.get("step_id"), int):
            structured_lookup[int(entry["step_id"])] = entry

    for entry in findings_entries:
        if not isinstance(entry, dict):
            continue
        step_payload = entry.get("findings") or {}
        if not isinstance(step_payload, dict):
            continue

        step_id = step_payload.get("step_id") or entry.get("step_id")
        if not isinstance(step_id, int):
            continue

        goal_text = ""
        if step_id in plan_lookup:
            goal_text = str(plan_lookup[step_id].get("goal", "") or "")
        elif step_id in structured_lookup:
            goal_text = str(structured_lookup[step_id].get("goal", "") or "")

        findings_obj = step_payload.get("findings") or {}
        if not isinstance(findings_obj, dict):
            findings_obj = {}

        summary = _truncate(findings_obj.get("summary"), 600)
        insights = _truncate(step_payload.get("insights"), 400)
        confidence = step_payload.get("confidence")

        poi = findings_obj.get("points_of_interest") or {}
        if not isinstance(poi, dict):
            poi = {}

        key_claims = []
        for claim in poi.get("key_claims") or []:
            if isinstance(claim, dict):
                key_claims.append(_truncate(claim.get("claim"), 200))
        counterpoints = []
        for topic in poi.get("controversial_topics") or []:
            if isinstance(topic, dict):
                label = _truncate(topic.get("topic"), 160)
                opposing = topic.get("opposing_views")
                if isinstance(opposing, list) and opposing:
                    label += " —— " + "; ".join(_truncate(v, 100) for v in opposing[:3])
                counterpoints.append(label)
        surprises = []
        for surprise in poi.get("surprising_insights") or []:
            surprises.append(_truncate(surprise, 160))
        open_questions = []
        for question in poi.get("open_questions") or []:
            open_questions.append(_truncate(question, 160))

        evidence_ids: List[str] = []

        for item in poi.get("notable_evidence") or []:
            if not isinstance(item, dict):
                continue
            evidence_id = f"EVID-{evidence_index:02d}"
            summary_text = _truncate(item.get("description") or item.get("quote"), 280)
            detail_text = _truncate(item.get("quote"), 320)
            source_hint = _truncate(item.get("source"), 160)
            category = str(item.get("evidence_type") or "evidence")
            evidence_records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    step_id=step_id,
                    goal=goal_text,
                    category=category,
                    summary=summary_text,
                    detail=detail_text,
                    source_hint=source_hint,
                )
            )
            evidence_ids.append(evidence_id)
            evidence_index += 1

        for example in poi.get("specific_examples") or []:
            if not isinstance(example, dict):
                continue
            evidence_id = f"EVID-{evidence_index:02d}"
            summary_text = _truncate(example.get("example") or example.get("description"), 280)
            detail_text = _truncate(example.get("context") or example.get("notes"), 320)
            evidence_records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    step_id=step_id,
                    goal=goal_text,
                    category="example",
                    summary=summary_text,
                    detail=detail_text,
                    source_hint=None,
                )
            )
            evidence_ids.append(evidence_id)
            evidence_index += 1

        for claim in poi.get("key_claims") or []:
            if not isinstance(claim, dict):
                continue
            claim_text = _truncate(claim.get("claim"), 220)
            if not claim_text:
                continue
            evidence_id = f"EVID-{evidence_index:02d}"
            supporting = _truncate(claim.get("supporting_evidence"), 320)
            evidence_records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    step_id=step_id,
                    goal=goal_text,
                    category="claim",
                    summary=claim_text,
                    detail=supporting,
                    source_hint=None,
                )
            )
            evidence_ids.append(evidence_id)
            evidence_index += 1

        step_synopsis = StepSynopsis(
            step_id=step_id,
            goal=goal_text,
            summary=summary or insights,
            insights=insights,
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
            key_claims=[_truncate(text, 220) for text in key_claims if text],
            counterpoints=counterpoints,
            surprises=surprises,
            open_questions=open_questions,
            evidence_ids=evidence_ids,
        )
        steps.append(step_synopsis)

    return steps, evidence_records


def _align_component_questions(
    component_questions: List[str],
    steps: List[StepSynopsis],
    evidence_records: List[EvidenceRecord],
) -> List[GoalAlignmentRow]:
    """Align component questions with Phase 3 steps and evidence heuristically."""

    if not component_questions:
        return []

    evidence_by_step: Dict[int, List[str]] = {}
    for record in evidence_records:
        evidence_by_step.setdefault(record.step_id, []).append(record.evidence_id)

    # simple lookup by step goal text
    step_lookup: Dict[int, StepSynopsis] = {step.step_id: step for step in steps}
    goal_text_index: Dict[str, int] = {}
    for step in steps:
        key = (step.goal or "").strip()
        if key:
            goal_text_index.setdefault(key, step.step_id)

    rows: List[GoalAlignmentRow] = []
    for idx, question in enumerate(component_questions):
        normalized = (question or "").strip()
        matched_steps: List[int] = []

        if normalized in goal_text_index:
            matched_steps.append(goal_text_index[normalized])
        else:
            # fallback: positional alignment
            if idx < len(steps):
                matched_steps.append(steps[idx].step_id)

        matched_steps = sorted(set(matched_steps))

        evidence_ids: List[str] = []
        summary_lines: List[str] = []
        for step_id in matched_steps:
            step = step_lookup.get(step_id)
            if not step:
                continue
            summary_lines.append(_truncate(step.summary or step.insights, 240))
            evidence_ids.extend(evidence_by_step.get(step_id, []))

        row = GoalAlignmentRow(
            question=normalized or f"问题 {idx + 1}",
            related_steps=matched_steps,
            related_evidence_ids=sorted(set(evidence_ids)),
            summary="；".join(filter(None, summary_lines)),
        )
        rows.append(row)

    return rows


