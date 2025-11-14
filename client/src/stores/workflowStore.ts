import { create } from 'zustand'

interface ScrapingItem {
  link_id?: string
  url: string
  status: 'pending' | 'in-progress' | 'completed' | 'failed'
  error?: string
  current_stage?: string
  stage_progress?: number
  overall_progress?: number
  status_message?: string
  started_at?: string
  completed_at?: string
  source?: string
  word_count?: number
  bytes_downloaded?: number
  total_bytes?: number
}

export interface SessionStep {
  step_id: number
  findings: {
    summary: string
    article?: string
    points_of_interest: {
      key_claims: Array<{
        claim: string
        supporting_evidence: string
      }>
      notable_evidence: Array<{
        evidence_type: string
        description: string
      }>
    }
    analysis_details: {
      five_whys: Array<{
        level: number
        question: string
        answer: string
      }>
      assumptions: string[]
      uncertainties: string[]
    }
  }
  insights: string
  confidence: number
  timestamp: string
}

export interface StreamState {
  isStreaming: boolean
  phase?: string | null
  metadata?: Record<string, any> | null
  startedAt?: string | null
  lastTokenAt?: string | null
  endedAt?: string | null
}

export interface StreamBufferState extends StreamState {
  id: string
  raw: string
  status: 'active' | 'completed' | 'error'
  tokenCount: number
  error?: string | null
  pinned?: boolean
}

interface StreamCollectionState {
  activeStreamId: string | null
  buffers: Record<string, StreamBufferState>
  order: string[]
  pinned: string[]
}

export interface LiveGoal {
  id: number
  goal_text?: string
  rationale?: string
  uses?: string[]
  sources?: string[]
  status: 'pending' | 'streaming' | 'ready' | 'error'
  updatedAt?: string
}

export interface LivePlanStep {
  step_id: number
  goal?: string
  required_data?: string
  chunk_strategy?: string
  notes?: string
  status: 'pending' | 'streaming' | 'ready' | 'error'
  updatedAt?: string
}

export interface LiveInsight {
  id: string
  title?: string
  summary?: string
  sources?: string[]
  status: 'pending' | 'streaming' | 'ready' | 'error'
  updatedAt?: string
}

export interface LiveAction {
  id: string
  description?: string
  result?: string
  status: 'pending' | 'streaming' | 'ready' | 'error'
  updatedAt?: string
}

export interface LiveReportSection {
  id: string
  heading?: string
  content?: string
  status: 'pending' | 'streaming' | 'ready' | 'error'
  updatedAt?: string
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  status: 'queued' | 'in_progress' | 'completed' | 'error'
  timestamp: string
  metadata?: Record<string, any>
}

interface WorkflowState {
  currentPhase: 'input' | 'scraping' | 'research' | 'phase3' | 'phase4' | 'complete'
  batchId: string | null
  workflowId: string | null
  workflowStarted: boolean  // Track if workflow has been started for current batchId
  sessionId: string | null
  reportStale: boolean
  rerunState: {
    inProgress: boolean
    phase: string | null
    phases: string[]
    lastError: string | null
  }
  stepRerunState: {
    inProgress: boolean
    stepId: number | null
    regenerateReport: boolean
    lastError: string | null
  }
  
  // Progress tracking
  overallProgress: number
  currentStep: string | null
  stepProgress: number
  
  // Scraping phase
  scrapingStatus: {
    total: number  // Total from started processes (for backward compatibility)
    expectedTotal: number  // Expected total from batch:initialized (the actual target)
    completed: number
    failed: number
    inProgress: number
    items: ScrapingItem[]
    completionRate: number  // 0.0 to 1.0 from backend
    is100Percent: boolean  // Flag from backend
    canProceedToResearch: boolean  // Flag from backend
  }
  
  // Cancellation state
  cancelled: boolean
  cancellationInfo: {
    cancelled_at?: string
    reason?: string
    state_at_cancellation?: any
  } | null
  
