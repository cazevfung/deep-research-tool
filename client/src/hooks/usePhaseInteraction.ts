import { useMemo } from 'react'
import { useWorkflowStore } from '../stores/workflowStore'

export type InteractionRole = 'assistant' | 'user' | 'system' | 'summary'

export type TimelineItemType = 'status' | 'content'

export interface PhaseTimelineItem {
  id: string
  type: TimelineItemType
  title: string
  subtitle: string | null
  message: string
  preview: string
  phaseLabel: string | null
  stepLabel: string | null
  timestamp: string | null
  status: 'active' | 'completed' | 'error'
  statusVariant: 'info' | 'success' | 'warning' | 'error'
  isStreaming: boolean
  isCollapsible: boolean
  defaultCollapsed: boolean
  metadata?: Record<string, any> | null
}

const roleLabelMap: Record<InteractionRole, string> = {
  assistant: 'AI 助手',
  user: '我',
  system: '系统',
  summary: '总结',
}

const componentLabelMap: Record<string, string> = {
  transcript: '转录摘要',
  comments: '评论摘要',
  role_generation: '角色生成',
  goal_generation: '目标生成',
  goal_generation_retry: '目标重试',
  synthesis: '确定主题',
  finalization: '确定主题',
  'phase1_5_synthesis': '阶段1.5 综合',
  step_initial: '初始分析',
  step_followup: '补充分析',
  'phase4-outline': '报告大纲',
  'phase4-coverage': '覆盖校验',
  'phase4-article': '最终报告写作',
  report_generation: '报告生成',
  summarization: '内容摘要',
}

const detectRole = (metadata: Record<string, any> | null | undefined): InteractionRole => {
  const rawRole = (metadata?.role || metadata?.speaker || metadata?.source || metadata?.sender || '')
    .toString()
    .toLowerCase()

  if (rawRole.includes('user')) {
    return 'user'
  }

  if (rawRole.includes('system') || rawRole.includes('orchestrator')) {
    return 'system'
  }

  if (
    rawRole.includes('summary') ||
    metadata?.summary === true ||
    (typeof metadata?.phase_class === 'string' && /summary|synthesize/i.test(metadata.phase_class)) ||
    (typeof metadata?.tag === 'string' && /summary|conclusion/i.test(metadata.tag))
  ) {
    return 'summary'
  }

  return 'assistant'
}

const deriveTitle = (role: InteractionRole, metadata: Record<string, any> | null | undefined): string => {
  if (typeof metadata?.display_name === 'string' && metadata.display_name.trim()) {
    return metadata.display_name.trim()
  }
  if (typeof metadata?.title === 'string' && metadata.title.trim()) {
    return metadata.title.trim()
  }
  if (typeof metadata?.prompt === 'string' && metadata.prompt.trim()) {
    return metadata.prompt.trim()
  }
  if (typeof metadata?.label === 'string' && metadata.label.trim()) {
    return metadata.label.trim()
  }
  return roleLabelMap[role]
}

const derivePhaseLabel = (
  bufferPhase: string | null | undefined,
  metadata: Record<string, any> | null | undefined
): string | null => {
  if (typeof metadata?.phase_label === 'string' && metadata.phase_label.trim()) {
    return metadata.phase_label.trim()
  }
  if (typeof metadata?.phase_key === 'string' && metadata.phase_key.trim()) {
    return metadata.phase_key.trim()
  }
  if (typeof metadata?.phase === 'string' && metadata.phase.trim()) {
    return metadata.phase.trim()
  }
  if (typeof bufferPhase === 'string' && bufferPhase.trim()) {
    return bufferPhase.trim()
  }
  if (typeof metadata?.phase_class === 'string' && metadata.phase_class.trim()) {
    return metadata.phase_class.trim()
  }
  return null
}

