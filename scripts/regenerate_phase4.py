"""Script to regenerate Phase 4 from an existing session file."""

import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from research.agent import DeepResearchAgent
from research.session import ResearchSession
from core.config import Config
from loguru import logger


def main():
    """Main entry point for regenerating Phase 4."""
    parser = argparse.ArgumentParser(description="Regenerate Phase 4 from an existing session")
    parser.add_argument(
        "session_id",
        help="Session ID to regenerate Phase 4 for (e.g., 20251113_181642)"
    )
    parser.add_argument(
        "--api-key",
        "-k",
        help="Qwen API key (or set DASHSCOPE_API_KEY env var)"
    )
    parser.add_argument(
        "--base-url",
        help="API base URL (default: Beijing region)",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Model name (overrides config.yaml)",
        default=None
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force regeneration even if Phase 4 already exists"
    )
    
    args = parser.parse_args()
    
    # Read model from config.yaml if not provided via CLI
    model = args.model
    if model is None:
        try:
            config = Config()
            model = config.get("qwen.model", "qwen3-max")
            logger.info(f"Using model from config.yaml: {model}")
        except Exception:
            model = "qwen3-max"  # Fallback default
            logger.info(f"Using default model: {model}")
    
    # Load session
    try:
        logger.info(f"Loading session: {args.session_id}")
        session = ResearchSession.load(args.session_id)
        logger.success(f"Session loaded successfully")
    except FileNotFoundError as e:
        logger.error(f"Session file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading session: {e}")
        sys.exit(1)
    
    # Get batch_id from session metadata
    batch_id = session.get_metadata("batch_id")
    if not batch_id:
        logger.error("Session does not have a batch_id. Cannot regenerate Phase 4.")
        sys.exit(1)
    
    # Get required phase artifacts
    phase2_artifact = session.get_phase_artifact("phase2")
    phase3_artifact = session.get_phase_artifact("phase3")
    
    if not phase2_artifact:
        logger.error("Session does not have Phase 2 artifact. Cannot regenerate Phase 4.")
        logger.info("Phase 4 requires Phase 2 (synthesized goal) output.")
        sys.exit(1)
    
    if not phase3_artifact:
        logger.error("Session does not have Phase 3 artifact. Cannot regenerate Phase 4.")
        logger.info("Phase 4 requires Phase 3 (research findings) output.")
        sys.exit(1)
    
    logger.info("Phase 2 artifact found")
    logger.info("Phase 3 artifact found")
    
    # Initialize agent
    try:
        agent = DeepResearchAgent(
            api_key=args.api_key,
            base_url=args.base_url,
            model=model
        )
        
        logger.info("Starting Phase 4 regeneration...")
        
        # Run Phase 4
        result = agent.run_phase4_synthesize(
            session=session,
            phase2_artifact=phase2_artifact,
            phase3_artifact=phase3_artifact,
            batch_id=batch_id,
            force=args.force
        )
        
        if result.get("report_path"):
            logger.success(f"Phase 4 regeneration completed successfully!")
            logger.info(f"Report saved to: {result.get('report_path')}")
            
            additional_paths = result.get("additional_report_paths", [])
            if additional_paths:
                logger.info("Additional report paths:")
                for path in additional_paths:
                    logger.info(f"  - {path}")
            
            logger.info("")
            logger.info("=" * 60)
            logger.success("PHASE 4 REGENERATION COMPLETE")
            logger.info("=" * 60)
            sys.exit(0)
        else:
            logger.warning("Phase 4 completed but no report path was returned")
            sys.exit(1)
    
    except KeyboardInterrupt:
        logger.warning("Phase 4 regeneration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Phase 4 regeneration failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