  // Research agent phase
  researchAgentStatus: {
    streams: StreamCollectionState
    phase: string
    currentAction: string | null
    waitingForUser: boolean
    userInputRequired: {
      type: 'goal_selection' | 'plan_confirmation' | 'custom_input'
      prompt_id?: string
      prompt?: string
      data?: any
    } | null
    streamBuffer: string
    streamingState: StreamState
    liveGoals: Record<number, LiveGoal>
    goalOrder: number[]
    goals: Array<{
      id: number
      goal_text: string
      uses?: string[]
    }> | null
    livePlanSteps: Record<number, LivePlanStep>
    planOrder: number[]
    plan: Array<{
      step_id: number
      goal: string
      required_data?: string
      chunk_strategy?: string
      notes?: string
    }> | null
    liveInsights: Record<string, LiveInsight>
    liveActions: Record<string, LiveAction>
    liveReportSections: Record<string, LiveReportSection>
    synthesizedGoal: {
      comprehensive_topic: string
      component_questions: string[]
      unifying_theme?: string
    } | null
    summarizationProgress: {
      currentItem: number
      totalItems: number
      linkId: string
      stage: string
      progress: number
      message: string
    } | null
    conversationMessages: ConversationMessage[]
  }
  
  // Phase 3
  phase3Steps: SessionStep[]
  currentStepId: number | null
  
  // Phase 4
  finalReport: {
    content: string
    generatedAt: string
    status: 'generating' | 'ready' | 'error'
  } | null
  
  // Error handling
  errors: Array<{
    phase: string
    message: string
    timestamp: string
  }>
  
  // Actions
  setBatchId: (batchId: string) => void
  setWorkflowStarted: (started: boolean) => void
  setCurrentPhase: (phase: WorkflowState['currentPhase']) => void
  updateProgress: (progress: number) => void
  updateScrapingStatus: (status: Partial<WorkflowState['scrapingStatus']>) => void
  updateScrapingItem: (url: string, status: ScrapingItem['status'], error?: string) => void
  updateScrapingItemProgress: (link_id: string | undefined, url: string, progress: Partial<ScrapingItem>) => void
  setCancelled: (cancelled: boolean, cancellationInfo?: WorkflowState['cancellationInfo']) => void
  updateResearchAgentStatus: (status: Partial<WorkflowState['researchAgentStatus']>) => void
  setGoals: (goals: WorkflowState['researchAgentStatus']['goals']) => void
  setPlan: (plan: WorkflowState['researchAgentStatus']['plan']) => void
  setSynthesizedGoal: (goal: WorkflowState['researchAgentStatus']['synthesizedGoal']) => void
  startStream: (streamId: string, options: { phase?: string | null; metadata?: Record<string, any> | null; startedAt?: string | null }) => void
  appendStreamToken: (streamId: string, token: string) => void
  completeStream: (streamId: string, metadata?: Partial<StreamBufferState>) => void
  setStreamError: (streamId: string, error: string) => void
  setActiveStream: (streamId: string | null) => void
  pinStream: (streamId: string) => void
  unpinStream: (streamId: string) => void
  clearStreamBuffer: (streamId?: string) => void
  updateLiveGoal: (goal: Partial<LiveGoal> & { id: number }) => void
  updateLivePlanStep: (step: Partial<LivePlanStep> & { step_id: number }) => void
  updateLiveInsight: (insight: Partial<LiveInsight> & { id: string }) => void
  updateLiveAction: (action: Partial<LiveAction> & { id: string }) => void
  updateLiveReportSection: (section: Partial<LiveReportSection> & { id: string }) => void
  upsertConversationMessage: (message: ConversationMessage) => void
  resetConversationMessages: () => void
  addPhase3Step: (step: SessionStep) => void
  setPhase3Steps: (steps: SessionStep[], nextStepId?: number | null) => void
  setFinalReport: (report: WorkflowState['finalReport']) => void
  addError: (phase: string, message: string) => void
  reset: () => void
  validateState: () => { isValid: boolean; errors: string[] }
  setSessionId: (sessionId: string | null) => void
  setReportStale: (stale: boolean) => void
  setPhaseRerunState: (state: Partial<WorkflowState['rerunState']>) => void
  setStepRerunState: (state: Partial<WorkflowState['stepRerunState']>) => void
}