const deriveStepLabel = (metadata: Record<string, any> | null | undefined): string | null => {
  const parts: string[] = []
  if (typeof metadata?.step_id === 'number' || typeof metadata?.step_id === 'string') {
    parts.push(`步骤 ${metadata.step_id}`)
  }
  if (typeof metadata?.component === 'string' && metadata.component.trim()) {
    const componentKey = metadata.component.trim().toLowerCase()
    parts.push(componentLabelMap[componentKey] ?? metadata.component.trim())
  } else if (typeof metadata?.action === 'string' && metadata.action.trim()) {
    parts.push(metadata.action.trim())
  }
  if (typeof metadata?.workflow === 'string' && metadata.workflow.trim()) {
    parts.push(metadata.workflow.trim())
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

const createPreview = (content: string, maxChars = 200): string => {
  if (!content) {
    return ''
  }
  if (content.length <= maxChars) {
    return content
  }
  return `${content.slice(0, maxChars)}…`
}

const getLineCount = (content: string): number => {
  if (!content) {
    return 0
  }
  return content.split(/\r?\n/).length
}

const determineStatusVariant = (status: 'active' | 'completed' | 'error'): 'info' | 'success' | 'warning' | 'error' => {
  if (status === 'active') {
    return 'info'
  }
  if (status === 'completed') {
    return 'success'
  }
  return 'error'
}

const isLikelyStatusMessage = (content: string, metadata: Record<string, any> | null | undefined): boolean => {
  if (!content) {
    return true
  }
  const trimmed = content.trim()
  if (!trimmed) {
    return true
  }
  const metadataType = (metadata?.message_type || metadata?.type || metadata?.category || '')
    .toString()
    .toLowerCase()
  if (metadataType.includes('status') || metadataType.includes('event')) {
    return true
  }
  if (trimmed.length <= 150 && getLineCount(trimmed) <= 3 && !/[\*\-\n]{2,}/.test(trimmed)) {
    return true
  }
  return false
}

export const usePhaseInteraction = () => {
  const {
    streams,
    streamingState,
    waitingForUser,
    userInputRequired,
    currentAction,
    phase,
    summarizationProgress,
    conversationMessages,
  } = useWorkflowStore((state) => ({
    streams: state.researchAgentStatus.streams,
    streamingState: state.researchAgentStatus.streamingState,
    waitingForUser: state.researchAgentStatus.waitingForUser,
    userInputRequired: state.researchAgentStatus.userInputRequired,
    currentAction: state.researchAgentStatus.currentAction,
    phase: state.researchAgentStatus.phase,
    summarizationProgress: state.researchAgentStatus.summarizationProgress,
    conversationMessages: state.researchAgentStatus.conversationMessages,
  }))

  const timelineItems = useMemo<PhaseTimelineItem[]>(() => {
    const orderedIds = [...streams.order]

    const streamItems = orderedIds
      .map((id) => {
        const buffer = streams.buffers[id]
        if (!buffer) {
          return null
        }

        const metadata = buffer.metadata ?? null
        const role = detectRole(metadata)
        const title = deriveTitle(role, metadata)
        const phaseLabel = derivePhaseLabel(buffer.phase, metadata)
        const stepLabel = deriveStepLabel(metadata)
        const message = (buffer.raw || '').trim()
        const preview = createPreview(message)
        const lineCount = getLineCount(message)
        const isStatus = isLikelyStatusMessage(message, metadata)
        const isCollapsible = !isStatus && (message.length > 320 || lineCount > 5)
        const defaultCollapsed = isCollapsible
        const subtitleParts: string[] = []
        if (phaseLabel) {
          subtitleParts.push(`阶段 ${phaseLabel}`)
        }
        if (stepLabel) {
          subtitleParts.push(stepLabel)
        }
        const subtitle = subtitleParts.length > 0 ? subtitleParts.join(' · ') : null

        return {
          id,
          type: isStatus ? 'status' : 'content',
          title,
          subtitle,
          message,
          preview,
          phaseLabel,
          stepLabel,
          timestamp: buffer.lastTokenAt || buffer.endedAt || buffer.startedAt || null,
          status: buffer.status,
          statusVariant: determineStatusVariant(buffer.status),
          isStreaming: Boolean(buffer.isStreaming),
          isCollapsible,
          defaultCollapsed,
          metadata,
        } as PhaseTimelineItem
      })
      .filter((item): item is PhaseTimelineItem => Boolean(item))

    const statusMap: Record<string, 'active' | 'completed' | 'error'> = {
      queued: 'active',
      in_progress: 'active',
      completed: 'completed',
      error: 'error',
    }

    const conversationItems: PhaseTimelineItem[] = (conversationMessages || []).map((message) => {
      const statusKey = statusMap[message.status] ?? 'completed'
      const title = message.role === 'user' ? '我' : message.role === 'assistant' ? 'AI 助手' : '系统'
      const body = (message.content || '').trim()
      const preview = createPreview(body)
      const lineCount = getLineCount(body)
      const isCollapsible = body.length > 320 || lineCount > 5

      return {
        id: `conversation:${message.id}`,
        type: 'content',
        title,
        subtitle: '互动反馈',
        message: body,
        preview,
        phaseLabel: null,
        stepLabel: null,
        timestamp: message.timestamp ?? null,
        status: statusKey,
        statusVariant: determineStatusVariant(statusKey),
        isStreaming: statusKey === 'active',
        isCollapsible,
        defaultCollapsed: isCollapsible,
      }
    })

    const combined = [...streamItems, ...conversationItems].sort((a, b) => {
      const aTime = a.timestamp ? new Date(a.timestamp).getTime() : 0
      const bTime = b.timestamp ? new Date(b.timestamp).getTime() : 0
      if (aTime === bTime) {
        return a.id.localeCompare(b.id)
      }
      return aTime - bTime
    })

    return combined
  }, [streams, conversationMessages])

  const combinedRaw = useMemo(() => {
    if (timelineItems.length === 0) {
      return ''
    }
    return timelineItems
      .map((item) => {
        const header = item.subtitle ? `${item.title} (${item.subtitle})` : item.title
        return `${header}\n${item.message}`.trim()
      })
      .join('\n\n')
  }, [timelineItems])

  const latestUpdateAt = useMemo(() => {
    const timestamps = timelineItems
      .map((item) => item.timestamp)
      .filter((value): value is string => Boolean(value))
    if (timestamps.length === 0) {
      return streamingState.lastTokenAt || streamingState.startedAt || null
    }
    return timestamps.sort().reverse()[0]
  }, [timelineItems, streamingState.lastTokenAt, streamingState.startedAt])

  const statusIndicatorClass = streamingState.isStreaming ? 'bg-primary-500 animate-pulse' : 'bg-emerald-500'
  const statusLabel = streamingState.isStreaming ? '正在流式' : '已连接'

  return {
    timelineItems,
    combinedRaw,
    latestUpdateAt,
    statusIndicatorClass,
    statusLabel,
    activeStreamId: streams.activeStreamId,
    isStreaming: streamingState.isStreaming,
    waitingForUser,
    userInputRequired,
    currentAction,
    phase,
    summarizationProgress,
  }
}
