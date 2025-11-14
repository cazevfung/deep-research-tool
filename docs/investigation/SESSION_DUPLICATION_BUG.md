# Session Duplication Bug Investigation

## Problem

Multiple research sessions are being created with the same `batch_id` but different `session_id`s and creation times. This results in duplicate entries in the history page showing the same batch ID with different statuses.

## Root Cause

The issue occurs in the workflow service's resume logic. Here's what happens:

### Current Flow

1. **Workflow Service Resume Check** (`backend/app/services/workflow_service.py:1700-1741`)
   - Checks for existing sessions with matching `batch_id`
   - Finds existing session and sets `session_id` variable (line 1722)
   - Sets `skip_scraping = True` if phase0 exists (line 1728)
   - **BUT**: Never passes `session_id` to the research agent

2. **Research Agent Call** (`backend/app/services/workflow_service.py:1944-1949`)
   ```python
   result = await asyncio.to_thread(
       run_research_agent,
       batch_id,
       ui=ui,
       progress_callback=progress_callback
   )
   ```
   - `session_id` is NOT passed to `run_research_agent`

3. **run_research_agent Function** (`tests/test_full_workflow_integration.py:221-294`)
   - Does NOT accept `session_id` parameter
   - Calls `agent.run_research()` without `session_id` (line 291-294)

4. **agent.run_research** (`research/agent.py:524-538`)
   ```python
   def run_research(
       self,
       batch_id: str,
       user_topic: Optional[str] = None,
       session_id: Optional[str] = None  # <-- This parameter exists but is never passed!
   ) -> Dict[str, Any]:
       if session_id:
           try:
               session = ResearchSession.load(session_id)  # <-- Would resume existing
               ...
           except FileNotFoundError:
               session = ResearchSession(session_id=session_id)
       else:
           session = ResearchSession()  # <-- Always creates NEW session!
   ```
   - Since `session_id` is `None`, it always creates a new session (line 538)

## The Bug

**The workflow service finds an existing session but never uses it.** Instead, it creates a brand new session every time, even when resuming.

## Evidence

Looking at the session files:
- `session_20251113_234721.json` - Created at 23:47:21, batch_id: `20251113_153137`, status: `initialized`
- `session_20251113_234839.json` - Created at 23:48:39, batch_id: `20251113_153137`, status: `complete`

Both have the same `batch_id` because:
1. First session was created when research started
2. User likely resumed/restarted the workflow
3. Workflow service found the first session but didn't use it
4. A second session was created instead

## Solution

### ✅ Fix 1: Pass session_id from Workflow Service

**IMPLEMENTED** - Updated `backend/app/services/workflow_service.py` to pass `session_id` to `run_research_agent`:

```python
# Line 1944-1950
result = await asyncio.to_thread(
    run_research_agent,
    batch_id,
    ui=ui,
    progress_callback=progress_callback,
    session_id=session_id  # ✅ Now passes session_id to resume existing session
)
```

### ✅ Fix 2: Update run_research_agent Signature

**IMPLEMENTED** - Updated `tests/test_full_workflow_integration.py` to accept `session_id`:

```python
def run_research_agent(
    batch_id: str, 
    ui=None, 
    progress_callback=None, 
    user_topic: Optional[str] = None,
    session_id: Optional[str] = None  # ✅ Added parameter
) -> Optional[Dict[str, Any]]:
    ...
    result = agent.run_research(
        batch_id=batch_id,
        user_topic=user_topic,
        session_id=session_id  # ✅ Now passes session_id to agent
    )
```

### Current Resume Logic

The current resume logic (lines 1700-1741 in `workflow_service.py`):
1. ✅ Checks if a session with matching `batch_id` exists
2. ✅ If it exists and has phase0, sets `skip_scraping = True` and uses that `session_id`
3. ✅ If it exists but doesn't have phase0, still uses that `session_id` (scraping will run again)
4. ✅ Now passes the `session_id` to the research agent (after fix)

**Note**: If multiple sessions exist for the same `batch_id`, the code uses the first one found. Future enhancement could select the most recent or most complete session.

## Additional Considerations

1. **Session Selection**: If multiple sessions exist for the same `batch_id`, which one should be used?
   - Option A: Use the most recent one
   - Option B: Use the one with the most progress
   - Option C: Use the one with `status: complete` if available

2. **UI Display**: The history page should probably group sessions by `batch_id` or show only the most recent session per batch.

3. **Cleanup**: Old incomplete sessions for the same batch could be automatically cleaned up when a new one is created.

## Files to Modify

1. `backend/app/services/workflow_service.py` - Pass session_id to run_research_agent
2. `tests/test_full_workflow_integration.py` - Accept session_id parameter
3. Consider: `backend/app/routes/history.py` - Improve session display logic

