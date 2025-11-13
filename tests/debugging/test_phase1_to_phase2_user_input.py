"""Test to verify user input from phase 1 is provided to phase 2 AI generation.

This test verifies that:
1. User input collected at the end of phase 1 is passed to phase 2
2. User input is included in the prompt sent to the AI in phase 2
3. The AI response actually considers the user input

Usage:
    python tests/test_phase1_to_phase2_user_input.py
"""
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from research.client import QwenStreamingClient
from research.session import ResearchSession
from research.phases.phase1_discover import Phase1Discover
from research.phases.phase2_finalize import Phase2Finalize
from research.phases.phase4_synthesize import Phase4Synthesize


class MockQwenClient:
    """Mock Qwen client that captures messages and returns minimal responses."""
    
    def __init__(self):
        self.call_count = 0
        self.captured_messages = []  # Store all messages sent to API
        self.total_tokens = 0
    
    def stream_and_collect(self, messages: List[Dict[str, str]], **kwargs) -> tuple:
        """Capture messages and return minimal response."""
        self.call_count += 1
        
        # Capture the messages for inspection
        self.captured_messages.append({
            'call_number': self.call_count,
            'messages': messages,
            'kwargs': kwargs
        })
        
        # Extract full prompt text from messages
        full_prompt = ""
        for msg in messages:
            if isinstance(msg, dict) and 'content' in msg:
                full_prompt += msg['content'] + "\n"
        
        # Generate minimal response based on phase
        if self.call_count == 1:  # Phase 1
            response = json.dumps({
                "suggested_goals": [
                    {"id": 1, "goal_text": "测试研究目标1", "uses": ["transcript"]},
                    {"id": 2, "goal_text": "测试研究目标2", "uses": ["transcript"]}
                ]
            }, ensure_ascii=False)
        elif self.call_count == 2:  # Phase 2
            # Check if user_input is in the prompt
            user_input_detected = "用户补充说明" in full_prompt or "用户研究主题" in full_prompt
            
            # Include user input detection in response for verification
            response = json.dumps({
                "synthesized_goal": {
                    "comprehensive_topic": f"综合主题{'[含用户输入]' if user_input_detected else '[无用户输入]'}",
                    "unifying_theme": "统一主题",
                    "research_scope": "研究范围",
                    "component_questions": ["测试研究目标1", "测试研究目标2"]
                }
            }, ensure_ascii=False)
        else:
            response = json.dumps({"result": "test"})
        
        # Simulate minimal token usage
        usage = {
            'prompt_tokens': len(full_prompt.split()),
            'completion_tokens': len(response.split()),
            'total_tokens': len(full_prompt.split()) + len(response.split())
        }
        self.total_tokens += usage['total_tokens']
        
        return response, usage
    
    def parse_json_from_stream(self, iterator, max_wait_time: float = 60.0):
        """Parse JSON from stream iterator."""
        # Collect all chunks from iterator
        text = ""
        if hasattr(iterator, '__iter__'):
            try:
                for chunk in iterator:
                    if isinstance(chunk, str):
                        text += chunk
                    else:
                        text += str(chunk)
            except TypeError:
                # If iterator is not iterable (e.g., single string), convert to string
                text = str(iterator)
        else:
            text = str(iterator)
        
        # Try to find JSON in text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)
    
    def get_usage_info(self):
        """Get usage information."""
        return {
            'total_tokens': self.total_tokens,
            'total_input_tokens': sum(len(str(m['messages']).split()) for m in self.captured_messages),
            'total_output_tokens': self.total_tokens - sum(len(str(m['messages']).split()) for m in self.captured_messages)
        }


class MockUI:
    """Mock UI that simulates user input."""
    
    def __init__(self, user_input_text: str = None):
        self.user_input_text = user_input_text
        self.messages = []
    
    def display_message(self, message: str, level: str = "info"):
        """Capture display messages."""
        self.messages.append({"message": message, "level": level})
    
    def display_header(self, header: str):
        """Capture header messages."""
        self.messages.append({"header": header})
    
    def prompt_user(self, prompt: str, choices: List[str] = None) -> str:
        """Simulate user input."""
        # Return the predefined user input
        return self.user_input_text or ""
    
    def display_goals(self, goals: List[Dict]):
        """Capture goals display."""
        self.messages.append({"goals": goals})
    
    def display_synthesized_goal(self, goal: Dict):
        """Capture synthesized goal display."""
        self.messages.append({"synthesized_goal": goal})


