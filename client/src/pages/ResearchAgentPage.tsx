import React, { useState, useEffect, useMemo } from 'react'
import Card from '../components/common/Card'
import Button from '../components/common/Button'
import { useWorkflowStore, LiveGoal, LivePlanStep } from '../stores/workflowStore'
import ResearchGoalList from '../components/research/ResearchGoalList'
import { apiService } from '../services/api'
import { useUiStore } from '../stores/uiStore'

const ResearchAgentPage: React.FC = () => {
  const researchAgentStatus = useWorkflowStore((state) => state.researchAgentStatus)
  const batchId = useWorkflowStore((state) => state.batchId)
  const sessionId = useWorkflowStore((state) => state.sessionId)
  const reportStale = useWorkflowStore((state) => state.reportStale)
  const phaseRerunState = useWorkflowStore((state) => state.rerunState)
  const [currentPlanIndex, setCurrentPlanIndex] = useState(0)
  const { addNotification } = useUiStore()

  const handleRerunPhase = async (phase: string, rerunDownstream = true) => {
    if (!batchId || !sessionId) {
      addNotification('缺少批次或会话信息，无法重新运行阶段', 'warning')
      return
    }

    try {
      await apiService.rerunPhase({
        batch_id: batchId,
        session_id: sessionId,
        phase,
        rerun_downstream: rerunDownstream,
      })
      addNotification('已提交阶段重新运行请求', 'info')
    } catch (error) {
      console.error('Failed to request phase rerun', error)
      addNotification('提交阶段重新运行请求失败', 'error')
    }
  }

  const goalItems = useMemo(() => {
    const orderedIds = researchAgentStatus.goalOrder
    if (orderedIds.length > 0) {
      const liveGoals = orderedIds
        .map((id) => researchAgentStatus.liveGoals[id])
        .filter((goal): goal is NonNullable<typeof goal> => Boolean(goal))
      if (liveGoals.length > 0) {
        return liveGoals
      }
    }

    if (researchAgentStatus.goals && researchAgentStatus.goals.length > 0) {
      return researchAgentStatus.goals.map((goal, index) => ({
        id: goal.id ?? index + 1,
        goal_text: goal.goal_text,
        uses: goal.uses,
        status: 'ready' as LiveGoal['status'],
      }))
    }

    return []
  }, [researchAgentStatus.goalOrder, researchAgentStatus.liveGoals, researchAgentStatus.goals])

  const planEntries = useMemo(() => {
    const orderedIds = researchAgentStatus.planOrder
    if (orderedIds.length > 0) {
      const liveSteps = orderedIds
        .map((id) => researchAgentStatus.livePlanSteps[id])
        .filter((step): step is NonNullable<typeof step> => Boolean(step))
      if (liveSteps.length > 0) {
        return liveSteps
      }
    }

    if (researchAgentStatus.plan && researchAgentStatus.plan.length > 0) {
      return researchAgentStatus.plan.map((step) => ({
        step_id: step.step_id,
        goal: step.goal,
        required_data: step.required_data,
        chunk_strategy: step.chunk_strategy,
        notes: step.notes,
        status: 'ready' as LivePlanStep['status'],
      }))
    }

    return []
  }, [researchAgentStatus.planOrder, researchAgentStatus.livePlanSteps, researchAgentStatus.plan])

  useEffect(() => {
    if (planEntries.length > 0) {
      setCurrentPlanIndex((prev) => (prev >= planEntries.length ? 0 : prev))
    } else {
      setCurrentPlanIndex(0)
    }
  }, [planEntries.length])

  const goToNextPlan = () => {
    if (planEntries.length > 0) {
      setCurrentPlanIndex((prev) => (prev < planEntries.length - 1 ? prev + 1 : prev))
    }
  }

  const goToPreviousPlan = () => {
    setCurrentPlanIndex((prev) => (prev > 0 ? prev - 1 : 0))
  }

  const goToPlan = (index: number) => {
    if (index >= 0 && index < planEntries.length) {
      setCurrentPlanIndex(index)
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }

      if (planEntries.length > 0) {
        if (e.key === 'ArrowRight' && e.shiftKey) {
          e.preventDefault()
          setCurrentPlanIndex((prev) => (prev < planEntries.length - 1 ? prev + 1 : prev))
        } else if (e.key === 'ArrowLeft' && e.shiftKey) {
          e.preventDefault()
          setCurrentPlanIndex((prev) => (prev > 0 ? prev - 1 : 0))
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [planEntries.length])

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Card
        title="研究规划"
        subtitle={
          <span className="shiny-text-hover">
            当前阶段: {researchAgentStatus.phase || '准备中'}
          </span>
        }
      >
        <div className="space-y-6">
          <div className="bg-neutral-light-bg border border-neutral-300 rounded-lg p-4 flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium text-neutral-700">快速重新运行阶段：</span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase0')}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              阶段 0 → 4
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase0_5')}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              阶段 0.5 → 4
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase1')}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              阶段 1 → 4
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase2')}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              阶段 2 → 4
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase3')}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              阶段 3 → 4
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleRerunPhase('phase4', false)}
              disabled={!sessionId || phaseRerunState.inProgress}
            >
              仅阶段 4
            </Button>
            {(!sessionId || phaseRerunState.inProgress) && (
              <span className="text-xs text-neutral-500">
                {!sessionId
                  ? '待研究完成后可重新运行阶段'
                  : `正在重新运行 ${phaseRerunState.phase ?? ''}...`}
              </span>
            )}
          </div>

          {reportStale && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 rounded-lg p-3 text-sm">
              最终报告基于旧的分析结果，请重新生成阶段 4 以获取最新的综合报告。
            </div>
          )}

          {researchAgentStatus.synthesizedGoal && (
            <div className="bg-primary-50 p-8 rounded-xl border border-primary-200">
              <p className="text-2xl text-primary-800 font-semibold leading-relaxed">
                {researchAgentStatus.synthesizedGoal.comprehensive_topic}
              </p>
              {researchAgentStatus.synthesizedGoal.unifying_theme && (
                <p className="text-lg text-primary-700 mt-4 leading-relaxed">
                  <span className="font-semibold text-primary-900">核心主题:</span> {researchAgentStatus.synthesizedGoal.unifying_theme}
                </p>
              )}
            </div>
          )}

          {goalItems.length > 0 && (
            <div className="bg-neutral-light-bg p-6 rounded-lg border border-neutral-300">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-neutral-900 shiny-text-hover">研究目标</h3>
                <span className="text-sm text-neutral-500">一次性浏览所有目标，提升审阅效率</span>
              </div>

              <ResearchGoalList goals={goalItems} />
            </div>
          )}

          {planEntries.length > 0 && (
            <div className="bg-neutral-light-bg p-6 rounded-lg border border-neutral-300">
              <h3 className="text-lg font-semibold text-neutral-900 mb-3 shiny-text-hover">
                研究计划
              </h3>

              <div className="flex items-center justify-between mb-4">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={goToPreviousPlan}
                  disabled={currentPlanIndex === 0}
                  aria-label="上一个步骤"
                >
                  ← 上一个
                </Button>

                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-700 shiny-text-pulse">
                    步骤 {currentPlanIndex + 1} / {planEntries.length}
                  </span>
                  {planEntries.length > 1 && (
                    <select
                      value={currentPlanIndex}
                      onChange={(e) => goToPlan(Number(e.target.value))}
                      className="text-sm border border-neutral-300 rounded px-2 py-1 bg-neutral-white text-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      aria-label="选择步骤"
                    >
                      {planEntries.map((step, index) => (
                        <option key={step.step_id} value={index}>
                          步骤 {step.step_id}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={goToNextPlan}
                  disabled={currentPlanIndex === planEntries.length - 1}
                  aria-label="下一个步骤"
                >
                  下一个 →
                </Button>
              </div>

              {planEntries[currentPlanIndex] && (() => {
                const currentPlan = planEntries[currentPlanIndex]
                if (!currentPlan) return null
                return (
                  <div className="bg-neutral-white rounded-lg border border-neutral-200 p-4">
                    <div className="flex items-start gap-3">
                      <span className="text-primary-500 font-semibold text-lg">
                        步骤 {currentPlan.step_id}
                      </span>
                      <div className="flex-1">
                        <p className="font-medium text-neutral-900 text-base leading-relaxed">
                          {currentPlan.goal || '正在生成研究步骤…'}
                        </p>
                        {currentPlan.required_data && (
                          <p className="text-sm text-neutral-600 mt-2">
                            <span className="font-medium">需要数据:</span> {currentPlan.required_data}
                          </p>
                        )}
                        {currentPlan.chunk_strategy && (
                          <p className="text-sm text-neutral-600 mt-1">
                            <span className="font-medium">处理方式:</span> {currentPlan.chunk_strategy}
                          </p>
                        )}
                        {currentPlan.notes && (
                          <p className="text-sm text-neutral-500 mt-2 italic border-l-2 border-neutral-300 pl-3">
                            {currentPlan.notes}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })()}

              {planEntries.length > 1 && (
                <p className="text-xs text-neutral-400 mt-2 text-center">
                  提示: 使用 Shift + ←/→ 键快速导航
                </p>
              )}
            </div>
          )}

          {researchAgentStatus.currentAction && (
            <div className="text-sm text-neutral-600 shiny-text-pulse">
              {researchAgentStatus.currentAction}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

export default ResearchAgentPage


