"""
Simplified workflow service using proven test functions.

This service uses the working code from tests/ folder directly,
with WebSocket progress callbacks for real-time updates.
"""
from typing import Dict, Optional, Any, List
from pathlib import Path
import sys
import asyncio
import queue
import time
import os
import json
from collections import defaultdict
from loguru import logger

# Ensure Playwright can spawn subprocesses on Windows by defaulting to Proactor policy.
if os.name == "nt":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.debug("Set WindowsProactorEventLoopPolicy for Playwright compatibility")
    except Exception as policy_err:  # pragma: no cover - defensive
        logger.warning(f"Could not set WindowsProactorEventLoopPolicy: {policy_err}")

# Debug mode flag
DEBUG_MODE = os.environ.get('WORKFLOW_DEBUG', 'false').lower() == 'true'

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Import working test functions via backend.lib
from backend.lib import (
    run_all_scrapers,
    run_all_scrapers_direct,  # Direct execution with progress callbacks
    verify_scraper_results,
    run_research_agent,
)
from research.agent import DeepResearchAgent
from research.session import ResearchSession
from app.websocket.manager import WebSocketManager
from app.services.progress_service import ProgressService
from app.services.conversation_service import ConversationContextService
from app.services.websocket_ui import WebSocketUI
from datetime import datetime


# Process count per link type
PROCESSES_PER_LINK_TYPE = {
    'youtube': 2,      # transcript + comments
    'bilibili': 2,    # transcript + comments
    'reddit': 1,
    'article': 1
}


def calculate_total_scraping_processes(links_by_type: Dict[str, list]) -> Dict[str, Any]:
    """
    Calculate total number of scraping processes from links.
    
    This is the single source of truth for calculating total processes.
    
    Args:
        links_by_type: Dict mapping link_type -> list of {id, url} dicts
            Example: {
                'youtube': [{'id': 'yt1', 'url': '...'}, ...],
                'bilibili': [{'id': 'bili1', 'url': '...'}, ...],
                'reddit': [{'id': 'rd1', 'url': '...'}, ...],
                'article': [{'id': 'art1', 'url': '...'}, ...]
            }
    
    Returns:
        Dict with:
            - total_processes: int (total count)
            - total_links: int (total link count)
            - breakdown: Dict[str, int] (processes per type)
            - link_breakdown: Dict[str, int] (links per type)
            - process_mapping: List[Dict] (detailed process list)
    """
    total_links = sum(len(links) for links in links_by_type.values())
    
    breakdown = {}
    link_breakdown = {}
    process_mapping = []
    
    for link_type, links in links_by_type.items():
        link_count = len(links)
        process_count = link_count * PROCESSES_PER_LINK_TYPE.get(link_type, 1)
        
        link_breakdown[link_type] = link_count
        breakdown[link_type] = process_count
        
        # Build detailed process mapping
        if link_type in ['youtube', 'bilibili']:
            # Each link generates 2 processes (transcript + comments)
            for link_info in links:
                # Transcript process
                process_mapping.append({
                    'link_id': link_info.get('id') or link_info.get('link_id'),
                    'url': link_info.get('url'),
                    'scraper_type': link_type,
                    'process_type': 'transcript'
                })
                # Comments process
                link_id = link_info.get('id') or link_info.get('link_id')
                process_mapping.append({
                    'link_id': f"{link_id}_comments",
                    'url': link_info.get('url'),
                    'scraper_type': f'{link_type}comments',
                    'process_type': 'comments'
                })
        else:
            # Reddit and Article: 1 process per link
            for link_info in links:
                process_mapping.append({
                    'link_id': link_info.get('id') or link_info.get('link_id'),
                    'url': link_info.get('url'),
                    'scraper_type': link_type,
                    'process_type': 'transcript'
                })
    
    expected_total = sum(breakdown.values())
    
    return {
        'expected_total': expected_total,  # Standardized name - total scraping processes expected
        'total_processes': expected_total,  # Keep for backward compatibility (deprecated)
        'total_links': total_links,
        'breakdown': breakdown,
        'link_breakdown': link_breakdown,
        'process_mapping': process_mapping
    }


