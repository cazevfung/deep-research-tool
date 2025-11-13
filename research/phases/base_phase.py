"""Base class for all research phases."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import uuid4
from loguru import logger

from research.client import QwenStreamingClient
from research.progress_tracker import ProgressTracker
from research.session import ResearchSession


class BasePhase(ABC):
    """Abstract base class for all research phases."""
    
    def __init__(
        self,
        client: QwenStreamingClient,
        session: ResearchSession,
        progress_tracker: Optional[ProgressTracker] = None,
        ui = None
    ):
        """
        Initialize phase.
        
        Args:
            client: Qwen streaming API client
            session: Research session
            progress_tracker: Optional progress tracker
            ui: Optional UI interface for progress updates
        """
        self.client = client
        self.session = session
        self.progress_tracker = progress_tracker
        self.ui = ui
        self.logger = logger.bind(phase=self.__class__.__name__)
        
        # Load phase-specific model configuration
        self._load_phase_config()
    
    def _get_phase_config_key(self) -> Optional[str]:
        """
        Map phase class name to config.yaml phase key.
        
        Returns:
            Config key for this phase (e.g., "phase0", "phase1"), or None
        """
        class_name = self.__class__.__name__.lower()
        phase_mapping = {
            "phase0prepare": "phase0",
            "phase0_5rolegeneration": "phase0_5",
            "phase1discover": "phase1",
            "phase2finalize": "phase2",
            "phase3execute": "phase3",
            "phase4synthesize": "phase4",
        }
        return phase_mapping.get(class_name)
    
    def _get_stream_identifier(self) -> str:
        """Return a consistent identifier for the current phase stream."""
        phase_key = self._get_phase_config_key()
        if phase_key:
            return phase_key
        return self.__class__.__name__.lower()
    
    def _get_user_intent_fields(self, include_post_phase1_feedback: bool = False) -> Dict[str, str]:
        """
        Extract user_guidance and user_context from session metadata.
        Used for unified User Intent section in prompts.
        
        Args:
            include_post_phase1_feedback: If True, include user_context from Phase 1 feedback.
                                         Only set to True for phases that run AFTER Phase 1.
        
        Returns:
            Dict with 'user_guidance' and 'user_context' fields
        """
        # Extract user_guidance (initial guidance before role generation)
        # This is available from Phase 0.5 onwards
        user_guidance = self.session.get_metadata("phase_feedback_pre_role", "") or ""
        
        # Extract user_context (post-phase feedback, excluding user_topic)
        # Only available AFTER Phase 1 completes
        user_context = ""
        if include_post_phase1_feedback:
            user_context = (
                self.session.get_metadata("phase_feedback_post_phase1", "") or
                self.session.get_metadata("phase1_user_input", "") or
                ""
            )
        
        return {
            "user_guidance": user_guidance.strip() if user_guidance else "",
            "user_context": user_context.strip() if user_context else "",
        }

    def _build_stream_metadata(self, **extra: Any) -> Dict[str, Any]:
        """Build metadata payload for stream start/end notifications."""
        metadata: Dict[str, Any] = {
            "phase_class": self.__class__.__name__,
        }
        phase_key = self._get_phase_config_key()
        if phase_key:
            metadata["phase_key"] = phase_key
        for key, value in extra.items():
            if value is not None:
                metadata[key] = value
        return metadata
    
    def _load_phase_config(self):
        """Load phase-specific model configuration from config.yaml."""
        try:
            from core.config import Config
            config = Config()
            phase_key = self._get_phase_config_key()
            
            if phase_key:
                config_path = f"research.phases.{phase_key}"
                self.phase_model = config.get(f"{config_path}.model")
                self.phase_enable_thinking = config.get(f"{config_path}.enable_thinking", False)
                self.phase_stream = config.get(f"{config_path}.stream", True)
                
                if self.phase_model:
                    self.logger.info(
                        f"Phase config loaded: model={self.phase_model}, "
                        f"enable_thinking={self.phase_enable_thinking}, stream={self.phase_stream}"
                    )
                else:
                    self.logger.warning(f"No phase config found for {phase_key}, using defaults")
                    self.phase_model = None
                    self.phase_enable_thinking = False
                    self.phase_stream = True
            else:
                self.logger.warning(f"Unknown phase class: {self.__class__.__name__}, using defaults")
                self.phase_model = None
                self.phase_enable_thinking = False
                self.phase_stream = True
        except Exception as e:
            self.logger.warning(f"Failed to load phase config: {e}, using defaults")
            self.phase_model = None
            self.phase_enable_thinking = False
            self.phase_stream = True
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute the phase.
        
        Returns:
            Phase results
        """
        pass
    
    def _stream_with_callback(
        self,
        messages: List[Dict[str, str]],
        *,
        usage_tag: Optional[str] = None,
        log_payload: bool = True,
        payload_label: Optional[str] = None,
        stream_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Stream API call with progress callback.
        
        Args:
            messages: API messages
            **kwargs: Additional arguments for stream_completion
            
        Returns:
            Full response text
        """
        import time
        import threading
        
        stream_phase = None
        stream_id = None
        stream_metadata_payload: Dict[str, Any] = {}

        # Send "starting" update
        if self.ui:
            stream_phase = self._get_stream_identifier()
            stream_metadata_payload = self._build_stream_metadata()
            if stream_metadata:
                try:
                    stream_metadata_payload.update(stream_metadata)
                except Exception as exc:
                    self.logger.warning("Failed to merge custom stream metadata: %s", exc)
            # Ensure phase is in metadata for frontend filtering/display
            if stream_phase:
                stream_metadata_payload["phase"] = stream_phase
                stream_metadata_payload["phase_key"] = stream_phase
            self.ui.display_message("正在调用AI API...", "info")
            stream_id = f"{stream_phase}:{uuid4().hex}"
            self.ui.clear_stream_buffer(stream_id)
            self.ui.notify_stream_start(stream_id, stream_phase, stream_metadata_payload)
            self.logger.info(
                "[STREAM-START] stream_id=%s phase=%s class=%s",
                stream_id,
                stream_phase,
                self.__class__.__name__,
            )
        
        token_count = 0
        last_update_time = time.time()
        last_token_time = time.time()
        update_interval = 2.0  # Update every 2 seconds
        heartbeat_interval = 15.0  # Send heartbeat every 15 seconds
        heartbeat_active = True
        
        # Heartbeat thread to send periodic updates during long waits
        def heartbeat_worker():
            nonlocal last_token_time, heartbeat_active
            iteration = 0
            while heartbeat_active:
                time.sleep(heartbeat_interval)
                iteration += 1
                # Check if we've received tokens recently (within 5 seconds)
                if time.time() - last_token_time >= 5.0:
                    # No tokens received recently, send heartbeat
                    if self.ui and heartbeat_active:
                        self.ui.display_message(f"仍在处理中，请稍候... ({iteration * heartbeat_interval:.0f}秒)", "info")
        
        heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        heartbeat_thread.start()
        
        def callback(token: str):
            nonlocal token_count, last_update_time, last_token_time, stream_id
            
            token_count += 1
            current_time = time.time()
            last_token_time = current_time  # Update last token time
            
            # Update progress tracker
            if self.progress_tracker:
                self.progress_tracker.stream_update(token)
            
            if self.ui and stream_id:
                self.ui.display_stream(token, stream_id)
            
            # Send periodic progress updates to UI
            if self.ui and (token_count % 10 == 0 or current_time - last_update_time >= update_interval):
                self.ui.display_message(f"正在接收响应... ({token_count} tokens)", "info")
                last_update_time = current_time
        
        # Apply phase-specific model configuration if not overridden in kwargs
        phase_kwargs = {}
        if self.phase_model and "model" not in kwargs:
            phase_kwargs["model"] = self.phase_model
        if "enable_thinking" not in kwargs:
            phase_kwargs["enable_thinking"] = self.phase_enable_thinking
        # stream is always True by default in the client, so we don't need to set it
        
        # Merge phase config with any provided kwargs (kwargs take precedence)
        final_kwargs = {**phase_kwargs, **kwargs}
        stream_start_time = time.time()
        
        if log_payload:
            try:
                prompt_lines = []
                for msg in messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    prompt_lines.append(f"[{role}] {content}")
                prompt_preview = "\n".join(prompt_lines)
                label = payload_label or usage_tag or stream_phase or self.__class__.__name__
                self.logger.info(
                    "[LLM-PROMPT] tag=%s length=%s\n%s",
                    label,
                    len(prompt_preview),
                    prompt_preview,
                )
            except Exception as e:
                self.logger.warning(f"Failed to log prompt payload: {e}")

        try:
            response, usage = self.client.stream_and_collect(
                messages,
                callback=callback,
                **final_kwargs
            )
        finally:
            # Stop heartbeat thread
            heartbeat_active = False
            if self.ui and stream_phase and stream_id:
                try:
                    stream_meta_with_counts = {
                        **stream_metadata_payload,
                        "tokens": token_count,
                    }
                    self.ui.notify_stream_end(stream_id, stream_phase, stream_meta_with_counts)
                    elapsed = time.time() - stream_start_time
                    self.logger.debug(
                        "Stream completed",
                        stream_id=stream_id,
                        phase=stream_phase,
                        tokens=token_count,
                        elapsed=elapsed,
                        metadata=stream_meta_with_counts,
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to notify stream end: {e}")
        
        # Send "parsing" update
        if self.ui:
            self.ui.display_message("AI响应已接收，正在解析结果...", "info")

        call_meta = getattr(self.client, "last_call_metadata", {}) if hasattr(self.client, "last_call_metadata") else {}
        if call_meta:
            if self.ui and call_meta.get("sanitized_retry") and not call_meta.get("fallback_used"):
                self.ui.display_message("提示已自动净化以通过模型安全审查。", "warning")
            if self.ui and call_meta.get("fallback_used"):
                provider_label = call_meta.get("fallback_provider") or "备用模型"
                self.ui.display_message(
                    f"主模型未通过安全审查，已切换至 {provider_label} 返回结果。",
                    "warning",
                )
                self.logger.warning(
                    "LLM fallback invoked provider=%s reason=%s request_id=%s",
                    call_meta.get("fallback_provider"),
                    call_meta.get("fallback_reason"),
                    call_meta.get("request_id"),
                )
        
        if usage:
            try:
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
                elapsed = time.time() - stream_start_time
                tag = usage_tag or stream_phase or self.__class__.__name__
                model_name = final_kwargs.get("model") or self.phase_model or getattr(self.client, "model", None)
                self.logger.info(
                    "[LLM-TOKENS] tag=%s model=%s input=%s output=%s total=%s elapsed=%.3fs",
                    tag,
                    model_name,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    elapsed,
                )
            except Exception as e:
                self.logger.warning(f"Failed to log token usage: {e}")
        
        if log_payload:
            try:
                label = payload_label or usage_tag or stream_phase or self.__class__.__name__
                self.logger.info(
                    "[LLM-RESPONSE] tag=%s length=%s\n%s",
                    label,
                    len(response),
                    response,
                )
            except Exception as e:
                self.logger.warning(f"Failed to log response payload: {e}")
        
        return response