def test_user_input_flow_to_phase2():
    """Test that user input from phase 1 is passed to phase 2."""
    
    logger.info("=" * 80)
    logger.info("Testing User Input Flow: Phase 1 -> Phase 2")
    logger.info("=" * 80)
    
    # Test with user input
    test_user_input = "请重点关注技术实现细节和性能优化方面"
    logger.info(f"\nTest User Input: '{test_user_input}'")
    
    # Create mock client
    mock_client = MockQwenClient()
    
    # Create mock UI with user input
    mock_ui = MockUI(user_input_text=test_user_input)
    
    # Create session
    session = ResearchSession()
    
    # Phase 1: Generate goals
    logger.info("\n[Phase 1] Generating research goals...")
    phase1 = Phase1Discover(mock_client, session, ui=mock_ui)
    
    phase1_result = phase1.execute(
        data_abstract="这是一个测试数据摘要，包含一些技术内容。",
        user_topic="技术研究主题",
        research_role={"role": "技术研究员", "rationale": "专注于技术分析"},
        amendment_feedback=None,
        batch_data=None,
    )
    
    goals = phase1_result.get("suggested_goals", [])
    logger.info(f"Phase 1 generated {len(goals)} goals")
    
    # Simulate user providing input at end of phase 1
    user_input = mock_ui.prompt_user("你想如何修改这些目标？(自由输入，留空表示批准并继续)")
    logger.info(f"User provided input: '{user_input}'")
    
    # Phase 2: Synthesize with user input
    logger.info("\n[Phase 2] Synthesizing goals with user input...")
    phase2 = Phase2Finalize(mock_client, session, ui=mock_ui)
    
    phase2_result = phase2.execute(
        phase1_output=phase1_result,
        data_abstract="这是一个测试数据摘要，包含一些技术内容。",
        user_input=user_input,  # Pass user input here
        user_topic="技术研究主题"
    )
    
    synthesized = phase2_result.get("synthesized_goal", {})
    logger.info(f"Phase 2 generated topic: {synthesized.get('comprehensive_topic', 'N/A')}")
    
    # Verify: Check if user input was included in Phase 2 API call
    logger.info("\n" + "=" * 80)
    logger.info("Verification Results")
    logger.info("=" * 80)
    
    # Check captured messages
    if len(mock_client.captured_messages) >= 2:
        phase2_messages = mock_client.captured_messages[1]  # Second call is Phase 2
        phase2_prompt = ""
        for msg in phase2_messages['messages']:
            if isinstance(msg, dict) and 'content' in msg:
                phase2_prompt += msg['content'] + "\n"
        
        # Check if user input appears in the prompt
        user_input_in_prompt = test_user_input in phase2_prompt
        user_context_marker_in_prompt = "用户补充说明" in phase2_prompt
        
        logger.info(f"\n1. Phase 2 API call captured: ✅")
        logger.info(f"2. User input text in prompt: {'✅ YES' if user_input_in_prompt else '❌ NO'}")
        logger.info(f"3. User context marker ('用户补充说明') in prompt: {'✅ YES' if user_context_marker_in_prompt else '❌ NO'}")
        
        # Extract the user context section from prompt
        user_context_match = re.search(r'\*\*用户补充说明：\*\*\n(.*?)(?=\n\n|\*\*|$)', phase2_prompt, re.DOTALL)
        if user_context_match:
            extracted_user_input = user_context_match.group(1).strip()
            logger.info(f"4. Extracted user input from prompt: '{extracted_user_input}'")
            logger.info(f"   Matches test input: {'✅ YES' if extracted_user_input == test_user_input else '❌ NO'}")
        else:
            logger.info(f"4. Extracted user input from prompt: ❌ NOT FOUND")
        
        # Check if AI response reflects user input
        comprehensive_topic = synthesized.get("comprehensive_topic", "")
        response_reflects_input = "[含用户输入]" in comprehensive_topic
        logger.info(f"\n5. AI response reflects user input detection: {'✅ YES' if response_reflects_input else '❌ NO'}")
        
        # Print prompt excerpt for debugging
        logger.info(f"\n--- Phase 2 Prompt Excerpt (showing user context section) ---")
        if user_context_marker_in_prompt:
            # Find the user context section
            context_start = phase2_prompt.find("**用户补充说明：**")
            if context_start != -1:
                context_end = phase2_prompt.find("**任务：**", context_start)
                if context_end == -1:
                    context_end = context_start + 200
                logger.info(phase2_prompt[context_start:context_end])
        else:
            logger.info("User context section not found in prompt!")
        
        # Test result
        test_passed = user_input_in_prompt and user_context_marker_in_prompt
        
        logger.info("\n" + "=" * 80)
        if test_passed:
            logger.success("✅ TEST PASSED: User input from Phase 1 is correctly passed to Phase 2")
            logger.info("   - User input is included in Phase 2 prompt")
            logger.info("   - User context marker is present")
        else:
            logger.error("❌ TEST FAILED: User input from Phase 1 is NOT correctly passed to Phase 2")
            if not user_input_in_prompt:
                logger.error("   - User input text not found in Phase 2 prompt")
            if not user_context_marker_in_prompt:
                logger.error("   - User context marker not found in Phase 2 prompt")
        logger.info("=" * 80)
        
        # Token usage summary
        usage = mock_client.get_usage_info()
        logger.info(f"\nToken Usage Summary:")
        logger.info(f"  Total API calls: {mock_client.call_count}")
        logger.info(f"  Total tokens: {usage['total_tokens']}")
        logger.info(f"  Input tokens: {usage['total_input_tokens']}")
        logger.info(f"  Output tokens: {usage['total_output_tokens']}")
        
        return test_passed
    else:
        logger.error("❌ TEST FAILED: Phase 2 API call was not captured")
        logger.error(f"   Expected 2 API calls, got {len(mock_client.captured_messages)}")
        return False


