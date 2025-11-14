"""
History API routes for managing previously saved research sessions.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger

# Add project root to path (for compatibility with existing imports)
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Sessions and reports directories
sessions_dir = project_root / "data" / "research" / "sessions"
reports_dir = project_root / "data" / "research" / "reports"

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_load_json_file(
    file_path: Path,
    *,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> Dict[str, Any]:
    """
    Safely load JSON file with retry logic.

    Args:
        file_path: Path to JSON file
        max_retries: Maximum number of retries
        retry_delay: Delay between retries in seconds

    Returns:
        Parsed JSON dictionary
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError as exc:
            logger.error(f"JSON decode error in {file_path}: {exc}")
            raise
        except (IOError, OSError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            raise IOError(f"Failed to read {file_path}: {exc}") from last_error

    raise IOError(f"Failed to read {file_path}: {last_error}")  # pragma: no cover


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO formatted datetime string safely."""
    if not value:
        return None
    try:
        # Support trailing Z (UTC) by replacing with +00:00
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _map_status(raw_status: Optional[str]) -> Tuple[str, str]:
    """Map raw status to frontend-friendly status."""
    normalized = (raw_status or "").strip().lower()

    if normalized in {"completed", "complete", "done", "finished"}:
        return "completed", normalized or "completed"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled", normalized or "cancelled"
    if normalized in {"failed", "error", "errored"}:
        return "failed", normalized or "failed"

    # Default to in-progress for unknown or initialized states
    return "in-progress", normalized or "initialized"


def _extract_phase3_plan(
    metadata: Dict[str, Any],
    session_data: Dict[str, Any],
) -> Optional[List[Dict[str, Any]]]:
    """Extract stored Phase 3 plan (if any)."""
    plan = metadata.get("research_plan")
    if isinstance(plan, list) and plan:
        return plan

    artifacts = session_data.get("phase_artifacts")
    if isinstance(artifacts, dict):
        phase2 = artifacts.get("phase2")
        if isinstance(phase2, dict):
            plan_candidate = phase2.get("plan")
            if isinstance(plan_candidate, list) and plan_candidate:
                return plan_candidate

    return None


def _extract_phase3_steps(session_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract completed Phase 3 steps from session scratchpad."""
    scratchpad = session_data.get("scratchpad")
    if not isinstance(scratchpad, dict):
        return []

    steps: List[Dict[str, Any]] = []
    for key, value in scratchpad.items():
        if not isinstance(key, str) or not key.startswith("step_"):
            continue
        if not isinstance(value, dict):
            continue

        step_id = value.get("step_id")
        if not isinstance(step_id, int):
            continue

        sanitized = dict(value)
        sanitized.setdefault("findings", {})
        steps.append(sanitized)

    steps.sort(key=lambda item: item.get("step_id", 0))
    return steps


def _extract_phase3_state(
    metadata: Dict[str, Any],
    session_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a Phase 3 state snapshot for frontend hydration."""
    plan = _extract_phase3_plan(metadata, session_data) or []
    steps = _extract_phase3_steps(session_data)
    completed_step_ids = [step.get("step_id") for step in steps if step.get("step_id") is not None]

    next_step_id: Optional[int] = None
    if plan:
        completed = set(filter(lambda sid: isinstance(sid, int), completed_step_ids))
        for step in plan:
            step_id = step.get("step_id")
            if isinstance(step_id, int) and step_id not in completed:
                next_step_id = step_id
                break

    artifacts = session_data.get("phase_artifacts", {})
    synthesized_goal = metadata.get("synthesized_goal")
    if not synthesized_goal and isinstance(artifacts, dict):
        phase2 = artifacts.get("phase2")
        if isinstance(phase2, dict):
            synthesized_goal = phase2.get("synthesized_goal")

    return {
        "plan": plan,
        "steps": steps,
        "completed_step_ids": completed_step_ids,
        "total_steps": len(plan),
        "next_step_id": next_step_id,
        "synthesized_goal": synthesized_goal,
    }


def _infer_current_phase(
    status: str,
    *,
    artifacts: Dict[str, Any],
    metadata: Dict[str, Any],
    session_data: Dict[str, Any],
) -> str:
    """Infer current workflow phase from stored artifacts and scratchpad."""
    normalized_status = (metadata.get("status") or "").strip().lower()
    if status == "completed" or normalized_status in {"completed", "complete"} or metadata.get("finished"):
        return "complete"

    artifact_keys = set(artifacts.keys())
    if "phase4" in artifact_keys or metadata.get("final_report") or session_data.get("final_report"):
        return "complete"

    scratchpad = session_data.get("scratchpad")
    if isinstance(scratchpad, dict) and any(key.startswith("step_") for key in scratchpad.keys()):
        return "phase3"

    plan = _extract_phase3_plan(metadata, session_data)
    if plan:
        return "phase3"

    if artifact_keys.intersection({"phase2", "phase1", "phase0_5"}):
        return "research"
    if metadata.get("data_loaded") or "phase0" in artifact_keys:
        return "research"

    return "scraping"


def _extract_topic(metadata: Dict[str, Any]) -> Optional[str]:
    """Extract a human-readable topic/title for the history card."""
    # Extract comprehensive_topic from synthesized_goal if available
    synthesized_goal = metadata.get("synthesized_goal")
    comprehensive_topic = None
    if isinstance(synthesized_goal, dict):
        comprehensive_topic = synthesized_goal.get("comprehensive_topic")
    
    topic_fields = [
        comprehensive_topic,
        metadata.get("selected_goal"),
        metadata.get("user_topic"),
        metadata.get("metadata", {}).get("selected_goal") if isinstance(metadata.get("metadata"), dict) else None,
    ]

    for value in topic_fields:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _build_scraping_status(
    metadata: Dict[str, Any],
    status: str,
) -> Dict[str, Any]:
    """
    Build a scraping status snapshot for the session detail response.

    Attempts to use stored statistics; falls back to sensible defaults.
    """
    qa_stats = (
        metadata.get("quality_assessment", {}).get("statistics")
        if isinstance(metadata.get("quality_assessment"), dict)
        else {}
    )

    total_items = 0
    if isinstance(qa_stats, dict):
        total_items = int(qa_stats.get("total_items") or 0)

    # Expected total scraping processes – fall back to item count if unknown
    expected_total = int(metadata.get("expected_total_processes") or total_items or 0)

    # Use stored scraping snapshot if available
    scraping_snapshot = metadata.get("scraping_status")
    if isinstance(scraping_snapshot, dict):
        result = {
            "total": int(scraping_snapshot.get("total") or expected_total),
            "expected_total": int(scraping_snapshot.get("expected_total") or expected_total),
            "completed": int(scraping_snapshot.get("completed") or 0),
            "failed": int(scraping_snapshot.get("failed") or 0),
            "inProgress": int(scraping_snapshot.get("inProgress") or scraping_snapshot.get("in_progress") or 0),
            "items": scraping_snapshot.get("items") or [],
            "completionRate": scraping_snapshot.get("completionRate")
            or scraping_snapshot.get("completion_rate")
            or 0.0,
            "is100Percent": bool(scraping_snapshot.get("is100Percent") or scraping_snapshot.get("is_100_percent")),
            "canProceedToResearch": bool(
                scraping_snapshot.get("canProceedToResearch")
                or scraping_snapshot.get("can_proceed_to_research")
            ),
        }
        # Ensure expected_total defaults correctly
        if not result["expected_total"]:
            result["expected_total"] = expected_total or result["total"]
        if not result["total"]:
            result["total"] = result["expected_total"]

        # Harmonize percentages if available
        if not result["completionRate"] and result["expected_total"]:
            completed = result["completed"] + result["failed"]
            result["completionRate"] = completed / max(result["expected_total"], 1)
        if not result["is100Percent"] and result["expected_total"]:
            completed = result["completed"] + result["failed"]
            result["is100Percent"] = completed >= result["expected_total"]
        if not result["canProceedToResearch"]:
            result["canProceedToResearch"] = result["is100Percent"]
        return result

    # Fallback: derive from totals
    completed = expected_total if status == "completed" and expected_total else 0
    failed = 0
    in_progress = max(expected_total - completed - failed, 0)

    completion_rate = (completed + failed) / expected_total if expected_total else 0.0
    is_complete = completed + failed >= expected_total and expected_total > 0

    return {
        "total": expected_total,
        "expected_total": expected_total,
        "completed": completed,
        "failed": failed,
        "inProgress": in_progress,
        "items": [],
        "completionRate": completion_rate,
        "is100Percent": is_complete,
        "canProceedToResearch": is_complete,
    }


def _collect_session_records() -> List[Dict[str, Any]]:
    """Load all session files and enrich with derived fields."""
    if not sessions_dir.exists():
        return []

    records: List[Dict[str, Any]] = []

    for session_path in sorted(sessions_dir.glob("session_*.json")):
        try:
            session_data = _safe_load_json_file(session_path)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Failed to load session file {session_path}: {exc}")
            continue

        metadata = session_data.get("metadata", {})
        if not isinstance(metadata, dict):
            logger.warning(f"Session {session_path} has invalid metadata format")
            continue

        batch_id = metadata.get("batch_id")
        session_id = metadata.get("session_id")

        if not (batch_id and session_id):
            logger.warning(f"Session {session_path} missing batch_id or session_id")
            continue

        raw_status = metadata.get("status")
        status, normalized_status = _map_status(raw_status)

        artifacts = session_data.get("phase_artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}

        current_phase = _infer_current_phase(
            status,
            artifacts=artifacts,
            metadata=metadata,
            session_data=session_data,
        )

        created_at = metadata.get("created_at")
        updated_at = metadata.get("updated_at")
        created_dt = _parse_datetime(created_at)
        updated_dt = _parse_datetime(updated_at) or created_dt

        # Fallback to filesystem timestamps if metadata missing
        if created_dt is None:
            created_dt = datetime.fromtimestamp(session_path.stat().st_ctime)
            created_at = created_dt.isoformat()
        if updated_dt is None:
            updated_dt = datetime.fromtimestamp(session_path.stat().st_mtime)
            updated_at = updated_dt.isoformat()

        topic = _extract_topic(metadata)

        qa_stats = metadata.get("quality_assessment", {}).get("statistics", {})
        url_count = None
        if isinstance(qa_stats, dict):
            raw_count = qa_stats.get("total_items")
            if raw_count is not None:
                try:
                    url_count = int(raw_count)
                except (TypeError, ValueError):
                    url_count = None

        records.append(
            {
                "session_id": session_id,
                "batch_id": batch_id,
                "status": status,
                "raw_status": normalized_status,
                "current_phase": current_phase,
                "created_at": created_at,
                "created_dt": created_dt,
                "updated_at": updated_at,
                "updated_dt": updated_dt,
                "topic": topic,
                "url_count": url_count,
                "artifacts": artifacts,
                "metadata": metadata,
                "session_path": session_path,
                "session_data": session_data,
            }
        )

    return records


def _find_session_by_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    """Find the most recent session record for a given batch ID."""
    sessions = [
        record for record in _collect_session_records() if record["batch_id"] == batch_id
    ]
    if not sessions:
        return None
    # Return the most recently updated session
    return max(sessions, key=lambda record: record.get("updated_dt") or datetime.min)


def _remove_associated_report(session_id: str) -> None:
    """Delete generated report associated with a session if it exists."""
    report_path = reports_dir / f"report_{session_id}.md"
    if report_path.exists():
        try:
            report_path.unlink()
            logger.info(f"Deleted report {report_path}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Failed to delete report {report_path}: {exc}")


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_history(
    status: Optional[str] = Query(
        default=None,
        description="Filter by session status (completed, in-progress, failed, cancelled)",
    ),
    date_from: Optional[str] = Query(
        default=None, description="Filter sessions created on/after this ISO timestamp"
    ),
    date_to: Optional[str] = Query(
        default=None, description="Filter sessions created before this ISO timestamp"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Return paginated list of historical sessions."""
    try:
        records = _collect_session_records()

        # Apply status filter
        if status:
            target_status = status.strip().lower()
            records = [r for r in records if r["status"] == target_status]

        # Apply date filters
        from_dt = _parse_datetime(date_from) if date_from else None
        to_dt = _parse_datetime(date_to) if date_to else None

        if from_dt:
            records = [r for r in records if r.get("created_dt") and r["created_dt"] >= from_dt]
        if to_dt:
            records = [r for r in records if r.get("created_dt") and r["created_dt"] < to_dt]

        # Sort by creation time (newest first)
        records.sort(key=lambda r: r.get("created_dt") or datetime.min, reverse=True)

        total = len(records)
        sliced = records[offset : offset + limit]

        sessions = [
            {
                "batch_id": record["batch_id"],
                "session_id": record["session_id"],
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
                "status": record["status"],
                "topic": record["topic"],
                "url_count": record["url_count"],
                "current_phase": record["current_phase"],
            }
            for record in sliced
        ]

        return {
            "sessions": sessions,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        }
    except Exception as exc:
        logger.error(f"Failed to list history: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list history: {exc}") from exc


@router.get("/{batch_id}")
async def get_history_session(batch_id: str) -> Dict[str, Any]:
    """Return detailed session information for a batch."""
    try:
        record = _find_session_by_batch(batch_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")

        metadata = record["metadata"]
        session_data = record["session_data"]
        session_id = record["session_id"]
        status = record["status"]

        scraping_status = _build_scraping_status(metadata, status)

        phase3_state = _extract_phase3_state(metadata, session_data)

        details = {
            "batch_id": batch_id,
            "session_id": session_id,
            "status": status,
            "raw_status": record["raw_status"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "topic": record["topic"],
            "url_count": record["url_count"],
            "current_phase": record["current_phase"],
            "scraping_status": scraping_status,
            "available_artifacts": list(record["artifacts"].keys()),
            "metadata": metadata,
            "has_scratchpad": bool(session_data.get("scratchpad")),
            "phase3": phase3_state,
            "data_loaded": bool(metadata.get("data_loaded")),
            "resume_required": record["current_phase"] == "scraping"
            and not scraping_status.get("is100Percent", False),
        }

        return details
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get session for batch {batch_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get session for batch {batch_id}: {exc}"
        ) from exc


@router.post("/{batch_id}/resume")
async def resume_session(batch_id: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Resume a previously saved session by restarting the workflow.

    This defers execution to the existing workflow service to ensure consistent behaviour.
    """
    try:
        record = _find_session_by_batch(batch_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")

        # Import lazily to avoid circular dependency at module import time
        from app.routes import workflow as workflow_routes  # Local import

        workflow_service = workflow_routes.workflow_service
        if workflow_service is None:
            raise HTTPException(status_code=500, detail="Workflow service not initialized")

        # Reuse existing background task runner from workflow routes
        background_tasks.add_task(workflow_routes.run_workflow_task, batch_id)

        logger.info(f"Resuming workflow for batch {batch_id} (session {record['session_id']})")

        return {
            "batch_id": batch_id,
            "session_id": record["session_id"],
            "status": "started",
            "message": "Workflow resume scheduled",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to resume session for batch {batch_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to resume session for batch {batch_id}: {exc}"
        ) from exc


@router.delete("/session/{session_id}")
async def delete_session_by_id(session_id: str) -> Dict[str, Any]:
    """Delete stored session and associated artifacts by session ID."""
    try:
        # Find session by session_id (more precise than batch_id)
        sessions_dir = project_root / "data" / "research" / "sessions"
        session_file = sessions_dir / f"session_{session_id}.json"
        
        if not session_file.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Load session to get batch_id for response
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            batch_id = session_data.get("metadata", {}).get("batch_id")
        except Exception:
            batch_id = None

        try:
            session_file.unlink()
            logger.info(f"Deleted session file {session_file}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to delete session file {session_file}: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to delete session file: {exc}") from exc

        # Remove associated report if present
        _remove_associated_report(session_id)

        return {
            "batch_id": batch_id,
            "session_id": session_id,
            "status": "deleted",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete session {session_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete session {session_id}: {exc}"
        ) from exc


@router.delete("/{batch_id}")
async def delete_session(batch_id: str) -> Dict[str, Any]:
    """Delete stored session and associated artifacts for a batch (DEPRECATED - use /session/{session_id} instead)."""
    try:
        record = _find_session_by_batch(batch_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")

        session_path: Path = record["session_path"]
        session_id: str = record["session_id"]

        try:
            session_path.unlink()
            logger.info(f"Deleted session file {session_path}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to delete session file {session_path}: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to delete session file: {exc}") from exc

        # Remove associated report if present
        _remove_associated_report(session_id)

        return {
            "batch_id": batch_id,
            "session_id": session_id,
            "status": "deleted",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete session for batch {batch_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete session for batch {batch_id}: {exc}"
        ) from exc
