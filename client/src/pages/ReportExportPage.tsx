import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

interface Phase3Step {
  step_id: number
  findings: any
  insights?: string
  confidence?: number
  timestamp?: string
}

interface ReportData {
  session_id: string
  batch_id?: string
  research_objective: string
  final_report: string
  phase3_steps: Phase3Step[]
  research_plan: Array<{ step_id: number; goal: string }>
}

/**
 * Print-optimized report page that uses browser's Print to PDF
 * Maintains all Tailwind styling for beautiful PDF exports
 */
const ReportExportPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reportData, setReportData] = useState<ReportData | null>(null)

  useEffect(() => {
    const loadReportData = async () => {
      if (!sessionId) {
        setError('No session ID provided')
        return
      }

      try {
        setLoading(true)
        // Load session data
        const sessionResponse = await fetch(`/data/research/sessions/session_${sessionId}.json`)
        if (!sessionResponse.ok) {
          throw new Error('Failed to load session data')
        }
        const sessionData = await sessionResponse.json()

        // Extract data
        const metadata = sessionData.metadata || {}
        const scratchpad = sessionData.scratchpad || {}
        const phase4 = sessionData.phase_artifacts?.phase4?.data || {}

        const research_objective = metadata.synthesized_goal?.comprehensive_topic || metadata.selected_goal || metadata.user_topic || '未提供研究目标'
        const final_report =
          phase4.report_content || phase4.final_report || metadata.final_report || '最终报告尚未生成。'

        // Extract phase 3 steps
        const phase3_steps: Phase3Step[] = []
        const research_plan = metadata.research_plan || []

        for (const key of Object.keys(scratchpad).sort()) {
          const entry = scratchpad[key]
          if (entry && entry.step_id) {
            phase3_steps.push({
              step_id: entry.step_id,
              findings: entry.findings,
              insights: entry.insights,
              confidence: entry.confidence,
              timestamp: entry.timestamp,
            })
          }
        }

        setReportData({
          session_id: sessionId,
          batch_id: metadata.batch_id,
          research_objective,
          final_report,
          phase3_steps,
          research_plan,
        })
      } catch (err: any) {
        console.error('Failed to load report:', err)
        setError(err.message || '无法加载报告数据')
      } finally {
        setLoading(false)
      }
    }

    loadReportData()
  }, [sessionId])

  useEffect(() => {
    // Add print styles
    const style = document.createElement('style')
    style.textContent = `
      @media print {
        @page {
          size: A4;
          margin: 1.5cm;
        }
        
        body {
          print-color-adjust: exact;
          -webkit-print-color-adjust: exact;
        }
        
        .no-print {
          display: none !important;
        }
        
        .page-break {
          page-break-after: always;
        }
        
        .avoid-break {
          page-break-inside: avoid;
        }
        
        /* Ensure cards have backgrounds in print */
        .card, .bg-neutral-white, .bg-neutral-50 {
          background-color: white !important;
        }
        
        .bg-yellow-50 {
          background-color: #FEFCE8 !important;
        }
        
        .bg-neutral-100 {
          background-color: #F0F3F6 !important;
        }
      }
    `
    document.head.appendChild(style)
    return () => {
      document.head.removeChild(style)
    }
  }, [])

  const handlePrint = () => {
    window.print()
  }

  const handleBack = () => {
    navigate(-1)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <p className="text-neutral-600">正在加载报告数据...</p>
        </div>
      </div>
    )
  }

  if (error || !reportData) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error || '无法加载报告'}</p>
          <button onClick={handleBack} className="btn-secondary">
            返回
          </button>
        </div>
      </div>
    )
  }

  const getStepTitle = (stepId: number): string => {
    const plan = reportData.research_plan.find((p) => p.step_id === stepId)
    return plan?.goal || `Step ${stepId}`
  }

  const formatTimestamp = (timestamp?: string): string => {
    if (!timestamp) return ''
    try {
      const dt = new Date(timestamp)
      return `Updated ${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
    } catch {
      return timestamp
    }
  }

  const extractContent = (step: Phase3Step) => {
    const findings_root = step.findings || {}
    const findings = findings_root.findings || findings_root
    const poi = findings.points_of_interest || {}
    const analysis = findings.analysis_details || {}

    return {
      summary: findings.summary,
      article: findings.article,
      keyClaims: poi.key_claims || [],
      notableEvidence: poi.notable_evidence || [],
      fiveWhys: analysis.five_whys || [],
      assumptions: analysis.assumptions || [],
      uncertainties: analysis.uncertainties || [],
      insights: step.insights,
      confidence: step.confidence,
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Print controls - hidden when printing */}
      <div className="no-print sticky top-0 z-50 bg-white border-b border-neutral-300 shadow-sm">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-neutral-black">研究报告导出</h1>
            <p className="text-sm text-neutral-500">Session {reportData.session_id}</p>
          </div>
          <div className="flex gap-3">
            <button onClick={handleBack} className="btn-secondary">
              返回
            </button>
            <button onClick={handlePrint} className="btn-primary">
              打印/导出 PDF
            </button>
          </div>
        </div>
      </div>

      {/* Report content - optimized for printing */}
      <div className="max-w-4xl mx-auto px-8 py-12">
        {/* Cover page */}
        <div className="mb-12 avoid-break">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-bold text-neutral-black">Research Tool</h1>
            <img src="/logo.png" alt="Logo" className="h-10" />
          </div>
          <div className="border-t-4 border-primary-500 pt-8">
            <h2 className="text-2xl font-bold text-neutral-800 mb-4">研究报告</h2>
            <div className="space-y-2 text-sm text-neutral-600">
              <p>Session ID: {reportData.session_id}</p>
              {reportData.batch_id && <p>Batch ID: {reportData.batch_id}</p>}
              <p>导出时间: {new Date().toLocaleString('zh-CN')}</p>
            </div>
          </div>
        </div>

        {/* Research Objective */}
        <section className="mb-12 avoid-break">
          <h2 className="text-xl font-bold text-neutral-800 mb-4">Research Objective</h2>
          <div className="card p-6">
            <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
              <ReactMarkdown>{reportData.research_objective}</ReactMarkdown>
            </div>
          </div>
        </section>

        {/* Phase 3 Steps */}
        <section className="mb-12">
          <h2 className="text-xl font-bold text-neutral-800 mb-4">Research Execution Summary</h2>
          <div className="space-y-6">
            {reportData.phase3_steps.map((step, idx) => {
              const content = extractContent(step)
              const title = getStepTitle(step.step_id)

              return (
                <div key={step.step_id} className="card p-6 avoid-break">
                  {/* Step header */}
                  <div className="mb-4 pb-4 border-b border-neutral-200">
                    <h3 className="text-lg font-semibold text-neutral-800 mb-1">
                      Step {idx + 1}: {title}
                    </h3>
                    {step.timestamp && (
                      <p className="text-xs text-neutral-500">{formatTimestamp(step.timestamp)}</p>
                    )}
                    {typeof content.confidence === 'number' && (
                      <div className="mt-2 inline-block px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-medium rounded-full">
                        Confidence: {(content.confidence * 100).toFixed(0)}%
                      </div>
                    )}
                  </div>

                  {/* Summary */}
                  {content.summary && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-2">📝 摘要</h4>
                      <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
                        <ReactMarkdown>{content.summary}</ReactMarkdown>
                      </div>
                    </div>
                  )}

                  {/* Key Claims */}
                  {content.keyClaims.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-2">🔑 主要观点</h4>
                      <div className="space-y-2">
                        {content.keyClaims.map((claim: any, i: number) => (
                          <div key={i} className="bg-neutral-50 rounded p-3">
                            <p className="text-sm font-medium text-neutral-800">{claim.claim}</p>
                            {claim.supporting_evidence && (
                              <div className="text-xs text-neutral-600 mt-1">
                                <span className="font-medium">论据：</span>
                                <div className="prose prose-xs max-w-none prose-p:my-1 prose-strong:text-neutral-600 inline">
                                  <ReactMarkdown>{claim.supporting_evidence}</ReactMarkdown>
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Notable Evidence */}
                  {content.notableEvidence.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-2">📊 重要发现</h4>
                      <div className="space-y-2">
                        {content.notableEvidence.map((ev: any, i: number) => (
                          <div key={i} className="bg-neutral-50 rounded p-3">
                            {ev.evidence_type && (
                              <span className="inline-block px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs font-medium rounded mr-2">
                                {ev.evidence_type}
                              </span>
                            )}
                            <div className="text-sm text-neutral-700 inline prose prose-sm max-w-none prose-p:my-0 prose-strong:text-neutral-700">
                              <ReactMarkdown>{ev.description}</ReactMarkdown>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Article */}
                  {content.article && (
                    <div className="mb-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-2">📄 深度文章</h4>
                      <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
                        <ReactMarkdown>{content.article}</ReactMarkdown>
                      </div>
                    </div>
                  )}

                  {/* Analysis */}
                  {(content.fiveWhys.length > 0 ||
                    content.assumptions.length > 0 ||
                    content.uncertainties.length > 0) && (
                    <div className="mb-4 bg-neutral-100 rounded p-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-3">🔍 Q&A</h4>

                      {content.fiveWhys.length > 0 && (
                        <div className="mb-3">
                          <h5 className="text-xs font-semibold text-neutral-700 mb-2">Five Whys</h5>
                          <div className="space-y-2">
                            {content.fiveWhys.map((item: any, i: number) => (
                              <div key={i} className="text-xs">
                                <div className="font-medium text-neutral-800 mb-1">
                                  Q: <span className="prose prose-xs max-w-none prose-p:my-0 prose-strong:text-neutral-800 inline">
                                    <ReactMarkdown>{item.question}</ReactMarkdown>
                                  </span>
                                </div>
                                <div className="text-neutral-600">
                                  A: <span className="prose prose-xs max-w-none prose-p:my-0 prose-strong:text-neutral-600 inline">
                                    <ReactMarkdown>{item.answer}</ReactMarkdown>
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {content.assumptions.length > 0 && (
                        <div className="mb-3">
                          <h5 className="text-xs font-semibold text-neutral-700 mb-2">本分析有何假设？</h5>
                          <ul className="list-disc list-inside text-xs text-neutral-600 space-y-1">
                            {content.assumptions.map((item: string, i: number) => (
                              <li key={i}>
                                <div className="prose prose-xs max-w-none prose-p:my-0 prose-strong:text-neutral-600 prose-li:my-0 inline">
                                  <ReactMarkdown>{item}</ReactMarkdown>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {content.uncertainties.length > 0 && (
                        <div>
                          <h5 className="text-xs font-semibold text-neutral-700 mb-2">有什么未能确定？</h5>
                          <ul className="list-disc list-inside text-xs text-neutral-600 space-y-1">
                            {content.uncertainties.map((item: string, i: number) => (
                              <li key={i}>
                                <div className="prose prose-xs max-w-none prose-p:my-0 prose-strong:text-neutral-600 prose-li:my-0 inline">
                                  <ReactMarkdown>{item}</ReactMarkdown>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Insights */}
                  {content.insights && (
                    <div className="bg-yellow-50 border-l-4 border-yellow-500 rounded p-4">
                      <h4 className="text-sm font-semibold text-neutral-800 mb-2">💡 洞察</h4>
                      <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
                        <ReactMarkdown>{content.insights}</ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        {/* Final Report */}
        <section className="mb-12">
          <h2 className="text-xl font-bold text-neutral-800 mb-4">Final Report Article</h2>
          <div className="card p-8">
            <div className="prose prose-lg max-w-none prose-headings:text-neutral-800 prose-headings:font-bold prose-p:text-neutral-700 prose-p:leading-relaxed prose-strong:text-neutral-700 prose-ul:text-neutral-700 prose-ol:text-neutral-700 prose-li:text-neutral-700 prose-hr:border-neutral-300">
              <ReactMarkdown>{reportData.final_report}</ReactMarkdown>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

export default ReportExportPage