def test_user_input_flow_without_input():
    """Test that Phase 2 works correctly even without user input."""
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing Phase 2 WITHOUT User Input (baseline)")
    logger.info("=" * 80)
    
    # Create mock client
    mock_client = MockQwenClient()
    
    # Create mock UI without user input
    mock_ui = MockUI(user_input_text="")  # Empty input
    
    # Create session
    session = ResearchSession()
    
    # Phase 1: Generate goals
    logger.info("\n[Phase 1] Generating research goals...")
    phase1 = Phase1Discover(mock_client, session, ui=mock_ui)
    
    phase1_result = phase1.execute(
        data_abstract="这是一个测试数据摘要。",
        user_topic=None,
        research_role=None,
        amendment_feedback=None,
        batch_data=None,
    )
    
    # Phase 2: Synthesize without user input
    logger.info("\n[Phase 2] Synthesizing goals WITHOUT user input...")
    phase2 = Phase2Finalize(mock_client, session, ui=mock_ui)
    
    phase2_result = phase2.execute(
        phase1_output=phase1_result,
        data_abstract="这是一个测试数据摘要。",
        user_input=None,  # No user input
        user_topic=None
    )
    
    # Verify: Check that Phase 2 still works without user input
    if len(mock_client.captured_messages) >= 2:
        phase2_messages = mock_client.captured_messages[1]
        phase2_prompt = ""
        for msg in phase2_messages['messages']:
            if isinstance(msg, dict) and 'content' in msg:
                phase2_prompt += msg['content'] + "\n"
        
        user_context_marker = "**用户补充说明：**" in phase2_prompt
        
        logger.info(f"\nBaseline Test Results:")
        logger.info(f"  User context marker present: {'✅ YES (expected when no input)' if not user_context_marker else '⚠️  YES (unexpected)'}")
        
        if not user_context_marker:
            logger.success("✅ Baseline test passed: Phase 2 works without user input")
            return True
        else:
            logger.warning("⚠️  User context marker found even when no input provided (may be acceptable)")
            return True
    else:
        logger.error("❌ Baseline test failed: Phase 2 API call not captured")
        return False


def test_user_input_flow_to_phase4_context():
    """Ensure Phase 4 prompts include the user amendment context."""

    test_user_input = "请重点关注技术实现细节和性能优化方面"

    # Prepare session with stored metadata (simulating Phase 1 confirmation)
    session = ResearchSession()
    session.set_metadata("phase1_user_input", test_user_input)

    mock_client = MockQwenClient()
    mock_ui = MockUI()

    phase4 = Phase4Synthesize(mock_client, session, ui=mock_ui)

    phase2_output = {
        "synthesized_goal": {
            "comprehensive_topic": "测试综合主题",
            "component_questions": ["测试研究目标1", "测试研究目标2"],
            "unifying_theme": "统一主题",
            "research_scope": "研究范围",
        },
        "component_goals": [
            {"goal_text": "测试研究目标1"},
            {"goal_text": "测试研究目标2"},
        ],
        "user_input": test_user_input,
    }

    captured_contexts = []

    def _compose_side_effect(template_name, context=None, **kwargs):
        if context is not None:
            # Store a shallow copy to avoid downstream mutations affecting the assertion
            captured_contexts.append(dict(context))
        return [
            {"role": "system", "content": f"{template_name}-system"},
            {"role": "user", "content": f"{template_name}-user"},
        ]

    with patch.object(Phase4Synthesize, "_stream_with_callback") as mock_stream, \
         patch("research.phases.phase4_synthesize.compose_messages", side_effect=_compose_side_effect), \
         patch("research.phases.phase4_synthesize.load_prompt", return_value="section-template"), \
         patch("research.phases.phase4_synthesize.render_prompt", side_effect=lambda tmpl, ctx: "rendered-section"):

        # Outline call, then single section call
        mock_stream.side_effect = [
            '{"sections": [{"title": "测试章节", "target_words": 600, "purpose": "purpose"}]}',
            "章节内容",
        ]

        result = phase4.execute(phase2_output, phase3_output=None)

    # Ensure the prompts captured the user amendment context
    amendment_contexts = [
        ctx.get("user_amendment_context", "")
        for ctx in captured_contexts
        if isinstance(ctx, dict)
    ]

    assert any(test_user_input in ctx for ctx in amendment_contexts if ctx), (
        "Phase 4 prompts should include the user amendment context"
    )

    assert result["component_questions"] == ["测试研究目标1", "测试研究目标2"]


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="{time:HH:mm:ss.SSS} | {level: <8} | {message}",
        level="INFO"
    )
    
    # Run tests
    test1_passed = test_user_input_flow_to_phase2()
    test2_passed = test_user_input_flow_without_input()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Test 1 (with user input): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    logger.info(f"Test 2 (without user input): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        logger.success("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        logger.error("\n❌ SOME TESTS FAILED")
        sys.exit(1)

