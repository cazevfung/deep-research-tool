# User Guidance Early Collection Implementation Plan

**Date:** 2025-11-14  
**Status:** Planning  
**Priority:** Medium

## Executive Summary

This plan outlines moving the `{user_guidance}` collection from **after Phase 0 summarization** to **before link input**, allowing users to provide research context upfront. This improves UX by letting users set research direction before data processing begins.

### Current Flow
```
User Input Links → Phase 0 (Summarization) → [PROMPT] User Guidance → Phase 0.5 (Role Generation)
```

### Target Flow
```
[PAGE 1] User Guidance Input → [PAGE 2] User Input Links → Phase 0 (Summarization) → Phase 0.5 (Role Generation)
```

**Note:** User guidance now starts the session, making it the first step in the workflow.

### Key Benefits
- ✅ Better UX: Users provide context upfront
- ✅ Minimal backend changes: Only 2 files modified
- ✅ Backward compatible: Falls back to prompting if not provided
- ✅ No breaking changes: Existing flows continue to work

---

## Problem Statement

Currently, `{user_guidance}` is collected **after** Phase 0 completes its summarization work. This means:
1. Users must wait for data processing before providing context
2. The guidance prompt appears mid-workflow, interrupting the flow
3. Users can't set research direction before links are processed

**Goal:** Collect `{user_guidance}` at the very beginning, before any link processing, while maintaining backward compatibility.

---

## Architecture Overview

### New Route Structure

**Current Routes:**
- `/` → LinkInputPage
- `/scraping` → ScrapingProgressPage
- `/research` → ResearchAgentPage
- ...

**New Routes:**
- `/` → **UserGuidancePage** (NEW - First step, starts session)
- `/links` → LinkInputPage (moved from `/`)
- `/scraping` → ScrapingProgressPage
- `/research` → ResearchAgentPage
- ...

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend: UserGuidancePage (NEW - Route: /)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. User Guidance Input (REQUIRED)                     │   │
│  │    "研究指导"                                         │   │
│  │    "在本次研究开始之前，你想强调哪些问题重点或背景？你希望有料到给你提供什么样的洞察？"     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 2. Submit → createSession({ user_guidance })         │   │
│  │    - Creates ResearchSession                          │   │
│  │    - Stores user_guidance in session metadata         │   │
│  │    - Returns session_id                               │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 3. Navigate to /links (LinkInputPage)                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend: LinkInputPage (Route: /links)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. URL Links Input (Existing)                        │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 2. Submit → formatLinks({ urls, session_id })        │   │
│  │    - Uses existing session (created in step 1)        │   │
│  │    - Creates batch_id                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: Create Session Endpoint (NEW)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Receive { user_guidance } (REQUIRED)              │   │
│  │ 2. Validate user_guidance is not empty               │   │
│  │ 3. Create ResearchSession                             │   │
│  │ 4. Store user_guidance in session metadata:           │   │
│  │    session.set_metadata("phase_feedback_pre_role",    │   │
│  │                        user_guidance)                 │   │
│  │ 4. Return { session_id }                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: Format Links Endpoint (Modified)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Receive { urls, session_id }                      │   │
│  │ 2. Load existing ResearchSession by session_id        │   │
│  │ 3. Create batch_id                                    │   │
│  │ 4. Return { batch_id, items, total }                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase 0.5: Role Generation (Modified)                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Read from session:                                 │   │
│  │    pre_role_feedback = session.get_metadata(         │   │
│  │        "phase_feedback_pre_role", "")                 │   │
│  │ 2. If exists: Use it (NO PROMPT)                      │   │
│  │ 3. If missing: Prompt user (FALLBACK)                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Frontend Changes

#### 1.1 Create UserGuidancePage.tsx (NEW)

**File:** `client/src/pages/UserGuidancePage.tsx` (NEW FILE)

**Purpose:** First step in workflow - collects user guidance and starts the session

**Features:**
- Required guidance input field (user must provide input)
- Form validation to ensure guidance is not empty
- Creates session when submitted
- Navigates to link input page after submission

**Code Structure:**

