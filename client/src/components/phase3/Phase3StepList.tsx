import React from 'react'
import Phase3StepCard from './Phase3StepCard'
import { Phase3StepViewModel, StepRerunState } from '../../hooks/usePhase3Steps'

interface Phase3StepListProps {
  steps: Phase3StepViewModel[]
  rerunState: StepRerunState
  onToggleStep: (stepId: number) => void
  onToggleRawData: (stepId: number) => void
  onRerun: (stepId: number, regenerateReport: boolean) => void
}

const Phase3StepList: React.FC<Phase3StepListProps> = ({
  steps,
  rerunState,
  onToggleStep,
  onToggleRawData,
  onRerun,
}) => {
  if (!steps.length) {
    return null
  }

  return (
    <div className="space-y-4">
      {steps.map((step) => (
        <Phase3StepCard
          key={step.id}
          step={step}
          rerunState={rerunState}
          onToggleExpand={onToggleStep}
          onToggleRawData={onToggleRawData}
          onRerun={onRerun}
        />
      ))}
    </div>
  )
}

export default Phase3StepList





