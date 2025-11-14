# History Session Phase Visibility Issue

## Problem Description

When clicking "查看报告" (View Report) on a completed session in the history page, the progress bar (WorkflowStepper) doesn't show all completed phases. Specifically:

1. **Not all phases are shown** - Phase 3 (深度研究) may not appear in the progress bar
2. **Research Agent appears unfinished** - The "研究代理" (Research Agent) step appears to be "shining" (in-progress) even though the final report was generated
3. **Cannot see the full process** - Users want to see the entire workflow process, including all phases that were completed

## Root Cause Analysis

### 1. Frontend State Hydration Issue

**Location:** `client/src/pages/HistoryPage.tsx` - `handleView` function

**Current Behavior:**
```typescript
const handleView = async (batchId: string) => {
  try {
    const sessionData = await apiService.getHistorySession(batchId)
    
    // Restore state
    setBatchId(batchId)
    setCurrentPhase('complete')
    
    // Navigate to report
    navigate('/report')
  } catch (err: any) {
    // Error handling...
  }
}
```

**Problem:** The `handleView` function only sets `batchId` and `currentPhase`, but doesn't hydrate the workflow store with:
- Scraping status
- Research agent status (goals, plan, phase, synthesized goal)
- Phase 3 steps
- Final report status

### 2. WorkflowStepper Visibility Logic

**Location:** `client/src/hooks/useWorkflowStep.ts` - `useWorkflowSteps` hook

**Step 2 (Content Extraction) Visibility:**
- `batchId !== null` - ✅ Always visible when batchId exists

**Step 3 (Research Agent) Visibility:**
- `scrapingComplete && researchStarted` - ❌ Requires `researchAgentStatus` to be hydrated
- Status: `researchComplete ? 'completed' : researchStarted || scrapingComplete ? 'in-progress' : 'not-started'`
- `researchComplete` requires: `researchAgentStatus.phase === '2' && researchAgentStatus.plan !== null && researchAgentStatus.plan.length > 0`

**Step 4 (Phase 3) Visibility:**
- `researchComplete || phase3Started` - ❌ Requires both `researchAgentStatus` and `phase3Steps` to be hydrated
- Status: `phase3Complete ? 'completed' : phase3Started || researchComplete ? 'in-progress' : 'not-started'`

**Step 5 (Final Report) Visibility:**
- `phase3Complete || reportGenerating || reportReady` - ✅ Works if final report is loaded

### 3. Why Research Agent Appears Unfinished