```typescript
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/common/Card'
import Button from '../components/common/Button'
import Textarea from '../components/common/Textarea'
import { useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'
import { apiService } from '../services/api'

const UserGuidancePage: React.FC = () => {
  const navigate = useNavigate()
  const [userGuidance, setUserGuidance] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setSessionId } = useWorkflowStore()
  const { addNotification } = useUiStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    
    // Validate: guidance is required
    const trimmedGuidance = userGuidance.trim()
    if (!trimmedGuidance) {
      setError('请输入研究指导，此字段为必填项')
      return
    }
    
    setIsLoading(true)

    try {
      // Create session with user guidance (required)
      const response = await apiService.createSession(trimmedGuidance)
      
      if (response.session_id) {
        setSessionId(response.session_id)
        addNotification('会话已创建，请继续输入链接', 'success')
        navigate('/links') // Navigate to link input page
      } else {
        throw new Error('未返回会话ID')
      }
    } catch (err: any) {
      console.error('Error creating session:', err)
      setError(err.response?.data?.detail || err.message || '创建会话时出错')
      addNotification('创建会话失败，请重试', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <Card
        title="研究指导"
        subtitle="在开始研究前，请提供研究重点或背景"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">
              研究指导 <span className="text-red-500">*</span>
            </label>
            <Textarea
              value={userGuidance}
              onChange={(e) => setUserGuidance(e.target.value)}
              placeholder="在生成研究角色前，你想强调哪些研究重点或背景？例如：\n- 重点关注技术实现细节\n- 分析用户反馈和评论\n- 对比不同方案的优缺点"
              rows={6}
              helperText="此指导将用于生成研究角色和后续分析。请详细描述你的研究重点和关注方向。"
              disabled={isLoading}
              error={error || undefined}
              required
            />
          </div>

          <div className="flex items-center justify-end space-x-4">
            <Button
              type="submit"
              variant="primary"
              isLoading={isLoading}
              disabled={isLoading || !userGuidance.trim()}
            >
              继续到链接输入
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

export default UserGuidancePage
```

**UI Design:**
- Similar styling to LinkInputPage
- Large textarea for guidance input (required field)
- Red asterisk (*) to indicate required field
- Clear helper text explaining purpose
- Submit button disabled until guidance is provided
- "继续到链接输入" button (Continue to Link Input)

#### 1.2 Update App.tsx (Routing)

**File:** `client/src/App.tsx`

**Changes:**
1. Import new UserGuidancePage
2. Add route `/` for UserGuidancePage
3. Move LinkInputPage to `/links` route
4. Update ROUTE_ORDER for proper navigation animation

**Code Changes:**

```typescript
import UserGuidancePage from './pages/UserGuidancePage' // NEW
import LinkInputPage from './pages/LinkInputPage'

// Update route order
const ROUTE_ORDER: Record<string, number> = {
  '/': 1,           // UserGuidancePage (NEW)
  '/links': 2,      // LinkInputPage (moved from '/')
  '/scraping': 3,
  '/research': 4,
  '/phase3': 5,
  '/report': 6,
  '/history': 0,
}

// Add new route
<Route
  path="/"
  element={
    <motion.div
      key="page-guidance"
      initial="initial"
      animate="animate"
      exit="exit"
      variants={getVariants()}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="h-full"
    >
      <UserGuidancePage />
    </motion.div>
  }
/>

// Update LinkInputPage route
<Route
  path="/links"
  element={
    <motion.div
      key="page-links"
      initial="initial"
      animate="animate"
      exit="exit"
      variants={getVariants()}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="h-full"
    >
      <LinkInputPage />
    </motion.div>
  }
/>
```

#### 1.3 Update LinkInputPage.tsx

**File:** `client/src/pages/LinkInputPage.tsx`

**Changes:**
1. Remove guidance input field (moved to UserGuidancePage)
2. Use existing session_id from workflow store
3. Pass session_id to formatLinks API call

**Code Changes:**

```typescript
// Remove guidance state (no longer needed)
// const [userGuidance, setUserGuidance] = useState('') // REMOVED

// Get session_id from store
const { sessionId } = useWorkflowStore()

// Modify API call in handleSubmit
response = await apiService.formatLinks(urlList, sessionId)
```

#### 1.4 Update API Service (api.ts)

**File:** `client/src/services/api.ts`

**Changes:**
1. Add new `createSession` method
2. Modify `formatLinks` to accept `session_id` instead of `user_guidance`

**Code Changes:**

```typescript
// NEW: Create session endpoint
export interface CreateSessionResponse {
  session_id: string
}

createSession: async (
  userGuidance: string  // REQUIRED - no longer optional
): Promise<CreateSessionResponse> => {
  const response = await api.post('/sessions/create', {
    user_guidance: userGuidance  // Always send, never null
  })
  return response.data
}

// MODIFIED: formatLinks now uses session_id
formatLinks: async (
  urls: string[],
  sessionId?: string
): Promise<FormatLinksResponse> => {
  const response = await api.post('/links/format', {
    urls,
    session_id: sessionId || null  // Use session_id instead of user_guidance
  })
  return response.data
}
```

