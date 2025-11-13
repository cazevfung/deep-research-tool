import React, { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import Button from '../common/Button'
import { PhaseTimelineItem } from '../../hooks/usePhaseInteraction'
import Phase0SummaryDisplay from '../streaming/Phase0SummaryDisplay'

interface StreamContentBubbleProps {
  item: PhaseTimelineItem
  collapsed: boolean
  onToggle: (item: PhaseTimelineItem) => void
  onCopy: (item: PhaseTimelineItem) => void
  isActive: boolean
}

const badgeVariantMap: Record<PhaseTimelineItem['statusVariant'], string> = {
  info: 'bg-primary-100 text-primary-700',
  success: 'bg-emerald-100 text-emerald-700',
  warning: 'bg-amber-100 text-amber-700',
  error: 'bg-secondary-100 text-secondary-700',
}

// Helper function to determine response type from message content
const determineResponseTypeFromContent = (message: string | null | undefined): 'request' | 'final' | 'analyzing' | null => {
  if (!message) return null
  
  try {
    // Try to parse as JSON
    const parsed = JSON.parse(message)
    if (typeof parsed !== 'object' || parsed === null) return null
    
    // Check if it has requests/missing_context but no findings (request type)
    const hasRequests = (parsed.requests && Array.isArray(parsed.requests) && parsed.requests.length > 0) ||
                       (parsed.missing_context && Array.isArray(parsed.missing_context) && parsed.missing_context.length > 0)
    const hasFindings = parsed.findings && typeof parsed.findings === 'object'
    
    if (hasRequests && !hasFindings) {
      return 'request'
    }
    if (hasFindings) {
      return 'final'
    }
  } catch {
    // Not valid JSON or can't determine, return null
  }
  
  return null
}

// Generate summary text from metadata for collapsed streaming state
const generateSummaryText = (metadata: Record<string, any> | null | undefined, stepLabel: string | null, message?: string | null): string => {
  if (!metadata) {
    return '正在处理中...'
  }

  // Check for stage_label or component first (Phase 4 stages)
  const stageLabel = metadata.stage_label || metadata.component
  if (stageLabel) {
    const stageMap: Record<string, string> = {
      'phase4-outline': '正在生成报告大纲...',
      'phase4-coverage': '正在生成覆盖检查...',
      'phase4-article': '正在生成最终报告...',
      'Phase4-Outline': '正在生成报告大纲...',
      'Phase4-Coverage': '正在生成覆盖检查...',
      'Phase4-Article': '正在生成最终报告...',
    }
    if (stageMap[stageLabel]) {
      return stageMap[stageLabel]
    }
  }

  // Check for step_id (Phase 3 steps)
  if (metadata.step_id) {
    const goal = metadata.goal || ''
    const goalPreview = goal.length > 30 ? goal.substring(0, 30) + '...' : goal
    return `正在分析步骤 ${metadata.step_id}${goalPreview ? `: ${goalPreview}` : ''}...`
  }

  // Check for component label with response_type
  if (metadata.component) {
    // Determine actual response type from metadata or message content
    const responseType = metadata.response_type || determineResponseTypeFromContent(message) || 'analyzing'
    
    const componentMap: Record<string, Record<string, string>> = {
      step_initial: {
        request: '正在请求更多信息...',
        final: '正在生成最终分析...',
        analyzing: '正在执行初始分析...',
      },
      step_followup: {
        request: '正在请求补充信息...',
        final: '正在完善最终答案...',
        analyzing: '正在执行补充分析...',
      },
      role_generation: {
        analyzing: '正在生成研究角色...',
      },
      goal_generation: {
        analyzing: '正在生成研究目标...',
      },
      synthesis: {
        analyzing: '正在综合研究结果...',
      },
      json_repair: {
        analyzing: '正在修复JSON格式...',
      },
    }
    
    const componentMessages = componentMap[metadata.component]
    if (componentMessages) {
      return componentMessages[responseType] || componentMessages['analyzing'] || '正在处理中...'
    }
  }

  // Use stepLabel if available
  if (stepLabel) {
    return `正在处理 ${stepLabel}...`
  }

  // Fallback
  return '正在处理中...'
}

const StreamContentBubble: React.FC<StreamContentBubbleProps> = ({ item, collapsed, onToggle, onCopy, isActive }) => {
  const badgeClass = badgeVariantMap[item.statusVariant]

  // Generate summary text for collapsed streaming state
  const summaryText = useMemo(() => {
    if (collapsed && item.isStreaming && item.status === 'active') {
      return generateSummaryText(item.metadata, item.stepLabel, item.message)
    }
    return null
  }, [collapsed, item.isStreaming, item.status, item.metadata, item.stepLabel, item.message])

  // Try to parse message as JSON and check if it's a Phase 0 summary
  const parsedSummary = useMemo(() => {
    try {
      const parsed = JSON.parse(item.message)
      // Check if this looks like a Phase 0 summary (transcript or comments)
      // Handle both flat structure (from stream) and nested structure (from backend)
      const transcriptSummary = parsed.transcript_summary || parsed
      const commentsSummary = parsed.comments_summary || parsed
      const summaryType = parsed.summary_type || parsed.type || item.metadata?.summary_type
      
      const isTranscriptSummary = 
        summaryType === 'transcript' ||
        transcriptSummary.key_facts || 
        transcriptSummary.key_opinions || 
        transcriptSummary.key_datapoints || 
        transcriptSummary.topic_areas
      
      const isCommentsSummary = 
        summaryType === 'comments' ||
        commentsSummary.key_facts_from_comments || 
        commentsSummary.key_opinions_from_comments || 
        commentsSummary.major_themes
      
      if (isTranscriptSummary || isCommentsSummary) {
        return parsed
      }
    } catch {
      // Not valid JSON or not a Phase 0 summary, will render as text
    }
    return null
  }, [item.message, item.metadata])

  return (
    <div
      className={`rounded-xl border px-3 py-2 shadow-sm transition ${
        isActive ? 'border-primary-300 ring-2 ring-primary-200/60 bg-primary-50/40' : 'border-neutral-200 bg-neutral-white'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-800">
            {item.subtitle && (
              <span className="rounded-full bg-neutral-200 px-1.5 py-0.5 text-xs text-neutral-600">
                {item.subtitle}
              </span>
            )}
            <span className={`rounded-full px-1.5 py-0.5 text-xs ${badgeClass}`}>
              {item.status === 'active' ? '进行中' : item.status === 'completed' ? '已完成' : '错误'}
            </span>
            {item.timestamp && (
              <span className="text-xs text-neutral-400">
                {new Date(item.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}
              </span>
            )}
          </div>
          {item.isStreaming && (
            <span className="flex items-center gap-1.5 text-xs text-primary-500">
              <span className="h-1.5 w-1.5 rounded-full bg-primary-500 animate-pulse" />
              正在流式输出…
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {item.isCollapsible && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="px-2 py-0.5 text-xs"
              onClick={() => onToggle(item)}
            >
              {collapsed ? '展开' : '收起'}
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="px-2 py-0.5 text-xs"
            onClick={() => onCopy(item)}
          >
            复制
          </Button>
        </div>
      </div>
      <div className="mt-2 rounded-lg bg-neutral-50 px-2 py-1.5 text-xs text-neutral-700">
        {parsedSummary ? (
          // Render Phase 0 summary with specialized component
          collapsed && item.isCollapsible ? (
            <div className="prose prose-xs max-w-none prose-p:my-1 prose-strong:text-neutral-600">
              <ReactMarkdown>{item.preview}</ReactMarkdown>
            </div>
          ) : (
            <Phase0SummaryDisplay data={parsedSummary} />
          )
        ) : (
          // Render as plain text or markdown
          item.isCollapsible && collapsed ? (
            // Show summary text with shining animation if streaming, otherwise show preview
            summaryText ? (
              <div className="prose prose-xs max-w-none prose-p:my-1 prose-strong:text-neutral-600 relative">
                <div className="relative z-10">
                  <ReactMarkdown>{summaryText}</ReactMarkdown>
                </div>
                <span 
                  className="absolute inset-0 z-20 pointer-events-none"
                  style={{
                    background: 'linear-gradient(90deg, transparent 0%, rgba(148,163,184,0.4) 50%, transparent 100%)',
                    backgroundSize: '200% 100%',
                    animation: 'shine 2.5s ease-in-out infinite',
                    mixBlendMode: 'overlay',
                  }}
                />
              </div>
            ) : (
              <div className="prose prose-xs max-w-none prose-p:my-1 prose-strong:text-neutral-600">
                <ReactMarkdown>{item.preview}</ReactMarkdown>
              </div>
            )
          ) : (
            <div className="prose prose-xs max-w-none prose-p:my-1 prose-strong:text-neutral-700 prose-pre:bg-transparent prose-pre:p-0 prose-pre:border-0">
              <ReactMarkdown>{item.message}</ReactMarkdown>
            </div>
          )
        )}
      </div>
    </div>
  )
}

export default StreamContentBubble
