"""Full integration test that runs the complete workflow:
1. Run all scrapers to gather content
2. Produce transcripts and comments saved in results folder
3. Run research agent to analyze the content
4. Produce research report saved in reports folder
"""
import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Try importing project modules
try:
    from research.agent import DeepResearchAgent
    from research.ui.mock_interface import MockConsoleInterface
    from core.config import Config
    from loguru import logger
    from tests.test_links_loader import TestLinksLoader
except ImportError as e:
    missing_module = str(e).split("'")[1] if "'" in str(e) else "unknown"
    print(f"\n❌ Missing runtime dependency: {missing_module}")
    print(f"   Please install all dependencies first:")
    print(f"   pip install -r requirements.txt")
    sys.exit(1)


def ensure_dependency(module_name: str, package_name: str = None, version: str = None):
    """Ensure a Python module is available, installing it if necessary."""
    install_package = package_name if package_name is not None else module_name
    if version:
        install_package = f"{install_package}{version}"
    
    try:
        __import__(module_name)
    except ImportError:
        print(f"⚠️  {module_name} not found. Installing {install_package}...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--quiet", install_package
            ])
            print(f"✓ Successfully installed {install_package}")
            __import__(module_name)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {install_package}: {e}")
            sys.exit(1)


# Ensure pytest is available
ensure_dependency("pytest", version=">=7.0.0")
import pytest


def check_api_key() -> Optional[str]:
    """Check if API key is available from env var or config.yaml."""
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    
    if not api_key:
        try:
            config = Config()
            api_key = config.get("qwen.api_key")
        except Exception:
            pass
    
    return api_key


def run_all_scrapers(progress_callback=None) -> Dict[str, Any]:
    """
    Run all scraper tests to gather content.
    
    Args:
        progress_callback: Optional callable(message: dict) for progress updates.
                          If provided, will be called with progress messages.
    
    Returns:
        Dict with batch_id and success status
    """
    if progress_callback:
        progress_callback({"type": "scraping:start", "message": "开始抓取内容..."})
    else:
        print("\n" + "=" * 80)
        print("STEP 1: Running All Scrapers")
        print("=" * 80)
    
    # Import the test runner
    from tests.test_all_scrapers_and_save_json import test_all_scrapers_and_save
    
    # Run all scrapers with progress callback
    run_results = test_all_scrapers_and_save(progress_callback=progress_callback)
    
    # Get batch ID from test links
    loader = TestLinksLoader()
    batch_id = loader.get_batch_id()
    
    # Calculate success rate
    total = len(run_results)
    passed = sum(1 for r in run_results if r["returncode"] == 0)
    
    if progress_callback:
        progress_callback({
            "type": "scraping:complete",
            "message": f"抓取完成: {passed}/{total} 成功",
            "passed": passed,
            "total": total,
            "batch_id": batch_id
        })
    else:
        print("\n" + "=" * 80)
        print(f"Scrapers Summary: {passed}/{total} passed")
        print("=" * 80)
    
    return {
        "batch_id": batch_id,
        "passed": passed,
        "total": total,
        "success": passed > 0  # At least one scraper succeeded
    }


