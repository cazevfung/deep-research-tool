"""Console interface for research agent."""

import sys
from typing import Dict, Any, Optional, Callable
from loguru import logger


class ConsoleInterface:
    """Console-based user interface with streaming display."""
    
    def __init__(self):
        """Initialize console interface."""
        self.stream_buffers: dict[str, str] = {}
        self.stream_callback = None
    
    def display_message(self, message: str, level: str = "info"):
        """
        Display a message to the console.
        
        Args:
            message: Message text
            level: Message level (info, success, warning, error)
        """
        symbols = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✗"
        }
        symbol = symbols.get(level, "•")
        try:
            print(f"{symbol} {message}")
        except UnicodeEncodeError:
            # Fallback to ASCII-safe symbols for Windows console
            ascii_symbols = {
                "info": "[i]",
                "success": "[+]",
                "warning": "[!]",
                "error": "[x]"
            }
            symbol = ascii_symbols.get(level, "[*]")
            print(f"{symbol} {message}")
    
    def display_header(self, title: str):
        """Display a section header."""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")
    
    def display_progress(self, status: Dict[str, Any]):
        """Display progress information."""
        progress = status.get("progress_percentage", 0)
        current_step = status.get("current_step_id")
        current_goal = status.get("current_step_goal")
        
        if current_step:
            print(f"\r[进度: {progress:.1f}%] 步骤 {current_step}: {current_goal[:50]}...", end="", flush=True)
    
    def display_stream(self, token: str, stream_id: str):
        """
        Display streaming token.
        
        Args:
            token: Token from stream
        """
        sys.stdout.write(token)
        sys.stdout.flush()
        if not stream_id:
            stream_id = "default"
        self.stream_buffers[stream_id] = self.stream_buffers.get(stream_id, "") + token
    
    def clear_stream_buffer(self, stream_id: Optional[str] = None):
        """Clear the streaming buffer."""
        if stream_id is None:
            self.stream_buffers.clear()
        else:
            self.stream_buffers.pop(stream_id, None)
    
    def get_stream_buffer(self, stream_id: Optional[str] = None) -> str:
        """Get current stream buffer contents."""
        if stream_id is None:
            if not self.stream_buffers:
                return ""
            last_stream = next(reversed(self.stream_buffers))
            return self.stream_buffers.get(last_stream, "")
        return self.stream_buffers.get(stream_id, "")
    
    def notify_stream_start(self, stream_id: str, stream_phase: str, metadata: Dict[str, Any]):
        """
        Notify that a stream has started.
        
        Args:
            stream_id: Unique stream identifier
            stream_phase: Phase name
            metadata: Stream metadata
        """
        # No-op for console interface
        pass
    
    def notify_stream_end(self, stream_id: str, stream_phase: str, metadata: Dict[str, Any]):
        """
        Notify that a stream has ended.
        
        Args:
            stream_id: Unique stream identifier
            stream_phase: Phase name
            metadata: Stream metadata
        """
        # No-op for console interface
        pass
    
    def prompt_user(self, prompt: str, choices: Optional[list] = None) -> str:
        """
        Prompt user for input.
        
        Args:
            prompt: Prompt text
            choices: Optional list of valid choices
            
        Returns:
            User input
        """
        while True:
            user_input = input(f"\n{prompt}: ").strip()
            
            if not choices:
                return user_input
            
            if user_input in choices:
                return user_input
            
            print(f"无效输入。请选择: {', '.join(choices)}")
    
    def display_goals(self, goals: list):
        """Display research goals for user selection."""
        print("\n" + "=" * 60)
        print("  可用的研究目标：")
        print("=" * 60)
        
        for goal in goals:
            goal_id = goal.get("id")
            goal_text = goal.get("goal_text", "")
            print(f"\n  [{goal_id}] {goal_text}")
        
        print("\n" + "=" * 60)
    
    def display_synthesized_goal(self, synthesized_goal: Dict[str, Any]):
        """
        Display the synthesized comprehensive topic and component questions.
        
        Args:
            synthesized_goal: Dictionary containing comprehensive_topic, 
                            component_questions, unifying_theme, research_scope
        """
        comprehensive_topic = synthesized_goal.get("comprehensive_topic", "")
        component_questions = synthesized_goal.get("component_questions", [])
        unifying_theme = synthesized_goal.get("unifying_theme", "")
        
        print("\n" + "=" * 60)
        print("  综合研究主题")
        print("=" * 60)
        print(f"\n{comprehensive_topic}")
        
        if unifying_theme:
            print(f"\n统一主题: {unifying_theme}")
        
        if component_questions:
            print("\n组成问题:")
            for i, question in enumerate(component_questions, 1):
                print(f"  {i}. {question}")
        print("=" * 60)
    
    def display_plan(self, plan: list):
        """Display research plan."""
        print("\n研究计划：")
        print("-" * 60)
        
        for step in plan:
            step_id = step.get("step_id")
            goal = step.get("goal", "")
            required_data = step.get("required_data", "")
            
            print(f"\n步骤 {step_id}: {goal}")
            print(f"  需要数据: {required_data}")
    
    def display_report(self, report: str, save_path: Optional[str] = None):
        """
        Display final report.
        
        Args:
            report: Report text (Markdown)
            save_path: Optional path where report was saved
        """
        print("\n" + "=" * 60)
        print("  最终研究报告")
        print("=" * 60)
        print("\n" + report)
        
        if save_path:
            print(f"\n报告已保存到: {save_path}")

