import React, { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/common/Card'
import ProgressBar from '../components/progress/ProgressBar'
import StatusBadge from '../components/progress/StatusBadge'
import ProgressGroup from '../components/progress/ProgressGroup'
import { Icon } from '../components/common/Icon'
import { useWorkflowStore } from '../stores/workflowStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { apiService } from '../services/api'
import { groupItemsByStatus, getItemId } from '../utils/progressUtils'

const ScrapingProgressPage: React.FC = () => {
  const navigate = useNavigate()
  const {
    batchId,
    workflowStarted,
    scrapingStatus,
    setCurrentPhase,
    cancelled,
    cancellationInfo,
    setWorkflowStarted,
    updateScrapingStatus,
    setFinalReport,
    setGoals,
    setPlan,
    setPhase3Steps,
    updateResearchAgentStatus,
  } = useWorkflowStore()
  
  const [isCancelling, setIsCancelling] = useState(false)
  const [isCheckingStatus, setIsCheckingStatus] = useState(false)
  const [workflowStatus, setWorkflowStatus] = useState<string | null>(null)
  
  // New item tracking and animation
  const [newItemIds, setNewItemIds] = useState<Set<string>>(new Set())
  const [showNewItemsNotification, setShowNewItemsNotification] = useState(false)
  const [newItemsCount, setNewItemsCount] = useState(0)
  const previousItemIdsRef = useRef<Set<string>>(new Set())
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [scrollPosition, setScrollPosition] = useState(0)
  const [userScrolled, setUserScrolled] = useState(false)
  const userScrollTimeoutRef = useRef<number | null>(null)
  
  // Use refs to track initialization and prevent duplicate checks
  // Track which batchId was initialized to prevent stale state
  const hasInitializedRef = useRef<string | null>(null)
  const checkInProgressRef = useRef(false)

  // Connect WebSocket when component mounts (always connect for updates)
  useWebSocket(batchId || '')

  // Detect new items
  useEffect(() => {
    const currentIds = new Set(scrapingStatus.items.map((item) => getItemId(item)))
    const previousIds = previousItemIdsRef.current
    
    // Find new items
    const newIds = new Set<string>()
    currentIds.forEach((id) => {
      if (!previousIds.has(id)) {
        newIds.add(id)
      }
    })

    if (newIds.size > 0) {
      setNewItemIds((prev) => {
        const updated = new Set(prev)
        newIds.forEach((id) => updated.add(id))
        return updated
      })
      setNewItemsCount(newIds.size)

      // Show notification if user has scrolled down
      if (userScrolled && scrollPosition > 200) {
        setShowNewItemsNotification(true)
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
          setShowNewItemsNotification(false)
        }, 5000)
      }
    }

    previousItemIdsRef.current = currentIds
  }, [scrapingStatus.items, userScrolled, scrollPosition])

  // Handle scroll position tracking
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const handleScroll = () => {
      const position = container.scrollTop
      setScrollPosition(position)
      
      // Mark as user scrolled if they scroll down significantly
      if (position > 200) {
        setUserScrolled(true)
        // Reset user scrolled flag after 2 seconds of no scrolling
        if (userScrollTimeoutRef.current) {
          clearTimeout(userScrollTimeoutRef.current)
        }
        userScrollTimeoutRef.current = setTimeout(() => {
          setUserScrolled(false)
        }, 2000)
      } else {
        setUserScrolled(false)
      }
    }

    container.addEventListener('scroll', handleScroll)
    return () => {
      container.removeEventListener('scroll', handleScroll)
      if (userScrollTimeoutRef.current) {
        clearTimeout(userScrollTimeoutRef.current)
      }
    }
  }, [])

  // Auto-scroll to top when new items appear (if user is near top)
  useEffect(() => {
    if (newItemIds.size > 0 && !userScrolled && scrollPosition < 200) {
      const container = scrollContainerRef.current
      if (container) {
        container.scrollTo({ top: 0, behavior: 'smooth' })
      }
    }
  }, [newItemIds.size, userScrolled, scrollPosition])

  const handleScrollToTop = () => {
    const container = scrollContainerRef.current
    if (container) {
      container.scrollTo({ top: 0, behavior: 'smooth' })
      setShowNewItemsNotification(false)
    }
  }

  const handleItemAnimationComplete = (itemId: string) => {
    setNewItemIds((prev) => {
      const updated = new Set(prev)
      updated.delete(itemId)
      return updated
    })
  }

  useEffect(() => {
    console.log('ScrapingProgressPage mounted, batchId:', batchId)
    
    if (!batchId) {
      console.log('No batchId, navigating to home')
      navigate('/')
      return
    }

    // Check workflow status and start if needed
    const checkAndStartWorkflow = async () => {
      // Prevent multiple simultaneous checks using ref
      if (checkInProgressRef.current) {
        console.log('Already checking status, skipping')
        return
      }
      
      // If already initialized for THIS specific batchId, skip
      if (hasInitializedRef.current === batchId) {
        console.log('Already initialized for this batchId, skipping')
        return
      }
      
      console.log('Starting workflow check for batchId:', batchId)
      checkInProgressRef.current = true
      setIsCheckingStatus(true)
      
      try {
        // FRONTEND FIX: Check if report exists FIRST before trusting workflow status
        // This prevents treating completed workflows as "running" based on WebSocket connections
        try {
          console.log('Checking if report exists for batch:', batchId)
          const report = await apiService.getFinalReport(batchId)
          
          if (report && report.status === 'ready') {
            console.log('✓ Report exists and is ready - workflow is COMPLETED')
            // Mark workflow as completed, not running
            setWorkflowStatus('completed')
            setWorkflowStarted(true)
            
            // Update scraping status to show completion
            updateScrapingStatus({
              is100Percent: true,
              canProceedToResearch: true,
            })
            
            // Set final report in store
            setFinalReport({
              content: report.content,
              generatedAt: report.metadata.generatedAt,
              status: 'ready',
            })
            
            // Try to load session data to populate research phases
            if (report.metadata.sessionId) {
              try {
                const historyData = await apiService.getHistorySession(batchId)
                console.log('Loaded session data for completed workflow:', historyData)
                
                // Populate research data if available
                if (historyData.research_results) {
                  const results = historyData.research_results
                  
                  // Set goals if available
                  if (results.goals) {
                    setGoals(results.goals)
                  }
                  
                  // Set plan if available
                  if (results.plan) {
                    setPlan(results.plan)
                  }
                  
                  // Set phase 3 steps if available
                  if (results.phase3_steps && Array.isArray(results.phase3_steps)) {
                    setPhase3Steps(results.phase3_steps)
                  }
                  
                  // Update research phase
                  updateResearchAgentStatus({
                    phase: '4', // Final phase
                  })
                  
                  // Update current phase to complete
                  setCurrentPhase('complete')
                }
              } catch (historyError) {
                console.log('Could not load session data:', historyError)
                // Not critical - just log and continue
              }
            }
            
            hasInitializedRef.current = batchId
            checkInProgressRef.current = false
            setIsCheckingStatus(false)
            return // Skip workflow status check - report proves it's done
          }
          
          console.log('Report not ready or doesn\'t exist, checking workflow status...')
        } catch (reportError: any) {
          // Report doesn't exist (404) or error fetching - continue to workflow status check
          if (reportError?.response?.status === 404) {
            console.log('Report not found (404), workflow may still be in progress')
          } else {
            console.log('Error fetching report:', reportError?.message)
          }
        }
        
        const workflowId = `workflow_${batchId}`
        let currentStatus: string | null = null
        
        // Check if workflow is already running
        try {
          console.log('Checking workflow status for:', workflowId)
          const status = await apiService.getWorkflowStatus(workflowId)
          currentStatus = status.status
          setWorkflowStatus(status.status)
          console.log('Workflow status:', currentStatus)
          
          if (status.status === 'running') {
            // CRITICAL FIX: Backend reports "running" if WebSocket connection exists,
            // but the actual background task might not have started yet.
            // Check if there's actual progress before trusting "running" status.
            const hasActualProgress = scrapingStatus.expectedTotal > 0 || scrapingStatus.items.length > 0 || scrapingStatus.total > 0
            
            if (hasActualProgress) {
              // Workflow is actually running with progress, just connect WebSocket
              console.log('Workflow already running with progress, connecting to updates...')
              setWorkflowStarted(true)
              hasInitializedRef.current = batchId
              checkInProgressRef.current = false
              setIsCheckingStatus(false)
              return
            } else {
              // Status says "running" but no progress - likely just WebSocket connection
              // The background task probably didn't start. Force start it.
              console.warn('⚠️ Workflow status is "running" but no progress detected. This likely means only WebSocket is connected but background task never started. Attempting to start workflow...')
              // Don't return - fall through to start workflow logic below
              currentStatus = null // Reset status to force start
            }
          }
          
          if (status.status === 'cancelled') {
            // Workflow was cancelled, don't restart
            console.log('Workflow was cancelled, not restarting')
            hasInitializedRef.current = batchId
            checkInProgressRef.current = false
            setIsCheckingStatus(false)
            return
          }
        } catch (error: any) {
          // Status endpoint might not exist or workflow doesn't exist yet
          // This is okay - we'll try to start
          console.log('Could not get workflow status, will try to start:', error?.response?.status, error?.message)
        }

        // Always verify backend status - don't rely solely on frontend flag
        // Start workflow if backend says it's not running (regardless of frontend flag)
        if (currentStatus !== 'running') {
          console.log('Starting new workflow for batchId:', batchId, '(backend status:', currentStatus || 'unknown', ')')
          try {
            const response = await apiService.startWorkflow(batchId)
            console.log('Workflow start response:', response)
            setWorkflowStarted(true)
            setWorkflowStatus('running')
            hasInitializedRef.current = batchId
          } catch (error: any) {
            console.error('Failed to start workflow:', error)
            console.error('Error details:', error?.response?.data, error?.response?.status)
            // If error is because workflow already exists, mark as started
            if (error?.response?.status === 409 || error?.message?.includes('already')) {
              console.log('Workflow already exists, marking as started')
              setWorkflowStarted(true)
              setWorkflowStatus('running')
              hasInitializedRef.current = batchId
            } else {
              // If start failed for other reasons, don't mark as initialized
              // This allows retry on next mount
              console.warn('Workflow start failed, will retry on next mount if needed')
            }
          }
        } else {
          console.log('Workflow already running according to backend, skipping start')
          setWorkflowStarted(true)
          hasInitializedRef.current = batchId
        }
      } catch (error: any) {
        console.error('Error checking/starting workflow:', error)
        console.error('Error details:', error?.response?.data, error?.response?.status)
      } finally {
        checkInProgressRef.current = false
        setIsCheckingStatus(false)
      }
    }

    // Only run check if not already initialized for this specific batchId
    if (hasInitializedRef.current !== batchId) {
      checkAndStartWorkflow()
    }
    
    // Cleanup: reset check in progress if batchId changes during check
    return () => {
      // If batchId changed while check was in progress, reset the flag
      // This allows the new batchId to start its own check
      if (checkInProgressRef.current && hasInitializedRef.current !== batchId) {
        checkInProgressRef.current = false
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]) // Only depend on batchId - navigate is stable and doesn't need to trigger re-runs
  
  // Reset initialization when batchId changes
  useEffect(() => {
    // Reset refs when batchId changes to allow re-initialization for new batch
    // Only reset if batchId actually changed (not on first mount)
    if (hasInitializedRef.current !== null && hasInitializedRef.current !== batchId) {
      hasInitializedRef.current = null
      checkInProgressRef.current = false
      previousItemIdsRef.current = new Set()
      setNewItemIds(new Set())
      setShowNewItemsNotification(false)
      setUserScrolled(false)
      setScrollPosition(0)
    }
  }, [batchId])

  // Fetch expected total from API if not set (fallback if WebSocket message was missed)
  useEffect(() => {
    const fetchExpectedTotal = async () => {
      // Only fetch if expectedTotal is 0 and we have a batchId
      if (batchId && scrapingStatus.expectedTotal === 0 && !isCheckingStatus) {
        try {
          console.log('Fetching expected total from API (fallback if WebSocket message missed)...')
          const data = await apiService.getBatchTotal(batchId)
          // Use expected_total (standardized), fallback to total_processes (deprecated)
          const expectedTotal = data?.expected_total || data?.total_processes
          if (expectedTotal) {
            console.log('Received expected total from API:', expectedTotal)
            updateScrapingStatus({
              expectedTotal: expectedTotal,
            })
          }
        } catch (error) {
          console.warn('Failed to fetch expected total from API:', error)
          // Don't show error to user, just log it
        }
      }
    }
    
    // Wait a bit for WebSocket to connect and receive batch:initialized
    // If after 2 seconds expectedTotal is still 0, fetch from API
    const timeoutId = setTimeout(() => {
      fetchExpectedTotal()
    }, 2000)
    
    return () => clearTimeout(timeoutId)
  }, [batchId, scrapingStatus.expectedTotal, isCheckingStatus, updateScrapingStatus])

  // Calculate overall progress using expectedTotal (from batch:initialized)
  // Fallback to completionRate from backend if available, otherwise calculate
  const overallProgress = scrapingStatus.expectedTotal > 0
    ? scrapingStatus.completionRate > 0
      ? scrapingStatus.completionRate * 100  // Use backend's completion_rate (calculated against expected_total)
      : ((scrapingStatus.completed + scrapingStatus.failed) / scrapingStatus.expectedTotal) * 100
    : scrapingStatus.total > 0
    ? ((scrapingStatus.completed + scrapingStatus.failed) / scrapingStatus.total) * 100  // Fallback to started processes total
    : 0

  // Debug logging
  useEffect(() => {
    console.log('Progress calculation:', {
      expectedTotal: scrapingStatus.expectedTotal,
      total: scrapingStatus.total,
      completed: scrapingStatus.completed,
      failed: scrapingStatus.failed,
      completionRate: scrapingStatus.completionRate,
      is100Percent: scrapingStatus.is100Percent,
      calculatedProgress: overallProgress,
    })
  }, [scrapingStatus, overallProgress])

  // Handle cancel button click
  const handleCancel = async () => {
    if (!batchId || cancelled || isCancelling) return
    
    if (window.confirm('确定要取消当前任务吗？已完成的链接会保留，未完成的将停止处理。')) {
      setIsCancelling(true)
      try {
        await apiService.cancelWorkflow(batchId, '用户取消')
        // State will be updated via WebSocket message
      } catch (error) {
        console.error('Failed to cancel workflow:', error)
        alert('取消操作失败，请重试')
        setIsCancelling(false)
      }
    }
  }
  
  // Note: Navigation is now handled globally by useProgressNavigation hook
  // This effect is kept for phase tracking only
  useEffect(() => {
    if (cancelled) return // Don't update phase if cancelled
    
    // Use backend's is_100_percent flag (calculated against expected_total)
    // This ensures we only transition when ALL expected processes are complete
    if (scrapingStatus.is100Percent || scrapingStatus.canProceedToResearch) {
      // Update phase for tracking, navigation handled by useProgressNavigation
      setCurrentPhase('research')
    }
  }, [scrapingStatus.is100Percent, scrapingStatus.canProceedToResearch, setCurrentPhase, cancelled])

  // Group items by status
  const groupedItems = groupItemsByStatus(scrapingStatus.items)

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <Card
        title="抓取进度"
        subtitle={`批次ID: ${batchId || 'N/A'}`}
      >
        <div className="space-y-6">
          {/* Workflow Status Indicator */}
          {isCheckingStatus && (
            <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-3 mb-4">
              <p className="text-sm text-yellow-700">正在检查工作流状态...</p>
            </div>
          )}
          
          {workflowStatus === 'running' && !isCheckingStatus && (
            <div className="bg-green-50 border border-green-300 rounded-lg p-3 mb-4">
              <p className="text-sm text-green-700">工作流正在运行中...</p>
            </div>
          )}
          
          {workflowStatus === 'completed' && !isCheckingStatus && (
            <div className="bg-blue-50 border border-blue-300 rounded-lg p-3 mb-4">
              <p className="text-sm text-blue-700">✓ 工作流已完成 - 查看报告</p>
            </div>
          )}
          
          {workflowStatus === 'stopped' && !isCheckingStatus && (
            <div className="bg-gray-50 border border-gray-300 rounded-lg p-3 mb-4">
              <p className="text-sm text-gray-700">工作流已停止</p>
            </div>
          )}

          {/* Cancellation Notice */}
          {cancelled && cancellationInfo && (
            <div className="bg-yellow-50 border border-yellow-400 rounded-lg p-4 mb-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-yellow-800 mb-1">任务已取消</h4>
                  <p className="text-sm text-yellow-700">
                    取消原因: {cancellationInfo.reason || '用户取消'}
                  </p>
                  {cancellationInfo.cancelled_at && (
                    <p className="text-xs text-yellow-600 mt-1">
                      取消时间: {new Date(cancellationInfo.cancelled_at).toLocaleString('zh-CN')}
                    </p>
                  )}
                  {cancellationInfo.state_at_cancellation && (
                    <div className="mt-2 text-xs text-yellow-700">
                      <p>取消时状态:</p>
                      <ul className="list-disc list-inside ml-2 mt-1">
                        <li>已完成: {cancellationInfo.state_at_cancellation.completed || 0}</li>
                        <li>失败: {cancellationInfo.state_at_cancellation.failed || 0}</li>
                        <li>处理中: {cancellationInfo.state_at_cancellation.in_progress || 0}</li>
                        <li>总计: {cancellationInfo.state_at_cancellation.total || 0}</li>
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          
          {/* Cancel Button */}
          {!cancelled && batchId && (
            <div className="flex justify-end mb-4">
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className={`px-4 py-2 rounded-lg font-medium text-white transition-colors ${
                  isCancelling
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-red-500 hover:bg-red-600 active:bg-red-700'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                {isCancelling ? '取消中...' : '取消任务'}
              </button>
            </div>
          )}

          {/* Overall Progress */}
          <div>
            <ProgressBar
              progress={overallProgress}
              label="总体进度"
              showPercentage
            />
          </div>

          {/* Status Summary */}
          <div className="flex items-center space-x-4">
            <StatusBadge status="success">
              已完成: {scrapingStatus.completed}
            </StatusBadge>
            <StatusBadge status="error">
              失败: {scrapingStatus.failed}
            </StatusBadge>
            <StatusBadge status="pending">
              处理中: {scrapingStatus.inProgress}
            </StatusBadge>
            <StatusBadge status="info">
              总计: {(() => {
                const displayValue = scrapingStatus.expectedTotal > 0 
                  ? scrapingStatus.expectedTotal 
                  : scrapingStatus.total
                // Debug: Log what value is being displayed
                if (scrapingStatus.expectedTotal === 0 && scrapingStatus.total > 0) {
                  console.warn('⚠️ Using fallback total instead of expectedTotal:', {
                    expectedTotal: scrapingStatus.expectedTotal,
                    total: scrapingStatus.total,
                    displayValue,
                    reason: 'This means expectedTotal was never set from WebSocket or API',
                  })
                }
                return displayValue
              })()}
            </StatusBadge>
          </div>

          {/* New Items Notification Badge */}
          {showNewItemsNotification && newItemsCount > 0 && (
            <div className="bg-primary-50 border border-primary-300 rounded-lg p-3 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Icon name="info" size={18} strokeWidth={2.5} className="text-primary-500" />
                <span className="text-sm text-primary-700">
                  {newItemsCount} 个新项目已开始处理
                </span>
              </div>
              <button
                onClick={handleScrollToTop}
                className="text-sm text-primary-600 hover:text-primary-700 font-medium underline"
              >
                回到顶部
              </button>
            </div>
          )}

          {/* Grouped URL List */}
          {scrapingStatus.items.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-semibold text-neutral-black">链接列表</h4>
              <div
                ref={scrollContainerRef}
                className="space-y-3 max-h-96 overflow-y-auto"
                style={{ scrollBehavior: 'smooth' }}
              >
                {groupedItems.map((group, index) => (
                  <ProgressGroup
                    key={`${group.status}-${index}`}
                    group={group}
                    newItemIds={newItemIds}
                    onItemAnimationComplete={handleItemAnimationComplete}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

export default ScrapingProgressPage
