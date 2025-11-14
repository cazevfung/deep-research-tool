import React, { useEffect, useState } from 'react'
import { useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'
import { apiService } from '../services/api'
import ReactMarkdown from 'react-markdown'

const FinalReportPage: React.FC = () => {
  const { batchId, finalReport, setFinalReport, reportStale, sessionId } = useWorkflowStore()
  const { addNotification } = useUiStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (finalReport?.content) {
      return
    }

    if (!batchId) {
      setError('还没有开始研究工作，请先添加链接并开始研究')
      return
    }

    const fetchReport = async () => {
      setLoading(true)
      setError(null)
      try {
        const reportData = await apiService.getFinalReport(batchId)
        setFinalReport({
          content: reportData.content,
          generatedAt: reportData.metadata.generatedAt,
          status: reportData.status as 'generating' | 'ready' | 'error',
        })
      } catch (err: any) {
        console.error('Failed to fetch report:', err)
        if (err.response?.status === 404) {
          setError('报告正在生成中，请稍候...')
        } else {
          setError(err.response?.data?.detail || err.message || '无法加载报告，请刷新页面重试')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchReport()
  }, [batchId, finalReport, setFinalReport])

  const handleExport = async () => {
    // Try to get sessionId from store first, then from report metadata
    let currentSessionId = sessionId
    
    if (!currentSessionId && finalReport) {
      // Try to get from report metadata if available
      try {
        const reportData = await apiService.getFinalReport(batchId!)
        currentSessionId = reportData.metadata.sessionId || null
      } catch (err) {
        console.error('Failed to fetch report for sessionId:', err)
      }
    }
    
    if (!currentSessionId) {
      addNotification('无法找到会话ID，无法导出', 'error')
      return
    }
    
    setExporting(true)
    try {
      const result = await apiService.exportSessionHtml(currentSessionId)
      
      // Open the HTML file in a new window
      window.open(result.file_url, '_blank')
      
      if (result.cached) {
        addNotification('已打开导出的HTML文件（使用缓存）', 'success')
      } else {
        addNotification('已导出并打开HTML文件', 'success')
      }
    } catch (err: any) {
      console.error('Failed to export HTML:', err)
      const errorMessage = err.response?.data?.detail || err.message || '导出失败，请重试'
      addNotification(errorMessage, 'error')
    } finally {
      setExporting(false)
    }
  }

  // Filter out metadata paragraphs from report content
  const filterMetadata = (content: string): string => {
    if (!content) return content
    
    // Remove metadata paragraphs: 研究目标, 生成时间, 批次ID
    // Also remove the h1 "研究报告" title if it's the first heading
    let filtered = content
      // Remove 研究目标 paragraph (markdown format)
      .replace(/^\*\*研究目标\*\*:\s*[^\n]+\s*\n?/gim, '')
      // Remove 生成时间 paragraph (markdown format)
      .replace(/^\*\*生成时间\*\*:\s*[^\n]+\s*\n?/gim, '')
      // Remove 批次ID paragraph (markdown format)
      .replace(/^\*\*批次ID\*\*:\s*[^\n]+\s*\n?/gim, '')
      // Remove standalone h1 "研究报告" title if it's at the beginning
      .replace(/^#\s+研究报告\s*\n+/m, '')
      // Remove first horizontal rule (--- or *** or <hr>)
      .replace(/^---\s*\n+/m, '')
      .replace(/^\*\*\*\s*\n+/m, '')
      .replace(/^<hr>\s*\n*/m, '')
      // Remove any empty lines at the start
      .replace(/^\s*\n+/m, '')
    
    return filtered.trim()
  }

  return (
    <div className="max-w-4xl mx-auto h-full flex flex-col">
      <div className="card h-full flex flex-col p-0">
        <div className="sticky top-0 bg-neutral-white pb-4 border-b border-neutral-300 mb-4 z-10 px-6 pt-6 rounded-t-lg">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-xl font-bold text-neutral-black">研究报告</h2>
              {reportStale && (
                <p className="text-sm text-secondary-500 mt-2">
                  提示：最终报告已过期，请重新运行阶段 4 以获取最新结果。
                </p>
              )}
            </div>

            <button
              type="button"
              onClick={handleExport}
              disabled={!sessionId || exporting}
              className="inline-flex items-center justify-center rounded-full border border-primary-200 bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-primary-600 disabled:cursor-not-allowed disabled:border-neutral-200 disabled:bg-neutral-200 disabled:text-neutral-500"
            >
              {exporting ? '导出中...' : '导出 PDF'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-6">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <p className="text-neutral-400">正在加载报告...</p>
            </div>
          )}

          {error && !loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-red-500 mb-2">{error}</p>
                <p className="text-sm text-neutral-500">
                  研究可能还在进行中，请稍后再查看报告
                </p>
              </div>
            </div>
          )}

          {!loading && !error && finalReport?.content && (
            <div className="prose prose-lg max-w-none prose-headings:text-neutral-black prose-headings:font-bold prose-p:text-neutral-black prose-p:leading-relaxed prose-strong:text-neutral-black prose-ul:text-neutral-black prose-ol:text-neutral-black prose-li:text-neutral-black prose-hr:border-neutral-300 pt-4">
              <ReactMarkdown>{filterMetadata(finalReport.content)}</ReactMarkdown>
            </div>
          )}

          {!loading && !error && !finalReport?.content && (
            <div className="flex items-center justify-center h-full">
              <p className="text-neutral-400">报告生成中...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default FinalReportPage