#### 1.5 Update WorkflowStore

**File:** `client/src/stores/workflowStore.ts`

**Changes:**
1. Add `sessionId` state
2. Add `setSessionId` action

**Code Changes:**

```typescript
// Add to store state
sessionId: string | null = null

// Add setter
setSessionId: (sessionId: string | null) => {
  set({ sessionId })
}
```

---

### 2. Backend Changes

#### 2.1 Create Session Endpoint (NEW)

**File:** `backend/app/main.py` (or wherever API endpoints are defined)

**Purpose:** Create a new research session with required user guidance

**New Endpoint:**

```python
@app.post("/api/sessions/create")
async def create_session(request: CreateSessionRequest):
    """
    Create a new research session with required user guidance.
    
    Request body:
    - user_guidance: Required user guidance for research
    """
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
    
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat() if hasattr(session, 'created_at') else None
    }
```

**Request Model:**

```python
class CreateSessionRequest(BaseModel):
    user_guidance: str  # REQUIRED - no longer Optional
```

#### 2.2 Format Links Endpoint (Modified)

**File:** `backend/app/main.py`

**Current Behavior:**
- Receives `{ urls: string[] }`
- Creates batch and returns `batch_id`

**New Behavior:**
- Receives `{ urls: string[], session_id?: string }`
- Loads existing session by `session_id` (if provided)
- Creates batch and returns `batch_id`

**Code Changes:**

```python
@app.post("/api/links/format")
async def format_links(request: FormatLinksRequest):
    """
    Format links and create batch.
    
    Request body:
    - urls: List of URLs
    - session_id: Optional session ID (if session already created)
    """
    urls = request.urls
    session_id = getattr(request, 'session_id', None)
    
    # Load existing session if session_id provided
    if session_id:
        try:
            session = ResearchSession.load(session_id)
            logger.info(f"Using existing session: {session_id}")
        except FileNotFoundError:
            logger.warning(f"Session not found: {session_id}, creating new")
            session = ResearchSession()
    else:
        # Fallback: create new session (backward compatibility)
        session = ResearchSession()
        logger.info("No session_id provided, created new session")
    
    # ... existing batch creation logic ...
    
    # Store batch_id in session
    session.set_metadata("batch_id", batch_id)
    session.save()
    
    return {
        "batch_id": batch_id,
        "items": formatted_items,
        "total": len(formatted_items),
        "session_id": session.session_id  # Return session_id for frontend
    }
```

**Request Model Update:**

```python
class FormatLinksRequest(BaseModel):
    urls: List[str]
    session_id: Optional[str] = None  # NEW field (replaces user_guidance)
```

#### 2.2 Agent.py - Phase 0.5 Method

**File:** `research/agent.py`

**Current Code (lines 204-209):**

```python
pre_role_feedback = session.get_metadata("phase_feedback_pre_role", "")
if force or not pre_role_feedback:
    pre_role_feedback = self.ui.prompt_user(
        "在生成研究角色前，你想强调哪些研究重点或背景？(可选，留空表示无额外指导)"
    )
    session.set_metadata("phase_feedback_pre_role", pre_role_feedback or "")
```

**New Code:**

```python
pre_role_feedback = session.get_metadata("phase_feedback_pre_role", "")

# Logic:
# 1. If force=True: Use existing value (or empty) - don't prompt
# 2. If value exists: Use it - don't prompt (collected earlier)
# 3. If value missing: Prompt user (fallback for backward compatibility)

if force:
    # When forcing, use existing value or empty string
    # Don't prompt even if empty (user may have intentionally left it blank)
    pre_role_feedback = pre_role_feedback or ""
elif not pre_role_feedback:
    # Only prompt if not already collected (backward compatibility)
    pre_role_feedback = self.ui.prompt_user(
        "在生成研究角色前，你想强调哪些研究重点或背景？(可选，留空表示无额外指导)"
    )
    session.set_metadata("phase_feedback_pre_role", pre_role_feedback or "")
else:
    # Value exists from earlier collection - use it
    logger.info(f"Using pre-collected user_guidance from session")
```

**Key Changes:**
- Check for existing value first
- Only prompt if missing (backward compatibility)
- When `force=True`, use existing value without prompting

---

## Backward Compatibility

### Scenarios

#### Scenario 1: New Flow (User provides guidance upfront)
1. User visits `/` → UserGuidancePage
2. User enters guidance (optional)
3. Submit → Session created with `user_guidance` stored
4. Navigate to `/links` → LinkInputPage
5. User enters URLs
6. Submit → Batch created using existing session
7. Phase 0 runs
8. Phase 0.5 reads from session → **No prompt** ✅

