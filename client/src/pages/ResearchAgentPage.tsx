import React, { useMemo } from 'react'
import Card from '../components/common/Card'
import Button from '../components/common/Button'
import { useWorkflowStore, LiveGoal } from '../stores/workflowStore'
import ResearchGoalList from '../components/research/ResearchGoalList'
import { apiService } from '../services/api'
import { useUiStore } from '../stores/uiStore'

const ResearchAgentPage: React.FC = () => {
  const researchAgentStatus = useWorkflowStore((state) => state.researchAgentStatus)
  const batchId = useWorkflowStore((state) => state.batchId)
  const sessionId = useWorkflowStore((state) => state.sessionId)
  const reportStale = useWorkflowStore((state) => state.reportStale)
  const phaseRerunState = useWorkflowStore((state) => state.rerunState)
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