def verify_scraper_results(batch_id: str, progress_callback=None) -> bool:
    """
    Verify that scraper results exist in the results folder.
    
    Args:
        batch_id: The batch ID to check for
        progress_callback: Optional callable(message: dict) for progress updates.
        
    Returns:
        True if results exist, False otherwise
    """
    results_dir = project_root / "tests" / "results" / f"run_{batch_id}"
    
    if not results_dir.exists():
        message = f"❌ Results directory not found: {results_dir}"
        if progress_callback:
            progress_callback({"type": "error", "message": message})
        else:
            print(message)
        return False
    
    # Check for JSON files
    json_files = list(results_dir.glob("*.json"))
    
    if not json_files:
        message = f"❌ No JSON files found in {results_dir}"
        if progress_callback:
            progress_callback({"type": "error", "message": message})
        else:
            print(message)
        return False
    
    if progress_callback:
        progress_callback({
            "type": "verification:progress",
            "message": f"找到 {len(json_files)} 个结果文件",
            "file_count": len(json_files)
        })
    else:
        print(f"✓ Found {len(json_files)} JSON files in results directory")
    
    # List the files
    if not progress_callback:
        print("\nFiles found:")
        for json_file in sorted(json_files):
            file_size = json_file.stat().st_size
            print(f"  - {json_file.name} ({file_size:,} bytes)")

    # Create per-batch manifest for research agent discovery
    try:
        manifest = []
        for json_file in sorted(json_files):
            # Skip aggregate result files that are not content items if needed
            rel_path = json_file.name
            entry = {
                "relative_path": rel_path,
                "batch_id": batch_id,
                "size_bytes": json_file.stat().st_size
            }
            # Infer source, link_id, kind from filename when possible
            stem = json_file.stem
            parts = stem.split('_')
            if len(parts) >= 4:
                entry["source_prefix"] = parts[2]
                entry["kind"] = parts[-1]
                entry["link_id"] = '_'.join(parts[3:-1]) if len(parts) > 4 else parts[3]
            manifest.append(entry)

        manifest_path = results_dir / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            import json as _json
            _json.dump({
                "batch_id": batch_id,
                "items": manifest
            }, f, ensure_ascii=False, indent=2)
        if progress_callback:
            progress_callback({
                "type": "verification:complete",
                "message": f"验证完成: 已创建清单文件",
                "file_count": len(json_files)
            })
        else:
            print(f"\n✓ Wrote manifest: {manifest_path}")
    except Exception as e:
        message = f"⚠️  Failed to write manifest.json: {e}"
        if progress_callback:
            progress_callback({"type": "warning", "message": message})
        else:
            print(message)

    return True


