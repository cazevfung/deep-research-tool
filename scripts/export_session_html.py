"""Export a session JSON to HTML with filename based on research title."""
import json
import sys
import re
import os
from pathlib import Path
from typing import Tuple

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


def export_session_html(session_id: str, output_dir: str = "downloads", force_regenerate: bool = False) -> Tuple[Path, bool]:
    """
    Export session to HTML with filename based on research title.
    
    Args:
        session_id: The session ID to export
        output_dir: Directory to save the HTML file (default: "downloads")
        force_regenerate: If True, regenerate even if cached file exists
    
    Returns:
        Tuple of (Path to HTML file, was_cached: bool)
        was_cached is True if existing file was used, False if new file was generated
    
    Caching:
        - Checks if HTML file already exists
        - Regenerates only if session JSON is newer than HTML file
        - Use force_regenerate=True to bypass cache
    """
    project_root = Path(__file__).parent.parent
    session_file = project_root / "data" / "research" / "sessions" / f"session_{session_id}.json"
    
    if not session_file.exists():
        raise FileNotFoundError(f"Session file not found: {session_file}")
    
    # Get research title
    research_title = get_research_title(session_file)
    
    # Sanitize title for filename
    filename_title = sanitize_filename(research_title)
    output_filename = f"有料到 - {filename_title}.html"
    
    # Ensure output_dir is absolute
    if not Path(output_dir).is_absolute():
        output_dir = project_root / output_dir
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    
    # Check if file already exists and is up-to-date
    was_cached = False
    if not force_regenerate and output_path.exists():
        # Compare modification times
        session_mtime = os.path.getmtime(session_file)
        html_mtime = os.path.getmtime(output_path)
        
        # If session is newer, regenerate; otherwise use cached
        if html_mtime >= session_mtime:
            was_cached = True
            print(f"Using cached HTML file: {output_path}")
            return (output_path, was_cached)
        else:
            print(f"Session file is newer, regenerating HTML...")
    
    # Generate HTML
    print(f"Generating HTML file: {output_path}")
    generate_html(session_id, str(output_path))
    
    print(f"Export complete! File: {output_path.absolute()}")
    return (output_path, was_cached)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_session_html.py <session_id> [output_dir] [--force]")
        print("Example: python export_session_html.py 20251113_181642")
        sys.exit(1)
    
    session_id = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else "downloads"
    force_regenerate = '--force' in sys.argv
    
    try:
        output_path, was_cached = export_session_html(session_id, output_dir, force_regenerate)
        if was_cached:
            print(f"\n✓ Used cached file: {output_path}")
        else:
            print(f"\n✓ Generated new file: {output_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