def _run_scrapers_in_thread(progress_callback, batch_id, cancellation_checker=None):
    """
    Wrapper function to run scrapers in a thread with proper Playwright initialization.
    
    This ensures Playwright/Chromium can be launched properly when called from asyncio.to_thread().
    The function runs in a separate thread, so Playwright can initialize its browser process.
    
    Args:
        progress_callback: Progress callback function
        batch_id: Batch ID
        cancellation_checker: Optional function that returns True if cancelled
        
    Returns:
        Result dictionary from run_all_scrapers_direct
    """
    try:
        # Ensure we're in a proper thread context
        import threading
        import os
        current_thread = threading.current_thread()
        logger.info(f"Running scrapers in thread: {current_thread.name} (ID: {current_thread.ident})")
        
        # Log environment info for debugging
        logger.debug(f"Current working directory: {os.getcwd()}")
        logger.debug(f"Python executable: {sys.executable}")
        logger.debug(f"Thread name: {current_thread.name}")

        # On Windows, ensure we use a Proactor event loop so Playwright can spawn subprocesses.
        # Uvicorn's reload mode switches the global policy to WindowsSelectorEventLoopPolicy,
        # which breaks asyncio.create_subprocess_exec used by Playwright.
        if os.name == "nt":
            try:
                from asyncio import windows_events  # type: ignore
                current_loop: Optional[asyncio.AbstractEventLoop] = None
                try:
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    current_loop = None

                if current_loop and current_loop.is_running():
                    logger.debug("Existing event loop already running; skipping loop swap")
                elif current_loop and isinstance(current_loop, windows_events.ProactorEventLoop):
                    logger.debug("ProactorEventLoop already configured for this thread")
                else:
                    if current_loop is not None:
                        try:
                            current_loop.close()
                        except Exception:
                            pass
                    proactor_loop = windows_events.ProactorEventLoop()
                    asyncio.set_event_loop(proactor_loop)
                    logger.debug("Configured ProactorEventLoop for Playwright compatibility on Windows")
            except Exception as loop_err:  # pragma: no cover - best effort safeguard
                logger.warning(f"Could not configure ProactorEventLoop on Windows: {loop_err}")
        
        # Ensure Playwright can find its browser
        # Check if PLAYWRIGHT_BROWSERS_PATH is set
        playwright_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        if playwright_path:
            logger.debug(f"PLAYWRIGHT_BROWSERS_PATH: {playwright_path}")
        else:
            logger.debug("PLAYWRIGHT_BROWSERS_PATH not set (using default)")
        
        # Run the scrapers - Playwright will initialize in this thread
        logger.info(f"Starting scrapers execution in thread...")
        result = run_all_scrapers_direct(
            progress_callback=progress_callback,
            batch_id=batch_id,
            cancellation_checker=cancellation_checker
        )
        
        logger.info(f"Scrapers completed in thread: {current_thread.name}")
        return result
        
    except Exception as e:
        logger.error(f"Error running scrapers in thread: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


class WorkflowService:
    """
    Simplified workflow service using proven test functions.
    
    This service directly uses the working code from tests/ folder,
    with progress callbacks for real-time WebSocket updates.
    """
    
    def __init__(self, websocket_manager: WebSocketManager):
        self.ws_manager = websocket_manager
        self.progress_service = ProgressService(websocket_manager)
        self.conversation_service = ConversationContextService()
        self.ws_manager.set_conversation_service(self.conversation_service)
        # Track link context for progress callbacks
        # Maps batch_id -> scraper_type -> list of {link_id, url}
        self.link_context: Dict[str, Dict[str, list]] = {}
        
        # Track total counts per batch
        # Maps batch_id -> {
        #     'total_processes': int,
        #     'total_links': int,
        #     'breakdown': Dict[str, int],
        #     'link_breakdown': Dict[str, int],
        #     'calculated_at': datetime,
        #     'source': 'user_input' | 'test_links_loader'
        # }
        self.batch_totals: Dict[str, Dict[str, Any]] = {}
        
        # Debug tracking
        if DEBUG_MODE:
            self._queue_stats: Dict[str, Dict] = defaultdict(lambda: {
                'messages_processed': 0,
                'messages_dropped': 0,
                'max_queue_size': 0,
                'queue_size_history': [],
                'processing_times': []
            })
            self._link_id_transformations: Dict[str, list] = defaultdict(list)
            self._message_sequence: Dict[str, int] = defaultdict(int)

    def _normalize_phase_key(self, phase: str) -> str:
        phase = (phase or "").lower()
        mapping = {
            "phase0.5": "phase0_5",
            "phase0-5": "phase0_5",
            "phase0_5": "phase0_5",
        }
        normalized = mapping.get(phase, phase)
        valid = {"phase0", "phase0_5", "phase1", "phase2", "phase3", "phase4"}
        if normalized not in valid:
            raise ValueError(f"Unsupported phase '{phase}'")
        return normalized

    def _resolve_phase_sequence(self, phase: str, rerun_downstream: bool = True) -> List[str]:
        order = ["phase0", "phase0_5", "phase1", "phase2", "phase3", "phase4"]
        phase_key = self._normalize_phase_key(phase)
        if phase_key not in order:
            raise ValueError(f"Unsupported phase '{phase}'")
        if not rerun_downstream:
            return [phase_key]
        start_index = order.index(phase_key)
        return order[start_index:]

    def _load_artifact(self, session: ResearchSession, cache: Dict[str, Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
        if key in cache:
            return cache[key]
        cached = session.get_phase_artifact(key)
        if cached:
            cache[key] = cached
        return cached

    def _execute_phase_sequence(
        self,
        *,
        agent: DeepResearchAgent,
        session: ResearchSession,
        batch_id: str,
        user_topic: Optional[str],
        phases: List[str],
    ) -> Dict[str, Any]:
        artifacts: Dict[str, Dict[str, Any]] = {}

        if user_topic is None:
            user_topic = session.get_metadata("user_topic", None)

        for phase_name in phases:
            if phase_name == "phase0":
                artifacts["phase0"] = agent.run_phase0_prepare(
                    batch_id=batch_id,
                    session=session,
                    force=True,
                )
            elif phase_name == "phase0_5":
                phase0 = artifacts.get("phase0") or self._load_artifact(session, artifacts, "phase0")
                if not phase0:
                    raise ValueError("Phase 0 artifacts missing; cannot rerun Phase 0.5")
                artifacts["phase0_5"] = agent.run_phase0_5_role_generation(
                    session=session,
                    combined_abstract=phase0["combined_abstract"],
                    user_topic=user_topic,
                    force=True,
                )
            elif phase_name == "phase1":
                phase0 = artifacts.get("phase0") or self._load_artifact(session, artifacts, "phase0")
                if not phase0:
                    raise ValueError("Phase 0 artifacts missing; cannot rerun Phase 1")
                phase0_5 = artifacts.get("phase0_5") or self._load_artifact(session, artifacts, "phase0_5")
                batch_data = phase0["batch_data"]
                artifacts["phase1"] = agent.run_phase1_discover(
                    session=session,
                    combined_abstract=phase0["combined_abstract"],
                    user_topic=user_topic,
                    research_role=phase0_5.get("research_role") if phase0_5 else None,
                    pre_role_feedback=(phase0_5 or {}).get("pre_role_feedback"),
                    batch_data=batch_data,
                    force=True,
                )
            elif phase_name == "phase2":
                phase0 = artifacts.get("phase0") or self._load_artifact(session, artifacts, "phase0")
                phase1_artifact = artifacts.get("phase1") or self._load_artifact(session, artifacts, "phase1")
                phase0_5 = artifacts.get("phase0_5") or self._load_artifact(session, artifacts, "phase0_5")
                if not phase0 or not phase1_artifact:
                    raise ValueError("Phase 0 and Phase 1 artifacts required for Phase 2 rerun")
                artifacts["phase2"] = agent.run_phase2_synthesize(
                    session=session,
                    phase1_artifact=phase1_artifact,
                    combined_abstract=phase0["combined_abstract"],
                    user_topic=user_topic,
                    pre_role_feedback=(phase0_5 or {}).get("pre_role_feedback"),
                    force=True,
                )
            elif phase_name == "phase3":
                phase0 = artifacts.get("phase0") or self._load_artifact(session, artifacts, "phase0")
                phase2_artifact = artifacts.get("phase2") or self._load_artifact(session, artifacts, "phase2")
                if not phase0 or not phase2_artifact:
                    raise ValueError("Phase 0 and Phase 2 artifacts required for Phase 3 rerun")
                plan = phase2_artifact.get("plan", [])
                if not plan:
                    raise ValueError("Plan missing from Phase 2 artifacts")
                artifacts["phase3"] = agent.run_phase3_execute(
                    session=session,
                    plan=plan,
                    batch_data=phase0["batch_data"],
                    force=True,
                    require_confirmation=False,
                )
            elif phase_name == "phase4":
                phase2_artifact = artifacts.get("phase2") or self._load_artifact(session, artifacts, "phase2")
                phase3_artifact = artifacts.get("phase3") or self._load_artifact(session, artifacts, "phase3")
                if not phase2_artifact or not phase3_artifact:
                    raise ValueError("Phase 2 and Phase 3 artifacts required for Phase 4 rerun")
                artifacts["phase4"] = agent.run_phase4_synthesize(
                    session=session,
                    phase2_artifact=phase2_artifact,
                    phase3_artifact=phase3_artifact,
                    batch_id=batch_id,
                    force=True,
                )
            else:
                raise ValueError(f"Unsupported phase '{phase_name}'")

        return artifacts

    def _execute_phase3_step(
        self,
        *,
        agent: DeepResearchAgent,
        session: ResearchSession,
        batch_id: str,
        step_id: int,
        regenerate_report: bool,
    ) -> Dict[str, Any]:
        phase0 = session.get_phase_artifact("phase0")
        if not phase0:
            phase0 = agent.run_phase0_prepare(batch_id=batch_id, session=session, force=True)

        phase2 = session.get_phase_artifact("phase2")
        if not phase2 or not phase2.get("plan"):
            raise ValueError("Phase 2 artifacts missing or invalid; cannot rerun step")

        plan = phase2.get("plan", [])
        batch_data = phase0.get("batch_data", {})
        artifacts = {}

        artifacts["phase3"] = agent.rerun_phase3_step(
            session=session,
            plan=plan,
            batch_data=batch_data,
            step_id=step_id,
        )

        if regenerate_report:
            phase3 = artifacts["phase3"]
            artifacts["phase4"] = agent.run_phase4_synthesize(
                session=session,
                phase2_artifact=phase2,
                phase3_artifact=phase3,
                batch_id=batch_id,
                force=True,
            )

        return artifacts

    async def rerun_phase(
        self,
        batch_id: str,
        session_id: str,
        phase: str,
        *,
        rerun_downstream: bool = True,
        user_topic: Optional[str] = None,
    ):
        sequence = self._resolve_phase_sequence(phase, rerun_downstream)
        await self.ws_manager.broadcast(batch_id, {
            "type": "research:phase_rerun_started",
            "batch_id": batch_id,
            "session_id": session_id,
            "phase": sequence[0],
            "phases": sequence,
        })

        loop = asyncio.get_running_loop()
        ui = WebSocketUI(
            self.ws_manager,
            batch_id,
            main_loop=loop,
            conversation_service=self.conversation_service,
        )
        self.ws_manager.register_ui(batch_id, ui)

        try:
            agent = DeepResearchAgent(ui=ui)
            session = ResearchSession.load(session_id)
            artifacts = await asyncio.to_thread(
                self._execute_phase_sequence,
                agent=agent,
                session=session,
                batch_id=batch_id,
                user_topic=user_topic,
                phases=sequence,
            )
            response_payload: Dict[str, Any] = {
                "type": "research:phase_rerun_complete",
                "batch_id": batch_id,
                "session_id": session_id,
                "phase": sequence[0],
                "phases": sequence,
            }
            if "phase2" in artifacts:
                response_payload["plan"] = artifacts["phase2"].get("plan")
            if "phase4" in artifacts:
                response_payload["report_path"] = artifacts["phase4"].get("report_path")
                response_payload["additional_report_paths"] = artifacts["phase4"].get("additional_report_paths")
                response_payload["report_stale"] = False
                # If phase4 was rerun, send research:complete signal
                await self.ws_manager.broadcast(batch_id, {
                    "type": "research:complete",
                    "batch_id": batch_id,
                    "session_id": session_id,
                    "status": "completed",
                    "message": "研究完成",
                })
            elif "phase3" in artifacts:
                response_payload["report_stale"] = True
            await self.ws_manager.broadcast(batch_id, response_payload)
        except Exception as exc:
            logger.error(f"Phase rerun failed: {exc}", exc_info=True)
            await self.ws_manager.broadcast(batch_id, {
                "type": "research:phase_rerun_error",
                "batch_id": batch_id,
                "session_id": session_id,
                "phase": sequence[0],
                "message": str(exc),
            })
            raise
        finally:
            self.ws_manager.unregister_ui(batch_id)

    async def rerun_phase3_step(
        self,
        batch_id: str,
        session_id: str,
        step_id: int,
        *,
        regenerate_report: bool = True,
    ):
        await self.ws_manager.broadcast(batch_id, {
            "type": "research:step_rerun_started",
            "batch_id": batch_id,
            "session_id": session_id,
            "step_id": step_id,
            "regenerate_report": regenerate_report,
        })

        loop = asyncio.get_running_loop()
        ui = WebSocketUI(
            self.ws_manager,
            batch_id,
            main_loop=loop,
            conversation_service=self.conversation_service,
        )
        self.ws_manager.register_ui(batch_id, ui)

        try:
            agent = DeepResearchAgent(ui=ui)
            session = ResearchSession.load(session_id)
            artifacts = await asyncio.to_thread(
                self._execute_phase3_step,
                agent=agent,
                session=session,
                batch_id=batch_id,
                step_id=step_id,
                regenerate_report=regenerate_report,
            )

            response_payload: Dict[str, Any] = {
                "type": "research:step_rerun_complete",
                "batch_id": batch_id,
                "session_id": session_id,
                "step_id": step_id,
                "regenerate_report": regenerate_report,
            }
            if "phase3" in artifacts:
                response_payload["updated_phase3"] = {
                    "plan": artifacts["phase3"].get("plan"),
                    "plan_hash": artifacts["phase3"].get("plan_hash"),
                }
            if regenerate_report and "phase4" in artifacts:
                response_payload["report_path"] = artifacts["phase4"].get("report_path")
                response_payload["additional_report_paths"] = artifacts["phase4"].get("additional_report_paths")
                response_payload["report_stale"] = False
                # If report was regenerated, send research:complete signal
                await self.ws_manager.broadcast(batch_id, {
                    "type": "research:complete",
                    "batch_id": batch_id,
                    "session_id": session_id,
                    "status": "completed",
                    "message": "研究完成",
                })
            else:
                response_payload["report_stale"] = True
            await self.ws_manager.broadcast(batch_id, response_payload)
        except Exception as exc:
            logger.error(f"Step rerun failed: {exc}", exc_info=True)
            await self.ws_manager.broadcast(batch_id, {
                "type": "research:step_rerun_error",
                "batch_id": batch_id,
                "session_id": session_id,
                "step_id": step_id,
                "message": str(exc),
            })
            raise
        finally:
            self.ws_manager.unregister_ui(batch_id)
    
    async def _load_link_context(self, batch_id: str):
        """
        Load link context from TestLinksLoader for this batch_id.
        Also pre-registers all expected links in the progress service to ensure accurate total count.
        
        Args:
            batch_id: Batch ID to load links for
        """
        try:
            from tests.test_links_loader import TestLinksLoader
            loader = TestLinksLoader()
            
            # Verify batch_id matches
            loader_batch_id = loader.get_batch_id()
            if loader_batch_id != batch_id:
                logger.warning(f"Batch ID mismatch: loader has {loader_batch_id}, expected {batch_id}")
            
            # Build link context mapping: scraper_type -> list of {link_id, url}
            context: Dict[str, list] = {}
            all_expected_processes = []  # Collect all expected PROCESSES (not just links)
            
            for link_type in ['youtube', 'bilibili', 'reddit', 'article']:
                links = loader.get_links(link_type)
                link_list = [
                    {'link_id': link['id'], 'url': link['url']}
                    for link in links
                ]
                context[link_type] = link_list
                
                # Count expected processes based on link type:
                # - YouTube: transcript + comments = 2 processes per link
                # - Bilibili: transcript + comments = 2 processes per link
                # - Reddit: 1 process per link
                # - Article: 1 process per link
                if link_type in ['youtube', 'bilibili']:
                    # Each link generates 2 processes (transcript + comments)
                    for link_info in link_list:
                        # Transcript process
                        all_expected_processes.append({
                            'link_id': link_info['link_id'],
                            'url': link_info['url'],
                            'scraper_type': link_type,  # 'youtube' or 'bilibili'
                            'process_type': 'transcript'
                        })
                        # Comments process (use modified link_id to avoid collision)
                        all_expected_processes.append({
                            'link_id': f"{link_info['link_id']}_comments",
                            'url': link_info['url'],
                            'scraper_type': f'{link_type}comments',  # 'youtubecomments' or 'bilibilicomments'
                            'process_type': 'comments'
                        })
                else:
                    # Reddit and Article: 1 process per link
                    for link_info in link_list:
                        all_expected_processes.append({
                            'link_id': link_info['link_id'],
                            'url': link_info['url'],
                            'scraper_type': link_type,
                            'process_type': 'transcript'  # or 'article'/'reddit'
                        })
            
            self.link_context[batch_id] = context
            
            # Calculate total processes using centralized function
            totals = calculate_total_scraping_processes(context)
            total_links = totals['total_links']
            # Use expected_total as the standardized name (total_processes is deprecated but kept for backward compatibility)
            expected_total = totals['expected_total']
            
            # Store totals in batch_totals
            self.batch_totals[batch_id] = {
                'expected_total': expected_total,  # Standardized name - primary field
                'total_processes': expected_total,  # Deprecated - kept for backward compatibility
                'total_links': total_links,
                'breakdown': totals['breakdown'],
                'link_breakdown': totals['link_breakdown'],
                'calculated_at': datetime.now().isoformat(),
                'source': 'test_links_loader'
            }
            
            logger.info(f"Loaded link context for batch {batch_id}: {total_links} links → {expected_total} expected processes")
            
            # Debug: Log link context details
            if DEBUG_MODE:
                logger.debug(f"[CONTEXT] Batch {batch_id} link context:")
                for link_type, links in context.items():
                    logger.debug(f"  {link_type}: {len(links)} links")
                    for link in links:
                        logger.debug(f"    - {link['link_id']}: {link['url']}")
                
                logger.debug(f"[CONTEXT] Batch {batch_id} expected processes: {len(all_expected_processes)}")
                for proc in all_expected_processes:
                    logger.debug(
                        f"  - {proc['link_id']} ({proc['scraper_type']}, {proc['process_type']})"
                    )
            
            # Pre-register all expected processes in progress service
            # This ensures total count is accurate from the start, preventing premature completion
            registered_count = self.progress_service.initialize_expected_links(batch_id, all_expected_processes)
            logger.info(f"Pre-registered {registered_count} expected processes in progress tracker for batch {batch_id}")
            
            if DEBUG_MODE:
                if registered_count != expected_total:
                    logger.warning(
                        f"[CONTEXT] Mismatch: expected {expected_total} processes, "
                        f"registered {registered_count}"
                    )
            
            # Send batch:initialized message with total count
            # Use expected_total as primary field (consistent with scraping:status)
            # Keep total_processes temporarily for backward compatibility (can be removed later)
            await self.ws_manager.broadcast(batch_id, {
                'type': 'batch:initialized',
                'batch_id': batch_id,
                'expected_total': expected_total,  # Standardized name - primary field
                'total_processes': expected_total,  # Deprecated - kept for backward compatibility only
                'total_links': total_links,
                'breakdown': totals['breakdown'],
                'link_breakdown': totals['link_breakdown'],
                'timestamp': datetime.now().isoformat(),
                'message': f'已初始化批次，共 {expected_total} 个抓取任务'
            })
            
            # Send initial batch status update with correct total
            await self.progress_service._update_batch_status(batch_id)
            
        except Exception as e:
            logger.error(f"Failed to load link context: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Initialize empty context
            self.link_context[batch_id] = {}
    
    def _normalize_scraper_type(self, scraper_type: str) -> str:
        """
        Normalize scraper type to match link types in TestLinksLoader.
        
        Args:
            scraper_type: Scraper type from class name (e.g., 'youtubecomments', 'bilibilicomments')
            
        Returns:
            Normalized type (e.g., 'youtube', 'bilibili')
        """
        # Map comments scrapers to their base types
        if scraper_type == 'youtubecomments':
            return 'youtube'
        elif scraper_type == 'bilibilicomments':
            return 'bilibili'
        # Other types match directly
        return scraper_type
    
    def _find_link_info(self, batch_id: str, scraper_type: str, link_id: Optional[str] = None, url: Optional[str] = None):
        """
        Find link_id and url from context or provided parameters.
        
        Args:
            batch_id: Batch ID
            scraper_type: Scraper type (e.g., 'bilibili', 'youtube', 'youtubecomments')
            link_id: Optional link_id from progress message
            url: Optional url from progress message
            
        Returns:
            Tuple of (link_id, url) or (None, None) if not found
        """
        original_link_id = link_id
        original_url = url
        
        # If both provided, use them
        if link_id and url:
            if DEBUG_MODE:
                logger.debug(
                    f"[FIND_LINK] Using provided values: batch_id={batch_id}, "
                    f"scraper={scraper_type}, link_id={link_id}, url={url}"
                )
            return link_id, url
        
        # Normalize scraper type to match link types
        normalized_type = self._normalize_scraper_type(scraper_type)
        
        # Try to find from context
        if batch_id in self.link_context:
            links = self.link_context[batch_id].get(normalized_type, [])
            
            # If link_id provided, find matching url
            if link_id:
                for link in links:
                    if link['link_id'] == link_id:
                        result_link_id, result_url = link_id, link['url']
                        if DEBUG_MODE:
                            logger.debug(
                                f"[FIND_LINK] Found by link_id: batch_id={batch_id}, "
                                f"scraper={scraper_type}, link_id={result_link_id}, url={result_url}"
                            )
                        return result_link_id, result_url
            
            # If url provided, find matching link_id
            if url:
                for link in links:
                    if link['url'] == url:
                        result_link_id, result_url = link['link_id'], url
                        if DEBUG_MODE:
                            logger.debug(
                                f"[FIND_LINK] Found by url: batch_id={batch_id}, "
                                f"scraper={scraper_type}, link_id={result_link_id}, url={result_url}"
                            )
                        return result_link_id, result_url
            
            # If neither provided, try first link of this type
            if links:
                result_link_id, result_url = links[0]['link_id'], links[0]['url']
                if DEBUG_MODE:
                    logger.debug(
                        f"[FIND_LINK] Using first link: batch_id={batch_id}, "
                        f"scraper={scraper_type}, link_id={result_link_id}, url={result_url}"
                    )
                return result_link_id, result_url
        
        # Fallback: generate link_id from scraper_type
        if not link_id:
            link_id = f"{scraper_type}_unknown"
        if not url:
            url = f"unknown_{scraper_type}_url"
        
        if DEBUG_MODE:
            logger.warning(
                f"[FIND_LINK] Fallback used: batch_id={batch_id}, scraper={scraper_type}, "
                f"original_link_id={original_link_id}, original_url={original_url}, "
                f"fallback_link_id={link_id}, fallback_url={url}"
            )
        
        return link_id, url
    
    def _create_progress_callback(self, batch_id: str, message_queue: queue.Queue):
        """
        Create a sync progress callback that converts scraper format to ProgressService format.
        
        Args:
            batch_id: Batch ID for messages
            message_queue: Queue to put messages in
            
        Returns:
            Sync callback function
        """
        def progress_callback(message: dict):
            """Sync callback that converts and queues messages."""
            try:
                message_type = message.get('type', '')
                scraper_type = message.get('scraper', 'unknown')
                
                logger.info(f"[WorkflowService] Progress callback received: type={message_type}, scraper={scraper_type}, keys={list(message.keys())}")
                
                # Handle different message types from workflow_direct.py
                if message_type == 'scraping:start_link':
                    # Link just started - set stage based on scraper type
                    stage = 'loading'  # Initial stage for all scrapers
                    progress = 0.0
                    message_text = message.get('message', '')
                    callback_batch_id = message.get('batch_id') or batch_id
                    callback_link_id = message.get('link_id')
                    callback_url = message.get('url')
                    
                    # For comments scrapers, append '_comments' to link_id to match pre-registered IDs
                    original_link_id = callback_link_id
                    if scraper_type in ['youtubecomments', 'bilibilicomments']:
                        if callback_link_id and not callback_link_id.endswith('_comments'):
                            callback_link_id = f"{callback_link_id}_comments"
                            if DEBUG_MODE:
                                self._link_id_transformations[batch_id].append({
                                    'operation': 'scraping:start_link',
                                    'scraper': scraper_type,
                                    'original': original_link_id,
                                    'transformed': callback_link_id,
                                    'reason': 'comments_scraper_suffix'
                                })
                                logger.debug(
                                    f"[TRANSFORM] {original_link_id} -> {callback_link_id} "
                                    f"(scraper={scraper_type}, reason=comments_scraper_suffix)"
                                )
                    
                    logger.info(f"[WorkflowService] Processing scraping:start_link - stage={stage}, link_id={callback_link_id}, url={callback_url}, scraper={scraper_type}")
                    
                    # Get link context if not already provided
                    if not callback_link_id or not callback_url:
                        callback_link_id, callback_url = self._find_link_info(
                            callback_batch_id,
                            scraper_type,
                            callback_link_id,
                            callback_url
                        )
                        # Apply _comments suffix for comments scrapers after finding link info
                        if scraper_type in ['youtubecomments', 'bilibilicomments']:
                            if callback_link_id and not callback_link_id.endswith('_comments'):
                                callback_link_id = f"{callback_link_id}_comments"
                    
                    # Extract metadata
                    bytes_downloaded = message.get('bytes_downloaded', 0)
                    total_bytes = message.get('total_bytes', 0)
                    
                    # Convert to ProgressService format and queue
                    converted_message = {
                        'action': 'update_link_progress',
                        'batch_id': callback_batch_id,
                        'link_id': callback_link_id,
                        'url': callback_url,
                        'stage': stage,
                        'stage_progress': progress,
                        'overall_progress': progress,
                        'message': message_text,
                        'metadata': {
                            'bytes_downloaded': bytes_downloaded,
                            'total_bytes': total_bytes,
                            'source': scraper_type
                        }
                    }
                    message_queue.put_nowait(converted_message)
                    return  # Done processing this message
                    
                elif message_type == 'scraping:complete_link':
                    # Link completed (success or failed)
                    status = message.get('status', 'unknown')
                    if status == 'success':
                        stage = 'completed'
                        progress = 100.0
                    else:
                        stage = 'failed'
                        progress = 0.0
                    
                    callback_batch_id = message.get('batch_id') or batch_id
                    callback_link_id = message.get('link_id')
                    callback_url = message.get('url')
                    
                    # For comments scrapers, append '_comments' to link_id to match pre-registered IDs
                    original_link_id = callback_link_id
                    if scraper_type in ['youtubecomments', 'bilibilicomments']:
                        if callback_link_id and not callback_link_id.endswith('_comments'):
                            callback_link_id = f"{callback_link_id}_comments"
                            if DEBUG_MODE:
                                self._link_id_transformations[batch_id].append({
                                    'operation': 'scraping:complete_link',
                                    'scraper': scraper_type,
                                    'original': original_link_id,
                                    'transformed': callback_link_id,
                                    'reason': 'comments_scraper_suffix'
                                })
                                logger.debug(
                                    f"[TRANSFORM] {original_link_id} -> {callback_link_id} "
                                    f"(scraper={scraper_type}, reason=comments_scraper_suffix)"
                                )
                    
                    logger.info(f"[WorkflowService] Processing scraping:complete_link - status={status}, stage={stage}, link_id={callback_link_id}, scraper={scraper_type}")
                    
                    # Extract error message from the message or error field
                    error_msg = message.get('error') or (message.get('message', '').split(' - ')[-1] if ' - ' in message.get('message', '') else None)
                    message_text = message.get('message', '')
                    
                    # Get link context if not already provided
                    if not callback_link_id or not callback_url:
                        callback_link_id, callback_url = self._find_link_info(
                            callback_batch_id,
                            scraper_type,
                            callback_link_id,
                            callback_url
                        )
                        # Apply _comments suffix for comments scrapers after finding link info
                        if scraper_type in ['youtubecomments', 'bilibilicomments']:
                            if callback_link_id and not callback_link_id.endswith('_comments'):
                                callback_link_id = f"{callback_link_id}_comments"
                    
                    # Extract metadata
                    bytes_downloaded = message.get('bytes_downloaded', 0)
                    total_bytes = message.get('total_bytes', 0)
                    
                    # Convert to ProgressService format and queue
                    converted_message = {
                        'action': 'update_link_progress',
                        'batch_id': callback_batch_id,
                        'link_id': callback_link_id,
                        'url': callback_url,
                        'stage': stage,
                        'stage_progress': progress,
                        'overall_progress': progress,
                        'message': message_text,
                        'metadata': {
                            'bytes_downloaded': bytes_downloaded,
                            'total_bytes': total_bytes,
                            'source': scraper_type
                        }
                    }
                    message_queue.put_nowait(converted_message)
                    
                    # Update link status for both success and failed links
                    # This ensures frontend receives completion notifications
                    if status == 'success':
                        # Queue a status update for successful links
                        status_message = {
                            'action': 'update_link_status',
                            'batch_id': callback_batch_id,
                            'link_id': callback_link_id,
                            'url': callback_url,
                            'status': 'completed',
                            'error': None,
                            'metadata': {
                                'bytes_downloaded': bytes_downloaded,
                                'total_bytes': total_bytes,
                                'source': scraper_type
                            }
                        }
                        try:
                            message_queue.put_nowait(status_message)
                        except queue.Full:
                            pass
                    elif status == 'failed':
                        # Queue a status update for failed links
                        status_message = {
                            'action': 'update_link_status',
                            'batch_id': callback_batch_id,
                            'link_id': callback_link_id,
                            'url': callback_url,
                            'status': 'failed',
                            'error': error_msg or message_text
                        }
                        try:
                            message_queue.put_nowait(status_message)
                        except queue.Full:
                            pass
                    return  # Done processing this message
                    
                elif message_type in ['scraping:start', 'scraping:discover', 'scraping:complete', 'scraping:start_type']:
                    # Batch-level messages - don't convert to link progress, just broadcast
                    # These don't have link_id/url, so skip progress conversion
                    logger.info(f"[WorkflowService] Handling batch-level message: {message_type}")
                    try:
                        # Broadcast directly (these are handled by the frontend)
                        message_queue.put_nowait({
                            'action': 'broadcast',
                            'message': message
                        })
                    except queue.Full:
                        pass
                    return  # Don't process further for batch-level messages
                
                elif message_type == 'scraping:verify_completion':
                    # Request from scraping service to verify and send confirmation
                    # This is called after scraping:complete to ensure all processes are done
                    verify_batch_id = message.get('batch_id', batch_id)
                    logger.info(f"[VERIFY] Received verify_completion request for batch {verify_batch_id}")
                    if DEBUG_MODE:
                        logger.debug(
                            f"[VERIFY] Queueing verify_completion action for batch {verify_batch_id}, "
                            f"queue_size={message_queue.qsize()}"
                        )
                    try:
                        # Schedule async verification (can't await in sync callback)
                        # We'll queue a special action that the async processor will handle
                        message_queue.put_nowait({
                            'action': 'verify_completion',
                            'batch_id': verify_batch_id,
                            '_debug_timestamp': time.time()
                        })
                    except queue.Full:
                        logger.error(
                            f"[VERIFY] Queue full, cannot queue verify_completion for batch {verify_batch_id}"
                        )
                    return  # Don't process further - async handler will verify
                
                elif message_type == 'scraping:all_complete_confirmed':
                    # Confirmation signal - broadcast and mark as received
                    logger.info(f"[WorkflowService] Received scraping completion confirmation for batch {batch_id}")
                    try:
                        message_queue.put_nowait({
                            'action': 'broadcast',
                            'message': message
                        })
                    except queue.Full:
                        pass
                    return  # Don't process further for confirmation messages
                
                elif message_type.startswith('research:'):
                    # Research-related messages are batch-level, not link-level
                    # Don't convert to link progress - broadcast directly
                    logger.info(f"[WorkflowService] Handling research message: {message_type}")
                    try:
                        message_queue.put_nowait({
                            'action': 'broadcast',
                            'message': message
                        })
                    except queue.Full:
                        pass
                    return  # Don't process further for research messages
                    
                else:
                    # Direct progress report from scraper (has stage field)
                    # Or unknown message type - log it for debugging
                    if not message_type:
                        logger.warning(f"[WorkflowService] Received message without type field: {list(message.keys())}")
                    else:
                        logger.info(f"[WorkflowService] Handling unknown message type: {message_type}")
                    
                    stage = message.get('stage', 'unknown')
                    progress = message.get('progress', 0.0)
                    message_text = message.get('message', '')
                    callback_batch_id = message.get('batch_id') or batch_id
                    callback_link_id = message.get('link_id')
                    callback_url = message.get('url')
                    
                    # For comments scrapers, append '_comments' to link_id to match pre-registered IDs
                    original_link_id = callback_link_id
                    if scraper_type in ['youtubecomments', 'bilibilicomments']:
                        if callback_link_id and not callback_link_id.endswith('_comments'):
                            callback_link_id = f"{callback_link_id}_comments"
                            if DEBUG_MODE:
                                logger.debug(
                                    f"[TRANSFORM] {original_link_id} -> {callback_link_id} "
                                    f"(scraper={scraper_type}, reason=comments_scraper_suffix)"
                                )
                    
                    # Get link context if not already provided
                    if not callback_link_id or not callback_url:
                        callback_link_id, callback_url = self._find_link_info(
                            callback_batch_id,
                            scraper_type,
                            callback_link_id,
                            callback_url
                        )
                        # Apply _comments suffix for comments scrapers after finding link info
                        if scraper_type in ['youtubecomments', 'bilibilicomments']:
                            if callback_link_id and not callback_link_id.endswith('_comments'):
                                original_before_suffix = callback_link_id
                                callback_link_id = f"{callback_link_id}_comments"
                                if DEBUG_MODE:
                                    logger.debug(
                                        f"[TRANSFORM] {original_before_suffix} -> {callback_link_id} "
                                        f"(scraper={scraper_type}, reason=comments_scraper_suffix_after_find)"
                                    )
                    
                    # Extract metadata
                    bytes_downloaded = message.get('bytes_downloaded', 0)
                    total_bytes = message.get('total_bytes', 0)
                    
                    # Convert to ProgressService format and queue
                    converted_message = {
                        'action': 'update_link_progress',
                        'batch_id': callback_batch_id,
                        'link_id': callback_link_id,
                        'url': callback_url,
                        'stage': stage,
                        'stage_progress': progress,
                        'overall_progress': progress,
                        'message': message_text,
                        'metadata': {
                            'bytes_downloaded': bytes_downloaded,
                            'total_bytes': total_bytes,
                            'source': scraper_type
                        }
                    }
                    # Track message sequence
                    if DEBUG_MODE:
                        self._message_sequence[batch_id] += 1
                        converted_message['_debug_sequence'] = self._message_sequence[batch_id]
                        converted_message['_debug_timestamp'] = time.time()
                    
                    message_queue.put_nowait(converted_message)
            except queue.Full:
                queue_size = message_queue.qsize()
                logger.warning(
                    f"Progress queue full (size={queue_size}), dropping message: "
                    f"{message.get('type', 'unknown')}"
                )
                if DEBUG_MODE:
                    self._queue_stats[batch_id]['messages_dropped'] += 1
            except Exception as e:
                logger.error(
                    f"Error in progress callback (batch_id={batch_id}, "
                    f"message_type={message.get('type', 'unknown')}): {e}",
                    exc_info=True
                )
        
        return progress_callback
    
    async def wait_for_scraping_confirmation(
        self,
        progress_queue: queue.Queue,
        batch_id: str,
        max_wait_seconds: float = 15.0,
        check_interval: float = 0.2
    ) -> Dict:
        """
        Wait for scraping:all_complete_confirmed signal from scraping service.
        
        Args:
            progress_queue: Queue to check for confirmation message
            batch_id: Batch ID to wait for
            max_wait_seconds: Maximum time to wait (default: 60 seconds)
            check_interval: Time between checks (default: 0.5 seconds)
            
        Returns:
            Dict with confirmation details if received, or None if timeout
        """
        start_time = time.time()
        last_log_time = 0
        logger.info(f"Waiting for scraping completion confirmation for batch {batch_id}...")
        
        # Also check progress service directly as fallback
        confirmation_received = False
        confirmation_data = None
        
        while time.time() - start_time < max_wait_seconds:
            # Check queue for confirmation message
            try:
                # Peek at queue without removing items
                queue_items = []
                temp_items = []
                while True:
                    try:
                        item = progress_queue.get_nowait()
                        temp_items.append(item)
                        if item.get('action') == 'broadcast':
                            message = item.get('message', {})
                            if message.get('type') == 'scraping:all_complete_confirmed':
                                confirmation_received = True
                                confirmation_data = message
                                logger.info(f"Received scraping completion confirmation for batch {batch_id}")
                        queue_items.append(item)
                    except queue.Empty:
                        break
                
                # Put items back
                for item in queue_items:
                    try:
                        progress_queue.put_nowait(item)
                    except queue.Full:
                        pass
                
                if confirmation_received:
                    break
            except Exception as e:
                logger.debug(f"Error checking queue for confirmation: {e}")
            
            # Fallback: Check progress service directly
            if not confirmation_received:
                try:
                    confirmation_result = await self.progress_service.confirm_all_scraping_complete(batch_id)
                    if confirmation_result.get('confirmed'):
                        confirmation_received = True
                        confirmation_data = {
                            'type': 'scraping:all_complete_confirmed',
                            'batch_id': batch_id,
                            **confirmation_result
                        }
                        logger.info(f"Confirmed scraping completion via direct check for batch {batch_id}")
                        break
                except Exception as e:
                    logger.debug(f"Error checking completion directly: {e}")
            
            # Log progress periodically
            elapsed = time.time() - start_time
            if int(elapsed) > last_log_time:
                last_log_time = int(elapsed)
                pending_count = self.progress_service.get_pending_links_count(batch_id)
                logger.debug(
                    f"Waiting for confirmation: elapsed={elapsed:.1f}s, "
                    f"pending_links={pending_count}, queue_size={progress_queue.qsize()}"
                )
            
            await asyncio.sleep(check_interval)
        
        elapsed = time.time() - start_time
        
        if confirmation_received and confirmation_data:
            logger.info(
                f"Scraping completion confirmed for batch {batch_id} after {elapsed:.2f}s: "
                f"{confirmation_data.get('completed_count', 0)} completed, "
                f"{confirmation_data.get('failed_count', 0)} failed out of "
                f"{confirmation_data.get('expected_total', 0)} expected"
            )
            return confirmation_data
        else:
            # Timeout - check final status
            logger.warning(
                f"Timeout waiting for scraping confirmation after {elapsed:.2f}s for batch {batch_id}. "
                f"Checking final status..."
            )
            confirmation_result = await self.progress_service.confirm_all_scraping_complete(batch_id)
            if confirmation_result.get('confirmed'):
                logger.info(f"Scraping completion confirmed via final check for batch {batch_id}")
                return {
                    'type': 'scraping:all_complete_confirmed',
                    'batch_id': batch_id,
                    **confirmation_result
                }
            else:
                logger.warning(
                    f"Scraping completion NOT confirmed for batch {batch_id}: "
                    f"{confirmation_result.get('registered_count', 0)}/{confirmation_result.get('expected_total', 0)} registered, "
                    f"{confirmation_result.get('completed_count', 0)} completed, "
                    f"{confirmation_result.get('failed_count', 0)} failed"
                )
                return None
    
    async def wait_for_100_percent_completion(
        self,
        batch_id: str,
        max_wait_seconds: float = 10.0,
        check_interval: float = 0.5
    ) -> bool:
        """
        Poll ProgressService until 100% completion rate is reached.
        
        This is a backup verification to catch timing issues where status updates
        might still be in flight when initial confirmation happens.
        
        Args:
            batch_id: Batch ID to check
            max_wait_seconds: Maximum time to wait (default: 10 seconds)
            check_interval: Time between checks (default: 0.5 seconds)
        
        Returns:
            True if 100% reached, False if timeout
        """
        start_time = time.time()
        logger.info(f"Polling for 100% completion for batch {batch_id}...")
        
        while time.time() - start_time < max_wait_seconds:
            result = await self.progress_service.confirm_all_scraping_complete(batch_id)
            
            completion_rate = result.get('completion_rate', 0.0)
            is_100_percent = result.get('is_100_percent', False)
            total_final = result.get('total_final', 0)
            expected_total = result.get('expected_total', 0)
            
            if is_100_percent and total_final == expected_total and result.get('confirmed'):
                logger.info(
                    f"100% completion confirmed via polling: {completion_rate * 100:.1f}% "
                    f"({total_final}/{expected_total})"
                )
                return True
            
            elapsed = time.time() - start_time
            logger.debug(
                f"Waiting for 100%: {completion_rate * 100:.1f}% "
                f"({total_final}/{expected_total}), elapsed={elapsed:.1f}s"
            )
            
            await asyncio.sleep(check_interval)
        
        # Final check
        result = await self.progress_service.confirm_all_scraping_complete(batch_id)
        is_100_percent = result.get('is_100_percent', False)
        total_final = result.get('total_final', 0)
        expected_total = result.get('expected_total', 0)
        
        if is_100_percent and total_final == expected_total:
            logger.info(f"100% completion confirmed on final check")
            return True
        
        logger.warning(
            f"100% completion not reached after {max_wait_seconds}s: "
            f"{result.get('completion_percentage', 0):.1f}% ({total_final}/{expected_total})"
        )
        return False
    
    async def _wait_for_status_updates(
        self,
        message_queue: queue.Queue,
        batch_id: str,
        max_wait_seconds: float = 10.0,
        check_interval: float = 0.1
    ) -> bool:
        """
        Wait for all queued status updates to be processed.
        
        Args:
            message_queue: Queue to check for remaining messages
            batch_id: Batch ID to check status for
            max_wait_seconds: Maximum time to wait (default: 30 seconds)
            check_interval: Time between checks (default: 0.2 seconds)
            
        Returns:
            True if all links have final status, False if timeout
        """
        start_time = time.time()
        last_log_time = 0
        logger.info(f"Waiting for status updates to complete for batch {batch_id}...")
        
        while time.time() - start_time < max_wait_seconds:
            # Check if queue is empty (or has only non-status messages)
            queue_empty = True
            queue_size = 0
            try:
                # Check queue size (approximate)
                queue_size = message_queue.qsize()
                if queue_size > 0:
                    # Check if there are status update messages
                    # We can't peek, so we'll check by trying to get one
                    # But we'll put it back if it's not a status update
                    try:
                        test_message = message_queue.get_nowait()
                        if test_message.get('action') in ['update_link_progress', 'update_link_status']:
                            # Put it back - it's a status update that needs processing
                            message_queue.put_nowait(test_message)
                            queue_empty = False
                        else:
                            # Put it back - it's not a status update
                            message_queue.put_nowait(test_message)
                            queue_empty = True
                    except queue.Empty:
                        queue_empty = True
                else:
                    queue_empty = True
            except Exception as e:
                logger.warning(f"Error checking queue: {e}")
                queue_empty = True
            
            # Check if all links have final status
            all_final = self.progress_service.all_links_have_final_status(batch_id)
            
            if queue_empty and all_final:
                elapsed = time.time() - start_time
                logger.info(f"All status updates processed in {elapsed:.2f}s for batch {batch_id}")
                return True
            
            # Log progress periodically (every second)
            elapsed = time.time() - start_time
            if int(elapsed) > last_log_time:
                last_log_time = int(elapsed)
                pending_count = self.progress_service.get_pending_links_count(batch_id)
                logger.debug(f"Waiting for status updates: queue_size={queue_size}, pending_links={pending_count}, elapsed={elapsed:.1f}s")
            
            await asyncio.sleep(check_interval)
        
        # Timeout - check final status
        elapsed = time.time() - start_time
        pending_count = self.progress_service.get_pending_links_count(batch_id)
        all_final = self.progress_service.all_links_have_final_status(batch_id)
        
        if all_final:
            logger.info(f"All status updates processed (after timeout) in {elapsed:.2f}s for batch {batch_id}")
            return True
        else:
            logger.warning(f"Timeout waiting for status updates after {elapsed:.2f}s for batch {batch_id}: {pending_count} links still pending")
            # Force update batch status to ensure frontend has latest state
            await self.progress_service._update_batch_status(batch_id)
            return False
    
    async def _process_progress_queue(self, message_queue: queue.Queue, batch_id: str):
        """
        Process messages from queue and call ProgressService.
        
        Args:
            message_queue: Queue to poll for messages
            batch_id: Batch ID for broadcasting
        """
        max_retries = 3
        retry_delay = 0.5
        consecutive_errors = 0
        max_consecutive_errors = 10
        last_queue_log_time = 0
        queue_log_interval = 5.0  # Log queue stats every 5 seconds
        
        while True:
            try:
                # Monitor queue size periodically
                if DEBUG_MODE:
                    current_time = time.time()
                    if current_time - last_queue_log_time >= queue_log_interval:
                        queue_size = message_queue.qsize()
                        stats = self._queue_stats[batch_id]
                        stats['max_queue_size'] = max(stats['max_queue_size'], queue_size)
                        stats['queue_size_history'].append((current_time, queue_size))
                        # Keep only last 100 entries
                        if len(stats['queue_size_history']) > 100:
                            stats['queue_size_history'] = stats['queue_size_history'][-100:]
                        
                        logger.debug(
                            f"[QUEUE] Batch {batch_id}: size={queue_size}, "
                            f"processed={stats['messages_processed']}, "
                            f"dropped={stats['messages_dropped']}, "
                            f"max_size={stats['max_queue_size']}"
                        )
                        last_queue_log_time = current_time
                
                # Try to get message (non-blocking)
                try:
                    message = message_queue.get_nowait()
                    consecutive_errors = 0  # Reset error counter on success
                    
                    # Log queue size if large
                    queue_size = message_queue.qsize()
                    if queue_size > 10:
                        logger.warning(f"[QUEUE] Large queue size: {queue_size} messages for batch {batch_id}")
                    
                    if DEBUG_MODE:
                        self._queue_stats[batch_id]['messages_processed'] += 1
                        processing_start = time.time()
                    else:
                        processing_start = time.time()
                    
                    # Check if this is a ProgressService update action
                    if message.get('action') == 'update_link_progress':
                        # Retry logic for progress updates
                        retry_count = 0
                        success = False
                        
                        while retry_count < max_retries and not success:
                            try:
                                # Call ProgressService.update_link_progress()
                                await self.progress_service.update_link_progress(
                                    batch_id=message['batch_id'],
                                    link_id=message['link_id'],
                                    url=message['url'],
                                    stage=message['stage'],
                                    stage_progress=message['stage_progress'],
                                    overall_progress=message['overall_progress'],
                                    message=message['message'],
                                    metadata=message.get('metadata')
                                )
                                success = True
                                
                                processing_time = time.time() - processing_start
                                if processing_time > 1.0:
                                    logger.warning(f"[QUEUE] Slow message processing: {processing_time:.3f}s for {message.get('action')} (batch {batch_id})")
                                
                                if DEBUG_MODE:
                                    self._queue_stats[batch_id]['processing_times'].append(processing_time)
                                    # Keep only last 100 processing times
                                    if len(self._queue_stats[batch_id]['processing_times']) > 100:
                                        self._queue_stats[batch_id]['processing_times'] = \
                                            self._queue_stats[batch_id]['processing_times'][-100:]
                            except Exception as e:
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.warning(f"Progress update failed (attempt {retry_count}/{max_retries}): {e}, retrying in {retry_delay}s")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(f"Progress update failed after {max_retries} attempts: {e}")
                                    # Don't re-queue to avoid infinite loops - log and move on
                    
                    elif message.get('action') == 'update_link_status':
                        # Retry logic for status updates
                        retry_count = 0
                        success = False
                        
                        while retry_count < max_retries and not success:
                            try:
                                # Call ProgressService.update_link_status()
                                await self.progress_service.update_link_status(
                                    batch_id=message['batch_id'],
                                    link_id=message['link_id'],
                                    url=message['url'],
                                    status=message['status'],
                                    error=message.get('error'),
                                    metadata=message.get('metadata')
                                )
                                success = True
                            except Exception as e:
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.warning(f"Status update failed (attempt {retry_count}/{max_retries}): {e}, retrying in {retry_delay}s")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(f"Status update failed after {max_retries} attempts: {e}")
                                    # Don't re-queue to avoid infinite loops - log and move on
                    
                    elif message.get('action') == 'verify_completion':
                        # Verify scraping completion and send confirmation signal
                        verify_batch_id = message.get('batch_id', batch_id)
                        verify_start_time = message.get('_debug_timestamp', time.time())
                        logger.info(f"[VERIFY] Processing verify_completion for batch {verify_batch_id}")
                        
                        if DEBUG_MODE:
                            logger.debug(
                                f"[VERIFY] Verification request queued at {verify_start_time}, "
                                f"processing now (delay={time.time() - verify_start_time:.3f}s)"
                            )
                        
                        try:
                            # Wait a bit for any pending status updates
                            await asyncio.sleep(0.5)
                            
                            # Verify completion
                            logger.debug(f"[VERIFY] Calling confirm_all_scraping_complete for batch {verify_batch_id}")
                            confirmation_result = await self.progress_service.confirm_all_scraping_complete(verify_batch_id)
                            
                            if DEBUG_MODE:
                                logger.info(
                                    f"[VERIFY] Confirmation result for batch {verify_batch_id}: "
                                    f"confirmed={confirmation_result.get('confirmed')}, "
                                    f"expected={confirmation_result.get('expected_total', 0)}, "
                                    f"registered={confirmation_result.get('registered_count', 0)}, "
                                    f"completed={confirmation_result.get('completed_count', 0)}, "
                                    f"failed={confirmation_result.get('failed_count', 0)}, "
                                    f"pending={confirmation_result.get('pending_count', 0)}"
                                )
                            
                            # Send confirmation signal
                            confirmation_message = {
                                'type': 'scraping:all_complete_confirmed',
                                'batch_id': verify_batch_id,
                                **confirmation_result
                            }
                            
                            # Broadcast confirmation
                            await self.ws_manager.broadcast(verify_batch_id, confirmation_message)
                            
                            # Also queue it for the wait_for_scraping_confirmation to pick up
                            try:
                                message_queue.put_nowait({
                                    'action': 'broadcast',
                                    'message': confirmation_message
                                })
                            except queue.Full:
                                logger.warning(
                                    f"[VERIFY] Queue full, cannot queue confirmation message for batch {verify_batch_id}"
                                )
                            
                            # Send explicit 100% completion signal if confirmed
                            if confirmation_result.get('is_100_percent') and confirmation_result.get('confirmed'):
                                completion_rate = confirmation_result.get('completion_rate', 0.0)
                                completion_percentage = confirmation_result.get('completion_percentage', 0.0)
                                total_final = confirmation_result.get('total_final', 0)
                                expected_total = confirmation_result.get('expected_total', 0)
                                
                                if total_final == expected_total:
                                    logger.info(
                                        f"[100%] Sending 100% completion signal for batch {verify_batch_id}: "
                                        f"{completion_percentage:.1f}% ({total_final}/{expected_total})"
                                    )
                                    
                                    await self.ws_manager.broadcast(verify_batch_id, {
                                        'type': 'scraping:100_percent_complete',
                                        'batch_id': verify_batch_id,
                                        'completion_rate': completion_rate,
                                        'completion_percentage': completion_percentage,
                                        'completed_count': confirmation_result.get('completed_count', 0),
                                        'failed_count': confirmation_result.get('failed_count', 0),
                                        'expected_total': expected_total,
                                        'message': '所有抓取任务已完成 (100%)',
                                        'timestamp': datetime.now().isoformat()
                                    })
                            
                            verify_elapsed = time.time() - verify_start_time
                            logger.info(
                                f"[VERIFY] Sent scraping completion confirmation for batch {verify_batch_id}: "
                                f"confirmed={confirmation_result.get('confirmed')}, elapsed={verify_elapsed:.3f}s"
                            )
                        except Exception as e:
                            verify_elapsed = time.time() - verify_start_time
                            logger.error(
                                f"[VERIFY] Error verifying completion for batch {verify_batch_id} "
                                f"(elapsed={verify_elapsed:.3f}s): {e}",
                                exc_info=True
                            )
                    
                    elif message.get('action') == 'broadcast':
                        # Broadcast batch-level messages directly
                        retry_count = 0
                        success = False
                        
                        while retry_count < max_retries and not success:
                            try:
                                # Broadcast the nested message
                                await self.ws_manager.broadcast(batch_id, message.get('message', message))
                                success = True
                            except Exception as e:
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.warning(f"Broadcast failed (attempt {retry_count}/{max_retries}): {e}, retrying in {retry_delay}s")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(f"Broadcast failed after {max_retries} attempts: {e}")
                    
                    else:
                        # Retry logic for other messages (with type field)
                        if 'type' in message:
                            retry_count = 0
                            success = False
                            
                            while retry_count < max_retries and not success:
                                try:
                                    # Broadcast messages with type field directly
                                    await self.ws_manager.broadcast(batch_id, message)
                                    success = True
                                except Exception as e:
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        logger.warning(f"Broadcast failed (attempt {retry_count}/{max_retries}): {e}, retrying in {retry_delay}s")
                                        await asyncio.sleep(retry_delay)
                                    else:
                                        logger.error(f"Broadcast failed after {max_retries} attempts: {e}")
                        else:
                            # Skip messages without type or action (internal messages)
                            # Also skip messages with action that aren't handled above
                            if message.get('action'):
                                logger.debug(f"Skipping unhandled action message: {message.get('action')}, keys: {list(message.keys())}")
                            else:
                                logger.debug(f"Skipping message without type or action: {message.keys()}")
                        
                except queue.Empty:
                    # No message, wait a bit
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error processing progress queue (consecutive errors: {consecutive_errors}): {e}")
                
                # If too many consecutive errors, wait longer before retrying
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), waiting longer before retry")
                    await asyncio.sleep(1.0)
                    consecutive_errors = 0  # Reset after waiting
                else:
                    await asyncio.sleep(0.1)
    
    async def run_workflow(self, batch_id: str) -> Dict:
        """
        Run full workflow using proven test functions with progress updates.
        
        Args:
            batch_id: Batch ID to process
            
        Returns:
            Result dictionary from the workflow
        """
        try:
            # Check for cancellation before starting
            if self.progress_service.is_cancelled(batch_id):
                logger.info(f"Batch {batch_id} was cancelled before workflow started")
                return {'success': False, 'error': 'Cancelled by user'}
            
            # Check if this is a resume of an existing session
            # If phase0 exists, scraping is already done - skip directly to research
            session_id = None
            skip_scraping = False
            logger.info(f"[RESUME DEBUG] Checking for existing session with batch_id={batch_id}")
            try:
                # Try to find existing session for this batch_id
                sessions_dir = project_root / "data" / "research" / "sessions"
                logger.info(f"[RESUME DEBUG] Sessions dir exists: {sessions_dir.exists()}, path: {sessions_dir}")
                if sessions_dir.exists():
                    # Look for session files for this batch
                    session_files = list(sessions_dir.glob("session_*.json"))
                    logger.info(f"[RESUME DEBUG] Found {len(session_files)} session files to check")
                    for session_file in session_files:
                        try:
                            with open(session_file, 'r', encoding='utf-8') as f:
                                session_data = json.load(f)
                            metadata = session_data.get("metadata", {})
                            session_batch_id = metadata.get("batch_id")
                            logger.info(f"[RESUME DEBUG] Checking {session_file.name}: batch_id={session_batch_id}, looking for={batch_id}, match={session_batch_id == batch_id}")
                            if session_batch_id == batch_id:
                                # Found session for this batch
                                session_id = metadata.get("session_id")
                                phase_artifacts = session_data.get("phase_artifacts", {})
                                has_phase0 = "phase0" in phase_artifacts
                                logger.info(f"[RESUME DEBUG] ✓ MATCH! session_id={session_id}, has phase0={has_phase0}, phase_artifacts keys={list(phase_artifacts.keys())}")
                                # If phase0 exists, scraping is done
                                if has_phase0:
                                    skip_scraping = True
                                    logger.info(f"[RESUME DEBUG] ✓ SKIPPING SCRAPING - Found existing session {session_id} with phase0 complete")
                                else:
                                    logger.info(f"[RESUME DEBUG] ✗ NOT SKIPPING - phase0 not found in artifacts")
                                break
                        except Exception as e:
                            logger.warning(f"[RESUME DEBUG] Error checking session file {session_file}: {e}")
                            continue
                else:
                    logger.warning(f"[RESUME DEBUG] Sessions directory does not exist: {sessions_dir}")
            except Exception as e:
                logger.error(f"[RESUME DEBUG] Error checking for existing session: {e}", exc_info=True)
            
            logger.info(f"[RESUME DEBUG] Final decision: skip_scraping={skip_scraping}, session_id={session_id}")
            
            # Load link context for this batch
            await self._load_link_context(batch_id)
            
            # Create progress queue for thread-safe communication
            progress_queue = queue.Queue()
            progress_callback = self._create_progress_callback(batch_id, progress_queue)
            
            # Start progress processor task
            progress_task = asyncio.create_task(
                self._process_progress_queue(progress_queue, batch_id)
            )
            
            try:
                # Step 1: Run all scrapers (or skip if already done)
                logger.info(f"[RESUME DEBUG] About to check skip_scraping={skip_scraping}")
                if skip_scraping:
                    # Scraping already complete - skip directly to research
                    logger.info(f"[RESUME DEBUG] ✓✓✓ TAKING SKIP PATH - Skipping scraping for batch {batch_id} - already complete (phase0 exists)")
                    
                    # Notify frontend that scraping is already complete
                    await self.ws_manager.broadcast(batch_id, {
                        "type": "scraping:already_complete",
                        "batch_id": batch_id,
                        "message": "抓取已完成，直接进入研究阶段",
                    })
                else:
                    # Run scrapers normally
                    logger.info(f"[RESUME DEBUG] ✗✗✗ TAKING SCRAPING PATH - Starting scrapers for batch: {batch_id}")
                    
                    # Notify frontend that we're in scraping phase
                    await self.ws_manager.broadcast(batch_id, {
                        "type": "research:phase_change",
                        "phase": "scraping",
                        "phase_name": "抓取进度",
                        "message": "开始抓取内容",
                    })
                    
                    # Check cancellation before scraping
                    if self.progress_service.is_cancelled(batch_id):
                        logger.info(f"Batch {batch_id} was cancelled before scraping")
                        return {'success': False, 'error': 'Cancelled by user'}
                    
                    # Use direct execution to pass progress callbacks to scrapers
                    # Run in thread pool - Playwright needs to be initialized in the thread
                    # Note: Playwright browser processes are created in the thread, so this should work
                    scrapers_result = await asyncio.to_thread(
                        _run_scrapers_in_thread,
                        progress_callback=progress_callback,
                        batch_id=batch_id,
                        cancellation_checker=lambda: self.progress_service.is_cancelled(batch_id)
                    )
                    
                    # Check cancellation after scraping
                    if self.progress_service.is_cancelled(batch_id):
                        logger.info(f"Batch {batch_id} was cancelled during scraping")
                        cancellation_info = self.progress_service.get_cancellation_info(batch_id)
                        return {
                            'success': False,
                            'error': 'Cancelled by user',
                            'cancellation_info': cancellation_info
                        }
                    
                    if not scrapers_result.get("success"):
                        logger.error(f"Scrapers failed: {scrapers_result}")
                        raise Exception("Scrapers failed")
                    
                    scraping_end_time = time.time()
                    logger.info(f"[TIMING] Scraping completed at {scraping_end_time:.3f}: {scrapers_result.get('passed', 0)}/{scrapers_result.get('total', 0)} succeeded")
                    
                    # Wait for all status updates to be processed before transitioning
                    # This ensures all links have final status before research phase starts
                    status_wait_start = time.time()
                    logger.info(f"[TIMING] Starting status updates wait at {status_wait_start:.3f} for batch {batch_id}")
                    logger.info(f"Waiting for status updates to complete for batch {batch_id}...")
                    all_status_complete = await self._wait_for_status_updates(progress_queue, batch_id, max_wait_seconds=10.0)
                    status_wait_elapsed = time.time() - status_wait_start
                    logger.info(f"[TIMING] Status updates wait completed in {status_wait_elapsed:.3f}s for batch {batch_id}")
                    
                    # Force a final batch status update to ensure frontend has accurate state
                    await self.progress_service._update_batch_status(batch_id)
                    
                    # CRITICAL: Wait for explicit confirmation signal from scraping service
                    # This ensures all expected processes (not just started ones) are complete
                    confirmation_start = time.time()
                    logger.info(f"[TIMING] Starting confirmation wait at {confirmation_start:.3f} for batch {batch_id}")
                    logger.info(f"Waiting for scraping completion confirmation for batch {batch_id}...")
                    confirmation = await self.wait_for_scraping_confirmation(progress_queue, batch_id, max_wait_seconds=15.0)
                    confirmation_elapsed = time.time() - confirmation_start
                    logger.info(f"[TIMING] Confirmation wait completed in {confirmation_elapsed:.3f}s for batch {batch_id}")
                    
                    if not confirmation or not confirmation.get('confirmed'):
                        # Confirmation not received or not confirmed
                        if confirmation:
                            logger.error(
                                f"Scraping completion NOT confirmed for batch {batch_id}: "
                                f"Expected {confirmation.get('expected_total', 0)}, "
                                f"Registered {confirmation.get('registered_count', 0)}, "
                                f"Completed {confirmation.get('completed_count', 0)}, "
                                f"Failed {confirmation.get('failed_count', 0)}, "
                                f"Pending {confirmation.get('pending_count', 0)}, "
                                f"In Progress {confirmation.get('in_progress_count', 0)}"
                            )
                            if confirmation.get('non_final_statuses'):
                                logger.error(f"Non-final statuses: {confirmation.get('non_final_statuses')}")
                        else:
                            logger.error(f"Scraping completion confirmation timeout for batch {batch_id}")
                        
                        # Don't proceed to research phase - this is a critical error
                        raise Exception(
                            f"Scraping completion not confirmed for batch {batch_id}. "
                            f"Cannot proceed to research phase until all expected processes complete."
                        )
                    
                    # Explicit 100% completion check
                    completion_rate = confirmation.get('completion_rate', 0.0)
                    completion_percentage = confirmation.get('completion_percentage', 0.0)
                    is_100_percent = confirmation.get('is_100_percent', False)
                    total_final = confirmation.get('total_final', 0)
                    expected_total = confirmation.get('expected_total', 0)
                    
                    # Require explicit 100% completion
                    if not (is_100_percent and total_final == expected_total and completion_percentage >= 100.0):
                        logger.error(
                            f"Completion rate not 100%: {completion_percentage:.1f}% "
                            f"({total_final}/{expected_total})"
                        )
                        raise Exception(
                            f"Scraping not 100% complete: {completion_percentage:.1f}% "
                            f"({total_final}/{expected_total}). Cannot proceed to research phase."
                        )
                    
                    logger.info(
                        f"Scraping 100% COMPLETE for batch {batch_id}: "
                        f"{completion_percentage:.1f}% ({total_final}/{expected_total}) - "
                        f"{confirmation.get('completed_count', 0)} completed, "
                        f"{confirmation.get('failed_count', 0)} failed"
                    )
                    
                    # Additional polling check as backup to catch timing issues
                    is_100_percent_polled = await self.wait_for_100_percent_completion(
                        batch_id,
                        max_wait_seconds=10.0
                    )
                    
                    if not is_100_percent_polled:
                        logger.error("100% completion not reached after polling")
                        raise Exception("Scraping not 100% complete after polling. Cannot proceed to research phase.")
                    
                    # Step 2: Verify scraper results (using proven test function)
                    verify_start = time.time()
                    logger.info(f"[TIMING] Starting verification at {verify_start:.3f} for batch {batch_id}")
                    logger.info(f"Verifying scraper results for batch: {batch_id}")
                    
                    verified = await asyncio.to_thread(
                        verify_scraper_results,
                        batch_id,
                        progress_callback=progress_callback
                    )
                    verify_elapsed = time.time() - verify_start
                    logger.info(f"[TIMING] Verification completed in {verify_elapsed:.3f}s for batch {batch_id}")
                    
                    if not verified:
                        await self.ws_manager.broadcast(batch_id, {
                            "type": "error",
                            "phase": "verification",
                            "message": "抓取结果验证失败",
                        })
                        raise Exception("Scraper results verification failed")
                
                # Step 3: Run research agent (using proven test function)
                phase_change_start = time.time()
                logger.info(f"[TIMING] Sending phase change at {phase_change_start:.3f} for batch {batch_id}")
                logger.info(f"Starting research agent for batch: {batch_id}")
                
                # NOW send phase change (after all scraping status is finalized)
                # This ensures frontend has received all status updates before Research Agent tab appears
                await self.ws_manager.broadcast(batch_id, {
                    "type": "research:phase_change",
                    "phase": "research",
                    "phase_name": "研究代理",
                    "message": "开始研究阶段",
                })
                phase_change_elapsed = time.time() - phase_change_start
                logger.info(f"[TIMING] Phase change sent in {phase_change_elapsed:.3f}s for batch {batch_id}")
                
                # Create UI with WebSocket callbacks and main event loop reference
                main_loop = asyncio.get_running_loop()
                ui = WebSocketUI(
                    self.ws_manager,
                    batch_id,
                    main_loop=main_loop,
                    conversation_service=self.conversation_service,
                )
                
                # Register UI instance with WebSocket manager for user input delivery
                self.ws_manager.register_ui(batch_id, ui)
                
                # Notify UI that research is starting
                ui.notify_phase_change("research", "研究代理")
                
                # Run research agent with progress callbacks
                result = await asyncio.to_thread(
                    run_research_agent,
                    batch_id,
                    ui=ui,
                    progress_callback=progress_callback,
                    session_id=session_id  # Pass session_id to resume existing session if found
                )
                
                if not result:
                    raise Exception("Research agent failed")

                session_id = result.get("session_id")
                if session_id:
                    self.conversation_service.set_session_id(batch_id, session_id)
                
                # Send research:complete signal to indicate research agent has finished
                await self.ws_manager.broadcast(batch_id, {
                    "type": "research:complete",
                    "batch_id": batch_id,
                    "session_id": session_id,
                    "status": "completed",
                    "message": "研究完成",
                })
                
                await self.ws_manager.broadcast(batch_id, {
                    "type": "workflow:complete",
                    "batch_id": batch_id,
                    "result": result,
                })
                
                return result
                
            finally:
                # Unregister UI instance when workflow completes
                self.ws_manager.unregister_ui(batch_id)
                # Cancel progress processor (will finish processing remaining messages)
                progress_task.cancel()
                try:
                    await asyncio.wait_for(progress_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                # Process any remaining messages (only broadcast if they have a 'type' field)
                # Skip ALL internal action messages (update_link_progress, update_link_status, etc.)
                while True:
                    try:
                        message = progress_queue.get_nowait()
                        # Only broadcast messages with 'type' field (WebSocket messages)
                        # Skip ALL internal action messages - they should be processed by ProgressService, not broadcast
                        if message.get('action') in ['update_link_progress', 'update_link_status']:
                            # These are internal messages - skip them (they should have been processed already)
                            logger.debug(f"Skipping internal action message in cleanup: {message.get('action')}")
                            continue
                        elif 'type' in message:
                            await self.ws_manager.broadcast(batch_id, message)
                        elif message.get('action') == 'broadcast':
                            # Handle broadcast action messages
                            await self.ws_manager.broadcast(batch_id, message.get('message', message))
                    except queue.Empty:
                        break
            
        except Exception as e:
            logger.error(f"Workflow error: {e}", exc_info=True)
            error_message = str(e)
            
            # Provide more detailed error messages
            if "Research agent failed" in error_message or "prompt_user" in error_message.lower():
                detailed_message = f"工作流错误: 研究代理失败 - 可能是用户输入超时或连接问题。错误详情: {error_message}"
            else:
                detailed_message = f"工作流错误: {error_message}"
            
            await self.ws_manager.broadcast(batch_id, {
                "type": "error",
                "phase": "workflow",
                "message": detailed_message,
            })
            raise


