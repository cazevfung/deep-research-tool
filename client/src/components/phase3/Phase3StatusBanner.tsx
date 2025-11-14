import React from 'react'
import { StepRerunState } from '../../hooks/usePhase3Steps'

interface Phase3StatusBannerProps {
  rerunState: StepRerunState
  reportStale: boolean
}

const Phase3StatusBanner: React.FC<Phase3StatusBannerProps> = ({ rerunState, reportStale }) => {
  if (!rerunState?.inProgress && !reportStale) {
    return null
  }

  return (
    <div className="space-y-4 mb-4">
      {rerunState?.inProgress && (
        <div className="bg-primary-50 border border-primary-200 text-primary-700 rounded-lg p-3 text-sm">
          正在重新执行步骤 {rerunState.stepId ?? ''}{' '}
          {rerunState.regenerateReport
            ? '并会生成新的最终报告。'
            : '（不会自动生成最终报告）。'}
        </div>
      )}
      {reportStale && (
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 rounded-lg p-3 text-sm">
          当前最终报告尚未更新，请重新生成阶段 4 以同步最新发现。
        </div>
      )}
    </div>
  )
}

export default Phase3StatusBanner





