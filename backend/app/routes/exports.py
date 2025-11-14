"""
Export routes for downloadable assets.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import FileResponse
from loguru import logger
from urllib.parse import unquote

# Ensure project root on sys.path for ResearchSession imports inside service.
import sys

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.services.pdf_export_service import (
    PdfExportError,
    SessionNotFoundError,
    generate_phase_report_pdf,
)

# Import the export function
from scripts.export_session_html import export_session_html

router = APIRouter()


@router.get("/phase-report/{session_id}")
async def export_phase_report(session_id: str) -> Response:
    """
    Generate and stream the phase report PDF for a given session.
    """
    try:
        pdf_bytes = generate_phase_report_pdf(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PdfExportError as exc:
        logger.error("PDF export failed for session %s: %s", session_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error generating PDF for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from exc

    filename = f"research-report-{session_id}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/session-html/{session_id}")
async def export_session_html_endpoint(
    session_id: str,
    force: bool = Query(False, description="Force regeneration even if cached file exists")
):
    """
    Export a session to HTML format with filename based on comprehensive_topic.
    
    Returns:
        JSON with file_path, file_url, cached status, and filename
    """
    try:
        # Call the export function
        output_path, was_cached = export_session_html(
            session_id=session_id,
            output_dir="downloads",
            force_regenerate=force
        )
        
        # Get relative path from project root
        relative_path = output_path.relative_to(project_root)
        filename = output_path.name
        
        # Create URL-encoded filename for the file serving endpoint
        from urllib.parse import quote
        encoded_filename = quote(filename, safe='')
        file_url = f"/api/exports/session-html-file/{encoded_filename}"
        
        return {
            "file_path": str(relative_path),
            "file_url": file_url,
            "cached": was_cached,
            "filename": filename
        }
        
    except FileNotFoundError as exc:
        logger.error("Session not found for HTML export: %s", session_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error generating HTML for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Failed to generate HTML: {str(exc)}") from exc


@router.get("/session-html-file/{filename}")
async def serve_session_html_file(filename: str):
    """
    Serve the generated HTML file.
    
    The filename should be URL-encoded. This endpoint decodes it and serves the file.
    """
    try:
        # Decode the filename
        decoded_filename = unquote(filename)
        
        # Security: prevent path traversal
        if '..' in decoded_filename or '/' in decoded_filename or '\\' in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        # Build file path
        file_path = project_root / "downloads" / decoded_filename
        
        # Check if file exists
        if not file_path.exists():
            logger.warning("HTML file not found: %s", file_path)
            raise HTTPException(status_code=404, detail="HTML file not found")
        
        # Verify it's actually in the downloads directory (prevent path traversal)
        try:
            file_path.resolve().relative_to((project_root / "downloads").resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Serve the file
        return FileResponse(
            path=str(file_path),
            media_type="text/html; charset=utf-8",
            filename=decoded_filename,
            headers={
                "Cache-Control": "public, max-age=3600",
            }
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error serving HTML file: %s", filename)
        raise HTTPException(status_code=500, detail=f"Failed to serve file: {str(exc)}") from exc

