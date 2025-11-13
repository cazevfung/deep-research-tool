"""Export a session JSON to HTML with filename based on research title."""
import json
import sys
import re
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_export_html import generate_html


def sanitize_filename(title: str, max_length: int = 100) -> str:
    """Sanitize a title to make it a valid filename.
    
    Removes invalid characters for Windows filenames:
    < > : " / \\ | ? *
    """
    if not title:
        return "research_report"
    
    # Remove invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '', title)
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Trim whitespace
    sanitized = sanitized.strip()
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip()
    
    # If empty after sanitization, use default
    if not sanitized:
        return "research_report"
    
    return sanitized


def get_research_title(session_file: Path) -> str:
    """Extract research title from session JSON."""
    with open(session_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    metadata = data.get("metadata", {})
    
    # Try to get title from various sources
    # 1. Check synthesized_goal.comprehensive_topic (primary source)
    synthesized_goal = metadata.get("synthesized_goal", {})
    if synthesized_goal.get("comprehensive_topic"):
        return synthesized_goal["comprehensive_topic"]
    
    # 2. Check for explicit title field
    if "title" in metadata and metadata["title"]:
        return metadata["title"]
    
    # 3. Check user_topic
    if metadata.get("user_topic"):
        return metadata["user_topic"]
    
    # 4. Check selected_goal
    if metadata.get("selected_goal"):
        return metadata["selected_goal"]
    
    # 5. Use first goal from research_plan
    research_plan = metadata.get("research_plan", [])
    if research_plan and len(research_plan) > 0:
        first_goal = research_plan[0].get("goal", "")
        if first_goal:
            return first_goal
    
    # 5. Extract from final report (first line)
    phase4 = data.get("phase_artifacts", {}).get("phase4", {}).get("data", {})
    final_report = phase4.get("report_content") or phase4.get("final_report") or metadata.get("final_report", "")
    if final_report:
        # Get first line (before first period or newline)
        first_line = final_report.split('\n')[0].split('。')[0].split('.')[0]
        if first_line and len(first_line) > 10:  # Make sure it's meaningful
            return first_line.strip()
    
    # Default fallback
    return "研究报告"


def export_session_html(session_id: str, output_dir: str = "downloads"):
    """Export session to HTML with filename based on research title."""
    session_file = Path(__file__).parent.parent / "data" / "research" / "sessions" / f"session_{session_id}.json"
    
    if not session_file.exists():
        print(f"Error: Session file not found: {session_file}")
        sys.exit(1)
    
    # Get research title
    research_title = get_research_title(session_file)
    print(f"Research Title: {research_title}")
    
    # Sanitize title for filename
    filename_title = sanitize_filename(research_title)
    output_filename = f"{filename_title}.html"
    output_path = Path(output_dir) / output_filename
    
    print(f"Output file: {output_path}")
    
    # Generate HTML
    generate_html(session_id, str(output_path))
    
    print(f"\nExport complete!")
    print(f"   File: {output_path.absolute()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_session_html.py <session_id> [output_dir]")
        print("Example: python export_session_html.py 20251113_181642")
        sys.exit(1)
    
    session_id = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "downloads"
    
    export_session_html(session_id, output_dir)

