import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import Card from '../components/common/Card'
import Button from '../components/common/Button'
import { apiService } from '../services/api'
import { SessionStep, useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'

interface HistorySession {
  batch_id: string
  session_id: string  // Added for precise session deletion
  created_at: string
  status: 'completed' | 'in-progress' | 'failed' | 'cancelled'
  topic?: string
  url_count?: number
  current_phase?: string
}

interface ScrapingStatusSnapshot {
  total?: number
  expected_total?: number
  completed?: number
  failed?: number
  inProgress?: number
  items?: any[]
  completionRate?: number
  is100Percent?: boolean
  canProceedToResearch?: boolean
}

interface Phase3State {
  plan?: Array<{ step_id: number }>
  steps?: SessionStep[]
  completed_step_ids?: number[]
  total_steps?: number
  next_step_id?: number | null
  synthesized_goal?: any
}

interface HistorySessionDetail extends HistorySession {
  session_id?: string
  metadata?: Record<string, any>
  scraping_status?: ScrapingStatusSnapshot
  phase3?: Phase3State
  resume_required?: boolean
  data_loaded?: boolean
}

const HistoryPage: React.FC = () => {
  const navigate = useNavigate()
  const {
    setBatchId,
    setCurrentPhase,
    setWorkflowStarted,
    setPlan,
    setSynthesizedGoal,
    setPhase3Steps,
    setSessionId,
    updateScrapingStatus,
    updateResearchAgentStatus,
    setGoals,
  } = useWorkflowStore()
  const { addNotification } = useUiStore()
  const [sessions, setSessions] = useState<HistorySession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [exportingBatchId, setExportingBatchId] = useState<string | null>(null)

  useEffect(() => {
    loadHistory()
  }, [filterStatus])

  /**
   * Hydrate workflow store with session data.
   * This ensures the progress bar shows all completed phases correctly.
   */
  const hydrateWorkflowState = (sessionData: HistorySessionDetail) => {
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

    // Hydrate research agent status from metadata
    const metadata = sessionData.metadata || {}
    const goals = metadata.phase1_confirmed_goals || []
    const plan = metadata.research_plan || sessionData.phase3?.plan || []
    const synthesizedGoal = metadata.synthesized_goal || sessionData.phase3?.synthesized_goal || null

    // Determine research agent phase based on available data
    // If plan exists, research agent is complete (phase 2)
    // If goals exist but no plan, research agent is in progress (phase 1)
    // Otherwise, research agent hasn't started (phase 0.5)
    let researchPhase: string = '0.5'
    if (plan && Array.isArray(plan) && plan.length > 0) {
      researchPhase = '2'  // Phase 2 complete - plan exists
    } else if (goals && Array.isArray(goals) && goals.length > 0) {
      researchPhase = '1'  // Phase 1 in progress - goals exist but no plan yet
    }

    // Map goals to the format expected by the store
    const mappedGoals = goals.map((g: any) => ({
      id: g.id || g.goal_id || 0,
      goal_text: g.goal_text || g.goal || '',
      uses: g.uses || [],
      sources: g.sources || [],
    }))

    // Update research agent status
    updateResearchAgentStatus({
      phase: researchPhase,
      currentAction: null,
      waitingForUser: false,
      userInputRequired: null,
    })

    // Set goals and plan
    if (mappedGoals.length > 0) {
      setGoals(mappedGoals)
    }
    if (plan && Array.isArray(plan) && plan.length > 0) {
      setPlan(plan)
    }
    if (synthesizedGoal) {
      setSynthesizedGoal(synthesizedGoal)
    }

    // Hydrate Phase 3 plan/steps if present
    if (sessionData.phase3) {
      const phase3Plan = sessionData.phase3.plan || plan || []
      const phase3Steps = (sessionData.phase3.steps as SessionStep[]) || []
      
      // Set plan if not already set
      if (phase3Plan.length > 0 && (!plan || plan.length === 0)) {
        setPlan(phase3Plan)
      }
      
      // Set synthesized goal if not already set
      if (sessionData.phase3.synthesized_goal && !synthesizedGoal) {
        setSynthesizedGoal(sessionData.phase3.synthesized_goal)
      }
      
      // Set phase 3 steps
      if (phase3Steps.length > 0) {
        setPhase3Steps(phase3Steps, sessionData.phase3.next_step_id ?? null)
      }
    }
  }

  const loadHistory = async () => {
    setLoading(true)
    setError(null)
    try {
      const params: any = {}
      if (filterStatus !== 'all') {
        params.status = filterStatus
      }
      const data = await apiService.getHistory(params)
      setSessions(data.sessions || data || [])
    } catch (err: any) {
      console.error('Failed to load history:', err)
      setError(err.response?.data?.detail || err.message || '无法加载历史记录，请刷新页面重试')
      addNotification('无法加载历史记录，请刷新页面重试', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleResume = async (batchId: string) => {
    try {
      // Load session data
      const sessionData = (await apiService.getHistorySession(batchId)) as HistorySessionDetail
      
      // Restore workflow state
      setBatchId(batchId)
      setSessionId(sessionData.session_id || null)
      setWorkflowStarted(false)

      // Hydrate workflow state (scraping, research agent, phase 3)
      hydrateWorkflowState(sessionData)
      
      // Determine current phase from session data
      const resolvedPhase =
        sessionData.current_phase ||
        (sessionData.status === 'completed' ? 'complete' : sessionData.data_loaded ? 'research' : 'scraping')

      // Resume workflow FIRST (before setting phase or navigating)
      // Resume if workflow is not complete (status or phase indicates incomplete)
      // Note: We check status and phase FIRST, resume_required is just a hint
      const isIncomplete = sessionData.status !== 'completed' && resolvedPhase !== 'complete'
      const shouldResume = isIncomplete || (sessionData.resume_required === true)
      
      console.log('[HistoryPage] Resume decision:', {
        isIncomplete,
        shouldResume,
        resume_required: sessionData.resume_required,
        status: sessionData.status,
        resolvedPhase,
        batchId
      })
      
      if (shouldResume) {
        console.log('[HistoryPage] Calling resumeSession API for batch:', batchId)
        await apiService.resumeSession(batchId)
        console.log('[HistoryPage] resumeSession API call completed')
        addNotification('已恢复会话', 'success')
      } else {
        console.log('[HistoryPage] NOT resuming - just loading state')
        addNotification('已加载会话状态', 'success')
      }
      
      // NOW set the phase (this triggers auto-navigation)
      setCurrentPhase(resolvedPhase as any)
      
      // Navigate based on current phase
      const phaseRoutes: Record<string, string> = {
        scraping: '/scraping',
        research: '/research',
        phase3: '/phase3',
        complete: '/report',
      }
      const route = phaseRoutes[resolvedPhase] || '/scraping'
      navigate(route)
    } catch (err: any) {
      console.error('Failed to resume session:', err)
      addNotification('无法恢复会话，请重试', 'error')
    }
  }

  const handleView = async (batchId: string) => {
    try {
      // Load session data
      const sessionData = (await apiService.getHistorySession(batchId)) as HistorySessionDetail
      
      // Restore workflow state
      setBatchId(batchId)
      setSessionId(sessionData.session_id || null)
      setWorkflowStarted(false)

      // Hydrate workflow state (scraping, research agent, phase 3)
      // This ensures the progress bar shows all completed phases correctly
      hydrateWorkflowState(sessionData)

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

  const handleDelete = async (sessionId: string, batchId: string) => {
    if (!window.confirm('确定要删除这个会话吗？此操作无法撤销。')) {
      return
    }

    try {
      await apiService.deleteSession(sessionId)
      addNotification('会话已删除', 'success')
      loadHistory() // Reload list
    } catch (err: any) {
      console.error('Failed to delete session:', err)
      addNotification('无法删除会话，请重试', 'error')
    }
  }

  const handleExportPdf = async (batchId: string) => {
    setExportingBatchId(batchId)
    try {
      const sessionData = (await apiService.getHistorySession(batchId)) as HistorySessionDetail
      const sessionId = sessionData.session_id
      if (!sessionId) {
        throw new Error('未找到会话ID，无法导出PDF')
      }

      // Export HTML using the new API
      const result = await apiService.exportSessionHtml(sessionId)
      
      // Open the HTML file in a new window
      window.open(result.file_url, '_blank')
      
      if (result.cached) {
        addNotification('已打开导出的HTML文件（使用缓存）', 'success')
      } else {
        addNotification('已导出并打开HTML文件', 'success')
      }
    } catch (err: any) {
      console.error('Failed to export HTML:', err)
      const detail = err?.response?.data?.detail || err?.message || '导出失败，请重试'
      addNotification(detail, 'error')
    } finally {
      setExportingBatchId(null)
    }
  }

  const getStatusBadge = (status: string) => {
    const statusConfig = {
      completed: { bg: 'bg-green-100', text: 'text-green-800', label: '已完成' },
      'in-progress': { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '某种努力中' },
      failed: { bg: 'bg-red-100', text: 'text-red-800', label: 'OMG出错了' },
      cancelled: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '已取消' },
    }

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig['in-progress']

    return (
      <span className={`px-2 py-1 rounded text-xs font-medium ${config.bg} ${config.text}`}>
        {config.label}
      </span>
    )
  }

  const filteredSessions = sessions.filter((session) => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      return (
        session.batch_id.toLowerCase().includes(query) ||
        (session.topic && session.topic.toLowerCase().includes(query))
      )
    }
    return true
  })

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <Card title="研究历史" subtitle="查看和管理之前的研究会话">
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex items-center gap-4 pb-4 border-b border-neutral-300">
            <div className="flex-1">
              <input
                type="text"
                placeholder="搜索批次ID或主题..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">全部状态</option>
              <option value="completed">已完成</option>
              <option value="in-progress">某种努力中</option>
              <option value="failed">OMG出错了</option>
              <option value="cancelled">已取消</option>
            </select>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="text-center py-8">
              <p className="text-neutral-400">正在加载历史记录...</p>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="text-center py-8">
              <p className="text-red-500 mb-4">{error}</p>
              <Button onClick={loadHistory}>重试</Button>
            </div>
          )}

          {/* Sessions List */}
          {!loading && !error && (
            <>
              {filteredSessions.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-neutral-400">暂无历史记录</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredSessions.map((session) => (
                    <div
                      key={session.batch_id}
                      className="bg-neutral-white border border-neutral-300 rounded-lg p-4 hover:shadow-md transition-shadow"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="font-semibold text-neutral-800">
                              {session.topic || '未命名会话'}
                            </h3>
                            {getStatusBadge(session.status)}
                          </div>
                          <div className="text-sm text-neutral-600 space-y-1">
                            <p>
                              <span className="font-medium">批次ID:</span> {session.batch_id}
                            </p>
                            <p>
                              <span className="font-medium">会话ID:</span> {session.session_id}
                            </p>
                            <p>
                              <span className="font-medium">创建时间:</span>{' '}
                              {new Date(session.created_at).toLocaleString('zh-CN')}
                            </p>
                            {session.url_count !== undefined && (
                              <p>
                                <span className="font-medium">链接数量:</span> {session.url_count}
                              </p>
                            )}
                            {session.current_phase && (
                              <p>
                                <span className="font-medium">当前阶段:</span> {session.current_phase}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleExportPdf(session.batch_id)}
                            isLoading={exportingBatchId === session.batch_id}
                            disabled={exportingBatchId !== null && exportingBatchId !== session.batch_id}
                          >
                            导出 PDF
                          </Button>
                          {session.status === 'completed' && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleView(session.batch_id)}
                            >
                              查看报告
                            </Button>
                          )}
                          {session.status === 'in-progress' && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleResume(session.batch_id)}
                            >
                              继续
                            </Button>
                          )}
                          <button
                            onClick={() => handleDelete(session.session_id, session.batch_id)}
                            className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors duration-200"
                            title="删除"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  )
}

export default HistoryPage