When viewing a completed session:
1. `researchAgentStatus` is not hydrated, so it's empty/default
2. `researchAgentStatus.phase` is not `'2'` (it's likely `'0.5'` or undefined)
3. `researchAgentStatus.plan` is `null` or `undefined`
4. Therefore, `researchComplete` is `false`
5. Since `scrapingComplete` might also be `false` (if scrapingStatus is not hydrated), the step shows as "in-progress" (shining)

## Backend Data Availability

**Location:** `backend/app/routes/history.py` - `get_history_session` endpoint

The backend **already provides** all the necessary data:

```python
details = {
    "batch_id": batch_id,
    "session_id": session_id,
    "status": status,
    "scraping_status": scraping_status,  # ✅ Available
    "phase3": phase3_state,  # ✅ Available (plan, steps, synthesized_goal)
    "metadata": metadata,  # ✅ Available (includes phase1_confirmed_goals, synthesized_goal, research_plan)
    "current_phase": record["current_phase"],  # ✅ Available
    # ... other fields
}
```

**Session Data Structure:**
- `metadata.phase1_confirmed_goals` - List of goals from Phase 1
- `metadata.research_plan` - List of plan steps from Phase 2
- `metadata.synthesized_goal` - Synthesized goal from Phase 2
- `phase3.plan` - Phase 3 plan (same as `metadata.research_plan`)
- `phase3.steps` - Phase 3 completed steps
- `phase3.synthesized_goal` - Synthesized goal
- `scraping_status` - Scraping status snapshot

## Solution

### Required Changes

#### 1. Update `handleView` in HistoryPage.tsx

**Current Implementation:**
```typescript
const handleView = async (batchId: string) => {
  try {
    const sessionData = await apiService.getHistorySession(batchId)
    
    // Restore state
    setBatchId(batchId)
    setCurrentPhase('complete')
    
    // Navigate to report
    navigate('/report')
  } catch (err: any) {
    // Error handling...
  }
}
```

**Required Implementation:**
```typescript
const handleView = async (batchId: string) => {
  try {
    const sessionData = (await apiService.getHistorySession(batchId)) as HistorySessionDetail
    
    // Restore workflow state (similar to handleResume)
    setBatchId(batchId)
    setSessionId(sessionData.session_id || null)
    
    // Hydrate scraping status
    if (sessionData.scraping_status) {
      const snapshot = sessionData.scraping_status
      updateScrapingStatus({
        total: snapshot.total ?? snapshot.expected_total ?? 0,
        expectedTotal: snapshot.expected_total ?? snapshot.total ?? 0,
        completed: snapshot.completed ?? 0,
        failed: snapshot.failed ?? 0,
        inProgress: snapshot.inProgress ?? 0,
        items: snapshot.items ?? [],
        completionRate: snapshot.completionRate ?? 0,
        is100Percent: Boolean(snapshot.is100Percent),
        canProceedToResearch: Boolean(snapshot.canProceedToResearch),
      })
    }
    
    // Hydrate research agent status
    const metadata = sessionData.metadata || {}
    const goals = metadata.phase1_confirmed_goals || []
    const plan = metadata.research_plan || sessionData.phase3?.plan || []
    const synthesizedGoal = metadata.synthesized_goal || sessionData.phase3?.synthesized_goal || null
    
    // Determine research agent phase
    // If plan exists, research agent is complete (phase 2)
    // If goals exist but no plan, research agent is in progress (phase 1)
    // Otherwise, research agent hasn't started (phase 0.5)
    let researchPhase: string = '0.5'
    if (plan && plan.length > 0) {
      researchPhase = '2'  // Phase 2 complete
    } else if (goals && goals.length > 0) {
      researchPhase = '1'  // Phase 1 in progress
    }
    
    // Update research agent status
    updateResearchAgentStatus({
      phase: researchPhase,
      goals: goals.map((g: any) => ({
        id: g.id || g.goal_id || 0,
        goal_text: g.goal_text || g.goal || '',
        rationale: g.rationale || '',
        uses: g.uses || [],
        sources: g.sources || [],
      })),
      plan: plan,
      synthesizedGoal: synthesizedGoal,
    })
    
    // Hydrate Phase 3 plan/steps
    setPlan((sessionData.phase3?.plan as any) ?? plan ?? null)
    setSynthesizedGoal(synthesizedGoal)
    const phase3Steps = (sessionData.phase3?.steps as SessionStep[]) ?? []
    setPhase3Steps(phase3Steps, sessionData.phase3?.next_step_id ?? null)
    
    // Set current phase (should be 'complete' for completed sessions)
    const resolvedPhase = sessionData.current_phase || 
      (sessionData.status === 'completed' ? 'complete' : 'research')
    setCurrentPhase(resolvedPhase as any)
    
    // Navigate to report
    navigate('/report')
  } catch (err: any) {
    console.error('Failed to view session:', err)
    addNotification('无法查看会话详情，请重试', 'error')
  }
}
```

#### 2. Verify Session Data Structure

**Check that sessions are registered correctly:**

1. **Scraping Status:** Should be stored in `metadata.scraping_status` or derived from `metadata.quality_assessment.statistics`
2. **Research Agent Status:** 
   - Goals stored in `metadata.phase1_confirmed_goals`
   - Plan stored in `metadata.research_plan`
   - Synthesized goal stored in `metadata.synthesized_goal` or `phase_artifacts.phase2.synthesized_goal`
3. **Phase 3 Status:**
   - Plan stored in `metadata.research_plan` or `phase_artifacts.phase2.plan`
   - Steps stored in `scratchpad.step_*` entries
   - Synthesized goal stored in `metadata.synthesized_goal`
4. **Final Report:** Should be stored in `phase_artifacts.phase4` or generated on-demand

### 3. Testing Checklist

- [ ] View a completed session from history
- [ ] Verify all phases appear in the progress bar
- [ ] Verify "研究代理" (Research Agent) shows as completed (not shining)
- [ ] Verify "深度研究" (Phase 3) shows as completed
- [ ] Verify "最终报告" (Final Report) shows as completed
- [ ] Verify clicking on any phase navigates to the correct page
- [ ] Verify the final report loads correctly
- [ ] Verify phase 3 steps are accessible if clicking on Phase 3

## Additional Notes

### Why `handleResume` Works but `handleView` Doesn't

**`handleResume` (for in-progress sessions):**
- ✅ Hydrates scraping status
- ✅ Hydrates phase 3 plan/steps
- ✅ Determines current phase
- ✅ Calls `resumeSession` API to restart workflow

**`handleView` (for completed sessions):**
- ❌ Only sets `batchId` and `currentPhase`
- ❌ Doesn't hydrate any workflow state
- ❌ Doesn't restore research agent status
- ❌ Doesn't restore phase 3 steps

### Session Data Registration

**Sessions ARE registered correctly:**
- ✅ Scraping status is stored in `metadata.scraping_status`
- ✅ Research agent goals are stored in `metadata.phase1_confirmed_goals`
- ✅ Research agent plan is stored in `metadata.research_plan`
- ✅ Phase 3 steps are stored in `scratchpad.step_*`
- ✅ Phase 3 plan is stored in `metadata.research_plan`
- ✅ Synthesized goal is stored in `metadata.synthesized_goal`

**The issue is that the frontend doesn't use this data when viewing completed sessions.**

## Conclusion

The problem is **not** with session registration - sessions are stored correctly with all phase data. The problem is that the `handleView` function doesn't hydrate the workflow store with the session data, so the WorkflowStepper component can't determine which phases are completed.

**Solution:** Update `handleView` to hydrate the workflow store similar to `handleResume`, but without calling the resume API (since the session is already completed).

## Implementation Status

### ✅ Implemented

**Date:** 2025-01-XX

**Changes Made:**

1. **Created `hydrateWorkflowState` helper function** in `HistoryPage.tsx`:
   - Hydrates scraping status from `sessionData.scraping_status`
   - Hydrates research agent status (goals, plan, phase) from `metadata`
   - Hydrates Phase 3 steps from `sessionData.phase3`
   - Determines research agent phase based on available data:
     - Phase `'2'` if plan exists (research agent complete)
     - Phase `'1'` if goals exist but no plan (research agent in progress)
     - Phase `'0.5'` otherwise (research agent not started)

2. **Updated `handleView` function**:
   - Now calls `hydrateWorkflowState` to restore all workflow state
   - Sets `batchId`, `sessionId`, and `workflowStarted` flag
   - Sets current phase to `'complete'` for completed sessions
   - Navigates to `/report` page

3. **Updated `handleResume` function**:
   - Now also uses `hydrateWorkflowState` to ensure consistency
   - This ensures the progress bar shows correctly when resuming sessions too

**Result:**
- ✅ All phases now appear in the progress bar when viewing completed sessions
- ✅ "研究代理" (Research Agent) shows as completed (not shining) when plan exists
- ✅ "深度研究" (Phase 3) shows as completed when all steps are done
- ✅ "最终报告" (Final Report) shows as completed when report is ready
- ✅ Users can now see the entire workflow process when viewing completed sessions

**Testing Checklist:**
- [x] View a completed session from history
- [x] Verify all phases appear in the progress bar
- [x] Verify "研究代理" (Research Agent) shows as completed (not shining)
- [x] Verify "深度研究" (Phase 3) shows as completed
- [x] Verify "最终报告" (Final Report) shows as completed
- [x] Verify clicking on any phase navigates to the correct page
- [x] Verify the final report loads correctly
- [x] Verify phase 3 steps are accessible if clicking on Phase 3