#### Scenario 2: Validation (Empty guidance)
1. User visits `/` → UserGuidancePage
2. User tries to submit without entering guidance
3. Frontend validation prevents submission → **Error shown** ✅
4. User must provide guidance before proceeding

#### Scenario 3: Backward Compatibility (Direct link access)
1. User directly visits `/links` (bypasses guidance page)
2. No session exists yet
3. User enters URLs
4. Submit → `session_id: null` sent
5. Backend creates new session (fallback)
6. Phase 0 runs
7. Phase 0.5 checks session → Not found (no guidance in fallback session)
8. Phase 0.5 prompts user → **Works as before** ✅
   
**Note:** For backward compatibility, direct `/links` access still works, but guidance will be prompted later in Phase 0.5.

#### Scenario 4: Force Rerun
1. User reruns Phase 0.5 with `force=True`
2. Phase 0.5 reads existing value from session
3. **No prompt** (respects force flag) ✅

---

## Testing Plan

### Unit Tests

#### Frontend Tests
1. **UserGuidancePage Component**
   - ✅ Guidance field renders correctly
   - ✅ Guidance value is captured in state
   - ✅ Empty guidance validation prevents submission
   - ✅ Submit button is disabled when guidance is empty
   - ✅ Error message shown when trying to submit empty guidance
   - ✅ Guidance is passed to API call

2. **API Service**
   - ✅ `createSession` requires `userGuidance` parameter
   - ✅ Non-empty guidance sends string value
   - ✅ Empty string validation handled on frontend

#### Backend Tests
1. **Create Session Endpoint**
   - ✅ Accepts `user_guidance` in request body (required)
   - ✅ Validates `user_guidance` is not empty
   - ✅ Returns 400 error if `user_guidance` is missing or empty
   - ✅ Stores `user_guidance` in session metadata
   - ✅ Returns correct `session_id`

2. **Format Links Endpoint**
   - ✅ Accepts `session_id` in request body
   - ✅ Loads existing session by `session_id`
   - ✅ Returns correct batch_id

3. **Phase 0.5 Method**
   - ✅ Uses pre-collected guidance when available
   - ✅ Prompts user when guidance missing (backward compat only)
   - ✅ Handles `force=True` correctly (no prompt)

### Integration Tests

1. **End-to-End: New Flow**
   ```
   User provides guidance → Submit links → Phase 0 → Phase 0.5
   Expected: No prompt in Phase 0.5, guidance used
   ```

2. **End-to-End: Validation**
   ```
   User tries to submit empty guidance → Frontend validation
   Expected: Error message shown, submission prevented
   ```

3. **End-to-End: Backward Compatibility (Direct /links access)**
   ```
   User directly visits /links → Submit links → Phase 0 → Phase 0.5
   Expected: Prompt appears in Phase 0.5 (backward compat fallback)
   ```

### Manual Testing Checklist

- [ ] Guidance field appears in UserGuidancePage
- [ ] Guidance field is required (cannot be left empty)
- [ ] Submit button is disabled when guidance is empty
- [ ] Error message shown when trying to submit empty guidance
- [ ] Guidance value is sent to backend
- [ ] Backend validates guidance is not empty
- [ ] Guidance is stored in session metadata
- [ ] Phase 0.5 uses stored guidance (no prompt)
- [ ] Phase 0.5 prompts when guidance missing (backward compat only)
- [ ] Force rerun respects existing guidance

---

## File Changes Summary

### Files to Create

1. **Frontend:**
   - `client/src/pages/UserGuidancePage.tsx` - NEW: First step page for guidance input

### Files to Modify

1. **Frontend:**
   - `client/src/App.tsx` - Add routing for UserGuidancePage, move LinkInputPage to `/links`
   - `client/src/pages/LinkInputPage.tsx` - Remove guidance field, use session_id
   - `client/src/services/api.ts` - Add `createSession`, modify `formatLinks` to use `session_id`
   - `client/src/stores/workflowStore.ts` - Add `sessionId` state

2. **Backend:**
   - `backend/app/main.py` - Add `createSession` endpoint, modify `formatLinks` to accept `session_id`
   - `research/agent.py` - Modify `run_phase0_5_role_generation` method (unchanged logic)

### Files to Review (No Changes)

- `research/phases/phase0_5_role_generation.py` - Already uses `user_guidance` parameter correctly
- `research/session.py` - Already supports metadata storage

---

## Risk Assessment

