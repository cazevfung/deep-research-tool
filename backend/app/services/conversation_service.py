"""
Conversation context management and LLM orchestration for right-column feedback.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import asyncio
import threading
import uuid
from typing import Deque, Dict, List, Optional, Tuple, Literal, Any

from loguru import logger

try:
    from research.client import QwenStreamingClient
except Exception as exc:  # pragma: no cover - handled lazily
    logger.warning(f"Unable to import QwenStreamingClient at module load: {exc}")
    QwenStreamingClient = None  # type: ignore

ConversationRole = Literal["user", "assistant", "system"]
MessageStatus = Literal["queued", "in_progress", "completed", "error"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConversationMessage:
    id: str
    role: ConversationRole
    content: str
    status: MessageStatus
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at
        payload["updated_at"] = self.updated_at
        return payload


@dataclass
class ProceduralPromptState:
    prompt_id: str
    prompt: str
    choices: List[str]
    created_at: str = field(default_factory=_now_iso)
    awaiting_response: bool = True


@dataclass
class StreamSnapshot:
    stream_id: str
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    phase: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class PhaseHistoryEntry:
    phase: str
    completed_at: str
    summary: Optional[str] = None


@dataclass
class BatchConversationState:
    batch_id: str
    session_id: Optional[str] = None
    active_phase: Optional[str] = None
    phase_history: List[PhaseHistoryEntry] = field(default_factory=list)
    goals: List[Dict[str, Any]] = field(default_factory=list)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    synthesized_goal: Optional[Dict[str, Any]] = None
    stream_snapshot: Optional[StreamSnapshot] = None
    procedural_prompt: Optional[ProceduralPromptState] = None
    deferred_messages: Deque[Tuple[str, str]] = field(default_factory=deque)
    conversation_messages: Dict[str, ConversationMessage] = field(default_factory=dict)
    conversation_order: Deque[str] = field(default_factory=lambda: deque(maxlen=100))
    known_constraints: List[str] = field(default_factory=list)
    last_context_refresh: str = field(default_factory=_now_iso)


@dataclass
class ConversationResult:
    status: Literal["ok", "queued"]
    user_message_id: str
    assistant_message_id: Optional[str] = None
    reply: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    context_bundle: Optional[Dict[str, Any]] = None
    queued_reason: Optional[str] = None


class ConversationContextService:
    """
    Tracks per-batch research context and orchestrates conversational replies.
    """

    def __init__(self):
        self._states: Dict[str, BatchConversationState] = {}
        self._lock = threading.RLock()
        self._llm_client: Optional[QwenStreamingClient] = None
        self._phase_playbook: Dict[str, str] = {
            "phase0": "Phase 0 focuses on validating scraped data quality, coverage, and readiness.",
            "phase0_5": "Phase 0.5 synthesizes an initial research role and tone calibration.",
            "phase1": "Phase 1 discovers research goals and clarifies investigative angles.",
            "phase2": "Phase 2 finalizes research goals into a unified comprehensive topic.",
            "phase3": "Phase 3 executes the plan step-by-step, extracting findings and evidence.",
            "phase4": "Phase 4 compiles final reports, ensuring coherence and coverage.",
            "research": "Research mode coordinates streaming outputs across active phases.",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_state(self, batch_id: str) -> BatchConversationState:
        with self._lock:
            if batch_id not in self._states:
                self._states[batch_id] = BatchConversationState(batch_id=batch_id)
            return self._states[batch_id]

    def ensure_batch(self, batch_id: str):
        self._get_state(batch_id)

    def _ensure_llm_client(self) -> QwenStreamingClient:
        if self._llm_client is None:
            if QwenStreamingClient is None:
                raise RuntimeError("QwenStreamingClient unavailable; cannot initialize conversation client.")
            self._llm_client = QwenStreamingClient()
        return self._llm_client

    def _add_message(self, batch_id: str, message: ConversationMessage):
        state = self._get_state(batch_id)
        with self._lock:
            state.conversation_messages[message.id] = message
            if message.id in state.conversation_order:
                state.conversation_order.remove(message.id)
            state.conversation_order.append(message.id)

    def _update_message_status(
        self,
        batch_id: str,
        message_id: str,
        status: MessageStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        state = self._get_state(batch_id)
        with self._lock:
            message = state.conversation_messages.get(message_id)
            if not message:
                logger.warning(f"Conversation message {message_id} not found for batch {batch_id}")
                return None
            message.status = status
            message.updated_at = _now_iso()
            if metadata:
                message.metadata.update(metadata)
            return message

    # ------------------------------------------------------------------
    # Context capture methods (invoked by WebSocketUI)
    # ------------------------------------------------------------------
    def record_phase_change(self, batch_id: str, phase: str, message: Optional[str] = None):
        state = self._get_state(batch_id)
        with self._lock:
            previous_phase = state.active_phase
            if previous_phase and previous_phase != phase:
                state.phase_history.append(
                    PhaseHistoryEntry(phase=previous_phase, completed_at=_now_iso(), summary=message)
                )
            state.active_phase = phase
            state.last_context_refresh = _now_iso()

    def set_session_id(self, batch_id: str, session_id: Optional[str]):
        state = self._get_state(batch_id)
        with self._lock:
            state.session_id = session_id
            state.last_context_refresh = _now_iso()

    def record_goals(self, batch_id: str, goals: List[Dict[str, Any]]):
        state = self._get_state(batch_id)
        with self._lock:
            state.goals = goals or []
            state.last_context_refresh = _now_iso()

    def record_plan(self, batch_id: str, plan: List[Dict[str, Any]]):
        state = self._get_state(batch_id)
        with self._lock:
            state.plan = plan or []
            state.last_context_refresh = _now_iso()

    def record_synthesized_goal(self, batch_id: str, synthesized_goal: Dict[str, Any]):
        state = self._get_state(batch_id)
        with self._lock:
            state.synthesized_goal = synthesized_goal or None
            state.last_context_refresh = _now_iso()

    def start_stream(self, batch_id: str, stream_id: str, phase: Optional[str], metadata: Optional[Dict[str, Any]]):
        state = self._get_state(batch_id)
        with self._lock:
            state.stream_snapshot = StreamSnapshot(
                stream_id=stream_id,
                metadata=metadata or {},
                phase=phase,
            )

    def append_stream_token(self, batch_id: str, stream_id: str, token: str):
        state = self._get_state(batch_id)
        with self._lock:
            if state.stream_snapshot and state.stream_snapshot.stream_id == stream_id:
                state.stream_snapshot.content += token
                state.stream_snapshot.updated_at = _now_iso()

    def end_stream(self, batch_id: str, stream_id: str):
        state = self._get_state(batch_id)
        with self._lock:
            if state.stream_snapshot and state.stream_snapshot.stream_id == stream_id:
                state.stream_snapshot.updated_at = _now_iso()

    def record_procedural_prompt(self, batch_id: str, prompt_id: str, prompt: str, choices: Optional[List[str]]):
        state = self._get_state(batch_id)
        with self._lock:
            state.procedural_prompt = ProceduralPromptState(
                prompt_id=prompt_id,
                prompt=prompt,
                choices=choices or [],
            )
            state.last_context_refresh = _now_iso()

    # ------------------------------------------------------------------
    # Context bundle generation
    # ------------------------------------------------------------------
    def _format_goals(self, goals: List[Dict[str, Any]]) -> str:
        if not goals:
            return "暂无研究目标。"
        lines = []
        for goal in goals[:6]:
            text = goal.get("goal_text") or goal.get("goal") or ""
            if not text:
                continue
            uses = goal.get("uses") or []
            uses_str = f"（用途: {', '.join(uses)}）" if uses else ""
            lines.append(f"- {text}{uses_str}")
        return "\n".join(lines) if lines else "暂无研究目标。"

    def _format_plan(self, plan: List[Dict[str, Any]]) -> str:
        if not plan:
            return "暂无研究计划。"
        lines = []
        for step in plan[:6]:
            step_id = step.get("step_id")
            goal = step.get("goal") or "未指定目标"
            required = step.get("required_data")
            chunk = step.get("chunk_strategy")
            detail_parts = []
            if required:
                detail_parts.append(f"数据: {required}")
            if chunk:
                detail_parts.append(f"策略: {chunk}")
            details = f" ({'; '.join(detail_parts)})" if detail_parts else ""
            lines.append(f"- 步骤 {step_id}: {goal}{details}")
        return "\n".join(lines)

    def _format_phase_history(self, history: List[PhaseHistoryEntry]) -> str:
        if not history:
            return ""
        lines = []
        for entry in history[-6:]:
            summary = entry.summary or "完成阶段无额外摘要。"
            lines.append(f"- {entry.phase} ({entry.completed_at}): {summary}")
        return "\n".join(lines)

    def _format_conversation_history(self, batch_id: str, limit: int = 5) -> List[Dict[str, str]]:
        state = self._get_state(batch_id)
        with self._lock:
            ordered_ids = list(state.conversation_order)[-limit:]
            history = []
            for message_id in ordered_ids:
                message = state.conversation_messages.get(message_id)
                if not message:
                    continue
                history.append(
                    {
                        "role": message.role,
                        "content": message.content,
                        "status": message.status,
                        "timestamp": message.created_at,
                    }
                )
        return history

    def build_context_bundle(self, batch_id: str) -> Dict[str, Any]:
        state = self._get_state(batch_id)
        with self._lock:
            active_phase = state.active_phase or "research"
            session_metadata = {
                "batch_id": batch_id,
                "session_id": state.session_id,
                "active_phase": active_phase,
                "procedural_prompt_active": state.procedural_prompt is not None,
                "known_constraints": state.known_constraints,
            }
            playbook_excerpt = self._phase_playbook.get(active_phase, "")
            completed_summary = self._format_phase_history(state.phase_history)
            stream_snapshot = None
            if state.stream_snapshot:
                stream_snapshot = {
                    "stream_id": state.stream_snapshot.stream_id,
                    "phase": state.stream_snapshot.phase,
                    "content": state.stream_snapshot.content[-1200:],
                    "metadata": state.stream_snapshot.metadata,
                    "updated_at": state.stream_snapshot.updated_at,
                }
            conversation_recent = self._format_conversation_history(batch_id)

        bundle = {
            "session_metadata": session_metadata,
            "phase_playbook_excerpt": playbook_excerpt,
            "completed_phase_summaries": completed_summary,
            "active_stream_snapshot": stream_snapshot,
            "user_message_history": conversation_recent,
            "known_constraints": session_metadata["known_constraints"],
            "goals_outline": self._format_goals(state.goals),
            "plan_outline": self._format_plan(state.plan),
            "synthesized_goal": state.synthesized_goal,
        }
        return bundle

    def _render_context_for_prompt(self, context_bundle: Dict[str, Any]) -> str:
        sections = []
        metadata = context_bundle.get("session_metadata") or {}
        meta_lines = [
            f"Batch ID: {metadata.get('batch_id')}",
            f"Session ID: {metadata.get('session_id') or '未记录'}",
            f"Active Phase: {metadata.get('active_phase')}",
            f"Procedural Prompt Active: {metadata.get('procedural_prompt_active')}",
        ]
        sections.append("## Session Metadata\n" + "\n".join(meta_lines))

        playbook = context_bundle.get("phase_playbook_excerpt")
        if playbook:
            sections.append(f"## Phase Playbook Guidance\n{playbook}")

        goal_outline = context_bundle.get("goals_outline")
        if goal_outline:
            sections.append(f"## Current Goals\n{goal_outline}")

        plan_outline = context_bundle.get("plan_outline")
        if plan_outline:
            sections.append(f"## Current Plan\n{plan_outline}")

        completed = context_bundle.get("completed_phase_summaries")
        if completed:
            sections.append(f"## Completed Phase Summaries\n{completed}")

        stream_snapshot = context_bundle.get("active_stream_snapshot")
        if stream_snapshot:
            sections.append(
                "## Active Stream Snapshot\n"
                f"- Stream ID: {stream_snapshot.get('stream_id')}\n"
                f"- Phase: {stream_snapshot.get('phase')}\n"
                f"- Last Updated: {stream_snapshot.get('updated_at')}\n"
                "### Recent Content\n"
                f"{stream_snapshot.get('content')}"
            )

        history_entries = context_bundle.get("user_message_history") or []
        if history_entries:
            formatted_history = []
            for entry in history_entries:
                formatted_history.append(f"{entry['timestamp']} [{entry['role']}]: {entry['content']}")
            sections.append("## Recent Conversation\n" + "\n".join(formatted_history))

        constraints = context_bundle.get("known_constraints") or []
        if constraints:
            sections.append("## Known Constraints\n" + "\n".join(f"- {c}" for c in constraints))

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Conversation handling
    # ------------------------------------------------------------------
    async def handle_user_message(
        self,
        batch_id: str,
        message: str,
        *,
        session_id: Optional[str] = None,
    ) -> ConversationResult:
        message = (message or "").strip()
        if not message:
            raise ValueError("Message content must not be empty.")

        if session_id:
            self.set_session_id(batch_id, session_id)

        user_message = ConversationMessage(
            id=f"user-{uuid.uuid4().hex}",
            role="user",
            content=message,
            status="in_progress",
        )
        self._add_message(batch_id, user_message)

        state = self._get_state(batch_id)
        with self._lock:
            prompt_state = state.procedural_prompt
            if prompt_state and prompt_state.awaiting_response:
                state.deferred_messages.append((user_message.id, message))
                user_message.status = "queued"
                user_message.updated_at = _now_iso()
                logger.info(
                    f"Queued conversation message {user_message.id} for batch {batch_id} "
                    f"due to active procedural prompt {prompt_state.prompt_id}"
                )
                return ConversationResult(
                    status="queued",
                    user_message_id=user_message.id,
                    queued_reason="Procedural prompt awaiting user response.",
                )

        # No procedural prompt active, process immediately
        try:
            result = await self._process_message(batch_id, user_message.id, message)
            return result
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Conversation processing failed: {exc}", exc_info=True)
            self._update_message_status(batch_id, user_message.id, "error", {"error": str(exc)})
            raise

    async def _process_message(self, batch_id: str, user_message_id: str, message: str) -> ConversationResult:
        self._update_message_status(batch_id, user_message_id, "in_progress")
        context_bundle = self.build_context_bundle(batch_id)
        context_rendered = self._render_context_for_prompt(context_bundle)

        system_prompt = (
            "You are the Research Tool Copilot. Provide grounded, pragmatic feedback.\n"
            "Always cross-check the provided context before recommending actions.\n"
            "Highlight risks or blockers explicitly. If information is missing, state the gap."
        )
        developer_instruction = (
            "Adhere to the active research workflow. Respect current goals and plan.\n"
            "When users ask for changes that contradict locked decisions, suggest clarification steps."
        )

        user_content = (
            "### Context Bundle\n"
            f"{context_rendered}\n\n"
            "### User Query\n"
            f"{message}\n\n"
            "Respond with concise, context-aware guidance. Prefer bullet lists when listing actions."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": developer_instruction},
            {"role": "user", "content": user_content},
        ]

        llm_client = self._ensure_llm_client()
        loop = asyncio.get_running_loop()

        def _invoke() -> Tuple[str, Dict[str, Any]]:
            tokens: List[str] = []
            for chunk in llm_client.stream_completion(messages, temperature=0.4, max_tokens=800):
                tokens.append(chunk)
            reply_text = "".join(tokens).strip()
            metadata = llm_client.last_call_metadata or {}
            usage = getattr(llm_client, "usage", None) or {}
            metadata = {**metadata, "usage": usage}
            return reply_text, metadata

        reply_text, metadata = await loop.run_in_executor(None, _invoke)

        self._update_message_status(batch_id, user_message_id, "completed", {"llm": "qwen3-max"})

        assistant_message = ConversationMessage(
            id=f"assistant-{uuid.uuid4().hex}",
            role="assistant",
            content=reply_text,
            status="completed",
            metadata={"in_reply_to": user_message_id},
        )
        self._add_message(batch_id, assistant_message)

        return ConversationResult(
            status="ok",
            user_message_id=user_message_id,
            assistant_message_id=assistant_message.id,
            reply=reply_text,
            metadata=metadata,
            context_bundle=context_bundle,
        )

    async def resolve_procedural_prompt(self, batch_id: str, prompt_id: Optional[str], response: Optional[str]):
        state = self._get_state(batch_id)
        with self._lock:
            prompt_state = state.procedural_prompt
            if prompt_state and prompt_state.prompt_id == prompt_id:
                prompt_state.awaiting_response = False
                state.procedural_prompt = None
                deferred = list(state.deferred_messages)
                state.deferred_messages.clear()
            else:
                deferred = []

        if not deferred:
            return []

        logger.info(
            f"Processing {len(deferred)} deferred conversation message(s) for batch {batch_id} "
            f"after resolving prompt {prompt_id}"
        )
        results = []
        for message_id, content in deferred:
            try:
                result = await self._process_message(batch_id, message_id, content)
                results.append(result)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"Deferred conversation processing failed for {message_id}: {exc}", exc_info=True)
                self._update_message_status(batch_id, message_id, "error", {"error": str(exc)})
        return results

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------
    def get_conversation_messages(self, batch_id: str) -> List[Dict[str, Any]]:
        state = self._get_state(batch_id)
        with self._lock:
            ordered_ids = list(state.conversation_order)
            return [
                state.conversation_messages[mid].to_payload()
                for mid in ordered_ids
                if mid in state.conversation_messages
            ]

    def get_message_payload(self, batch_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        state = self._get_state(batch_id)
        with self._lock:
            message = state.conversation_messages.get(message_id)
            if not message:
                return None
            return message.to_payload()


__all__ = ["ConversationContextService", "ConversationResult"]