def run_research_agent(batch_id: str, ui=None, progress_callback=None, user_topic: Optional[str] = None, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Run the research agent to analyze the gathered content.
    
    Args:
        batch_id: The batch ID to analyze
        ui: Optional UI interface. If provided, will be used instead of creating a new one.
            If None, will create appropriate UI based on environment.
        progress_callback: Optional callable(message: dict) for progress updates.
                         Note: This is separate from UI. If UI is provided with callbacks,
                         use that instead. This callback is for high-level progress only.
        user_topic: Optional user-specified research topic or guidance
        session_id: Optional session ID to resume an existing session instead of creating a new one
        
    Returns:
        Result dictionary from the research agent
    """
    if progress_callback:
        progress_callback({"type": "research:start", "message": "开始研究代理..."})
    else:
        print("\n" + "=" * 80)
        print("STEP 2: Running Research Agent")
        print("=" * 80)
    
    # Check API key
    api_key = check_api_key()
    if not api_key:
        message = "❌ API key not found. Cannot run research agent."
        if progress_callback:
            progress_callback({"type": "error", "message": message})
        else:
            print(message)
        return None
    
    # Create output directory
    output_dir = project_root / "tests" / "results" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create UI if not provided
    if ui is None:
        # Create UI: interactive by default; use mock in non-interactive mode
        env_non_interactive = os.getenv("NON_INTERACTIVE", "0").lower() in ("1", "true", "yes", "on")
        force_interactive = os.getenv("FORCE_INTERACTIVE", "0").lower() in ("1", "true", "yes", "on")
        non_interactive = env_non_interactive and not force_interactive

        if non_interactive:
            mock_ui = MockConsoleInterface(
                auto_select_goal_id=None,
                auto_confirm_plan=True,
                verbose=True
            )
            ui = mock_ui
        else:
            # Use the real console interface for role and amendment prompts
            from research.ui.console_interface import ConsoleInterface
            ui = ConsoleInterface()
    
    # Initialize agent
    if not progress_callback:
        print(f"\nInitializing Deep Research Agent for batch: {batch_id}")
    agent = DeepResearchAgent(
        api_key=api_key,
        ui=ui,
        additional_output_dirs=[str(output_dir)]
    )
    
    # Run research
    if not progress_callback:
        print("Starting research workflow...")
    start_time = time.time()
    
    result = agent.run_research(
        batch_id=batch_id,
        user_topic=user_topic,  # Pass user topic if provided
        session_id=session_id  # Pass session_id to resume existing session if provided
    )
    
    elapsed_time = time.time() - start_time
    
    # Verify completion
    if result.get("status") != "completed":
        message = f"❌ Research did not complete. Status: {result.get('status')}"
        if progress_callback:
            progress_callback({"type": "error", "message": message})
        else:
            print(message)
        return None
    
    if progress_callback:
        progress_callback({
            "type": "research:complete",
            "message": f"研究完成，耗时 {elapsed_time:.1f}秒",
            "elapsed_time": elapsed_time,
            "result": result
        })
    else:
        print(f"\n✓ Research workflow completed in {elapsed_time:.1f}s")
    
    # Return result
    return result


def verify_research_report(result: Dict[str, Any], batch_id: str) -> bool:
    """
    Verify that the research report was generated and saved correctly.
    
    Args:
        result: The result dictionary from the research agent
        batch_id: The batch ID
        
    Returns:
        True if report is valid, False otherwise
    """
    print("\n" + "=" * 80)
    print("STEP 3: Verifying Research Report")
    print("=" * 80)
    
    # Check for additional report paths
    if "additional_report_paths" not in result or not result["additional_report_paths"]:
        print("❌ No additional report paths found in result")
        return False
    
    report_path = Path(result["additional_report_paths"][0])
    
    if not report_path.exists():
        print(f"❌ Report file not found: {report_path}")
        return False
    
    # Read report content
    with open(report_path, 'r', encoding='utf-8') as f:
        report_content = f.read()
    
    # Verify report content
    checks = [
        (len(report_content) > 100, "Report content too short"),
        ("# 研究报告" in report_content or "# Research Report" in report_content, "Report missing title header"),
        (f"**批次ID**: {batch_id}" in report_content, "Report missing batch ID"),
        (result.get("selected_goal") and result["selected_goal"] in report_content, "Report missing selected goal"),
    ]
    
    all_passed = True
    for check, message in checks:
        if not check:
            print(f"❌ {message}")
            all_passed = False
    
    if all_passed:
        print("✓ All report checks passed")
        print(f"\nReport Details:")
        print(f"  - Path: {report_path}")
        print(f"  - Size: {len(report_content):,} characters")
        print(f"  - Goal: {result.get('selected_goal', 'N/A')[:80]}...")
        
        # Log usage if available
        if "usage" in result:
            usage = result["usage"]
            print(f"  - Tokens: {usage.get('total_tokens', 'N/A')}")
    
    return all_passed


def main():
    """Run the full integration test workflow."""
    print("\n" + "=" * 80)
    print("FULL WORKFLOW INTEGRATION TEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Run all scrapers
    scrapers_result = run_all_scrapers()
    
    if not scrapers_result["success"]:
        print("\n❌ Scrapers failed. Aborting workflow.")
        return False
    
    batch_id = scrapers_result["batch_id"]
    
    # Verify scraper results
    print("\n" + "=" * 80)
    print("Verifying Scraper Results")
    print("=" * 80)
    
    if not verify_scraper_results(batch_id):
        print("\n❌ Scraper results not found. Aborting workflow.")
        return False
    
    # Step 2: Run research agent
    research_result = run_research_agent(batch_id)
    
    if not research_result:
        print("\n❌ Research agent failed. Aborting workflow.")
        return False
    
    # Step 3: Verify research report
    if not verify_research_report(research_result, batch_id):
        print("\n❌ Research report verification failed.")
        return False
    
    # Success!
    print("\n" + "=" * 80)
    print("✓ FULL WORKFLOW INTEGRATION TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return True


if __name__ == "__main__":
    """Run the integration test directly."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # Check API key
    api_key = check_api_key()
    if not api_key:
        print("\n❌ Error: API key not found.")
        print("   Please set it in one of:")
        print("   1. Environment variable:")
        print("      export DASHSCOPE_API_KEY=your_key_here  # Linux/Mac")
        print("      set DASHSCOPE_API_KEY=your_key_here     # Windows")
        print("   2. config.yaml file:")
        print("      qwen:")
        print("        api_key: 'your_key_here'")
        sys.exit(1)
    
    # Run the workflow
    success = main()
    sys.exit(0 if success else 1)

