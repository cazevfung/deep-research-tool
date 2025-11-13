"""Phase 1.5: Synthesize All Research Goals into Unified Topic."""

import json
from typing import Dict, Any, List
from research.phases.base_phase import BasePhase
from research.prompts import compose_messages, load_schema


class Phase1Synthesize(BasePhase):
    """Phase 1.5: Synthesize all research goals into unified topic."""
    
    def execute(
        self,
        phase1_output: Dict[str, Any],
        data_abstract: str
    ) -> Dict[str, Any]:
        """
        Synthesize all research goals into one comprehensive topic.
        
        Args:
            phase1_output: Full Phase 1 output object containing suggested_goals
            data_abstract: Abstract of available data
            
        Returns:
            Dict with synthesized_goal and raw_response (full output object)
        """
        self.logger.info("Phase 1.5: Synthesizing research goals")
        
        # Extract goals from full phase1_output (backward compatible)
        all_goals = phase1_output.get("suggested_goals", [])
        if not all_goals and isinstance(phase1_output, list):
            # Backward compatibility: accept list directly
            all_goals = phase1_output
        
        if len(all_goals) < 1:
            raise ValueError(f"Expected at least 1 goal, got {len(all_goals)}")
        
        # Store goals count for validation
        self._goals_count = len(all_goals)
        
        # Format goals as numbered list dynamically
        goals_list = "\n".join([
            f"{i+1}. {goal.get('goal_text', '')}" 
            for i, goal in enumerate(all_goals)
        ])
        
        # Get research role from session metadata
        from research.prompts.context_formatters import format_research_role_for_context
        research_role = self.session.get_metadata("research_role") if self.session else None
        role_context = format_research_role_for_context(research_role)
        # Phase 1.5 runs after Phase 1 and user feedback (if provided)
        # Include user feedback so Phase 1.5 can adjust/refine questions based on user input
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
            "user_context": user_intent["user_context"],  # Contains user feedback from Phase 1
        }
        messages = compose_messages("phase1_synthesize", context=context)
        
        # Stream and parse JSON response
        response = self._stream_with_callback(
            messages,
            stream_metadata={
                "component": "phase1_5_synthesis",
                "phase_label": "1.5",
                "goals_count": len(all_goals),
            },
        )
        
        # Parse JSON from response
        try:
            # Try to extract JSON from response
            parsed = self.client.parse_json_from_stream(iter([response]))
            synthesized_goal = parsed.get("synthesized_goal", {})
        except Exception as e:
            self.logger.warning(f"JSON parsing error, trying to extract manually: {e}")
            # Fallback: try to find JSON in response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                synthesized_goal = parsed.get("synthesized_goal", {})
            else:
                raise ValueError(f"Could not parse synthesized goal from response: {response[:200]}")
        
        # Optional schema validation
        schema = load_schema("phase1_synthesize", name="output_schema.json")
        if schema:
            self._validate_against_schema(parsed, schema)
        
        result = {
            "synthesized_goal": synthesized_goal,
            "component_goals": all_goals,
            "raw_response": response
        }
        
        # Store in session
        self.session.set_metadata("synthesized_goal", synthesized_goal)
        self.session.set_metadata("component_goals", all_goals)
        
        self.logger.info("Phase 1.5 complete: Synthesized research goals")
        
        return result
    
    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Minimal validator for the expected Phase 1.5 schema.
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
        goal_required = goal_schema.get("required", ["comprehensive_topic", "component_questions"])
        
        for req in goal_required:
            if req not in synthesized_goal:
                raise ValueError(f"Schema validation failed: 'synthesized_goal' missing '{req}'")
        
        # Type checks
        if not isinstance(synthesized_goal.get("comprehensive_topic"), str):
            raise ValueError("Schema validation failed: 'comprehensive_topic' must be a string")
        
        component_questions = synthesized_goal.get("component_questions")
        if not isinstance(component_questions, list):
            raise ValueError("Schema validation failed: 'component_questions' must be a list")
        
        # Ensure all questions from previous phase are preserved
        expected_count = getattr(self, '_goals_count', None)
        if expected_count and len(component_questions) != expected_count:
            raise ValueError(
                f"'component_questions' must preserve all {expected_count} questions from previous phase, "
                f"got {len(component_questions)} questions"
            )

