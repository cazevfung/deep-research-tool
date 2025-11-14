"""
Session API routes.
"""
import json
import sys
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

router = APIRouter()


class CreateSessionRequest(BaseModel):
    user_guidance: str  # REQUIRED


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: Optional[str] = None

def _safe_load_json_file(file_path: Path, max_retries: int = 3, retry_delay: float = 0.1):
    """
    Safely load JSON file with retry logic for file locking issues.
    
    Args:
        file_path: Path to JSON file
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    
    Returns:
        Parsed JSON data as dictionary
    
    Raises:
        json.JSONDecodeError: If file contains invalid JSON
        IOError: If file cannot be read after retries
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Don't retry JSON decode errors - file is corrupted
            raise
        except (IOError, OSError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                logger.warning(f"Retry {attempt + 1}/{max_retries} reading {file_path}: {e}")
            else:
                raise IOError(f"Failed to read file after {max_retries} attempts: {str(e)}") from last_error
    
    raise IOError(f"Failed to read file: {str(last_error)}")

@router.post("/create", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new research session with required user guidance."""
    try:
        from research.session import ResearchSession
        
        user_guidance = request.user_guidance
        
        # Validate: user_guidance is required
        if not user_guidance or not user_guidance.strip():
            raise HTTPException(
                status_code=400,
                detail="user_guidance is required and cannot be empty"
            )
        
        # Create new session
        session = ResearchSession()
        
        # Store user_guidance in session metadata (required, so always store)
        session.set_metadata("phase_feedback_pre_role", user_guidance.strip())
        logger.info(f"Stored user_guidance in new session {session.session_id}")
        
        # Save session
        session.save()
        
        return CreateSessionResponse(
            session_id=session.session_id,
            created_at=session.metadata.get("created_at")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session data by session ID."""
    try:
        session_file = project_root / "data" / "research" / "sessions" / f"session_{session_id}.json"
        if not session_file.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        try:
            session_data = _safe_load_json_file(session_file)
        except json.JSONDecodeError as e:
            logger.error(f"Session file {session_file} contains invalid JSON: {e}")
            return {
                "session_id": session_id,
                "status": "corrupted",
                "error": "Session file is corrupted or incomplete. This may have occurred due to an interruption during save.",
                "detail": str(e)
            }
        except IOError as e:
            logger.error(f"Failed to read session file {session_file}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read session file: {str(e)}")
        
        return session_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/steps")
async def get_session_steps(session_id: str):
    """Get steps for a session."""
    try:
        session_file = project_root / "data" / "research" / "sessions" / f"session_{session_id}.json"
        if not session_file.exists():
            raise HTTPException(status_code=404, detail="Session not found")
        
        try:
            session_data = _safe_load_json_file(session_file)
        except json.JSONDecodeError as e:
            logger.error(f"Session file {session_file} contains invalid JSON when reading steps: {e}")
            return {"steps": []}
        except IOError as e:
            logger.error(f"Failed to read session file {session_file}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read session file: {str(e)}")
        
        if session_data.get("status") == "corrupted":
            return {"steps": []}
        
        steps = []
        scratchpad = session_data.get("scratchpad", {})
        
        if not isinstance(scratchpad, dict):
            logger.warning(f"Session {session_id} has invalid scratchpad type: {type(scratchpad)}")
            return {"steps": []}
        
        for key, step_data in scratchpad.items():
            if not isinstance(step_data, dict):
                continue
            steps.append({
                "step_id": step_data.get("step_id"),
                "findings": step_data.get("findings"),
                "insights": step_data.get("insights"),
                "confidence": step_data.get("confidence"),
                "timestamp": step_data.get("timestamp"),
            })
        
        steps.sort(key=lambda x: x["step_id"] if x["step_id"] is not None else float('inf'))
        
        return {"steps": steps}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session steps: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
