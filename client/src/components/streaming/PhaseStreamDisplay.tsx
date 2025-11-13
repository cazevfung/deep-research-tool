import React from 'react'
import StreamDisplay from './StreamDisplay'
import { streamVariants, StreamVariant } from './streamDesignTokens'
import StreamStructuredView from './StreamStructuredView'

interface PhaseStreamDisplayProps {
  phase: 'phase0' | 'phase0.5' | 'phase0_5' | 'phase1' | 'phase2' | 'phase3' | 'phase4' | string
  content: string
  isStreaming?: boolean
  metadata?: Record<string, any> | null
  subtitle?: string | React.ReactNode
  viewVariant?: StreamVariant
  showStructuredView?: boolean
}

const phasePreset = {
  phase0: { title: '阶段 0: 数据准备', icon: '📊', variant: 'default' as StreamVariant },
  'phase0.5': { title: '阶段 0.5: 角色生成', icon: '🎭', variant: 'compact' as StreamVariant },
  phase0_5: { title: '阶段 0.5: 角色生成', icon: '🎭', variant: 'compact' as StreamVariant },
  phase1: { title: '阶段 1: 发现', icon: '🔍', variant: 'default' as StreamVariant },
  phase2: { title: '阶段 2: 确定', icon: '🔗', variant: 'default' as StreamVariant },
  phase3: { title: '阶段 3: 执行', icon: '⚡', variant: 'expanded' as StreamVariant },
  phase4: { title: '阶段 4: 最终综合', icon: '📝', variant: 'expanded' as StreamVariant },
}

const PhaseStreamDisplay: React.FC<PhaseStreamDisplayProps> = ({
  phase,
  content,
  isStreaming = false,
  metadata,
  subtitle,
  viewVariant,
  showStructuredView = true,
}) => {
  const preset = phasePreset[phase as keyof typeof phasePreset] || {
    title: 'AI 响应流',
    icon: '🤖',
    variant: 'default' as StreamVariant,
  }

  const variant = viewVariant ?? preset.variant
  const variantConfig = streamVariants[variant]

  return (
    <StreamDisplay
      content={content}
      phase={phase}
      metadata={metadata}
      isStreaming={isStreaming}
      title={`${preset.icon} ${preset.title}`}
      subtitle={subtitle}
      minHeight={variantConfig.minHeight}
      maxHeight={variantConfig.maxHeight}
      showCopyButton={variantConfig.showCopyButton}
      collapsible={variantConfig.collapsible}
      secondaryView={showStructuredView ? <StreamStructuredView /> : undefined}
      viewMode="tabs"
    />
  )
}

export default PhaseStreamDisplay

