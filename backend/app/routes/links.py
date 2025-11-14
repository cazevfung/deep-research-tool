"""
Links API routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.link_formatter_service import LinkFormatterService
from app.services.progress_service import ProgressService
from app.websocket.manager import WebSocketManager
from loguru import logger

router = APIRouter()

# Lazy initialization - don't initialize service at import time
# This prevents the app from hanging during startup
_link_formatter_service = None
_initialization_error = None

def get_link_formatter_service():
    """Get or create LinkFormatterService instance (lazy initialization)."""
    global _link_formatter_service, _initialization_error
    if _link_formatter_service is None and _initialization_error is None:
        try:
            _link_formatter_service = LinkFormatterService()
            logger.info("LinkFormatterService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize LinkFormatterService: {e}", exc_info=True)
            _initialization_error = e
            _link_formatter_service = None
    return _link_formatter_service

# Note: ProgressService instance should ideally come from a shared instance
# For now, we'll create it here - but this should be refactored to use dependency injection
_websocket_manager = None
_progress_service = None

def get_progress_service() -> ProgressService:
    """Get or create ProgressService instance."""
    global _progress_service, _websocket_manager
    if _progress_service is None:
        _websocket_manager = WebSocketManager()
        _progress_service = ProgressService(_websocket_manager)
    return _progress_service


class FormatLinksRequest(BaseModel):
    urls: List[str]
    session_id: Optional[str] = None  # NEW field


class FormatLinksResponse(BaseModel):
    batch_id: str
    items: List[dict]
    total: int
    session_id: Optional[str] = None  # Return session_id for frontend


@router.post("/format", response_model=FormatLinksResponse)
async def format_links(request: FormatLinksRequest):
    """
    Format URLs and create batch.
    
    Args:
        request: Request with list of URLs and optional session_id
        
    Returns:
        Batch ID, formatted items, and session_id
    """
    try:
        link_formatter_service = get_link_formatter_service()
        if link_formatter_service is None:
            error_msg = str(_initialization_error) if _initialization_error else "Unknown initialization error"
            raise HTTPException(
                status_code=500,
                detail=f"LinkFormatterService not initialized. Check backend logs for initialization errors. Error: {error_msg}"
            )
        
        if not request.urls:
            raise HTTPException(status_code=400, detail="No URLs provided")
        
        # Handle session_id
        session_id = request.session_id
        session = None
        
        if session_id:
            try:
                from research.session import ResearchSession
                session = ResearchSession.load(session_id)
                logger.info(f"Using existing session: {session_id}")
            except FileNotFoundError:
                logger.warning(f"Session not found: {session_id}, creating new")
                from research.session import ResearchSession
                session = ResearchSession()
                session_id = session.session_id
        else:
            # Fallback: create new session (backward compatibility)
            from research.session import ResearchSession
            session = ResearchSession()
            session_id = session.session_id
            logger.info("No session_id provided, created new session")
        
        logger.info(f"Formatting {len(request.urls)} URLs")
        result = link_formatter_service.format_links(request.urls)
        
        # Store batch_id in session
        if session:
            session.set_metadata("batch_id", result['batch_id'])
            session.save()
        
        logger.info(f"Formatted {result['total']} links, batch_id: {result['batch_id']}, session_id: {session_id}")
        
        return FormatLinksResponse(
            batch_id=result['batch_id'],
            items=result['items'],
            total=result['total'],
            session_id=session_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to format links: {e}", exc_info=True)
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Full error traceback:\n{full_traceback}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "traceback": full_traceback
            }
        )


@router.get("/batches/{batch_id}/status")
async def get_batch_status(batch_id: str):
    """
    Get batch scraping status.
    
    Args:
        batch_id: Batch ID to get status for
        
    Returns:
        Batch status with progress information
    """
    try:
        progress_service = get_progress_service()
        status = progress_service.get_batch_status(batch_id)
        
        if status is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get batch status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint for link formatter service - should respond quickly."""
    try:
        # Quick check - try to get service (lazy initialization)
        # Don't block if initialization is slow
        link_formatter_service = get_link_formatter_service()
        
        if link_formatter_service is None:
            return {
                "status": "error",
                "message": f"LinkFormatterService not initialized: {str(_initialization_error) if _initialization_error else 'Unknown error'}",
                "service": "LinkFormatterService"
            }
        
        # Just check if method exists, don't call it
        if not hasattr(link_formatter_service, 'format_links'):
            return {
                "status": "error",
                "message": "LinkFormatterService is missing required methods",
                "service": "LinkFormatterService"
            }
        
        return {
            "status": "ok",
            "service": "LinkFormatterService",
            "message": "Service is ready"
        }
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "service": "LinkFormatterService"
        }


