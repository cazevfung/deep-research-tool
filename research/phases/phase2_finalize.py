"""Phase 2: Finalize Research Goals into Unified Topic (Preserve Questions)."""

import json
from typing import Dict, Any, List, Optional
from research.phases.base_phase import BasePhase
from research.prompts import compose_messages, load_schema


class Phase2Finalize(BasePhase):
    """Phase 2: Finalize unified topic while preserving Phase 1 questions directly."""
    
    def execute(
        self,
        phase1_output: Dict[str, Any],
        data_abstract: str,
        user_input: Optional[str] = None,
        user_topic: Optional[str] = None,
        pre_phase_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Finalize unified topic while preserving Phase 1 questions directly.
        
        Args:
            phase1_output: Full Phase 1 output object containing suggested_goals
            data_abstract: Abstract of available data
            user_input: Optional user amendment feedback or project description
            user_topic: Optional user-specified research topic
            
        Returns:
            Dict with synthesized_goal (preserving Phase 1 questions) and raw_response
        """
        self.logger.info("Phase 2: Finalizing research goals (preserving questions)")
        
        # Progress indicator
        if self.ui:
            self.ui.display_message("正在确定研究主题...", "info")
        
        # Extract goals from full phase1_output (backward compatible)
        all_goals = phase1_output.get("suggested_goals", []) if isinstance(phase1_output, dict) else []
        if not all_goals and isinstance(phase1_output, list):
            # Backward compatibility: accept list directly
            all_goals = phase1_output

        if not all_goals:
            # Final fallback to session metadata (e.g., from confirmation step)
            metadata_goals = self.session.get_metadata("phase1_confirmed_goals")
            if isinstance(metadata_goals, list):
                all_goals = metadata_goals
        
        if len(all_goals) < 1:
            raise ValueError(f"Expected at least 1 goal, got {len(all_goals)}")
        
        # Store goals count for validation
        self._goals_count = len(all_goals)
        
        # Extract goal_text directly from Phase 1 - DON'T regenerate
        component_questions = [goal.get("goal_text", "") for goal in all_goals]

        # Ensure we didn't accidentally transform the confirmed goals
        if any(not question for question in component_questions):
            raise ValueError("Phase 2 received invalid goal entries without goal_text")
        
        # Format goals as numbered list dynamically (for prompt context only)
        goals_list = "\n".join([
            f"{i+1}. {goal.get('goal_text', '')}" 
            for i, goal in enumerate(all_goals)
        ])
        
        # Get research role from session metadata
        from research.prompts.context_formatters import format_research_role_for_context
        research_role = self.session.get_metadata("research_role") if self.session else None
        role_context = format_research_role_for_context(research_role)
        # Phase 2 finalize runs AFTER Phase 1, so user_context should be available
        user_intent = self._get_user_intent_fields(include_post_phase1_feedback=True)
        
        # Compose messages from externalized prompt templates
        context = {
            "goals_list": goals_list,
            "goals_count": len(all_goals),
            "data_abstract": data_abstract,
            "system_role_description": role_context["system_role_description"],
            "research_role_display": role_context["research_role_display"],
            "research_role_rationale": role_context["research_role_rationale"],
            "user_guidance": user_intent["user_guidance"],
            "user_context": user_intent["user_context"],
        }
        messages = compose_messages("phase2_finalize", context=context)
        
        # Progress indicator: calling AI
        if self.ui:
            self.ui.display_message("正在生成综合研究主题...", "info")
        
        # Stream and parse JSON response
        import time
        api_start_time = time.time()
        self.logger.info(f"[TIMING] Starting API call for Phase 2 at {api_start_time:.3f}")
        response = self._stream_with_callback(
            messages,
            stream_metadata={
                "component": "finalization",
                "phase_label": "2",
                "goals_count": len(all_goals),
            },
        )
        api_elapsed = time.time() - api_start_time
        self.logger.info(f"[TIMING] API call completed in {api_elapsed:.3f}s for Phase 2")
        
        # Parse JSON from response
        try:
            # Try to extract JSON from response
            parsed = self.client.parse_json_from_stream(iter([response]))
            synthesized_goal_raw = parsed.get("synthesized_goal", {})
        except Exception as e:
            self.logger.warning(f"JSON parsing error, trying to extract manually: {e}")
            # Fallback: try to find JSON in response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                synthesized_goal_raw = parsed.get("synthesized_goal", {})
            else:
                raise ValueError(f"Could not parse synthesized goal from response: {response[:200]}")
        
        # Optional schema validation
        schema = load_schema("phase2_finalize", name="output_schema.json")
        if schema:
            self._validate_against_schema(parsed, schema)
        
        # Build synthesized_goal with preserved Phase 1 questions
        synthesized_goal = {
            "comprehensive_topic": synthesized_goal_raw.get("comprehensive_topic", ""),
            "component_questions": component_questions,  # Use Phase 1 questions directly
            "unifying_theme": synthesized_goal_raw.get("unifying_theme", ""),
            "research_scope": synthesized_goal_raw.get("research_scope", "")
        }
        
        result = {
            "synthesized_goal": synthesized_goal,
            "component_goals": all_goals,  # Preserve original Phase 1 goals
            "raw_response": response,
            "user_input": user_input or "",
            "user_topic": user_topic or "",
            "user_initial_input": pre_phase_feedback or "",
        }
        
        # Store in session
        self.session.set_metadata("synthesized_goal", synthesized_goal)
        self.session.set_metadata("component_goals", all_goals)
        if user_input:
            self.session.set_metadata("phase1_user_input", user_input)
        
        self.logger.info(f"Phase 2 complete: Finalized unified topic, preserved {len(component_questions)} questions")
        
        return result
    
    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Minimal validator for the expected Phase 2 schema.
        Raises ValueError if validation fails.
        """
        # Top-level required
        required_keys = schema.get("required", [])
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Schema validation failed: missing required key '{key}'")

        # synthesized_goal specifics
        synthesized_goal = data.get("synthesized_goal")
        if not isinstance(synthesized_goal, dict):
            raise ValueError("Schema validation failed: 'synthesized_goal' must be an object")
        
        goal_schema = schema.get("properties", {}).get("synthesized_goal", {})
        goal_required = goal_schema.get("required", ["comprehensive_topic"])
        
        for req in goal_required:
            if req not in synthesized_goal:
                raise ValueError(f"Schema validation failed: 'synthesized_goal' missing '{req}'")
        
        # Type checks
        if not isinstance(synthesized_goal.get("comprehensive_topic"), str):
            raise ValueError("Schema validation failed: 'comprehensive_topic' must be a string")