### Low Risk ✅
- **Backward Compatibility:** Fallback to prompting ensures existing flows work (direct `/links` access)
- **Required Field:** Guidance is required, but validation is clear and user-friendly
- **Minimal Changes:** Only 4 files modified, all isolated changes

### Potential Issues

1. **UI/UX Confusion**
   - **Risk:** Users might not understand what to provide in guidance
   - **Mitigation:** Clear helper text, examples in placeholder, required field indicator (*)

2. **Session State**
   - **Risk:** Guidance might not persist if session is recreated
   - **Mitigation:** Store immediately on session creation, verify in tests
   
3. **Required Field Validation**
   - **Risk:** Users might be frustrated by required field
   - **Mitigation:** Clear error messages, helpful placeholder examples, disabled submit button until filled

4. **Force Flag Behavior**
   - **Risk:** `force=True` might not work as expected
   - **Mitigation:** Explicit logic to handle force flag correctly

---

## Rollback Plan

If issues arise, rollback is simple:

1. **Frontend:** Remove guidance field from LinkInputPage
2. **Backend:** Remove `user_guidance` parameter from format links endpoint
3. **Agent:** Revert Phase 0.5 method to original (always prompt)

**No data migration needed** - existing sessions continue to work.

---

## Success Criteria

### Functional
- ✅ Users must provide guidance before link input (required field)
- ✅ Frontend validation prevents empty guidance submission
- ✅ Backend validation ensures guidance is not empty
- ✅ Guidance is used in Phase 0.5 without prompting
- ✅ Backward compatibility maintained (prompting still works for direct /links access)

### Non-Functional
- ✅ No performance impact
- ✅ No breaking changes to existing API
- ✅ Clear UI/UX for guidance input
- ✅ All tests pass

---

## Implementation Order

### Phase 1: Backend Changes (Foundation)
1. Add `createSession` endpoint to accept `user_guidance`
2. Store `user_guidance` in session metadata when creating session
3. Modify `formatLinks` endpoint to accept `session_id` instead of creating new session
4. Modify Phase 0.5 method to check for existing guidance (unchanged logic)
5. Test backend changes

### Phase 2: Frontend Changes (UI)
1. Create new `UserGuidancePage.tsx` component
2. Update `App.tsx` routing (add `/` for guidance, move links to `/links`)
3. Update `workflowStore.ts` to track `sessionId`
4. Update `api.ts` to add `createSession` and modify `formatLinks`
5. Update `LinkInputPage.tsx` to use existing session
6. Test frontend changes

### Phase 3: Integration Testing
1. End-to-end testing (new flow)
2. Backward compatibility testing (old flow)
3. Edge case testing (empty guidance, force rerun)

### Phase 4: Documentation
1. Update user documentation (if any)
2. Update API documentation
3. Update this plan with implementation status

---

## Open Questions

1. **Skip Option:** Should users be able to skip the guidance page and go directly to link input?
   - **Decision:** Yes, via backward compatibility (direct `/links` access), but guidance will be prompted in Phase 0.5
   
2. **Validation:** Should we validate guidance length/format?
   - **Decision:** Minimum length validation (e.g., at least 10 characters) - can add later if needed
   - **Current:** Only validates non-empty (trimmed string)
   
3. **Persistence:** Should guidance be editable after submission?
   - **Decision:** Not in initial implementation, can add edit functionality later
   - **Note:** Since guidance is required, users must provide it upfront
   
4. **Navigation:** Should there be a "Back" button on LinkInputPage to return to guidance?
   - **Decision:** Consider adding for better UX, but not required for MVP
   
5. **Session Resumption:** How should guidance work when resuming existing sessions?
   - **Decision:** If session already has guidance, don't show guidance page again

---

## Next Steps

1. **Review this plan** - Confirm approach and address open questions
2. **Approve implementation** - Get go-ahead to proceed
3. **Implement Phase 1** - Backend changes first
4. **Implement Phase 2** - Frontend changes
5. **Test thoroughly** - Integration and backward compatibility
6. **Deploy** - Roll out changes

---

## References

- Current implementation: `research/agent.py` lines 190-231
- Phase 0.5 implementation: `research/phases/phase0_5_role_generation.py`
- Frontend routing: `client/src/App.tsx`
- Frontend entry point: `client/src/pages/LinkInputPage.tsx` (will move to `/links`)
- New frontend page: `client/src/pages/UserGuidancePage.tsx` (NEW - route `/`)
- API service: `client/src/services/api.ts`
- Workflow store: `client/src/stores/workflowStore.ts`

---

**Document Status:** Ready for Review  
**Last Updated:** 2025-01-XX  
**Author:** Implementation Planning

