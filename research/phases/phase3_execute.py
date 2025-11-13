"""Phase 3: Execute Research Plan."""

import json
import re
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional, Set, Iterable
from research.phases.base_phase import BasePhase
from research.data_loader import ResearchDataLoader
from research.prompts import compose_messages, load_schema
from research.prompts.context_formatters import format_research_role_for_context
from research.retrieval_handler import RetrievalHandler
from core.config import Config
from research.utils.marker_formatter import format_marker_overview
from research.retrieval.vector_retrieval_service import (
    VectorRetrievalService,
    RetrievalFilters,
    VectorSearchResult,
)
from research.embeddings.embedding_client import EmbeddingClient, EmbeddingConfig
from research.session import StepDigest


class Phase3Execute(BasePhase):
    """Phase 3: Execute research plan step by step."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_loader = ResearchDataLoader()
        # Track chunks for sequential processing (enhancement #1)
        self._chunk_tracker: Dict[int, List[Dict[str, Any]]] = {}
        # Load retrieval config
        cfg = Config()
        self._window_words = cfg.get_int("research.retrieval.window_words", 3000)
        self._window_overlap = cfg.get_int("research.retrieval.window_overlap_words", 400)
        self._max_windows = cfg.get_int("research.retrieval.max_windows_per_step", 8)
        # Optional per-step time budget (only enforced if explicitly configured)
        try:
            self._max_step_seconds = cfg.get("research.retrieval.max_seconds_per_step", None)
        except Exception:
            self._max_step_seconds = None
        # Sanity guard: avoid pathological overlap >= window size
        if isinstance(self._window_words, int) and isinstance(self._window_overlap, int):
            if self._window_overlap >= max(1, self._window_words):
                self.logger.warning(
                    f"Configured overlap ({self._window_overlap}) >= window size ({self._window_words}); adjusting to window_size//2"
                )
                self._window_overlap = max(1, self._window_words // 2)

        # New knobs for context retrieval flow
        self._max_followups = cfg.get_int("research.retrieval.max_followups_per_step", 2)
        self._min_chars_per_item = cfg.get_int("research.retrieval.min_chars_per_request_item", 400)
        self._max_chars_per_item = cfg.get_int("research.retrieval.max_chars_per_request_item", 4000)
        self._min_total_followup_chars = cfg.get_int("research.retrieval.min_total_followup_chars", 1500)
        self._max_total_followup_chars = cfg.get_int("research.retrieval.max_total_followup_chars", 20000)
        self._enable_cache = bool(cfg.get("research.retrieval.enable_cache", True))
        # Never truncate items flag (new: marker-based approach)
        self._never_truncate_items = cfg.get_bool("research.retrieval.never_truncate_items", True)
        # Max transcript chars (0 = no limit, let API handle token limits)
        self._max_transcript_chars = cfg.get_int("research.retrieval.max_transcript_chars", 0)
        # Vector-first routing controls
        self._vector_first_enabled = bool(cfg.get("research.retrieval.vector_first.enabled", True))
        self._vector_min_chars = cfg.get_int("research.retrieval.vector_first.min_appended_chars", 600)
        self._vector_window_cap = cfg.get_int("research.retrieval.vector_first.max_sequential_windows", 3)
        self._vector_block_chars = cfg.get_int("research.retrieval.vector_first.max_block_chars", 800)
        self._vector_top_k = cfg.get_int("research.retrieval.vector_first.top_k", 12)
        self._vector_max_rounds = cfg.get_int("research.retrieval.vector_first.max_rounds", 3)
        self._vector_debug_logs = bool(cfg.get("research.retrieval.vector_first.debug_logs", False))
        # Debug: log config loading (INFO level for troubleshooting)
        try:
            self.logger.info(
                f"[CONFIG] Phase3Execute loaded: window_words={self._window_words}, "
                f"window_overlap={self._window_overlap}, max_windows={self._max_windows}, "
                f"max_transcript_chars={self._max_transcript_chars} (0=no limit)"
            )
        except Exception:
            pass
        # Simple in-memory cache (per executor instance)
        self._retrieval_cache: Dict[str, str] = {}

        # Vector retrieval service
        try:
            self.vector_service: Optional[VectorRetrievalService] = VectorRetrievalService(config=cfg)
        except Exception as exc:
            self.logger.warning("Vector retrieval service unavailable: %s", exc)
            self.vector_service = None

        # Novelty enforcement controls
        self._novelty_enabled = bool(cfg.get("research.phase3.novelty.enforce", True))
        self._novelty_similarity_threshold = float(cfg.get("research.phase3.novelty.similarity_threshold", 0.82) or 0.82)
        self._keyword_overlap_threshold = float(cfg.get("research.phase3.novelty.keyword_overlap_threshold", 0.7) or 0.7)
        self._allow_revision_duplicates = bool(cfg.get("research.phase3.novelty.allow_revision_duplicates", True))
        self._digest_token_cap = cfg.get_int("research.phase3.novelty.digest_token_cap", 1800)

        def _cfg_int(path: str, default: int) -> int:
            try:
                return int(cfg.get(path, default) or default)
            except Exception:
                return default

        embedding_provider = (
            cfg.get("research.phase3.novelty.embedding.provider", None)
            or cfg.get("research.embeddings.provider", None)
            or "hash"
        )
        embedding_model = (
            cfg.get("research.phase3.novelty.embedding.model", None)
            or cfg.get("research.embeddings.model", None)
            or "text-embedding-v1"
        )
        embedding_dimension = _cfg_int("research.phase3.novelty.embedding.dimension", 768)
        embedding_batch_size = _cfg_int("research.phase3.novelty.embedding.batch_size", 16)
        embedding_timeout = _cfg_int("research.phase3.novelty.embedding.timeout", 45)
        embedding_base_url = cfg.get("research.phase3.novelty.embedding.base_url", None) or cfg.get(
            "research.embeddings.base_url", None
        )

        novelty_embedding_cfg = EmbeddingConfig(
            provider=str(embedding_provider),
            model=str(embedding_model),
            dimension=int(embedding_dimension or 768),
            batch_size=int(embedding_batch_size or 16),
            timeout=int(embedding_timeout or 45),
            base_url=embedding_base_url,
        )
        try:
            self._embedding_client: Optional[EmbeddingClient] = EmbeddingClient(novelty_embedding_cfg)
        except Exception as exc:
            self.logger.warning("Embedding client unavailable for novelty filtering: %s", exc)
            self._embedding_client = None

        # Telemetry per step
        self._step_stats: Dict[int, Dict[str, float]] = {}
        self._vector_seen_chunks: Dict[int, Set[str]] = defaultdict(set)
        self._vector_full_items: Dict[int, bool] = defaultdict(bool)
        self._shared_role_context: Dict[str, str] = {}
    
    def _has_vector_service(self) -> bool:
        return self.vector_service is not None and getattr(self.vector_service, "enabled", True)

    def execute(
        self,
        research_plan: List[Dict[str, Any]],
        batch_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute Phase 3: Execute research plan.
        
        Args:
            research_plan: List of plan steps
            batch_data: Loaded batch data
            
        Returns:
            Dict with execution results
        """
        self.logger.info(f"Phase 3: Executing {len(research_plan)} steps")
        
        # Reset telemetry for this run
        self._step_stats = {}
        self._vector_seen_chunks.clear()
        self._vector_full_items.clear()

        role_artifact = self.session.get_phase_artifact("phase0_5", {}) or {}
        research_role_obj = None
        if isinstance(role_artifact, dict):
            research_role_obj = role_artifact.get("research_role")
            if not research_role_obj:
                role_result = role_artifact.get("role_result")
                if isinstance(role_result, dict):
                    research_role_obj = role_result.get("research_role")
        role_context = format_research_role_for_context(research_role_obj)
        role_display = role_context.get("research_role_display", "")
        role_rationale = (role_context.get("research_role_rationale", "") or "").strip()
        if role_display:
            role_section_lines = [f"- 角色：{role_display}"]
            if role_rationale:
                role_section_lines.append(role_rationale)
        else:
            role_section_lines = ["未提供专属研究角色；默认以资深数据分析专家视角执行任务。"]
            role_rationale = ""
        shared_role_context = {
            "system_role_description": role_display or "资深数据分析专家",
            "research_role_rationale": role_rationale,
            "research_role_section": "\n".join(role_section_lines),
            "research_role_display": role_display,
        }
        self._shared_role_context = dict(shared_role_context)

        all_findings = []
        
        # Execute each step
        for step in research_plan:
            step_id = step.get("step_id")
            goal = step.get("goal")
            required_data = step.get("required_data")
            chunk_strategy = step.get("chunk_strategy", "all")
            
            self._init_step_stats(step_id)

            # Log step configuration and batch stats for debugging
            try:
                transcripts_count = sum(1 for d in batch_data.values() if d.get("transcript"))
                total_words = sum(len((d.get("transcript") or "").split()) for d in batch_data.values())
                total_items = len(batch_data)
                chunk_size = step.get("chunk_size", self._window_words)
                self.logger.info(
                    "[Step %s] Config: required_data=%s, strategy=%s, chunk_size=%s | "
                    "batch: items=%s, transcripts=%s, total_words=%s",
                    step_id, required_data, chunk_strategy, chunk_size, total_items, transcripts_count, total_words
                )
            except Exception:
                pass

            if self.progress_tracker:
                self.progress_tracker.start_step(step_id, goal)
            
            # Send progress update
            total_steps = len(research_plan)
            if hasattr(self, 'ui') and self.ui:
                self.ui.display_message(
                    f"正在执行步骤 {step_id}/{total_steps}: {goal[:50]}...",
                    "info"
                )
            
            try:
                chunk_size = step.get("chunk_size", self._window_words)
                if chunk_strategy == "sequential":
                    vector_attempted = False
                    vector_result: Optional[Dict[str, Any]] = None
                    if self._vector_first_enabled and self._has_vector_service():
                        vector_attempted = True
                        vector_result = self._attempt_vector_first(
                            step_id,
                            goal,
                            required_data,
                            batch_data,
                            step.get("required_content_items"),
                        )
                    if vector_result is not None:
                        finalized = self._finalize_step_output(step_id, goal, vector_result)
                        all_findings.append(finalized)
                        self._log_step_summary(step_id)
                        if self.progress_tracker:
                            self.progress_tracker.complete_step(step_id, finalized["findings"])
                        if hasattr(self, 'ui') and self.ui:
                            self.ui.display_message(
                                f"步骤 {step_id}/{total_steps} 执行完成",
                                "success"
                            )
                        continue

                    router_reason = "vector_insufficient" if vector_attempted else "chunk_strategy"
                    findings = self._execute_step_paged(
                        step_id,
                        goal,
                        batch_data,
                        required_data,
                        chunk_size,
                        router_reason=router_reason,
                    )
                    finalized = self._finalize_step_output(step_id, goal, findings)
                    all_findings.append(finalized)
                    if self.progress_tracker:
                        self.progress_tracker.complete_step(step_id, finalized["findings"])
                    
                    if hasattr(self, 'ui') and self.ui:
                        self.ui.display_message(
                            f"步骤 {step_id}/{total_steps} 执行完成",
                            "success"
                        )
                    
                    self._log_step_summary(step_id)
                else:
                    # Prepare data chunk with source tracking (enhancement #2)
                    data_chunk, source_info = self._prepare_data_chunk(
                        batch_data,
                        required_data,
                        chunk_strategy,
                        chunk_size
                    )
                    
                    # Get scratchpad for context
                    scratchpad_summary = self.session.get_scratchpad_summary()
                    
                    # Get previous chunks context if sequential (enhancement #1)
                    previous_chunks_context = self._get_previous_chunks_context(step_id)
                    
                    # Execute step
                    required_content_items = step.get("required_content_items", None)
                    findings = self._execute_step(
                        step_id,
                        goal,
                        data_chunk,
                        scratchpad_summary,
                        required_data,
                        chunk_strategy,
                        previous_chunks_context,
                        batch_data=batch_data,  # Pass batch_data for marker overview
                        required_content_items=required_content_items  # Pass required items
                    )
                    
                    # Update scratchpad and track findings
                    finalized = self._finalize_step_output(
                        step_id,
                        goal,
                        findings,
                        default_sources=source_info.get("link_ids", []),
                    )
                    all_findings.append(finalized)
                    
                    self._log_step_summary(step_id)

                    if self.progress_tracker:
                        self.progress_tracker.complete_step(step_id, finalized["findings"])
                    
                    # Send completion update
                    if hasattr(self, 'ui') and self.ui:
                        self.ui.display_message(
                            f"步骤 {step_id}/{len(research_plan)} 执行完成",
                            "success"
                        )
                
            except Exception as e:
                self.logger.error(f"Step {step_id} failed: {str(e)}")
                if self.progress_tracker:
                    self.progress_tracker.fail_step(step_id, str(e))
                raise
        
        result = {
            "completed_steps": len(all_findings),
            "findings": all_findings,
            "telemetry": self._step_stats,
        }
        
        self.logger.info(f"Phase 3 complete: Executed {len(all_findings)} steps")
        
        return result

    def _execute_step_paged(
        self,
        step_id: int,
        goal: str,
        batch_data: Dict[str, Any],
        required_data: str,
        chunk_size: int,
        *,
        overlap_words: int = None,
        max_windows: int = None,
        router_reason: str = "chunk_strategy",
    ) -> Dict[str, Any]:
        """Process large transcripts by paging through windows to avoid truncation."""
        if overlap_words is None:
            overlap_words = self._window_overlap
        if max_windows is None:
            max_windows = self._max_windows
        if self._vector_first_enabled and isinstance(self._vector_window_cap, int) and self._vector_window_cap > 0:
            max_windows = min(max_windows, max(1, self._vector_window_cap))
        # Build combined transcript once
        transcript_content, source_info = self._get_transcript_content(
            batch_data, "sequential", chunk_size
        )
        words = transcript_content.split()
        n = len(words)
        if n == 0:
            # Fallback to normal single-call path with whatever is available
            scratchpad_summary = self.session.get_scratchpad_summary()
            return self._execute_step(
                step_id,
                goal,
                transcript_content,
                scratchpad_summary,
                required_data,
                "all",
                None,
                batch_data=batch_data,  # Pass batch_data for marker overview
                required_content_items=None,
                usage_tag=f"phase3_step_{step_id}_fallback",
            )

        # Log paging plan
        try:
            effective_overlap = min(max(0, (overlap_words or 0)), max(0, chunk_size - 1))
            stride = max(1, chunk_size - effective_overlap)
            planned_windows = (n + stride - 1) // stride if stride > 0 else 1
            self.logger.info(
                f"[Step {step_id}] Paging: words={n}, chunk_size={chunk_size}, overlap={effective_overlap}, "
                f"max_windows={max_windows}, planned_windows≈{planned_windows}"
            )
        except Exception:
            pass

        self.logger.warning(
            "[PHASE3-FALLBACK] step=%s mode=sequential reason=%s goal='%s'",
            step_id,
            router_reason,
            goal[:80] if goal else "",
        )
        try:
            stats_snapshot = self._step_stats.get(step_id, {})
            self.logger.warning(
                "[PHASE3-ROUTER] step=%s action=sequential_fallback reason=%s windows_cap=%s vector_hits=%s appended_chars=%s",
                step_id,
                router_reason,
                max_windows,
                int(stats_snapshot.get("vector_hits", 0)),
                int(stats_snapshot.get("vector_appended_chars", 0)),
            )
        except Exception:
            pass

        # Initialize loop state
        window_start = 0
        windows_processed = 0
        aggregated_findings: Dict[str, Any] = {"summary": "", "points_of_interest": {}, "sources": source_info.get("link_ids", [])}
        insights_parts: List[str] = []
        overall_confidence: float = 0.0
        step_t0 = time.time()

        # Do not call progress_tracker per window; handle at the caller level
        while window_start < n and windows_processed < (max_windows or 8):
            window_end = min(n, window_start + chunk_size)
            window_text = " ".join(words[window_start:window_end])

            # Progress logging per window
            try:
                self.logger.info(
                    f"[Step {step_id}] Processing window {windows_processed+1} "
                    f"({window_start}-{window_end}/{n})"
                )
            except Exception:
                pass

            # Execute per-window analysis
            scratchpad_summary = self.session.get_scratchpad_summary()
            prev_ctx = self._get_previous_chunks_context(step_id)
            # Debug: log what we're passing to _execute_step
            try:
                self.logger.info(
                    f"[WINDOW_CALL] Step {step_id} Window {windows_processed+1}: calling _execute_step with "
                    f"required_data='{required_data}', chunk_strategy='sequential', "
                    f"window_text_len={len(window_text)}, max_transcript_chars={self._max_transcript_chars}"
                )
            except Exception:
                pass
            window_result = self._execute_step(
                step_id,
                goal,
                window_text,
                scratchpad_summary,
                required_data,
                "sequential",
                prev_ctx,
                batch_data=batch_data,  # Pass batch_data for marker overview
                required_content_items=None,
                allow_vector=False,
                usage_tag=f"phase3_step_{step_id}_window_{windows_processed+1}",
            )

            # Merge results into aggregated structures
            findings = window_result.get("findings", {})
            if not isinstance(findings, dict):
                findings = {"raw": findings}

            # Merge summary
            summary_piece = findings.get("summary") or window_result.get("insights", "")
            if summary_piece:
                insights_parts.append(str(summary_piece)[:1000])

            # Merge points_of_interest shallowly by concatenation of lists
            poi = findings.get("points_of_interest", {}) or {}
            agg_poi = aggregated_findings.setdefault("points_of_interest", {})
            if isinstance(poi, dict):
                for k, v in poi.items():
                    if isinstance(v, list):
                        agg_poi.setdefault(k, [])
                        agg_poi[k].extend(v[:10])  # cap per-window additions

            # Update sources
            if "sources" in findings and isinstance(findings["sources"], list):
                aggregated_findings["sources"] = list(
                    { *aggregated_findings.get("sources", []), *findings["sources"] }
                )

            # Persist scratchpad for this window without hitting disk each time
            self.session.update_scratchpad(
                step_id,
                findings,
                window_result.get("insights", ""),
                float(window_result.get("confidence", 0.5)),
                findings.get("sources", []),
                autosave=False,
            )

            # Track for sequential context
            self._track_chunk(step_id, window_text, window_result)

            # Advance window with overlap (with guards to ensure real progress)
            windows_processed += 1
            self._increment_step_stat(step_id, "sequential_windows", 1)
            if window_end >= n:
                break
            # Ensure overlap is strictly less than chunk size to avoid 1-word sliding
            effective_overlap = min(max(0, overlap_words or 0), max(0, chunk_size - 1))
            next_window_start = window_end - effective_overlap
            # Ensure we advance by a meaningful stride if overlap is too large
            if next_window_start <= window_start:
                minimal_stride = max(1, chunk_size // 2)
                next_window_start = window_start + minimal_stride
            window_start = min(next_window_start, n)

            # Enforce per-step time budget only if explicitly configured
            elapsed = time.time() - step_t0
            if isinstance(self._max_step_seconds, (int, float)) and self._max_step_seconds > 0 and elapsed > self._max_step_seconds:
                try:
                    self.logger.warning(
                        f"[Step {step_id}] Time budget exceeded after {elapsed:.1f}s; "
                        f"stopping paging early at window {windows_processed}."
                    )
                except Exception:
                    pass
                break

        # Persist accumulated window progress once for the step
        try:
            self.session.save()
            self.logger.debug(f"[PERF] Saved session after processing {windows_processed} windows for step {step_id}")
        except Exception as e:
            self.logger.warning(f"Failed to save session after step {step_id}: {e}")

        # Build aggregated return object
        aggregated_insights = "\n\n".join(insights_parts)
        return {
            "step_id": step_id,
            "findings": aggregated_findings,
            "insights": aggregated_insights[:2000],
            "confidence": overall_confidence or 0.6,
        }

    def _attempt_vector_first(
        self,
        step_id: int,
        goal: str,
        required_data: str,
        batch_data: Dict[str, Any],
        required_content_items: Optional[List[str]],
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt a vector-first execution round before falling back to sequential paging.
        """
        scratchpad_summary = self.session.get_scratchpad_summary()
        result = self._execute_step(
            step_id,
            goal,
            "",
            scratchpad_summary,
            required_data,
            "vector_first",
            None,
            batch_data=batch_data,
            required_content_items=required_content_items,
            usage_tag=f"phase3_step_{step_id}_vector_first",
        )
        if self._should_use_vector_result(step_id, result):
            self.logger.info(
                "[PHASE3-ROUTER] step=%s action=vector_first_success hits=%s appended_chars=%s",
                step_id,
                int(self._step_stats.get(step_id, {}).get("vector_hits", 0)),
                int(self._step_stats.get(step_id, {}).get("vector_appended_chars", 0)),
            )
            return result
        stats_snapshot = self._step_stats.get(step_id, {})
        still_missing = result.get("still_missing") if isinstance(result, dict) else None
        completion_reason = result.get("completion_reason") if isinstance(result, dict) else ""
        try:
            self.logger.warning(
                "[PHASE3-ROUTER] step=%s action=vector_first_fallback reason=insufficient_context hits=%s appended_chars=%s followup_turns=%s completion_reason=%s still_missing=%s",
                step_id,
                int(stats_snapshot.get("vector_hits", 0)),
                int(stats_snapshot.get("vector_appended_chars", 0)),
                int(stats_snapshot.get("vector_followup_turns", 0)),
                completion_reason or "",
                still_missing if isinstance(still_missing, list) else None,
            )
        except Exception:
            pass
        return None

    def _should_use_vector_result(self, step_id: int, result: Any) -> bool:
        if self._vector_full_items.get(step_id):
            try:
                self.logger.info(
                    "[PHASE3-ROUTER] step=%s treating vector result as success (full_content_item delivered)",
                    step_id,
                )
            except Exception:
                pass
            return True
        if not isinstance(result, dict):
            return False
        
        # CRITICAL: If result still has pending requests, it's incomplete - don't use it
        pending_requests = result.get("requests")
        if isinstance(pending_requests, list) and len(pending_requests) > 0:
            try:
                self.logger.warning(
                    "[PHASE3-ROUTER] step=%s rejecting incomplete result: %s pending requests not processed",
                    step_id,
                    len(pending_requests),
                )
            except Exception:
                pass
            return False
        
        stats = self._step_stats.get(step_id) or {}
        vector_hits = int(stats.get("vector_hits", 0))
        appended_chars = int(stats.get("vector_appended_chars", 0))
        if isinstance(self._vector_min_chars, int) and self._vector_min_chars > 0:
            if vector_hits > 0 and appended_chars < self._vector_min_chars:
                return False
        still_missing = result.get("still_missing")
        if isinstance(still_missing, list) and still_missing:
            if self._is_generic_missing_context(still_missing):
                try:
                    self.logger.info(
                        "[PHASE3-ROUTER] step=%s ignoring generic still_missing hints (%s)",
                        step_id,
                        len(still_missing),
                    )
                except Exception:
                    pass
            else:
                return False
        completion_reason = str(result.get("completion_reason", "") or "").lower()
        if completion_reason in {"missing_context", "need_more_context", "insufficient_context"}:
            return False
        findings = result.get("findings")
        if isinstance(findings, dict) and findings:
            return True
        if result.get("insights"):
            return True
        return vector_hits > 0

    def _is_generic_missing_context(self, still_missing: List[Dict[str, Any]]) -> bool:
        if not still_missing:
            return False
        generic_terms = [
            "full transcript",
            "entire transcript",
            "whole transcript",
            "完整转录",
            "完整內容",
            "完整内容",
            "全文",
            "全部内容",
            "more context",
        ]
        for item in still_missing:
            if isinstance(item, str):
                item = {"query": item}
            elif not isinstance(item, dict):
                return False
            parts: List[str] = []
            for key in ("reason", "details", "request", "description", "search_hint"):
                value = item.get(key)
                if isinstance(value, str):
                    parts.append(value)
            payload = " ".join(parts).lower()
            if not payload:
                return False
            if not any(term in payload for term in generic_terms):
                return False
        return True

    def _limit_block(self, text: str, *, max_chars: Optional[int] = None) -> str:
        if not isinstance(text, str):
            text = str(text or "")
        configured_limit = max_chars if isinstance(max_chars, int) and max_chars > 0 else 0
        default_block = self._vector_block_chars if isinstance(self._vector_block_chars, int) else 0
        item_limit = self._max_chars_per_item if isinstance(self._max_chars_per_item, int) else 0
        total_cap = self._max_total_followup_chars if isinstance(self._max_total_followup_chars, int) else 0
        candidates = [configured_limit, default_block, item_limit, total_cap]
        positive = [c for c in candidates if isinstance(c, int) and c > 0]
        limit = min(positive) if positive else 1500
        limit = max(300, limit)
        if len(text) <= limit:
            return text
        return text[: limit - 20].rstrip() + "\n...[内容截断]"

    def _summarize_vector_results(
        self,
        query: str,
        results: List[VectorSearchResult],
        *,
        max_chars: Optional[int] = None,
    ) -> str:
        if not results:
            return "(No semantic matches found)"
        limit = max_chars or self._vector_block_chars or 1500
        limit = max(400, limit)
        header = f"[Vector Evidence] query=\"{query[:80]}\""
        lines: List[str] = [header]
        used = len(header)

        grouped: Dict[str, List[VectorSearchResult]] = {}
        for res in results:
            grouped.setdefault(res.link_id, []).append(res)

        for link_id, group in grouped.items():
            top = sorted(group, key=lambda r: r.score, reverse=True)
            best = top[0]
            link_header = f"- link_id={link_id} score={best.score:.3f}"
            if used + len(link_header) + 1 > limit:
                break
            lines.append(link_header)
            used += len(link_header) + 1

            for res in top:
                snippet_raw = res.text_preview or ""
                snippet = re.sub(r"\s+", " ", snippet_raw).strip()
                if not snippet:
                    continue
                snippet = snippet[:280]
                metadata_bits: List[str] = []
                chunk_type = res.metadata.get("chunk_type")
                if chunk_type:
                    metadata_bits.append(str(chunk_type))
                chunk_index = res.metadata.get("chunk_index")
                if chunk_index is not None:
                    metadata_bits.append(f"idx={chunk_index}")
                meta_label = f"[{', '.join(metadata_bits)}]" if metadata_bits else ""
                bullet = f"    • {meta_label} {snippet}"
                if used + len(bullet) + 1 > limit:
                    break
                lines.append(bullet)
                used += len(bullet) + 1
            if used >= limit:
                break

        if used >= limit:
            lines.append("    • ...[更多匹配已截断]")

        return "\n".join(lines)

    def _finalize_step_output(
        self,
        step_id: int,
        goal: str,
        step_output: Dict[str, Any],
        *,
        default_sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        step_output["step_id"] = step_id
        processed_output = self._apply_novelty_filter(step_id, step_output)
        findings_data = processed_output.get("findings")
        if not isinstance(findings_data, dict):
            findings_data = {"raw": findings_data}
            processed_output["findings"] = findings_data
        sources = findings_data.get("sources")
        if not isinstance(sources, list):
            sources = list(default_sources or [])
        elif default_sources:
            sources = list({*sources, *default_sources})
        findings_data["sources"] = sources
        insights = processed_output.get("insights", "")
        confidence = float(processed_output.get("confidence", 0.0) or 0.0)
        self._persist_step_digest(step_id, goal, processed_output, sources)
        self.session.update_scratchpad(step_id, findings_data, insights, confidence, sources)
        return {"step_id": step_id, "findings": processed_output}

    def _persist_step_digest(
        self,
        step_id: int,
        goal: str,
        step_output: Dict[str, Any],
        sources: Optional[List[str]] = None,
    ) -> None:
        findings_data = step_output.get("findings", {}) or {}
        summary = str(findings_data.get("summary") or "").strip()
        poi_lines: List[str] = []
        text_units = self._collect_digest_text_units(findings_data)
        notable_evidence_entries: List[Dict[str, Any]] = []
        poi = findings_data.get("points_of_interest") or {}
        if isinstance(poi, dict):
            for key, values in poi.items():
                if not isinstance(values, list):
                    continue
                for entry in values:
                    primary_text = self._extract_entry_text(key, entry)
                    if primary_text:
                        poi_lines.append(f"{key}: {primary_text}")
                    if key == "notable_evidence" and isinstance(entry, dict):
                        evidence_payload = {
                            "description": entry.get("description") or entry.get("quote") or primary_text,
                            "quote": entry.get("quote"),
                            "source_link_id": entry.get("source_link_id"),
                        }
                        notable_evidence_entries.append(evidence_payload)
        if sources and not any(ev.get("source_link_id") for ev in notable_evidence_entries):
            notable_evidence_entries.append({"description": "参考来源", "source_link_id": ", ".join(sources)})

        digest = StepDigest(
            step_id=step_id,
            goal_text=goal or "",
            summary=summary,
            points_of_interest=poi_lines[:20],
            notable_evidence=notable_evidence_entries[:20],
            text_units=text_units[:128],
        )
        novelty_meta = step_output.get("novelty") or {}
        if isinstance(novelty_meta, dict) and novelty_meta.get("revision_note"):
            digest.revision_notes = str(novelty_meta["revision_note"])
        self.session.upsert_step_digest(digest, autosave=False)

    def _collect_digest_text_units(self, findings_data: Dict[str, Any]) -> List[str]:
        units: List[str] = []
        summary = findings_data.get("summary")
        if isinstance(summary, str) and summary.strip():
            units.append(summary.strip())
        for entry in self._enumerate_poi_entries(findings_data):
            text = entry.get("text")
            if text:
                units.append(text)
        return [u for u in units if isinstance(u, str) and u.strip()]

    def _apply_novelty_filter(self, step_id: int, step_output: Dict[str, Any]) -> Dict[str, Any]:
        if not self._novelty_enabled:
            return step_output
        findings_data = step_output.get("findings")
        if not isinstance(findings_data, dict):
            return step_output
        entries = self._enumerate_poi_entries(findings_data)
        candidate_count = len(entries)
        novelty_meta = step_output.setdefault("novelty", {})
        novelty_meta["candidate_count"] = candidate_count
        if candidate_count == 0:
            return step_output
        prior_units = self.session.get_digest_text_units_before(step_id)
        if not prior_units:
            self._increment_step_stat(step_id, "novelty_candidates", candidate_count)
            return step_output

        candidate_texts = [entry["text"] for entry in entries]
        prior_vecs: List[List[float]] = []
        candidate_vecs: List[List[float]] = []

        if self._embedding_client:
            try:
                combined_embeddings = self._embedding_client.embed_texts([*prior_units, *candidate_texts])
                expected = len(prior_units) + len(candidate_texts)
                if len(combined_embeddings) == expected:
                    prior_vecs = combined_embeddings[: len(prior_units)]
                    candidate_vecs = combined_embeddings[len(prior_units) :]
            except Exception as exc:
                self.logger.warning(
                    "[PHASE3-NOVELTY] step=%s embedding similarity failed (%s); falling back to keyword overlap only",
                    step_id,
                    exc,
                )
                prior_vecs = []
                candidate_vecs = []

        prior_keyword_bags = [self._build_keyword_bag(text) for text in prior_units]

        removals: Dict[str, Set[int]] = defaultdict(set)
        pruned_meta: List[Dict[str, Any]] = []

        for idx, entry in enumerate(entries):
            if entry.get("is_revision") and self._allow_revision_duplicates:
                continue

            best_sim = 0.0
            best_match_idx = -1
            if candidate_vecs:
                candidate_vec = candidate_vecs[idx]
                for p_idx, prior_vec in enumerate(prior_vecs):
                    sim = self._cosine_similarity(candidate_vec, prior_vec)
                    if sim > best_sim:
                        best_sim = sim
                        best_match_idx = p_idx

            keyword_score = 0.0
            match_text = ""
            if best_match_idx >= 0:
                match_text = prior_units[best_match_idx]
                keyword_score = self._keyword_overlap_score(
                    candidate_texts[idx],
                    match_text,
                    prior_keyword_bags[best_match_idx],
                )
            else:
                for p_idx, prior_text in enumerate(prior_units):
                    overlap = self._keyword_overlap_score(
                        candidate_texts[idx],
                        prior_text,
                        prior_keyword_bags[p_idx],
                    )
                    if overlap > keyword_score:
                        keyword_score = overlap
                        best_match_idx = p_idx
                        match_text = prior_text

            duplicate = False
            reasons: List[str] = []
            if best_sim >= self._novelty_similarity_threshold and best_match_idx >= 0:
                duplicate = True
                reasons.append(f"sim={best_sim:.3f}")
            if keyword_score >= self._keyword_overlap_threshold and best_match_idx >= 0:
                duplicate = True
                reasons.append(f"kw={keyword_score:.3f}")

            if not duplicate:
                continue

            removals[entry["category"]].add(entry["index"])
            pruned_meta.append(
                {
                    "category": entry["category"],
                    "text": entry["text"],
                    "matched_text": match_text,
                    "similarity": round(best_sim, 3),
                    "keyword_overlap": round(keyword_score, 3),
                    "reason": ", ".join(reasons) or "duplicate",
                }
            )

        duplicates_removed = sum(len(indices) for indices in removals.values())
        self._increment_step_stat(step_id, "novelty_candidates", candidate_count)
        if duplicates_removed:
            poi = findings_data.get("points_of_interest")
            if isinstance(poi, dict):
                for category, indices in removals.items():
                    values = poi.get(category)
                    if not isinstance(values, list):
                        continue
                    filtered = [item for i, item in enumerate(values) if i not in indices]
                    poi[category] = filtered
            novelty_meta["duplicates_removed"] = duplicates_removed
            novelty_meta["pruned"] = pruned_meta
            self._increment_step_stat(step_id, "novelty_duplicates_removed", duplicates_removed)
            self.logger.info(
                "[PHASE3-NOVELTY] step=%s pruned=%s/%s entries (sim>=%.2f | kw>=%.2f)",
                step_id,
                duplicates_removed,
                candidate_count,
                self._novelty_similarity_threshold,
                self._keyword_overlap_threshold,
            )
        else:
            novelty_meta["duplicates_removed"] = 0
            self.logger.info(
                "[PHASE3-NOVELTY] step=%s no duplicate entries detected (%s candidates)",
                step_id,
                candidate_count,
            )

        return step_output

    def _enumerate_poi_entries(self, findings_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        poi = findings_data.get("points_of_interest") or {}
        if not isinstance(poi, dict):
            return entries
        for category, values in poi.items():
            if not isinstance(values, list):
                continue
            for index, entry in enumerate(values):
                text = self._extract_entry_text(category, entry)
                if not text:
                    continue
                entries.append(
                    {
                        "category": category,
                        "index": index,
                        "value": entry,
                        "text": text.strip(),
                        "is_revision": self._is_revision_entry(entry),
                    }
                )
        return entries

    def _extract_entry_text(self, category: str, entry: Any) -> str:
        if isinstance(entry, str):
            return entry.strip()
        if isinstance(entry, dict):
            if category == "notable_evidence":
                quote = entry.get("quote")
                description = entry.get("description")
                if description and quote:
                    return f"{description}｜引述：{quote}"
                if description:
                    return str(description)
                if quote:
                    return str(quote)
            preferred_fields = [
                "claim",
                "description",
                "quote",
                "example",
                "topic",
                "insight",
                "summary",
                "question",
                "observation",
                "note",
                "text",
            ]
            for field in preferred_fields:
                value = entry.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _is_revision_entry(self, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        flags = [
            entry.get("is_revision"),
            entry.get("revision"),
            entry.get("revision_flag"),
            entry.get("update_reason"),
            entry.get("status"),
        ]
        for flag in flags:
            if isinstance(flag, str) and flag.lower() in {"true", "yes", "updated", "revised"}:
                return True
            if isinstance(flag, bool) and flag:
                return True
        text_fields = [
            entry.get("note"),
            entry.get("description"),
            entry.get("claim"),
            entry.get("quote"),
            entry.get("summary"),
        ]
        for text in text_fields:
            if isinstance(text, str) and any(keyword in text for keyword in ("修订", "更新", "更正", "revision", "update")):
                return True
        return False

    def _keyword_overlap_score(self, text_a: str, text_b: str, precomputed_bag_b: Optional[Set[str]] = None) -> float:
        if not self._keyword_overlap_threshold:
            return 0.0
        bag_a = self._build_keyword_bag(text_a)
        bag_b = precomputed_bag_b if precomputed_bag_b is not None else self._build_keyword_bag(text_b)
        if not bag_a or not bag_b:
            return 0.0
        intersection = len(bag_a & bag_b)
        normalizer = max(1, min(len(bag_a), len(bag_b)))
        return intersection / normalizer

    def _build_keyword_bag(self, text: str) -> Set[str]:
        if not isinstance(text, str):
            text = str(text or "")
        lowered = text.lower().strip()
        if not lowered:
            return set()
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", lowered)
        bag = {token for token in tokens if len(token) > 1}
        if not bag and len(lowered) > 2:
            bag = {lowered[i : i + 2] for i in range(len(lowered) - 1)}
        if not bag and lowered:
            bag = {lowered}
        return bag

    def _cosine_similarity(self, vec_a: Iterable[float], vec_b: Iterable[float]) -> float:
        a_list = list(vec_a)
        b_list = list(vec_b)
        if not a_list or not b_list or len(a_list) != len(b_list):
            length = min(len(a_list), len(b_list))
            if length == 0:
                return 0.0
            a_list = a_list[:length]
            b_list = b_list[:length]
        return sum(x * y for x, y in zip(a_list, b_list))
    
    def _prepare_data_chunk(
        self,
        batch_data: Dict[str, Any],
        required_data: str,
        chunk_strategy: str,
        chunk_size: int
    ) -> tuple[str, Dict[str, Any]]:
        """
        Prepare data chunk for analysis using transcript-anchored approach.
        Transcripts are primary anchors, comments are augmentation.
        
        Returns:
            Tuple of (data_chunk_string, source_info_dict)
        """
        source_info = {"link_ids": [], "source_types": []}
        
        if required_data == "previous_findings":
            return self.session.get_scratchpad_summary(), source_info
        
        # Migrate legacy data requirements to transcript-anchored approach
        required_data = self._migrate_legacy_required_data(required_data, batch_data)
        
        # Handle transcript-based data (primary anchor)
        if required_data in ["transcript", "transcript_with_comments"]:
            # Get transcript content (PRIMARY)
            transcript_content, transcript_source_info = self._get_transcript_content(
                batch_data, chunk_strategy, chunk_size
            )
            
            # Get comments content (AUGMENTATION) - only if explicitly requested
            comments_content = None
            comments_source_info = {"link_ids": [], "source_types": []}
            
            if required_data == "transcript_with_comments":
                comments_content, comments_source_info = self._get_comments_content(
                    batch_data, chunk_strategy, chunk_size
                )
            
            # Merge source info
            source_info["link_ids"] = list(set(
                transcript_source_info["link_ids"] + comments_source_info["link_ids"]
            ))
            source_info["source_types"] = list(set(
                transcript_source_info["source_types"] + comments_source_info["source_types"]
            ))
            
            # Structure combined chunk with clear hierarchy
            combined_chunk = self._structure_combined_chunk(
                transcript_content,
                comments_content,
                source_info
            )

            # Debug: report sizes and sources
            try:
                t_len = len(transcript_content or "")
                c_len = len(comments_content or "") if comments_content else 0
                self.logger.info(
                    "Prepared data chunk: transcript_len=%s, comments_len=%s, sources=%s",
                    t_len, c_len, len(source_info.get("link_ids", []))
                )
            except Exception:
                pass
            
            return combined_chunk, source_info
        
        # Legacy: comments-only (edge case - no transcripts available)
        elif required_data == "comments":
            self.logger.warning(
                "Processing comments-only step (no transcripts available). "
                "This is an edge case - consider using transcript_with_comments instead."
            )
            comments_content, comments_source_info = self._get_comments_content(
                batch_data, chunk_strategy, chunk_size
            )
            source_info = comments_source_info
            
            # Format as edge case with warning
            edge_case_chunk = (
                "⚠️ 警告: 无转录本数据，仅基于评论进行分析\n\n"
                "--------------------------------------------------------------------------------\n"
                "可用数据（评论）\n"
                "--------------------------------------------------------------------------------\n\n"
                + comments_content
            )
            return edge_case_chunk, source_info
        
        return "", source_info
    
    def _migrate_legacy_required_data(
        self, 
        required_data: str, 
        batch_data: Dict[str, Any]
    ) -> str:
        """
        Migrate legacy data requirements to transcript-anchored approach.
        
        Args:
            required_data: Original required_data value
            batch_data: Batch data to check for transcript availability
            
        Returns:
            Migrated required_data value
        """
        if required_data == "comments":
            # Check if transcripts available
            has_transcripts = any(
                data.get("transcript") for data in batch_data.values()
            )
            if has_transcripts:
                self.logger.info(
                    "Migrating comment-only step to transcript_with_comments "
                    "(transcripts available)"
                )
                return "transcript_with_comments"
            else:
                self.logger.warning(
                    "No transcripts available, using comments only (edge case)"
                )
                return "comments"  # Fallback for edge cases
        
        return required_data
    
    def _get_transcript_content(
        self,
        batch_data: Dict[str, Any],
        chunk_strategy: str,
        chunk_size: int
    ) -> tuple[str, Dict[str, Any]]:
        """
        Get transcript content as primary anchor.
        
        Returns:
            Tuple of (transcript_content_string, source_info_dict)
        """
        source_info = {"link_ids": [], "source_types": []}
        all_transcripts = []
        
        for link_id, data in batch_data.items():
            transcript = data.get("transcript", "")
            if transcript:
                all_transcripts.append(transcript)
                source_info["link_ids"].append(link_id)
                source_info["source_types"].append(data.get("source", "unknown"))
        
        if not all_transcripts:
            return "(无可用转录本数据)", source_info
        
        combined = " ".join(all_transcripts)
        
        # Apply chunking strategy
        if chunk_strategy == "sequential":
            words = combined.split()
            total_words = len(words)
            
            # Check if we need to chunk (only if larger than chunk_size)
            if total_words <= chunk_size:
                return combined, source_info
            
            # For sequential, return all and let plan handle chunking
            # In future, could return first chunk here
            return combined, source_info
        else:
            return combined, source_info
    
    def _get_comments_content(
        self,
        batch_data: Dict[str, Any],
        chunk_strategy: str,
        chunk_size: int
    ) -> tuple[str, Dict[str, Any]]:
        """
        Get comments content as augmentation.
        Uses engagement-based sampling for large comment sets.
        
        Returns:
            Tuple of (comments_content_string, source_info_dict)
        """
        source_info = {"link_ids": [], "source_types": []}
        all_comments = []  # Normalized to list of dicts with consistent structure
        
        for link_id, data in batch_data.items():
            comments = data.get("comments", [])
            if isinstance(comments, list) and comments:
                # Normalize all comments to standardized dict format
                # Scrapers now export consistent format, but handle legacy data for backward compatibility
                normalized_comments = []
                for c in comments:
                    if isinstance(c, str):
                        # Legacy YouTube format: string -> convert to dict
                        normalized_comments.append({
                            "content": c,
                            "likes": 0,
                            "replies": 0,
                            "source_link_id": link_id
                        })
                    elif isinstance(c, dict):
                        # Standard format (or legacy Bilibili): extract and ensure all fields present
                        content = c.get("content", "")
                        if content:
                            normalized_comments.append({
                                "content": content,
                                "likes": c.get("likes", 0),
                                "replies": c.get("replies", 0),  # Added in standardized format
                                "source_link_id": link_id
                            })
                
                all_comments.extend(normalized_comments)
        
        if not all_comments:
            return None, source_info
        
        # Now all_comments is guaranteed to be a list of dicts with consistent structure
        # Sample comments based on strategy
        if chunk_strategy == "random_sample" and len(all_comments) > chunk_size:
            import random
            sampled = random.sample(all_comments, chunk_size)
            comments_text = "\n".join([
                f"- [点赞:{c.get('likes', 0)}, 回复:{c.get('replies', 0)}] {c.get('content', '')}"
                for c in sampled
            ])
            sampled_sources = [c.get("source_link_id") for c in sampled]
            source_info["link_ids"] = list(set(sampled_sources))
        else:
            # Use all comments or engagement-based top selection
            # Sort by engagement (likes + replies/2) and take top N
            sorted_comments = sorted(
                all_comments,
                key=lambda x: x.get("likes", 0) + (x.get("replies", 0) / 2),
                reverse=True
            )
            # Limit to chunk_size if specified
            if chunk_size > 0 and chunk_size < len(sorted_comments):
                sorted_comments = sorted_comments[:chunk_size]
            
            comments_text = "\n".join([
                f"- [点赞:{c.get('likes', 0)}, 回复:{c.get('replies', 0)}] {c.get('content', '')}"
                for c in sorted_comments
            ])
            source_info["link_ids"] = list(set([
                c.get("source_link_id") for c in sorted_comments
            ]))
        
        source_info["source_types"] = [
            batch_data.get(link_id, {}).get("source", "unknown")
            for link_id in source_info["link_ids"]
        ]
        
        return comments_text, source_info
    
    def _structure_combined_chunk(
        self,
        transcript_content: str,
        comments_content: Optional[str],
        source_info: Dict[str, Any]
    ) -> str:
        """
        Structure data chunk with transcript as primary anchor,
        comments as augmentation.
        
        Args:
            transcript_content: Primary transcript content
            comments_content: Optional comments content for augmentation
            source_info: Source tracking information
            
        Returns:
            Formatted string with clear sections
        """
        parts = []
        
        # PRIMARY SECTION: Transcript content
        parts.append("=" * 80)
        parts.append("主要内容（转录本/文章）")
        parts.append("=" * 80)
        parts.append(transcript_content)
        
        # AUGMENTATION SECTION: Comments (if available)
        if comments_content:
            parts.append("\n\n")
            parts.append("-" * 80)
            parts.append("补充数据（评论）")
            parts.append("-" * 80)
            parts.append("以下评论数据可用于验证、补充情感反应或识别争议点：")
            parts.append("")
            parts.append(comments_content)
        else:
            # Note when comments are not available
            parts.append("\n\n")
            parts.append("(注: 无可用评论数据)")
        
        return "\n".join(parts)
    
    def _prepare_marker_overview_for_step(
        self,
        step_id: int,
        goal: str,
        batch_data: Dict[str, Any],
        required_content_items: Optional[List[str]] = None
    ) -> str:
        """
        Prepare marker overview for a step.
        
        Args:
            step_id: Step identifier
            goal: Step goal
            batch_data: Batch data with summaries
            required_content_items: Optional list of link_ids relevant to this step
            
        Returns:
            Formatted marker overview string
        """
        try:
            # Format marker overview for relevant content items
            marker_overview = format_marker_overview(
                batch_data,
                link_ids=required_content_items,
                max_items=None  # Show all relevant items
            )
            
            # Add step context
            overview_with_context = f"""**步骤 {step_id}: {goal}**

**相关内容的标记概览**

{marker_overview}

**已检索的完整内容**
(初始为空 - 将根据请求填充)

**检索能力说明**
你可以通过以下方式请求更多内容：
1. 请求完整内容项: 指定 link_id 和内容类型 (transcript/comments/both)
2. 基于标记检索: 指定相关标记，系统会检索包含该标记的完整上下文
3. 按话题检索: 指定话题领域，系统会检索相关内容

请分析可用的标记，然后：
- 如果需要更多上下文来完成分析，请明确请求
- 如果标记已足够，直接进行分析"""
            
            return overview_with_context
        except Exception as e:
            self.logger.warning(f"Failed to prepare marker overview for step {step_id}: {e}")
            return f"**步骤 {step_id}: {goal}**\n\n(无法加载标记概览)"
    
    def _safe_truncate_data_chunk(
        self,
        data_chunk: str,
        required_data: str,
        chunk_strategy: str
    ) -> str:
        """
        Truncate data chunk safely based on content type and strategy.
        
        Args:
            data_chunk: Full data chunk
            required_data: Type of data (transcript, comments, etc.)
            chunk_strategy: Chunking strategy used
            
        Returns:
            Safely truncated (or full) data chunk
        """
        data_len = len(data_chunk)
        
        # Debug logging (INFO level for troubleshooting)
        try:
            self.logger.info(
                f"[TRUNCATE_CHECK] required_data='{required_data}', "
                f"chunk_strategy='{chunk_strategy}', data_len={data_len}, "
                f"max_transcript_chars={self._max_transcript_chars}"
            )
        except Exception:
            pass
        
        # For transcript-based data
        if required_data in ["transcript", "transcript_with_comments"]:
            # Skip truncation for sequential strategy - window size already controls input
            if chunk_strategy == "sequential":
                try:
                    self.logger.info(
                        f"[TRUNCATE_SKIP] Sequential strategy detected, returning full chunk ({data_len} chars)"
                    )
                except Exception:
                    pass
                return data_chunk
            
            # Skip truncation if config is 0 (no limit) - let API handle token limits
            if self._max_transcript_chars == 0:
                try:
                    self.logger.info(
                        f"[TRUNCATE_SKIP] max_transcript_chars=0 (no limit), returning full chunk ({data_len} chars)"
                    )
                except Exception:
                    pass
                return data_chunk
            
            # Apply configured limit if set
            if self._max_transcript_chars > 0 and len(data_chunk) > self._max_transcript_chars:
                self.logger.warning(
                    f"Transcript chunk truncated from {len(data_chunk)} to {self._max_transcript_chars} chars "
                    f"(configured limit exceeded)"
                )
                return data_chunk[:self._max_transcript_chars] + "\n\n[注意: 内容被截断，可能遗漏部分细节]"
            return data_chunk
        
        # For comments-only, use moderate limit
        elif required_data == "comments":
            MAX_COMMENTS_CHARS = 15000
            if len(data_chunk) > MAX_COMMENTS_CHARS:
                self.logger.warning(
                    f"Comments chunk truncated from {len(data_chunk)} to {MAX_COMMENTS_CHARS} chars"
                )
                return data_chunk[:MAX_COMMENTS_CHARS] + "\n\n[注意: 评论内容被截断]"
            return data_chunk
        
        # Default: keep current limit for edge cases
        DEFAULT_LIMIT = 8000
        if len(data_chunk) > DEFAULT_LIMIT:
            return data_chunk[:DEFAULT_LIMIT] + "\n\n[注意: 内容被截断]"
        return data_chunk

    def _execute_step(
        self,
        step_id: int,
        goal: str,
        data_chunk: str,
        scratchpad_summary: str,
        required_data: str,
        chunk_strategy: str = "all",
        previous_chunks_context: Optional[str] = None,
        batch_data: Optional[Dict[str, Any]] = None,
        required_content_items: Optional[List[str]] = None,
        allow_vector: bool = True,
        usage_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a single step using two-stage workflow: context request then analysis generation."""
        safe_summary = scratchpad_summary if scratchpad_summary != "暂无发现。" else "暂无之前的发现。"
        safe_data_chunk = self._safe_truncate_data_chunk(data_chunk, required_data, chunk_strategy)
        digest_context = self.session.aggregate_step_digests(
            step_id,
            token_cap=self._digest_token_cap if isinstance(self._digest_token_cap, int) else None,
        )
        novelty_guidance = (
            "务必生成全新的观点或信息，禁止重复之前步骤的摘要或兴趣点。"
        )
        
        # Add previous chunks context for sequential chunking (enhancement #1)
        chunks_context_str = ""
        if previous_chunks_context and chunk_strategy == "sequential":
            chunks_context_str = f"\n\n**之前处理的数据块摘要**:\n{previous_chunks_context}\n"
        
        # Prepare marker overview if batch_data is available
        marker_overview = ""
        retrieved_content = ""  # Initially empty, will be populated by requests from Stage 1
        
        if batch_data:
            try:
                marker_overview = self._prepare_marker_overview_for_step(
                    step_id, goal, batch_data, required_content_items
                )
                self.logger.info(f"[Step {step_id}] Using marker overview (marker-first approach)")
            except Exception as e:
                self.logger.warning(f"Failed to prepare marker overview for step {step_id}: {e}")
                # Fallback to data_chunk if marker overview fails
                marker_overview = ""
        else:
            # Fallback: use truncated data_chunk if no batch_data
            self.logger.info(f"[Step {step_id}] Using data_chunk (no batch_data for markers)")
        
        user_guidance_context = self._build_user_feedback_context()
        # Get user intent fields for system prompt (includes user_guidance placeholder)
        user_intent = self._get_user_intent_fields(include_post_phase1_feedback=True)

        role_context = getattr(self, "_shared_role_context", {}) or {}
        context = {
            **role_context,
            "step_id": step_id,
            "goal": goal,
            "marker_overview": marker_overview,
            "data_chunk": safe_data_chunk if not marker_overview else "",  # Keep for backward compatibility
            "retrieved_content": retrieved_content,  # Will be populated by requests from Stage 1
            "scratchpad_summary": safe_summary,
            "previous_chunks_context": chunks_context_str,
            "user_guidance_context": user_guidance_context,
            "user_guidance": user_intent["user_guidance"],  # Required by system.md template
            "user_context": user_intent["user_context"],  # For consistency
            "cumulative_digest": digest_context,
            "novelty_guidance": novelty_guidance,
        }
        
        # ===================================================================
        # STAGE 1: Context Request (Request-Only)
        # ===================================================================
        self.logger.info(f"[PHASE3-TWO-STAGE] Step {step_id}: Starting Stage 1 - Context Request")
        if hasattr(self, 'ui') and self.ui:
            self.ui.display_message(f"正在请求上下文 (步骤 {step_id})...", "info")
        
        # Stage 1: Context Request
        context_request_messages = compose_messages("phase3_execute_context_request", context=context)
        
        # Time the Stage 1 API call
        stage1_start = time.time()
        stage1_tag = usage_tag or f"phase3_step_{step_id}_context_request"

        request_response = self._stream_with_callback(
            context_request_messages,
            usage_tag=stage1_tag,
            log_payload=True,
            payload_label=stage1_tag,
            stream_metadata={
                "component": "step_context_request",
                "phase_label": "3",
                "step_id": step_id,
                "goal": goal,
                "required_data": required_data,
                "chunk_strategy": chunk_strategy,
                "vector_enabled": bool(allow_vector),
            },
        )
        stage1_elapsed = time.time() - stage1_start
        self.logger.info(f"[TIMING] Stage 1 (Context Request) completed in {stage1_elapsed:.3f}s for Step {step_id}")
        
        # Parse Stage 1 response (requests only, no findings field)
        try:
            request_parsed = self._parse_context_request_response(request_response, step_id)
        except Exception as e:
            self.logger.error(f"[PHASE3-TWO-STAGE] Step {step_id}: Failed to parse context request response: {e}")
            # Fallback: create empty requests
            request_parsed = {
                "step_id": step_id,
                "requests": [],
                "insights": f"Parsing error: {str(e)}",
                    "confidence": 0.3,
            }
        
        # Extract requests from Stage 1
        requests = request_parsed.get("requests", [])
        if not isinstance(requests, list):
            requests = []
        
        self.logger.info(
            f"[PHASE3-TWO-STAGE] Step {step_id}: Stage 1 returned {len(requests)} requests"
        )

        # If requests exist, retrieve context
        if requests:
            self.logger.info(
                f"[PHASE3-TWO-STAGE] Step {step_id}: Retrieving context for {len(requests)} requests"
            )
            if hasattr(self, 'ui') and self.ui:
                self.ui.display_message(f"正在检索上下文 (步骤 {step_id})...", "info")
            
            retrieved_content = self._retrieve_context_for_requests(
                requests,
                batch_data=batch_data,
                step_id=step_id,
                allow_vector=allow_vector,
            )
            
            # Update context with retrieved content
            context["retrieved_content"] = retrieved_content
            
            self.logger.info(
                f"[PHASE3-TWO-STAGE] Step {step_id}: Retrieved {len(retrieved_content)} chars of context"
            )
        else:
            self.logger.info(
                f"[PHASE3-TWO-STAGE] Step {step_id}: No requests from Stage 1, proceeding with existing context"
            )
        
        # ===================================================================
        # STAGE 2: Analysis Generation (Findings-Only)
        # ===================================================================
        self.logger.info(f"[PHASE3-TWO-STAGE] Step {step_id}: Starting Stage 2 - Analysis Generation")
        if hasattr(self, 'ui') and self.ui:
            self.ui.display_message(f"正在生成分析 (步骤 {step_id})...", "info")
        
        # Stage 2: Analysis Generation
        analysis_messages = compose_messages("phase3_execute_analysis_generation", context=context)
        
        # Time the Stage 2 API call
        stage2_start = time.time()
        stage2_tag = usage_tag or f"phase3_step_{step_id}_analysis_generation"
        
        analysis_response = self._stream_with_callback(
            analysis_messages,
            usage_tag=stage2_tag,
            log_payload=True,
            payload_label=stage2_tag,
            stream_metadata={
                "component": "step_analysis_generation",
                "phase_label": "3",
                "step_id": step_id,
                "goal": goal,
                "required_data": required_data,
                "chunk_strategy": chunk_strategy,
                "vector_enabled": bool(allow_vector),
            },
        )
        stage2_elapsed = time.time() - stage2_start
        self.logger.info(f"[TIMING] Stage 2 (Analysis Generation) completed in {stage2_elapsed:.3f}s for Step {step_id}")
        
        # Parse Stage 2 response (findings only, no requests field)
        try:
            analysis_parsed = self._parse_analysis_generation_response(analysis_response, step_id)
        except Exception as e:
            self.logger.error(f"[PHASE3-TWO-STAGE] Step {step_id}: Failed to parse analysis generation response: {e}")
            # This is a critical error - we can't proceed without findings
            # Return error response
            return {
                "step_id": step_id,
                "findings": {
                    "summary": f"分析生成失败: {str(e)}",
                    "article": f"无法解析AI响应: {str(e)}",
                    "points_of_interest": {},
                    "analysis_details": {},
                },
                "insights": f"解析错误: {str(e)}",
                "confidence": 0.1,
                "requests": [],  # No requests in Stage 2
            }
        
        # Validate: analysis should not have requests (schema doesn't include it)
        if "requests" in analysis_parsed:
            self.logger.error(
                f"[PHASE3-TWO-STAGE] Step {step_id}: Analysis generation returned requests field, "
                f"which should not exist in the schema. This indicates a schema violation."
            )
            del analysis_parsed["requests"]
        
        # Ensure requests field is set to empty array for consistency
        analysis_parsed["requests"] = []
        
        self.logger.info(
            f"[PHASE3-TWO-STAGE] Step {step_id}: Stage 2 completed successfully with findings"
            )

        return analysis_parsed

    # ----------------------------- Enhanced Retrieval Loop -----------------------------
    def _run_followups_with_retrieval(
        self,
        step_id: int,
        base_messages: List[Dict[str, Any]],
        prior_response_text: str,
        prior_parsed: Dict[str, Any],
        initial_requests: List[Dict[str, Any]],
        batch_data: Optional[Dict[str, Any]] = None,
        *,
        base_usage_tag: Optional[str] = None,
        allow_vector: bool = True,
        vector_round_cap: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run up to N follow-up turns with normalized, deduped, cached retrieval and size controls."""
        retriever = RetrievalHandler()
        
        # Get batch_data from session if not provided
        if batch_data is None:
            try:
                batch_data = self.session.batch_data  # type: ignore[attr-defined]
            except AttributeError:
                batch_data = None

        if not base_usage_tag:
            base_usage_tag = f"phase3_step_{step_id}"

        def _normalize_request(req: Dict[str, Any]) -> Dict[str, Any]:
            # Support new request types
            normalized = {
                "id": str(req.get("id") or ""),
                "request_type": req.get("request_type", req.get("method", "keyword")),
                "content_type": req.get("content_type") or req.get("type") or "transcript",
                "source_link_id": req.get("source_link_id") or req.get("source") or "",
                "method": req.get("method") or "keyword",
                "parameters": req.get("parameters") or {},
            }
            if req.get("source_link_ids"):
                normalized["source_link_ids"] = req.get("source_link_ids")
            # Add new request type specific fields
            if req.get("request_type") == "full_content_item":
                normalized["content_types"] = req.get("content_types", ["transcript", "comments"])
            elif req.get("request_type") == "by_marker":
                normalized["marker_text"] = req.get("marker_text", "")
                normalized["context_window"] = req.get("context_window", 2000)
            elif req.get("request_type") == "by_topic":
                normalized["topic"] = req.get("topic", "")
                normalized["source_link_ids"] = req.get("source_link_ids", [])
                normalized["content_types"] = req.get("content_types", ["transcript", "comments"])
            elif req.get("request_type") == "selective_markers":
                normalized["marker_types"] = req.get("marker_types", [])
            return normalized

        def _req_key(req: Dict[str, Any]) -> str:
            import json
            norm = _normalize_request(req)
            return json.dumps(norm, sort_keys=True, ensure_ascii=False)

        def _augment_with_semantic(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if not allow_vector:
                return requests
            if not requests or not self._has_vector_service():
                return requests
            augmented: List[Dict[str, Any]] = []
            for req in requests:
                augmented.append(req)
                request_type = req.get("request_type") or req.get("method")
                if request_type in {"semantic", "vector"}:
                    continue
                params = req.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}
                query_candidates: List[str] = []
                keywords = params.get("keywords")
                if isinstance(keywords, list):
                    query_candidates.extend(str(k).strip() for k in keywords if k)
                elif isinstance(keywords, str):
                    query_candidates.append(keywords.strip())
                if params.get("query"):
                    query_candidates.append(str(params.get("query")).strip())
                for field in ("marker_text", "topic"):
                    value = req.get(field)
                    if value:
                        query_candidates.append(str(value).strip())
                # Remove empties
                query_candidates = [q for q in query_candidates if q]
                if not query_candidates:
                    continue
                semantic_req = dict(req)
                semantic_req["request_type"] = "semantic"
                semantic_req["method"] = "semantic"
                semantic_params = dict(params)
                semantic_params["query"] = " ".join(query_candidates)
                semantic_params.setdefault("top_k", self._vector_top_k)
                semantic_params.setdefault("context_window", params.get("context_window", 500))
                fallback_keywords = semantic_params.get("fallback_keywords") or query_candidates[:5]
                if isinstance(fallback_keywords, list):
                    semantic_params["fallback_keywords"] = [str(k) for k in fallback_keywords if k]
                else:
                    semantic_params["fallback_keywords"] = [str(fallback_keywords)]
                semantic_req["parameters"] = semantic_params
                source_link_id = semantic_req.get("source_link_id")
                if source_link_id and not semantic_req.get("source_link_ids"):
                    semantic_req["source_link_ids"] = [source_link_id]
                augmented.append(semantic_req)
            deduped: List[Dict[str, Any]] = []
            dedup_keys: set = set()
            for req in augmented:
                key = _req_key(req)
                if key in dedup_keys:
                    continue
                dedup_keys.add(key)
                deduped.append(_normalize_request(req))
            return deduped

        def _clip(text: str) -> str:
            if not isinstance(text, str):
                text = str(text or "")
            # Check never_truncate_items flag - never truncate if enabled
            if self._never_truncate_items:
                # Never truncate - return full content
                return text
            # Legacy truncation (only if flag is False)
            if self._max_chars_per_item and len(text) > self._max_chars_per_item:
                return text[: self._max_chars_per_item] + "\n[...截断...]"
            return text

        def _retrieve_block(req: Dict[str, Any]) -> str:
            key = _req_key(req)
            if self._enable_cache and key in self._retrieval_cache:
                return self._retrieval_cache[key]
            try:
                block = self._handle_retrieval_request(
                    _normalize_request(req),
                    retriever,
                    batch_data,
                    step_id=step_id,
                ) or ""
            except Exception as e:
                block = f"[Retrieval error] {e}"
            max_chars_override = None
            if req.get("request_type") == "full_content_item":
                max_chars_override = self._max_total_followup_chars or max(4000, (self._vector_block_chars or 800) * 4)
            block = self._limit_block(block, max_chars=max_chars_override)
            block = _clip(block)
            if self._enable_cache:
                self._retrieval_cache[key] = block
            return block

        # Normalize and dedupe initial requests
        seen_req_keys: set = set()
        pending: List[Dict[str, Any]] = []
        for r in initial_requests:
            k = _req_key(r)
            if k not in seen_req_keys:
                seen_req_keys.add(k)
                pending.append(_normalize_request(r))
        if pending:
            pending = _augment_with_semantic(pending)
        prev_req_keys: set = {_req_key(req) for req in pending}
        turn = 0
        current_messages = list(base_messages)
        last_response_text = prior_response_text
        last_parsed = prior_parsed

        configured_rounds = int(self._max_followups)
        max_rounds = vector_round_cap if vector_round_cap is not None else configured_rounds
        max_rounds = max(0, min(max_rounds, configured_rounds))

        while pending and (turn < max_rounds):
            turn += 1
            self._increment_step_stat(step_id, "vector_followup_turns", 1)

            if self._vector_debug_logs:
                try:
                    req_summaries = []
                    for req in pending:
                        req_summaries.append(
                            f"{req.get('request_type', req.get('method'))}:{req.get('content_type')}:{req.get('source_link_id') or 'all'}"
                        )
                    self.logger.info(
                        "[PHASE3-VECTOR-DEBUG] step=%s followup=%s pending_requests=%s descriptors=%s",
                        step_id,
                        turn,
                        len(pending),
                        req_summaries[:10],
                    )
                except Exception:
                    pass

            # Fetch all blocks
            blocks: List[str] = []
            total_chars = 0
            for req in pending:
                b = _retrieve_block(req)
                if b:
                    # Enforce min size: if too small, keep it but we will supplement
                    blocks.append(b)
                    total_chars += len(b)

            # If total is too small, optionally broaden by relaxing constraints (simple: include raw transcript excerpts)
            if allow_vector and total_chars < self._min_total_followup_chars:
                try:
                    self.logger.info(
                        f"[Step {step_id}] Follow-up {turn}: total appended chars {total_chars} < min {self._min_total_followup_chars}, broadening context"
                    )
                except Exception:
                    pass

            # Cap total size
            if self._max_total_followup_chars and total_chars > self._max_total_followup_chars:
                trimmed = []
                running = 0
                for b in blocks:
                    if running + len(b) > self._max_total_followup_chars:
                        break
                    trimmed.append(b)
                    running += len(b)
                blocks = trimmed

            appended_context = "\n\n".join(blocks) if blocks else "(No additional context retrieved)"
            self._increment_step_stat(step_id, "vector_appended_chars", len(appended_context))
            if any("type=full_content_item" in b for b in blocks):
                self._vector_full_items[step_id] = True

            if self._vector_debug_logs:
                try:
                    block_lengths = [len(b) for b in blocks]
                    self.logger.info(
                        "[PHASE3-VECTOR-DEBUG] step=%s followup=%s blocks=%s block_lengths=%s appended_len=%s",
                        step_id,
                        turn,
                        len(blocks),
                        block_lengths[:10],
                        len(appended_context),
                    )
                except Exception:
                    pass

            try:
                self.logger.info(
                    f"[Step {step_id}] Follow-up {turn}: appended_context_len={len(appended_context)} from {len(blocks)} blocks"
                )
            except Exception:
                pass

            followup_messages = [
                *current_messages,
                {"role": "assistant", "content": last_response_text},
                {
                    "role": "user",
                    "content": (
                        "以下是你请求的额外上下文（已去重并限制长度），请整合后完成分析。\n"
                        "- 若仍缺少关键信息，请一次性列出完整需求，避免重复请求。\n"
                        "- **重要**：无论源内容使用何种语言，所有输出必须使用中文。专业术语需提供跨语言引用（格式：中文术语（原文））。\n\n"
                        f"{appended_context}\n\n请给出最终的结构化输出（必须使用中文），并附上 completion_reason 与 still_missing 概要。"
                    ),
                },
            ]

            # Time follow-up API call
            followup_start = time.time()
            self.logger.info(f"[TIMING] Starting follow-up API call for Step {step_id} at {followup_start:.3f}")
            if hasattr(self, 'ui') and self.ui:
                self.ui.display_message(f"正在获取补充数据 (步骤 {step_id})...", "info")
            usage_before = {}
            if self._vector_debug_logs:
                try:
                    usage_before = self.client.get_usage_info() if getattr(self, "client", None) else {}
                except Exception:
                    usage_before = {}
            followup_tag = f"{base_usage_tag}_followup_{turn}"
            last_response_text = self._stream_with_callback(
                followup_messages,
                usage_tag=followup_tag,
                log_payload=True,
                payload_label=followup_tag,
                stream_metadata={
                    "component": "step_followup",
                    "phase_label": "3",
                    "step_id": step_id,
                    "followup_round": turn,
                    "vector_enabled": bool(allow_vector),
                },
            )
            followup_elapsed = time.time() - followup_start
            self.logger.info(f"[TIMING] Follow-up API call completed in {followup_elapsed:.3f}s for Step {step_id}")
            last_parsed = self._parse_phase3_response_forgiving(last_response_text, step_id)
            if self._vector_debug_logs:
                try:
                    usage_after = self.client.get_usage_info() if getattr(self, "client", None) else {}
                    delta_input = usage_after.get("input_tokens", 0) - usage_before.get("input_tokens", 0)
                    delta_output = usage_after.get("output_tokens", 0) - usage_before.get("output_tokens", 0)
                    self.logger.info(
                        "[PHASE3-VECTOR-DEBUG] step=%s followup=%s latency=%.3fs input_tokens=%s output_tokens=%s",
                        step_id,
                        turn,
                        followup_elapsed,
                        delta_input,
                        delta_output,
                    )
                except Exception:
                    pass

            # Prepare next-turn requests, dedupe and detect churn
            new_requests: List[Dict[str, Any]] = []
            if isinstance(last_parsed, dict) and last_parsed.get("requests"):
                for r in last_parsed["requests"]:
                    k = _req_key(r)
                    if k not in prev_req_keys:
                        prev_req_keys.add(k)
                        new_requests.append(_normalize_request(r))
            if allow_vector and hasattr(last_parsed, "get"):
                still_missing = last_parsed.get("still_missing")
                if isinstance(still_missing, list) and still_missing:
                    if self._vector_debug_logs:
                        try:
                            self.logger.info(
                                "[PHASE3-VECTOR-DEBUG] step=%s followup=%s still_missing_samples=%s",
                                step_id,
                                turn,
                                still_missing[:3],
                            )
                        except Exception:
                            pass
                    missing_reqs = self._convert_missing_context_to_requests(still_missing)
                    for r in missing_reqs:
                        k = _req_key(r)
                        if k not in prev_req_keys:
                            prev_req_keys.add(k)
                            new_requests.append(_normalize_request(r))

            # If no new requests or only duplicates, stop early
            if not new_requests:
                try:
                    self.logger.info(f"[Step {step_id}] Follow-up {turn}: no new requests or missing context; ending loop")
                except Exception:
                    pass
                break

            # Next turn
            if new_requests and allow_vector and self._has_vector_service():
                new_requests = _augment_with_semantic(new_requests)
            prev_req_keys.update(_req_key(req) for req in new_requests)
            pending = new_requests
            current_messages = followup_messages

        return last_parsed

    def _parse_phase3_response_forgiving(self, response_text: str, step_id: int) -> Dict[str, Any]:
        """Parse model response into the expected JSON shape with a forgiving fallback."""
        # CRITICAL: Handle None or empty response_text - must check BEFORE any operations
        if response_text is None:
            self.logger.error(f"[PHASE3-PARSE] response_text is None for step {step_id} - this should not happen!")
            return {
                "step_id": step_id,
                "findings": {"raw_analysis": "No response received from API"},
                "insights": "No response received from API",
                "confidence": 0.3,
                "requests": [],
            }
        
        if not isinstance(response_text, str):
            self.logger.warning(f"[PHASE3-PARSE] response_text is not a string for step {step_id}: {type(response_text)}")
            # Try to convert to string, but also try to extract requests if it's a dict
            if isinstance(response_text, dict):
                extracted_requests = response_text.get("requests", [])
                if isinstance(extracted_requests, list) and len(extracted_requests) > 0:
                    self.logger.info(f"[PHASE3-PARSE] Extracted {len(extracted_requests)} requests from dict response")
                    return {
                        "step_id": step_id,
                        "findings": None,
                        "insights": str(response_text.get("insights", ""))[:500],
                        "confidence": float(response_text.get("confidence", 0.5)),
                        "requests": extracted_requests,
                    }
            return {
                "step_id": step_id,
                "findings": {"raw_analysis": str(response_text)},
                "insights": str(response_text)[:500],
                "confidence": 0.3,
                "requests": [],
            }
        
        if not response_text.strip():
            self.logger.warning(f"[PHASE3-PARSE] Empty response_text for step {step_id}")
            return {
                "step_id": step_id,
                "findings": {"raw_analysis": "Empty response received"},
                "insights": "Empty response received",
                "confidence": 0.3,
                "requests": [],
            }
        
        # Store original response_text for request extraction in case parsing fails
        original_response = response_text
        
        try:
            parsed = self.client.parse_json_from_stream(iter([response_text]))
            # Handle None or non-dict returns from parse_json_from_stream
            if parsed is None or not isinstance(parsed, dict):
                # Treat as parsing failure, fall through to exception handler
                raise ValueError(f"parse_json_from_stream returned {type(parsed).__name__}, expected dict")
            
            # Auto-fill missing required fields to be forgiving
            if "step_id" not in parsed:
                parsed["step_id"] = step_id
            
            # Ensure requests and missing_context are lists
            if "requests" not in parsed or not isinstance(parsed.get("requests"), list):
                parsed["requests"] = []
            if "missing_context" not in parsed or not isinstance(parsed.get("missing_context"), list):
                parsed["missing_context"] = []
            
            # Check if there are any requests
            has_requests = (
                (parsed.get("requests") and len(parsed["requests"]) > 0) or
                (parsed.get("missing_context") and len(parsed["missing_context"]) > 0)
            )
            
            # Handle findings conditionally:
            # - If requests exist, allow findings to be null/omitted
            # - If no requests, ensure findings is a dict
            if has_requests:
                # When requests exist, allow findings to be null or omitted
                if "findings" not in parsed:
                    parsed["findings"] = None
                elif parsed.get("findings") is not None and not isinstance(parsed.get("findings"), dict):
                    # If findings is provided but not null/dict, set to null when requests exist
                    parsed["findings"] = None
            else:
                # When no requests, ensure findings is a dict
                if "findings" not in parsed or not isinstance(parsed.get("findings"), dict):
                    parsed["findings"] = parsed.get("findings", {}) if isinstance(parsed.get("findings"), dict) else {}
            
            if "insights" not in parsed or not isinstance(parsed.get("insights"), str):
                parsed["insights"] = str(parsed.get("insights", ""))
            if "confidence" not in parsed or not isinstance(parsed.get("confidence"), (int, float)):
                parsed["confidence"] = 0.6
            self._validate_phase3_schema(parsed)
            return parsed
        except Exception as e:
            self.logger.warning(f"[PHASE3-PARSE] JSON parsing error for step {step_id}: {e}")
            import re
            # Use original_response which we know is a valid string
            response_to_parse = original_response
            # Safety check: ensure we have a valid string to work with
            if not response_to_parse or not isinstance(response_to_parse, str):
                self.logger.error(f"[PHASE3-PARSE] original_response is invalid in exception handler for step {step_id}: {type(response_to_parse)}")
                return {
                    "step_id": step_id,
                    "findings": {"raw_analysis": str(response_to_parse) if response_to_parse else "No response received"},
                    "insights": str(response_to_parse)[:500] if response_to_parse else "No response received",
                    "confidence": 0.3,
                    "requests": [],
                }
            json_match = re.search(r'\{.*\}', response_to_parse, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    # Schema validation remains forgiving (extra fields allowed)
                    if isinstance(parsed, dict):
                        if "step_id" not in parsed:
                            parsed["step_id"] = step_id
                        
                        # Ensure requests and missing_context are lists
                        if "requests" not in parsed or not isinstance(parsed.get("requests"), list):
                            parsed["requests"] = []
                        if "missing_context" not in parsed or not isinstance(parsed.get("missing_context"), list):
                            parsed["missing_context"] = []
                        
                        # Check if there are any requests
                        has_requests = (
                            (parsed.get("requests") and len(parsed["requests"]) > 0) or
                            (parsed.get("missing_context") and len(parsed["missing_context"]) > 0)
                        )
                        
                        # Handle findings conditionally:
                        # - If requests exist, allow findings to be null/omitted
                        # - If no requests, ensure findings is a dict
                        if has_requests:
                            # When requests exist, allow findings to be null or omitted
                            if "findings" not in parsed:
                                parsed["findings"] = None
                            elif parsed.get("findings") is not None and not isinstance(parsed.get("findings"), dict):
                                # If findings is provided but not null/dict, set to null when requests exist
                                parsed["findings"] = None
                        else:
                            # When no requests, ensure findings is a dict
                            if "findings" not in parsed or not isinstance(parsed.get("findings"), dict):
                                parsed["findings"] = parsed.get("findings", {}) if isinstance(parsed.get("findings"), dict) else {}
                        
                        if "insights" not in parsed or not isinstance(parsed.get("insights"), str):
                            parsed["insights"] = str(parsed.get("insights", ""))
                        if "confidence" not in parsed or not isinstance(parsed.get("confidence"), (int, float)):
                            parsed["confidence"] = 0.6
                        self._validate_phase3_schema(parsed)
                        return parsed
                except (json.JSONDecodeError, ValueError, TypeError) as json_err:
                    self.logger.warning(f"[PHASE3-PARSE] Fallback JSON parsing also failed for step {step_id}: {json_err}")
                    # CRITICAL: Even when parsing fails, try to extract requests from raw response
                    # This is essential - requests must not be lost!
                    extracted_requests = []
                    try:
                        # Find "requests": and extract the array using balanced bracket matching
                        requests_start = response_to_parse.find('"requests"')
                        if requests_start >= 0:
                            # Find the opening bracket after "requests"
                            bracket_start = response_to_parse.find('[', requests_start)
                            if bracket_start >= 0:
                                # Count brackets to find the matching closing bracket
                                bracket_count = 0
                                bracket_end = bracket_start
                                for i in range(bracket_start, len(response_to_parse)):
                                    if response_to_parse[i] == '[':
                                        bracket_count += 1
                                    elif response_to_parse[i] == ']':
                                        bracket_count -= 1
                                        if bracket_count == 0:
                                            bracket_end = i + 1
                                            break
                                if bracket_end > bracket_start:
                                    requests_str = response_to_parse[bracket_start:bracket_end]
                                    try:
                                        extracted_requests = json.loads(requests_str)
                                        if isinstance(extracted_requests, list):
                                            self.logger.info(f"[PHASE3-PARSE] Extracted {len(extracted_requests)} requests from raw response despite parsing failure")
                                    except json.JSONDecodeError:
                                        self.logger.warning(f"[PHASE3-PARSE] Found requests array but couldn't parse it: {requests_str[:100]}")
                    except Exception as extract_err:
                        self.logger.warning(f"[PHASE3-PARSE] Failed to extract requests from raw response: {extract_err}")
                    
                    # Return with extracted requests if found, otherwise empty
                    # CRITICAL: Always return requests if we found any, even if full parsing failed
                    if extracted_requests:
                        self.logger.info(f"[PHASE3-PARSE] Returning {len(extracted_requests)} extracted requests despite parsing failure for step {step_id}")
                    return {
                        "step_id": step_id,
                        "findings": {"raw_analysis": response_to_parse},
                        "insights": response_to_parse[:500],
                        "confidence": 0.5,
                        "requests": extracted_requests,  # Include extracted requests - CRITICAL!
                    }
            # Final fallback - no JSON found at all, but still try to extract requests
            extracted_requests = []
            try:
                # Find "requests": and extract the array using balanced bracket matching
                requests_start = response_to_parse.find('"requests"')
                if requests_start >= 0:
                    # Find the opening bracket after "requests"
                    bracket_start = response_to_parse.find('[', requests_start)
                    if bracket_start >= 0:
                        # Count brackets to find the matching closing bracket
                        bracket_count = 0
                        bracket_end = bracket_start
                        for i in range(bracket_start, len(response_to_parse)):
                            if response_to_parse[i] == '[':
                                bracket_count += 1
                            elif response_to_parse[i] == ']':
                                bracket_count -= 1
                                if bracket_count == 0:
                                    bracket_end = i + 1
                                    break
                        if bracket_end > bracket_start:
                            requests_str = response_to_parse[bracket_start:bracket_end]
                            try:
                                extracted_requests = json.loads(requests_str)
                                if isinstance(extracted_requests, list):
                                    self.logger.info(f"[PHASE3-PARSE] Extracted {len(extracted_requests)} requests from raw response (no JSON found) for step {step_id}")
                            except json.JSONDecodeError:
                                pass
            except Exception as final_err:
                self.logger.warning(f"[PHASE3-PARSE] Failed to extract requests in final fallback for step {step_id}: {final_err}")
            # CRITICAL: Always return requests if we found any, even if full parsing failed
            if extracted_requests:
                self.logger.info(f"[PHASE3-PARSE] Returning {len(extracted_requests)} extracted requests from final fallback for step {step_id}")
            return {
                "step_id": step_id,
                "findings": {"raw_analysis": response_to_parse},
                "insights": response_to_parse[:500],
                "confidence": 0.5,
                "requests": extracted_requests,  # Include extracted requests - CRITICAL!
            }

    def _parse_context_request_response(
        self, 
        response_text: str, 
        step_id: int
    ) -> Dict[str, Any]:
        """Parse context request response (requests only, no findings field in schema)."""
        # CRITICAL: Handle None or empty response_text
        if response_text is None:
            self.logger.error(f"[PHASE3-CONTEXT-REQUEST] response_text is None for step {step_id}")
            return {
                "step_id": step_id,
                "requests": [],
                "insights": "No response received from API",
                "confidence": 0.3,
            }
        
        if not isinstance(response_text, str):
            self.logger.warning(f"[PHASE3-CONTEXT-REQUEST] response_text is not a string for step {step_id}: {type(response_text)}")
            if isinstance(response_text, dict):
                requests = response_text.get("requests", [])
                return {
                    "step_id": step_id,
                    "requests": requests if isinstance(requests, list) else [],
                    "insights": str(response_text.get("insights", "")),
                    "confidence": float(response_text.get("confidence", 0.5)),
                }
            return {
                "step_id": step_id,
                "requests": [],
                "insights": "Invalid response format",
                "confidence": 0.3,
            }
        
        if not response_text.strip():
            self.logger.warning(f"[PHASE3-CONTEXT-REQUEST] Empty response_text for step {step_id}")
            return {
                "step_id": step_id,
                "requests": [],
                "insights": "Empty response received",
                "confidence": 0.3,
            }
        
        # Try to parse using context_request schema
        try:
            parsed = self.client.parse_json_from_stream(iter([response_text]))
            if parsed is None or not isinstance(parsed, dict):
                raise ValueError(f"parse_json_from_stream returned {type(parsed).__name__}, expected dict")
            
            # Validate: findings field should not exist in schema
            if "findings" in parsed:
                self.logger.warning(
                    f"[PHASE3-CONTEXT-REQUEST] Step {step_id}: Context request returned findings field, "
                    f"which is not in the schema. Removing it."
                )
                del parsed["findings"]
            
            # Ensure step_id is set
            if "step_id" not in parsed:
                parsed["step_id"] = step_id
            elif parsed["step_id"] != step_id:
                self.logger.warning(
                    f"[PHASE3-CONTEXT-REQUEST] Step {step_id}: step_id mismatch in response: {parsed['step_id']}"
                )
                parsed["step_id"] = step_id
            
            # Validate: must have requests (can be empty array)
            if "requests" not in parsed:
                parsed["requests"] = []
            elif not isinstance(parsed.get("requests"), list):
                self.logger.warning(
                    f"[PHASE3-CONTEXT-REQUEST] Step {step_id}: requests is not a list, converting to empty list"
                )
                parsed["requests"] = []
            
            # Optional fields
            if "insights" not in parsed:
                parsed["insights"] = ""
            elif not isinstance(parsed.get("insights"), str):
                parsed["insights"] = str(parsed.get("insights", ""))
            
            if "confidence" not in parsed:
                parsed["confidence"] = 0.5
            elif not isinstance(parsed.get("confidence"), (int, float)):
                parsed["confidence"] = 0.5
            
            # Validate schema
            schema = load_schema("phase3_execute_context_request", name="output_schema.json")
            if schema:
                # Basic validation - check required fields
                if "step_id" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'step_id'")
                if "requests" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'requests'")
            
            return parsed
            
        except Exception as e:
            self.logger.warning(f"[PHASE3-CONTEXT-REQUEST] JSON parsing error for step {step_id}: {e}")
            # Fallback: try to extract requests from raw response
            import re
            extracted_requests = []
            try:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict):
                        # Remove findings if present
                        if "findings" in parsed:
                            del parsed["findings"]
                        # Extract requests
                        if "requests" in parsed and isinstance(parsed.get("requests"), list):
                            extracted_requests = parsed["requests"]
                            self.logger.info(
                                f"[PHASE3-CONTEXT-REQUEST] Extracted {len(extracted_requests)} requests "
                                f"from fallback parsing for step {step_id}"
                            )
                        return {
                            "step_id": step_id,
                            "requests": extracted_requests,
                            "insights": str(parsed.get("insights", ""))[:500],
                            "confidence": float(parsed.get("confidence", 0.5)),
                        }
            except Exception as fallback_err:
                self.logger.warning(
                    f"[PHASE3-CONTEXT-REQUEST] Fallback parsing also failed for step {step_id}: {fallback_err}"
                )
            
            # Final fallback: try to extract requests array directly
            try:
                requests_start = response_text.find('"requests"')
                if requests_start >= 0:
                    bracket_start = response_text.find('[', requests_start)
                    if bracket_start >= 0:
                        bracket_count = 0
                        bracket_end = bracket_start
                        for i in range(bracket_start, len(response_text)):
                            if response_text[i] == '[':
                                bracket_count += 1
                            elif response_text[i] == ']':
                                bracket_count -= 1
                                if bracket_count == 0:
                                    bracket_end = i + 1
                                    break
                        if bracket_end > bracket_start:
                            requests_str = response_text[bracket_start:bracket_end]
                            extracted_requests = json.loads(requests_str)
                            if isinstance(extracted_requests, list):
                                self.logger.info(
                                    f"[PHASE3-CONTEXT-REQUEST] Extracted {len(extracted_requests)} requests "
                                    f"from raw response for step {step_id}"
                                )
            except Exception as extract_err:
                self.logger.warning(
                    f"[PHASE3-CONTEXT-REQUEST] Failed to extract requests from raw response for step {step_id}: {extract_err}"
                )
            
            return {
                "step_id": step_id,
                "requests": extracted_requests,
                "insights": response_text[:500] if response_text else "Parsing failed",
                "confidence": 0.3,
            }

    def _parse_analysis_generation_response(
        self,
        response_text: str,
        step_id: int
    ) -> Dict[str, Any]:
        """Parse analysis generation response (findings only, no requests field in schema)."""
        # CRITICAL: Handle None or empty response_text
        if response_text is None:
            self.logger.error(f"[PHASE3-ANALYSIS-GENERATION] response_text is None for step {step_id}")
            raise ValueError(f"Step {step_id}: Analysis generation must return findings, got None response")
        
        if not isinstance(response_text, str):
            self.logger.warning(f"[PHASE3-ANALYSIS-GENERATION] response_text is not a string for step {step_id}: {type(response_text)}")
            if isinstance(response_text, dict):
                findings = response_text.get("findings")
                if not isinstance(findings, dict) or not findings:
                    raise ValueError(
                        f"Step {step_id}: Analysis generation must return findings, "
                        f"got: {type(findings)}"
                    )
                # Remove requests if present
                result = {
                    "step_id": step_id,
                    "findings": findings,
                    "insights": str(response_text.get("insights", "")),
                    "confidence": float(response_text.get("confidence", 0.5)),
                }
                if "completion_reason" in response_text:
                    result["completion_reason"] = str(response_text.get("completion_reason", ""))
                if "requests" in result:
                    del result["requests"]
                return result
            raise ValueError(f"Step {step_id}: Analysis generation must return findings, got invalid response format")
        
        if not response_text.strip():
            self.logger.warning(f"[PHASE3-ANALYSIS-GENERATION] Empty response_text for step {step_id}")
            raise ValueError(f"Step {step_id}: Analysis generation must return findings, got empty response")
        
        # Try to parse using analysis_generation schema
        try:
            parsed = self.client.parse_json_from_stream(iter([response_text]))
            if parsed is None or not isinstance(parsed, dict):
                raise ValueError(f"parse_json_from_stream returned {type(parsed).__name__}, expected dict")
            
            # Validate: requests field should not exist in schema
            if "requests" in parsed:
                self.logger.warning(
                    f"[PHASE3-ANALYSIS-GENERATION] Step {step_id}: Analysis generation returned requests field, "
                    f"which is not in the schema. Removing it."
                )
                del parsed["requests"]
            
            # Ensure step_id is set
            if "step_id" not in parsed:
                parsed["step_id"] = step_id
            elif parsed["step_id"] != step_id:
                self.logger.warning(
                    f"[PHASE3-ANALYSIS-GENERATION] Step {step_id}: step_id mismatch in response: {parsed['step_id']}"
                )
                parsed["step_id"] = step_id
            
            # Validate: must have findings
            findings = parsed.get("findings")
            if not isinstance(findings, dict) or not findings:
                raise ValueError(
                    f"Step {step_id}: Analysis generation must return findings, "
                    f"got: {type(findings)}"
                )
            
            # Validate required fields
            if not findings.get("summary") or not findings.get("article"):
                raise ValueError(
                    f"Step {step_id}: Findings must include summary and article. "
                    f"Got summary={bool(findings.get('summary'))}, article={bool(findings.get('article'))}"
                )
            
            # Ensure required fields exist
            if "insights" not in parsed:
                parsed["insights"] = ""
            elif not isinstance(parsed.get("insights"), str):
                parsed["insights"] = str(parsed.get("insights", ""))
            
            if "confidence" not in parsed:
                parsed["confidence"] = 0.5
            elif not isinstance(parsed.get("confidence"), (int, float)):
                parsed["confidence"] = 0.5
            
            # Validate schema
            schema = load_schema("phase3_execute_analysis_generation", name="output_schema.json")
            if schema:
                # Basic validation - check required fields
                if "step_id" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'step_id'")
                if "findings" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'findings'")
                if "insights" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'insights'")
                if "confidence" not in parsed:
                    raise ValueError("Schema validation failed: missing required key 'confidence'")
            
            return parsed
            
        except Exception as e:
            self.logger.error(f"[PHASE3-ANALYSIS-GENERATION] JSON parsing error for step {step_id}: {e}")
            # Fallback: try to extract findings from raw response
            import re
            try:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict):
                        # Remove requests if present
                        if "requests" in parsed:
                            del parsed["requests"]
                        # Validate findings
                        findings = parsed.get("findings")
                        if not isinstance(findings, dict) or not findings:
                            raise ValueError(
                                f"Step {step_id}: Analysis generation must return findings, "
                                f"got: {type(findings)}"
                            )
                        if not findings.get("summary") or not findings.get("article"):
                            raise ValueError(
                                f"Step {step_id}: Findings must include summary and article"
                            )
                        # Ensure step_id
                        if "step_id" not in parsed:
                            parsed["step_id"] = step_id
                        return parsed
            except Exception as fallback_err:
                self.logger.error(
                    f"[PHASE3-ANALYSIS-GENERATION] Fallback parsing also failed for step {step_id}: {fallback_err}"
                )
            
            # If all parsing fails, raise error (we can't proceed without findings)
            raise ValueError(
                f"Step {step_id}: Failed to parse analysis generation response. "
                f"Expected findings object with summary and article. Error: {str(e)}"
            )

    def _retrieve_context_for_requests(
        self,
        requests: List[Dict[str, Any]],
        batch_data: Optional[Dict[str, Any]] = None,
        step_id: Optional[int] = None,
        allow_vector: bool = True,
    ) -> str:
        """Retrieve context for all requests and return as a single string."""
        if not requests:
            return ""
        
        retriever = RetrievalHandler()
        
        # Get batch_data from session if not provided
        if batch_data is None:
            try:
                batch_data = self.session.batch_data  # type: ignore[attr-defined]
            except AttributeError:
                batch_data = None
        
        if batch_data is None:
            self.logger.warning("[PHASE3-RETRIEVE] No batch_data available for retrieval")
            return "(No batch data available for retrieval)"
        
        def _normalize_request(req: Dict[str, Any]) -> Dict[str, Any]:
            """Normalize request to standard format."""
            normalized = {
                "id": str(req.get("id") or ""),
                "request_type": req.get("request_type", req.get("method", "keyword")),
                "content_type": req.get("content_type") or req.get("type") or "transcript",
                "source_link_id": req.get("source_link_id") or req.get("source") or "",
                "method": req.get("method") or "keyword",
                "parameters": req.get("parameters") or {},
            }
            if req.get("source_link_ids"):
                normalized["source_link_ids"] = req.get("source_link_ids")
            # Add new request type specific fields
            if req.get("request_type") == "full_content_item":
                normalized["content_types"] = req.get("content_types", ["transcript", "comments"])
            elif req.get("request_type") == "by_marker":
                normalized["marker_text"] = req.get("marker_text", "")
                normalized["context_window"] = req.get("context_window", 2000)
            elif req.get("request_type") == "by_topic":
                normalized["topic"] = req.get("topic", "")
                normalized["source_link_ids"] = req.get("source_link_ids", [])
                normalized["content_types"] = req.get("content_types", ["transcript", "comments"])
            elif req.get("request_type") == "selective_markers":
                normalized["marker_types"] = req.get("marker_types", [])
            return normalized
        
        def _req_key(req: Dict[str, Any]) -> str:
            """Generate a unique key for request deduplication."""
            import json
            norm = _normalize_request(req)
            return json.dumps(norm, sort_keys=True, ensure_ascii=False)
        
        def _augment_with_semantic(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """Augment requests with semantic search if vector service is available."""
            if not allow_vector:
                return requests
            if not requests or not self._has_vector_service():
                return requests
            augmented: List[Dict[str, Any]] = []
            for req in requests:
                augmented.append(req)
                request_type = req.get("request_type") or req.get("method")
                if request_type in {"semantic", "vector"}:
                    continue
                params = req.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}
                query_candidates: List[str] = []
                keywords = params.get("keywords")
                if isinstance(keywords, list):
                    query_candidates.extend(str(k).strip() for k in keywords if k)
                elif isinstance(keywords, str):
                    query_candidates.append(keywords.strip())
                if params.get("query"):
                    query_candidates.append(str(params.get("query")).strip())
                for field in ("marker_text", "topic"):
                    value = req.get(field)
                    if value:
                        query_candidates.append(str(value).strip())
                # Remove empties
                query_candidates = [q for q in query_candidates if q]
                if not query_candidates:
                    continue
                semantic_req = dict(req)
                semantic_req["request_type"] = "semantic"
                semantic_req["method"] = "semantic"
                semantic_params = dict(params)
                semantic_params["query"] = " ".join(query_candidates)
                semantic_params.setdefault("top_k", self._vector_top_k)
                semantic_params.setdefault("context_window", params.get("context_window", 500))
                fallback_keywords = semantic_params.get("fallback_keywords") or query_candidates[:5]
                if isinstance(fallback_keywords, list):
                    semantic_params["fallback_keywords"] = [str(k) for k in fallback_keywords if k]
                else:
                    semantic_params["fallback_keywords"] = [str(fallback_keywords)]
                semantic_req["parameters"] = semantic_params
                source_link_id = semantic_req.get("source_link_id")
                if source_link_id and not semantic_req.get("source_link_ids"):
                    semantic_req["source_link_ids"] = [source_link_id]
                augmented.append(semantic_req)
            return augmented
        
        def _clip(text: str) -> str:
            """Clip text to max length if needed."""
            if not isinstance(text, str):
                text = str(text or "")
            # Check never_truncate_items flag
            if self._never_truncate_items:
                return text
            # Legacy truncation (only if flag is False)
            if self._max_chars_per_item and len(text) > self._max_chars_per_item:
                return text[: self._max_chars_per_item] + "\n[...截断...]"
            return text
        
        def _retrieve_block(req: Dict[str, Any]) -> str:
            """Retrieve a single block of content for a request."""
            key = _req_key(req)
            if self._enable_cache and key in self._retrieval_cache:
                return self._retrieval_cache[key]
            try:
                block = self._handle_retrieval_request(
                    _normalize_request(req),
                    retriever,
                    batch_data,
                    step_id=step_id,
                ) or ""
            except Exception as e:
                self.logger.warning(f"[PHASE3-RETRIEVE] Error retrieving block for request {req.get('id', 'unknown')}: {e}")
                block = f"[Retrieval error] {e}"
            max_chars_override = None
            if req.get("request_type") == "full_content_item":
                max_chars_override = self._max_total_followup_chars or max(4000, (self._vector_block_chars or 800) * 4)
            block = self._limit_block(block, max_chars=max_chars_override)
            block = _clip(block)
            if self._enable_cache:
                self._retrieval_cache[key] = block
            return block
        
        # Normalize and dedupe requests
        seen_req_keys: set = set()
        normalized_requests: List[Dict[str, Any]] = []
        for r in requests:
            k = _req_key(r)
            if k not in seen_req_keys:
                seen_req_keys.add(k)
                normalized_requests.append(_normalize_request(r))
        
        # Augment with semantic if vector is enabled
        if allow_vector and self._has_vector_service():
            normalized_requests = _augment_with_semantic(normalized_requests)
            # Dedupe again after augmentation
            seen_req_keys.clear()
            final_requests: List[Dict[str, Any]] = []
            for r in normalized_requests:
                k = _req_key(r)
                if k not in seen_req_keys:
                    seen_req_keys.add(k)
                    final_requests.append(r)
            normalized_requests = final_requests
        
        # Retrieve all blocks
        blocks: List[str] = []
        total_chars = 0
        for req in normalized_requests:
            b = _retrieve_block(req)
            if b:
                blocks.append(b)
                total_chars += len(b)
                if step_id is not None:
                    self._increment_step_stat(step_id, "vector_appended_chars", len(b))
        
        # Cap total size
        if self._max_total_followup_chars and total_chars > self._max_total_followup_chars:
            trimmed = []
            running = 0
            for b in blocks:
                if running + len(b) > self._max_total_followup_chars:
                    break
                trimmed.append(b)
                running += len(b)
            blocks = trimmed
        
        # Join all blocks
        retrieved_content = "\n\n".join(blocks) if blocks else "(No additional context retrieved)"
        
        self.logger.info(
            f"[PHASE3-RETRIEVE] Step {step_id}: Retrieved {len(blocks)} blocks, "
            f"total {len(retrieved_content)} chars from {len(requests)} requests"
        )
        
        return retrieved_content

    def _convert_missing_context_to_requests(self, missing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Best-effort conversion of missing_context hints into retrieval requests."""
        requests: List[Dict[str, Any]] = []
        for idx, item in enumerate(missing):
            if isinstance(item, str):
                item = {"query": item}
            elif not isinstance(item, dict):
                try:
                    self.logger.warning(
                        "[PHASE3-VECTOR] Ignoring unsupported missing_context entry type=%s value=%s",
                        type(item),
                        item,
                    )
                except Exception:
                    pass
                continue
            source_link_id = item.get("source") or item.get("source_link_id") or "unknown"
            search_hint = item.get("search_hint") or item.get("query") or ""
            if not search_hint:
                continue

            link_candidates: List[str] = []
            # Explicit fields first
            explicit_link = item.get("source") or item.get("source_link_id")
            if isinstance(explicit_link, str) and explicit_link:
                link_candidates.append(explicit_link.strip())
            # Regex scan inside hint/details
            link_pattern = re.compile(r"(link[_\-][0-9a-zA-Z]+)")
            matches = link_pattern.findall(search_hint)
            if not matches:
                for key in ("reason", "details", "description"):
                    text_val = item.get(key)
                    if isinstance(text_val, str):
                        matches.extend(link_pattern.findall(text_val))
            if matches:
                for m in matches:
                    link_candidates.append(m.strip())

            if link_candidates:
                primary_link = link_candidates[0].replace("-", "_")
                requests.append(
                    {
                        "id": f"auto_full_{idx+1}",
                        "content_type": "transcript",
                        "source_link_id": primary_link,
                        "request_type": "full_content_item",
                        "content_types": ["transcript", "comments"],
                        "parameters": {},
                        "reason": item.get("reason", "Full content requested via missing_context"),
                    }
                )

            requests.append(
                {
                    "id": f"auto_req_{idx+1}",
                    "content_type": "transcript",
                    "source_link_id": source_link_id,
                    "request_type": "semantic",
                    "method": "semantic",
                    "parameters": {
                        "query": search_hint,
                        "fallback_keywords": [search_hint],
                        "context_window": 500,
                        "top_k": self._vector_top_k,
                    },
                    "source_link_ids": [] if source_link_id in {"", "unknown"} else [source_link_id],
                    "reason": item.get("reason", "Fill missing context"),
                }
            )
        return requests

    def _handle_retrieval_request(
        self,
        req: Dict[str, Any],
        retriever: RetrievalHandler,
        batch_data: Optional[Dict[str, Any]] = None,
        *,
        step_id: Optional[int] = None,
    ) -> Optional[str]:
        """Route a single retrieval request to the appropriate handler and format a block."""
        # Get batch_data from session if not provided
        if batch_data is None:
            try:
                batch_data = self.session.batch_data  # type: ignore[attr-defined]
            except AttributeError:
                batch_data = None
        
        if batch_data is None:
            return "[Retrieval] Error: No batch_data available"
        
        request_type = req.get("request_type", req.get("method", "keyword"))  # Support new request_type field
        content_type = req.get("content_type") or req.get("type")
        link_id = req.get("source_link_id") or req.get("source")
        params = req.get("parameters", {})
        
        block_header = (
            f"[Retrieval Result] type={request_type}, content_type={content_type}, link_id={link_id}"
        )

        if request_type in {"semantic", "vector"} or req.get("method") == "semantic":
            if not isinstance(params, dict):
                params = dict(params) if params else {}
            query = (
                params.get("query")
                or req.get("query")
                or req.get("marker_text")
                or req.get("topic")
                or ""
            )
            if not query:
                return "[Retrieval] Error: Missing query for semantic request"

            fallback_keywords_raw = params.get("fallback_keywords") or []
            if isinstance(fallback_keywords_raw, str):
                fallback_keywords = [fallback_keywords_raw]
            else:
                fallback_keywords = [str(k) for k in fallback_keywords_raw if k]
            context_window = int(params.get("context_window", 500))

            link_filters = req.get("source_link_ids") or ([] if not link_id else [link_id])
            filters = RetrievalFilters(
                link_ids=link_filters or None,
                chunk_types=req.get("chunk_types"),
            )

            top_k_param = params.get("top_k") if isinstance(params, dict) else None
            top_k = top_k_param or self._vector_top_k
            try:
                step_context = req.get("step_id") or req.get("source_step_id")
                self.logger.info(
                    "[PHASE3-VECTOR] Semantic retrieval request: query='%s', step=%s, link_filters=%s",
                    query[:80],
                    step_context if step_context is not None else "?",
                    link_filters,
                )
            except Exception:
                pass
            filter_desc = {
                "link_ids": filters.link_ids if filters else None,
                "chunk_types": filters.chunk_types if filters else None,
            }

            vector_results: List[VectorSearchResult] = []
            latency_ms = 0.0
            if self._has_vector_service():
                search_start = time.perf_counter()
                vector_results = self.vector_service.search(query, filters=filters, top_k=top_k)
                latency_ms = (time.perf_counter() - search_start) * 1000.0
                if step_id is not None:
                    self._increment_step_stat(step_id, "vector_calls", 1)
                    self._increment_step_stat(step_id, "vector_latency_ms", latency_ms)
            else:
                self.logger.warning(
                    "[PHASE3-FALLBACK] step=%s reason=vector_service_unavailable query='%s'",
                    step_id,
                    query[:80],
                )

            hit_count = len(vector_results)

            if hit_count > 0:
                top_score = max(r.score for r in vector_results)
                self.logger.info(
                    "[PHASE3-VECTOR] step=%s hits=%s latency=%.1fms top_score=%.3f filters=%s",
                    step_id,
                    hit_count,
                    latency_ms,
                    top_score,
                    filter_desc,
                )
                if step_id is not None:
                    self._increment_step_stat(step_id, "vector_hits", 1)
                    self._increment_step_stat(step_id, "vector_results_returned", hit_count)
                    self._set_step_stat_max(step_id, "vector_best_score", top_score)
                # Filter out chunks already delivered for this step to avoid duplicates
                filtered_results = vector_results[:top_k]
                if step_id is not None:
                    seen_chunks = self._vector_seen_chunks.setdefault(step_id, set())
                    fresh = [res for res in filtered_results if res.chunk_id not in seen_chunks]
                    if fresh:
                        seen_chunks.update(res.chunk_id for res in fresh)
                        filtered_results = fresh
                formatted = self._summarize_vector_results(query, filtered_results, max_chars=self._vector_block_chars)
                return self._limit_block(f"{block_header}\n{formatted}")

            # Vector empty or unavailable – attempt keyword fallback if possible
            if step_id is not None:
                self._increment_step_stat(step_id, "vector_empty", 1)

            if fallback_keywords and link_id:
                keyword_content = retriever.retrieve_by_keywords(
                    link_id,
                    fallback_keywords,
                    batch_data,
                    context_window=context_window,
                )
                return self._limit_block(
                    f"{block_header}\nQuery: {query}\n"
                    "(Vector search yielded no matches; keyword fallback provided below)\n"
                    f"{keyword_content}"
                )

            formatted = "(Vector retrieval unavailable)" if not self._has_vector_service() else "(No semantic matches found)"
            return self._limit_block(f"{block_header}\nQuery: {query}\n{formatted}")
        
        # New request types: full_content_item, by_marker, by_topic, by_marker_types
        if request_type == "full_content_item":
            content_types = req.get("content_types", ["transcript", "comments"])
            if not isinstance(content_types, list):
                content_types = [content_types]
            if not link_id:
                return "[Retrieval] Error: Missing source_link_id for full_content_item"
            content = retriever.retrieve_full_content_item(link_id, content_types, batch_data)
            return f"{block_header}\n{content}"
        
        elif request_type == "by_marker":
            marker_text = req.get("marker_text", "")
            if not marker_text:
                return "[Retrieval] Error: Missing marker_text for by_marker request"
            if not link_id:
                return "[Retrieval] Error: Missing source_link_id for by_marker request"
            content_type_marker = req.get("content_type", "transcript")
            context_window = params.get("context_window", 2000)
            content = retriever.retrieve_by_marker(marker_text, link_id, content_type_marker, context_window, batch_data)
            return f"{block_header}\n{content}"
        
        elif request_type == "by_topic":
            topic = req.get("topic", "")
            if not topic:
                return "[Retrieval] Error: Missing topic for by_topic request"
            source_link_ids = req.get("source_link_ids", [])
            if not source_link_ids:
                return "[Retrieval] Error: Missing source_link_ids for by_topic request"
            content_types = req.get("content_types", ["transcript", "comments"])
            if not isinstance(content_types, list):
                content_types = [content_types]
            content = retriever.retrieve_by_topic(topic, source_link_ids, content_types, batch_data)
            return f"{block_header}\n{content}"
        
        elif request_type == "selective_markers":
            marker_types = req.get("marker_types", [])
            if not marker_types:
                return "[Retrieval] Error: Missing marker_types for selective_markers request"
            if not link_id:
                return "[Retrieval] Error: Missing source_link_id for selective_markers request"
            content_type_selective = req.get("content_type", "transcript")
            content = retriever.retrieve_by_marker_types(marker_types, link_id, content_type_selective, batch_data)
            return f"{block_header}\n{content}"
        
        # Legacy request types: word_range, keyword, semantic
        if not link_id:
            return "[Retrieval] Error: Missing source_link_id"
        
        if content_type == "transcript":
            method = req.get("method", "keyword")
            if method == "word_range":
                start_word = int(params.get("start_word", 0))
                end_word = int(params.get("end_word", 0))
                content = retriever.retrieve_by_word_range(link_id, start_word, end_word, batch_data)
            elif method == "semantic":
                # Semantic search not implemented – degrade to keyword if possible
                query = params.get("query") or ""
                keywords = [query] if query else []
                content = retriever.retrieve_by_keywords(link_id, keywords, batch_data, params.get("context_window", 500)) if keywords else "(Semantic search unavailable)"
            else:
                keywords = params.get("keywords") or []
                content = retriever.retrieve_by_keywords(link_id, keywords, batch_data, params.get("context_window", 500))
            return f"{block_header}\n{content}"
        
        if content_type == "comments":
            keywords = params.get("filter_keywords") or params.get("keywords") or []
            limit = int(params.get("limit", 10))
            sort_by = params.get("sort_by", "relevance")
            content = retriever.retrieve_matching_comments(link_id, keywords, batch_data, limit=limit, sort_by=sort_by)
            return f"{block_header}\n{content}"
        
        # Fallback
        return f"{block_header}\n(Unsupported request_type: {request_type})"

    def _track_chunk(self, step_id: int, data_chunk: str, findings: Dict[str, Any]) -> None:
        """
        Track processed chunk for sequential processing.
        Enhancement #1: Context preservation for sequential chunking.
        Solution 4: Enhanced tracking with quotes and examples.
        """
        if step_id not in self._chunk_tracker:
            self._chunk_tracker[step_id] = []
        
        # Extract key quotes and examples from findings
        findings_data = findings.get("findings", {})
        points_of_interest = findings_data.get("points_of_interest", {})
        
        key_quotes = []
        if points_of_interest:
            # Extract quotable statements
            key_claims = points_of_interest.get("key_claims", [])
            notable_evidence = points_of_interest.get("notable_evidence", [])
            
            # Collect quotes from key claims
            for claim in key_claims[:2]:  # Top 2 claims
                if isinstance(claim, dict):
                    claim_text = claim.get("claim", "")
                    if claim_text and len(claim_text) > 20:  # Meaningful quotes
                        key_quotes.append(claim_text[:150])  # First 150 chars
            
            # Collect quotes from evidence
            for evidence in notable_evidence[:2]:  # Top 2 evidence
                if isinstance(evidence, dict):
                    quote = evidence.get("quote", "")
                    if quote:
                        key_quotes.append(quote[:150])
        
        # Store chunk summary with enhanced context
        chunk_summary = {
            "chunk_index": len(self._chunk_tracker[step_id]) + 1,
            "data_preview": " ".join(data_chunk.split()[:200]) + "..." if len(data_chunk.split()) > 200 else data_chunk,
            "insights": findings.get("insights", "")[:300],  # First 300 chars of insights
            "key_quotes": key_quotes[:3]  # Top 3 quotes/examples from this chunk
        }
        
        self._chunk_tracker[step_id].append(chunk_summary)

    def _init_step_stats(self, step_id: int) -> None:
        if step_id not in self._step_stats:
            self._step_stats[step_id] = {
                "vector_calls": 0,
                "vector_hits": 0,
                "vector_empty": 0,
                "vector_results_returned": 0,
                "vector_latency_ms": 0.0,
                "vector_best_score": 0.0,
                "sequential_windows": 0,
                "vector_appended_chars": 0,
                "vector_followup_turns": 0,
                "novelty_candidates": 0,
                "novelty_duplicates_removed": 0,
            }
            self._vector_seen_chunks[step_id] = set()
            self._vector_full_items[step_id] = False

    def _increment_step_stat(self, step_id: int, key: str, value: float) -> None:
        self._init_step_stats(step_id)
        stats = self._step_stats[step_id]
        stats[key] = stats.get(key, 0.0) + value

    def _set_step_stat_max(self, step_id: int, key: str, value: float) -> None:
        self._init_step_stats(step_id)
        stats = self._step_stats[step_id]
        stats[key] = max(stats.get(key, 0.0), value)

    def _log_step_summary(self, step_id: int) -> None:
        stats = self._step_stats.get(step_id) or {}
        if not stats:
            return
        self.logger.info(
            "[PHASE3-STEP] step=%s vector_calls=%s hits=%s empty=%s seq_windows=%s appended_chars=%s followups=%s latency_ms=%.1f best_score=%.3f",
            step_id,
            int(stats.get("vector_calls", 0)),
            int(stats.get("vector_hits", 0)),
            int(stats.get("vector_empty", 0)),
            int(stats.get("sequential_windows", 0)),
            int(stats.get("vector_appended_chars", 0)),
            int(stats.get("vector_followup_turns", 0)),
            stats.get("vector_latency_ms", 0.0),
            stats.get("vector_best_score", 0.0),
        )
    
    def _get_previous_chunks_context(self, step_id: int) -> Optional[str]:
        """
        Get context summary from previously processed chunks.
        Enhancement #1: Context preservation for sequential chunking.
        Solution 4: Enhanced context with quotes and examples.
        """
        if step_id not in self._chunk_tracker or not self._chunk_tracker[step_id]:
            return None
        
        chunks = self._chunk_tracker[step_id]
        context_parts = []
        
        for chunk in chunks[-3:]:  # Last 3 chunks to avoid overload
            chunk_info = (
                f"数据块 {chunk['chunk_index']}:\n"
                f"  内容预览: {chunk['data_preview']}\n"
                f"  关键洞察: {chunk['insights']}"
            )
            
            # Add key quotes if available
            key_quotes = chunk.get("key_quotes", [])
            if key_quotes:
                chunk_info += f"\n  重要引述/例子: {', '.join([q[:80] + '...' if len(q) > 80 else q for q in key_quotes[:2]])}"
            
            context_parts.append(chunk_info)
        
        if len(chunks) > 3:
            context_parts.append(f"\n(已处理 {len(chunks) - 3} 个之前的数据块)")
        
        return "\n\n".join(context_parts)
    
    def _build_user_feedback_context(self) -> str:
        """
        Combine stored user guidance so each step can honor original intent.
        """
        # Retrieve initial guidance before role generation
        pre_feedback = self.session.get_metadata("phase_feedback_pre_role", "") or ""
        # Prefer explicitly stored post-Phase-1 feedback; fall back to legacy field
        post_feedback = self.session.get_metadata("phase_feedback_post_phase1", "") or ""
        if not post_feedback:
            post_feedback = self.session.get_metadata("phase1_user_input", "") or ""
        
        parts = []
        if pre_feedback.strip():
            parts.append(f"**用户初始指导：**\n{pre_feedback.strip()}")
        if post_feedback.strip():
            parts.append(f"**用户优先事项：**\n{post_feedback.strip()}")
        
        return "\n\n".join(parts)
    
    def _validate_phase3_schema(self, data: Dict[str, Any]) -> None:
        """
        Validate Phase 3 step output using output_schema.json if available.
        Enhanced to support points_of_interest structure and conditional findings.
        """
        schema = load_schema("phase3_execute", name="output_schema.json")
        if not schema:
            return
        
        # Check if there are any requests
        has_requests = (
            (data.get("requests") and len(data.get("requests", [])) > 0) or
            (data.get("missing_context") and len(data.get("missing_context", [])) > 0)
        )
        
        # Basic required fields (findings is conditionally required)
        required_keys = ["step_id", "insights", "confidence"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Schema validation failed: missing required key '{key}' in step output")
        
        # Type checks
        if not isinstance(data.get("step_id"), int):
            raise ValueError("Schema validation failed: 'step_id' must be integer")
        if not isinstance(data.get("insights"), str):
            raise ValueError("Schema validation failed: 'insights' must be string")
        if not isinstance(data.get("confidence"), (int, float)):
            raise ValueError("Schema validation failed: 'confidence' must be number")
        
        # Conditional findings validation:
        # - If requests exist, findings can be null/omitted
        # - If no requests, findings must be a dict
        findings = data.get("findings")
        if has_requests:
            # When requests exist, findings should be null or omitted
            if findings is not None and not isinstance(findings, dict):
                # Allow null, but warn if it's something else
                self.logger.debug(f"Findings should be null when requests exist, got: {type(findings)}")
        else:
            # When no requests, findings must be a dict
            if findings is None:
                raise ValueError("Schema validation failed: 'findings' must be object when no requests are present")
            if not isinstance(findings, dict):
                raise ValueError("Schema validation failed: 'findings' must be object when no requests are present")
        
        # Validate findings structure (only if findings is present and not null)
        findings = data.get("findings")
        if findings is not None and isinstance(findings, dict):
            # Check for summary (recommended but not strictly required for backward compatibility)
            if "summary" not in findings:
                self.logger.debug("Findings missing 'summary' field (recommended)")
            if "article" not in findings:
                self.logger.warning("Findings missing 'article' field (required for comprehensive answer)")
            elif not isinstance(findings.get("article"), str):
                raise ValueError("Schema validation failed: 'article' must be string")
        
        # Validate points_of_interest if present (only if findings is a dict)
        if findings is not None and isinstance(findings, dict) and "points_of_interest" in findings:
            poi = findings["points_of_interest"]
            if not isinstance(poi, dict):
                raise ValueError("Schema validation failed: 'points_of_interest' must be object")
            
            # Validate each interest type (all optional arrays)
            expected_types = [
                "key_claims", "notable_evidence", "controversial_topics",
                "surprising_insights", "specific_examples", "open_questions"
            ]
            
            for poi_type in expected_types:
                if poi_type in poi:
                    if not isinstance(poi[poi_type], list):
                        raise ValueError(
                            f"Schema validation failed: 'points_of_interest.{poi_type}' must be array"
                        )
                    
                    # Validate structure for complex types
                    if poi_type == "key_claims" and poi[poi_type]:
                        for idx, claim in enumerate(poi[poi_type]):
                            if not isinstance(claim, dict) or "claim" not in claim:
                                self.logger.warning(
                                    f"Key claim {idx} missing 'claim' field"
                                )
                    
                    elif poi_type == "notable_evidence" and poi[poi_type]:
                        for idx, evidence in enumerate(poi[poi_type]):
                            if not isinstance(evidence, dict):
                                self.logger.warning(
                                    f"Notable evidence {idx} must be object"
                                )
                            elif "evidence_type" not in evidence or "description" not in evidence:
                                self.logger.warning(
                                    f"Notable evidence {idx} missing required fields"
                                )
                    
                    elif poi_type == "controversial_topics" and poi[poi_type]:
                        for idx, topic in enumerate(poi[poi_type]):
                            if not isinstance(topic, dict) or "topic" not in topic:
                                self.logger.warning(
                                    f"Controversial topic {idx} missing 'topic' field"
                                )
                    
                    elif poi_type == "specific_examples" and poi[poi_type]:
                        for idx, example in enumerate(poi[poi_type]):
                            if not isinstance(example, dict) or "example" not in example:
                                self.logger.warning(
                                    f"Specific example {idx} missing 'example' field"
                                )
        
        # Validate analysis_details if present (flexible structure)
        if "analysis_details" in findings:
            if not isinstance(findings["analysis_details"], dict):
                self.logger.warning("analysis_details should be object")