const initialState: Omit<WorkflowState, keyof {
  setBatchId: any
  setWorkflowStarted: any
  setCurrentPhase: any
  updateProgress: any
  updateScrapingStatus: any
  updateScrapingItem: any
  updateResearchAgentStatus: any
  startStream: any
  appendStreamToken: any
  completeStream: any
  setStreamError: any
  setActiveStream: any
  pinStream: any
  unpinStream: any
  clearStreamBuffer: any
  updateLiveGoal: any
  updateLivePlanStep: any
  updateLiveInsight: any
  updateLiveAction: any
  updateLiveReportSection: any
  addPhase3Step: any
  setFinalReport: any
  addError: any
  reset: any
  validateState: any
}> = {
  currentPhase: 'input',
  batchId: null,
  workflowId: null,
  workflowStarted: false,
  sessionId: null,
  reportStale: false,
  rerunState: {
    inProgress: false,
    phase: null,
    phases: [],
    lastError: null,
  },
  stepRerunState: {
    inProgress: false,
    stepId: null,
    regenerateReport: true,
    lastError: null,
  },
  overallProgress: 0,
  currentStep: null,
  stepProgress: 0,
  scrapingStatus: {
    total: 0,
    expectedTotal: 0,  // Will be set from batch:initialized
    completed: 0,
    failed: 0,
    inProgress: 0,
    items: [],
    completionRate: 0.0,
    is100Percent: false,
    canProceedToResearch: false,
  },
  researchAgentStatus: {
    streams: {
      activeStreamId: null,
      buffers: {},
      order: [],
      pinned: [],
    },
    phase: '0.5',
    currentAction: null,
    waitingForUser: false,
    userInputRequired: null,
    streamBuffer: '',
    streamingState: {
      isStreaming: false,
      phase: null,
      metadata: null,
      startedAt: null,
      lastTokenAt: null,
      endedAt: null,
    },
    liveGoals: {},
    goalOrder: [],
    goals: null,
    livePlanSteps: {},
    planOrder: [],
    plan: null,
    liveInsights: {},
    liveActions: {},
    liveReportSections: {},
    synthesizedGoal: null,
    summarizationProgress: null,
    conversationMessages: [],
  },
  phase3Steps: [],
  currentStepId: null,
  finalReport: null,
  errors: [],
  cancelled: false,
  cancellationInfo: null,
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  ...initialState,
  
  setBatchId: (batchId) => {
    // Reset ALL workflow state when batchId changes (new session)
    set((state) => {
      // If batchId is the same, don't reset
      if (state.batchId === batchId) {
        return { batchId, workflowStarted: state.workflowStarted }
      }
      
      // If batchId changed, reset all workflow state to initial values
      return {
        batchId,
        workflowId: null,
        workflowStarted: false,
        currentPhase: 'input',
        sessionId: null,
        reportStale: false,
        rerunState: {
          inProgress: false,
          phase: null,
          phases: [],
          lastError: null,
        },
        stepRerunState: {
          inProgress: false,
          stepId: null,
          regenerateReport: true,
          lastError: null,
        },
        overallProgress: 0,
        currentStep: null,
        stepProgress: 0,
        scrapingStatus: {
          total: 0,
          expectedTotal: 0,
          completed: 0,
          failed: 0,
          inProgress: 0,
          items: [],
          completionRate: 0.0,
          is100Percent: false,
          canProceedToResearch: false,
        },
        cancelled: false,
        cancellationInfo: null,
        researchAgentStatus: {
          streams: {
            activeStreamId: null,
            buffers: {},
            order: [],
            pinned: [],
          },
          phase: '0.5',
          currentAction: null,
          waitingForUser: false,
          userInputRequired: null,
          streamBuffer: '',
          streamingState: {
            isStreaming: false,
            phase: null,
            metadata: null,
            startedAt: null,
            lastTokenAt: null,
            endedAt: null,
          },
          liveGoals: {},
          goalOrder: [],
          goals: null,
          livePlanSteps: {},
          planOrder: [],
          plan: null,
          liveInsights: {},
          liveActions: {},
          liveReportSections: {},
          synthesizedGoal: null,
          summarizationProgress: null,
          conversationMessages: [],
        },
        phase3Steps: [],
        currentStepId: null,
        finalReport: null,
        errors: [],
      }
    })
  },
  setWorkflowStarted: (started) => set({ workflowStarted: started }),
  setCurrentPhase: (phase) => set({ currentPhase: phase }),
  updateProgress: (progress) => set({ overallProgress: progress }),
  updateScrapingStatus: (status) =>
    set((state) => {
      // CRITICAL: Only include expectedTotal in update if it's > 0
      // Never overwrite with 0 or undefined - preserve existing value if new value is invalid
      const updatedStatus = { ...status }
      if (updatedStatus.expectedTotal !== undefined) {
        if (updatedStatus.expectedTotal === 0 || updatedStatus.expectedTotal === null) {
          // Don't overwrite with 0 - preserve existing value if we have one
          if (state.scrapingStatus.expectedTotal > 0) {
            delete updatedStatus.expectedTotal  // Don't overwrite existing value
          } else {
            // If we don't have a value yet, don't set it to 0 either - wait for valid value
            delete updatedStatus.expectedTotal
          }
        }
        // If expectedTotal > 0, keep it in the update (will overwrite existing)
      }
      return {
        scrapingStatus: { ...state.scrapingStatus, ...updatedStatus },
      }
    }),
  updateScrapingItem: (url, status, error) =>
    set((state) => {
      const items = state.scrapingStatus.items.map((item) =>
        item.url === url ? { ...item, status, error } : item
      )
      const completed = items.filter((i) => i.status === 'completed').length
      const failed = items.filter((i) => i.status === 'failed').length
      const inProgress = items.filter((i) => i.status === 'in-progress').length
      
      return {
        scrapingStatus: {
          ...state.scrapingStatus,
          items,
          completed,
          failed,
          inProgress,
        },
      }
    }),
  updateScrapingItemProgress: (link_id, url, progress) =>
    set((state) => {
      const items = state.scrapingStatus.items.map((item) => {
        // Match by link_id if available, otherwise by url
        const matches = link_id ? item.link_id === link_id : item.url === url
        if (matches) {
          return { ...item, ...progress, status: progress.status || item.status || 'in-progress' }
        }
        return item
      })
      
      // If item doesn't exist, add it
      const exists = items.some((item) => 
        (link_id && item.link_id === link_id) || (!link_id && item.url === url)
      )
      if (!exists) {
        items.push({
          link_id,
          url,
          status: progress.status || 'in-progress',
          ...progress,
        })
      }
      
      const completed = items.filter((i) => i.status === 'completed').length
      const failed = items.filter((i) => i.status === 'failed').length
      const inProgress = items.filter((i) => i.status === 'in-progress' || i.status === 'pending').length
      
      return {
        scrapingStatus: {
          ...state.scrapingStatus,
          items,
          completed,
          failed,
          inProgress,
        },
      }
    }),
  updateResearchAgentStatus: (status) =>
    set((state) => ({
      researchAgentStatus: { ...state.researchAgentStatus, ...status },
    })),
  setGoals: (goals) =>
    set((state) => {
      const liveGoals = { ...state.researchAgentStatus.liveGoals }
      const goalOrder: number[] = []
      const timestamp = new Date().toISOString()

      if (goals) {
        goals.forEach((goal) => {
          if (!goal) {
            return
          }
          const id = goal.id ?? goalOrder.length + 1
          goalOrder.push(id)
          const existing = liveGoals[id] || { id, status: 'ready' as LiveGoal['status'] }
          liveGoals[id] = {
            ...existing,
            ...goal,
            id,
            status: 'ready',
            updatedAt: timestamp,
          }
        })
      }

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          goals,
          liveGoals,
          goalOrder: goalOrder.length ? goalOrder : state.researchAgentStatus.goalOrder,
        },
      }
    }),
  setPlan: (plan) =>
    set((state) => {
      const livePlanSteps = { ...state.researchAgentStatus.livePlanSteps }
      const planOrder: number[] = []
      const timestamp = new Date().toISOString()

      if (plan) {
        plan.forEach((step) => {
          if (!step) {
            return
          }
          const id = step.step_id
          planOrder.push(id)
          const existing = livePlanSteps[id] || { step_id: id, status: 'ready' as LivePlanStep['status'] }
          livePlanSteps[id] = {
            ...existing,
            ...step,
            step_id: id,
            status: 'ready',
            updatedAt: timestamp,
          }
        })
      }

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          plan,
          livePlanSteps,
          planOrder: planOrder.length ? planOrder : state.researchAgentStatus.planOrder,
        },
      }
    }),
  setSynthesizedGoal: (synthesizedGoal) =>
    set((state) => ({
      researchAgentStatus: { ...state.researchAgentStatus, synthesizedGoal },
    })),
  startStream: (streamId, options) =>
    set((state) => {
      const now = options.startedAt || new Date().toISOString()
      const buffers = { ...state.researchAgentStatus.streams.buffers }
      buffers[streamId] = {
        id: streamId,
        raw: '',
        status: 'active',
        tokenCount: 0,
        isStreaming: true,
        phase: options.phase ?? null,
        metadata: options.metadata ?? null,
        startedAt: now,
        lastTokenAt: null,
        endedAt: null,
      }

      const order = [streamId, ...state.researchAgentStatus.streams.order.filter((id) => id !== streamId)]

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            activeStreamId: streamId,
            buffers,
            order,
          },
          streamBuffer: '',
          streamingState: {
            isStreaming: true,
            phase: options.phase ?? null,
            metadata: options.metadata ?? null,
            startedAt: now,
            lastTokenAt: null,
            endedAt: null,
          },
        },
      }
    }),
  appendStreamToken: (streamId, token) =>
    set((state) => {
      const buffers = { ...state.researchAgentStatus.streams.buffers }
      const buffer = buffers[streamId] || {
        id: streamId,
        raw: '',
        status: 'active' as const,
        tokenCount: 0,
        isStreaming: true,
        phase: null,
        metadata: null,
        startedAt: new Date().toISOString(),
        lastTokenAt: null,
        endedAt: null,
      }
      const lastTokenAt = new Date().toISOString()
      const updatedBuffer: StreamBufferState = {
        ...buffer,
        raw: buffer.raw + token,
        tokenCount: buffer.tokenCount + 1,
        lastTokenAt,
        isStreaming: true,
        status: 'active',
      }
      buffers[streamId] = updatedBuffer

      const isActive = state.researchAgentStatus.streams.activeStreamId === streamId
      const streamBufferValue = isActive ? updatedBuffer.raw : state.researchAgentStatus.streamBuffer
      const streamingState = isActive
        ? {
            isStreaming: true,
            phase: updatedBuffer.phase ?? state.researchAgentStatus.streamingState.phase ?? null,
            metadata: updatedBuffer.metadata ?? state.researchAgentStatus.streamingState.metadata ?? null,
            startedAt: updatedBuffer.startedAt ?? state.researchAgentStatus.streamingState.startedAt ?? null,
            lastTokenAt,
            endedAt: null,
          }
        : state.researchAgentStatus.streamingState

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            buffers,
          },
          streamBuffer: streamBufferValue,
          streamingState,
        },
      }
    }),
  completeStream: (streamId, metadata) =>
    set((state) => {
      const buffers = { ...state.researchAgentStatus.streams.buffers }
      const buffer = buffers[streamId]
      if (!buffer) {
        return {}
      }
      const endedAt = metadata?.endedAt ?? new Date().toISOString()
      buffers[streamId] = {
        ...buffer,
        status: metadata?.status ?? 'completed',
        metadata: metadata?.metadata ?? buffer.metadata,
        isStreaming: false,
        endedAt,
        lastTokenAt: metadata?.lastTokenAt ?? buffer.lastTokenAt,
      }

      const isActive = state.researchAgentStatus.streams.activeStreamId === streamId
      const streamingState = isActive
        ? {
            isStreaming: false,
            phase: buffers[streamId].phase ?? state.researchAgentStatus.streamingState.phase ?? null,
            metadata: buffers[streamId].metadata ?? state.researchAgentStatus.streamingState.metadata ?? null,
            startedAt: buffers[streamId].startedAt ?? state.researchAgentStatus.streamingState.startedAt ?? null,
            lastTokenAt: buffers[streamId].lastTokenAt ?? state.researchAgentStatus.streamingState.lastTokenAt ?? null,
            endedAt,
          }
        : state.researchAgentStatus.streamingState

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            buffers,
          },
          streamingState,
        },
      }
    }),
  setStreamError: (streamId, error) =>
    set((state) => {
      const buffers = { ...state.researchAgentStatus.streams.buffers }
      const buffer = buffers[streamId]
      if (!buffer) {
        return {}
      }
      buffers[streamId] = {
        ...buffer,
        status: 'error',
        error,
        isStreaming: false,
        endedAt: new Date().toISOString(),
      }
      const isActive = state.researchAgentStatus.streams.activeStreamId === streamId
      const streamingState = isActive
        ? {
            isStreaming: false,
            phase: buffer.phase ?? null,
            metadata: buffer.metadata ?? null,
            startedAt: buffer.startedAt ?? null,
            lastTokenAt: buffer.lastTokenAt ?? null,
            endedAt: buffers[streamId].endedAt ?? null,
          }
        : state.researchAgentStatus.streamingState
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            buffers,
          },
          streamingState,
        },
      }
    }),
  setActiveStream: (streamId) =>
    set((state) => {
      if (streamId === state.researchAgentStatus.streams.activeStreamId) {
        return {}
      }
      const buffers = state.researchAgentStatus.streams.buffers
      const buffer = streamId ? buffers[streamId] : undefined
      const streamBufferValue = buffer ? buffer.raw : ''
      const streamingState = buffer
        ? {
            isStreaming: buffer.isStreaming,
            phase: buffer.phase ?? null,
            metadata: buffer.metadata ?? null,
            startedAt: buffer.startedAt ?? null,
            lastTokenAt: buffer.lastTokenAt ?? null,
            endedAt: buffer.endedAt ?? null,
          }
        : {
            isStreaming: false,
            phase: null,
            metadata: null,
            startedAt: null,
            lastTokenAt: null,
            endedAt: null,
          }
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            activeStreamId: streamId,
          },
          streamBuffer: streamBufferValue,
          streamingState,
        },
      }
    }),
  pinStream: (streamId) =>
    set((state) => {
      const pinned = new Set(state.researchAgentStatus.streams.pinned)
      pinned.add(streamId)
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            pinned: Array.from(pinned),
          },
        },
      }
    }),
  unpinStream: (streamId) =>
    set((state) => {
      const pinned = state.researchAgentStatus.streams.pinned.filter((id) => id !== streamId)
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            ...state.researchAgentStatus.streams,
            pinned,
          },
        },
      }
    }),
  clearStreamBuffer: (streamId) =>
    set((state) => {
      if (streamId) {
        const buffers = { ...state.researchAgentStatus.streams.buffers }
        const buffer = buffers[streamId]
        if (buffer) {
          buffers[streamId] = {
            ...buffer,
            raw: '',
            tokenCount: 0,
          }
        }
        const isActive = state.researchAgentStatus.streams.activeStreamId === streamId
        return {
          researchAgentStatus: {
            ...state.researchAgentStatus,
            streams: {
              ...state.researchAgentStatus.streams,
              buffers,
            },
            streamBuffer: isActive ? '' : state.researchAgentStatus.streamBuffer,
          },
        }
      }
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          streams: {
            activeStreamId: null,
            buffers: {},
            order: [],
            pinned: [],
          },
          streamBuffer: '',
          streamingState: {
            isStreaming: false,
            phase: null,
            metadata: null,
            startedAt: null,
            lastTokenAt: null,
            endedAt: null,
          },
        },
      }
    }),
  updateLiveGoal: (goal) =>
    set((state) => {
      const id = goal.id
      const previous = state.researchAgentStatus.liveGoals[id]
      const merged: LiveGoal = {
        id,
        goal_text: previous?.goal_text,
        rationale: previous?.rationale,
        uses: previous?.uses,
        sources: previous?.sources,
        status: goal.status || previous?.status || 'streaming',
        updatedAt: new Date().toISOString(),
        ...goal,
      }

      const liveGoals = {
        ...state.researchAgentStatus.liveGoals,
        [id]: merged,
      }

      const existingGoals = state.researchAgentStatus.goals || []
      const goals = existingGoals.length
        ? existingGoals.map((g) => (g?.id === id ? { ...g, ...goal } : g))
        : null

      const goalOrder = state.researchAgentStatus.goalOrder.includes(id)
        ? state.researchAgentStatus.goalOrder
        : [...state.researchAgentStatus.goalOrder, id]

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          liveGoals,
          goals,
          goalOrder,
        },
      }
    }),
  updateLivePlanStep: (step) =>
    set((state) => {
      const id = step.step_id
      const previous = state.researchAgentStatus.livePlanSteps[id]
      const merged: LivePlanStep = {
        step_id: id,
        goal: previous?.goal,
        required_data: previous?.required_data,
        chunk_strategy: previous?.chunk_strategy,
        notes: previous?.notes,
        status: step.status || previous?.status || 'streaming',
        updatedAt: new Date().toISOString(),
        ...step,
      }

      const livePlanSteps = {
        ...state.researchAgentStatus.livePlanSteps,
        [id]: merged,
      }

      const existingPlan = state.researchAgentStatus.plan || []
      const plan = existingPlan.length
        ? existingPlan.map((p) => (p?.step_id === id ? { ...p, ...step } : p))
        : null

      const planOrder = state.researchAgentStatus.planOrder.includes(id)
        ? state.researchAgentStatus.planOrder
        : [...state.researchAgentStatus.planOrder, id]

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          livePlanSteps,
          plan,
          planOrder,
        },
      }
    }),
  updateLiveInsight: (insight) =>
    set((state) => {
      const id = insight.id
      const previous = state.researchAgentStatus.liveInsights[id]
      const merged: LiveInsight = {
        id,
        title: previous?.title,
        summary: previous?.summary,
        sources: previous?.sources,
        status: insight.status || previous?.status || 'streaming',
        updatedAt: new Date().toISOString(),
        ...insight,
      }

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          liveInsights: {
            ...state.researchAgentStatus.liveInsights,
            [id]: merged,
          },
        },
      }
    }),
  updateLiveAction: (action) =>
    set((state) => {
      const id = action.id
      const previous = state.researchAgentStatus.liveActions[id]
      const merged: LiveAction = {
        id,
        description: previous?.description,
        result: previous?.result,
        status: action.status || previous?.status || 'streaming',
        updatedAt: new Date().toISOString(),
        ...action,
      }

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          liveActions: {
            ...state.researchAgentStatus.liveActions,
            [id]: merged,
          },
        },
      }
    }),
  updateLiveReportSection: (section) =>
    set((state) => {
      const id = section.id
      const previous = state.researchAgentStatus.liveReportSections[id]
      const merged: LiveReportSection = {
        id,
        heading: previous?.heading,
        content: previous?.content,
        status: section.status || previous?.status || 'streaming',
        updatedAt: new Date().toISOString(),
        ...section,
      }

      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          liveReportSections: {
            ...state.researchAgentStatus.liveReportSections,
            [id]: merged,
          },
        },
      }
    }),
  upsertConversationMessage: (message) =>
    set((state) => {
      const existing = state.researchAgentStatus.conversationMessages.filter((item) => item.id !== message.id)
      const merged = [...existing, message].sort((a, b) => {
        const aTime = new Date(a.timestamp).getTime()
        const bTime = new Date(b.timestamp).getTime()
        return aTime - bTime
      })
      const limited = merged.length > 200 ? merged.slice(merged.length - 200) : merged
      return {
        researchAgentStatus: {
          ...state.researchAgentStatus,
          conversationMessages: limited,
        },
      }
    }),
  resetConversationMessages: () =>
    set((state) => ({
      researchAgentStatus: {
        ...state.researchAgentStatus,
        conversationMessages: [],
      },
    })),
  addPhase3Step: (step) =>
    set((state) => {
      // Use Set for O(1) lookup to check if step already exists
      // This prevents race conditions when multiple messages arrive quickly
      const stepIds = new Set(state.phase3Steps.map((s) => s.step_id))
      
      let updatedSteps: SessionStep[]
      if (stepIds.has(step.step_id)) {
        // Step already exists - update it and remove any duplicates
        // Use Map to ensure only one entry per step_id (keeps the latest)
        const stepsMap = new Map<number, SessionStep>()
        
        // First, add all existing steps (this will deduplicate if there are already duplicates)
        state.phase3Steps.forEach((s) => {
          if (s.step_id !== step.step_id) {
            stepsMap.set(s.step_id, s)
          }
        })
        
        // Then add/update the new step
        stepsMap.set(step.step_id, step)
        
        updatedSteps = Array.from(stepsMap.values())
      } else {
        // New step - add it
        updatedSteps = [...state.phase3Steps, step]
      }
      
      // Sort steps by step_id to ensure correct order
      updatedSteps.sort((a, b) => a.step_id - b.step_id)
      
      return {
        phase3Steps: updatedSteps,
        currentStepId: step.step_id,
      }
    }),
  setPhase3Steps: (steps, nextStepId) =>
    set(() => {
      const sorted = [...steps].sort((a, b) => a.step_id - b.step_id)
      const lastCompleted = sorted.length ? sorted[sorted.length - 1].step_id : null
      const currentStepId = typeof nextStepId === 'number' ? nextStepId : lastCompleted
      return {
        phase3Steps: sorted,
        currentStepId,
      }
    }),
  setFinalReport: (report) => set({ finalReport: report }),
  addError: (phase, message) =>
    set((state) => ({
      errors: [
        ...state.errors,
        {
          phase,
          message,
          timestamp: new Date().toISOString(),
        },
      ],
    })),
  setCancelled: (cancelled, cancellationInfo) =>
    set({ cancelled, cancellationInfo: cancellationInfo || null }),
  setSessionId: (sessionId) => set({ sessionId }),
  setReportStale: (stale) => set({ reportStale: stale }),
  setPhaseRerunState: (payload) =>
    set((state) => ({
      rerunState: {
        ...state.rerunState,
        ...payload,
        phases: payload.phases ?? state.rerunState.phases,
      },
    })),
  setStepRerunState: (payload) =>
    set((state) => ({
      stepRerunState: {
        ...state.stepRerunState,
        ...payload,
      },
    })),
  reset: () => set({ ...initialState, workflowStarted: false }),
  validateState: () => {
    const state = useWorkflowStore.getState()
    const errors: string[] = []

    // Validate that if batchId exists, workflow state is consistent
    if (state.batchId) {
      // If scrapingStatus has items, they should belong to current batchId
      if (state.scrapingStatus.items.length > 0 && !state.batchId) {
        errors.push('Scraping items exist but no batchId set')
      }

      // If research goals exist, scraping should be completed
      if (state.researchAgentStatus.goals !== null && state.scrapingStatus.completed === 0) {
        errors.push('Research goals exist but scraping not completed')
      }

      // If phase3 steps exist, research plan should exist
      if (state.phase3Steps.length > 0 && state.researchAgentStatus.plan === null) {
        errors.push('Phase3 steps exist but no research plan found')
      }

      // If final report exists, phase3 should be completed
      if (state.finalReport !== null && state.researchAgentStatus.plan !== null) {
        const expectedSteps = state.researchAgentStatus.plan.length
        if (state.phase3Steps.length < expectedSteps) {
          errors.push(`Final report exists but phase3 incomplete (${state.phase3Steps.length}/${expectedSteps} steps)`)
        }
      }

      // Workflow started should be true if there's any progress
      if (state.workflowStarted === false && (
        state.scrapingStatus.total > 0 ||
        state.researchAgentStatus.goals !== null ||
        state.phase3Steps.length > 0
      )) {
        errors.push('Workflow has progress but workflowStarted is false')
      }
    } else {
      // If no batchId, all state should be reset
      if (state.scrapingStatus.total > 0 ||
          state.researchAgentStatus.goals !== null ||
          state.phase3Steps.length > 0 ||
          state.finalReport !== null) {
        errors.push('No batchId but workflow state exists (state should be reset)')
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
    }
  },
}))


