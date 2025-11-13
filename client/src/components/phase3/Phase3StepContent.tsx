import React from 'react'
import ReactMarkdown from 'react-markdown'
import { Icon } from '../common/Icon'
import {
  Phase3StepContentModel,
  Phase3StepEvidence,
  Phase3StepKeyClaim,
  FiveWhyItem,
} from '../../hooks/usePhase3Steps'

interface Phase3StepContentProps {
  content: Phase3StepContentModel
  confidence?: number | null
  showRawData: boolean
  onToggleRawData: () => void
  rawStep?: unknown
}

const baseSectionClass = 'bg-neutral-50 rounded-lg p-4'
const subSectionClass = 'bg-neutral-100 rounded-lg p-4'

const ConfidenceBar: React.FC<{ confidence: number }> = ({ confidence }) => {
  const getConfidenceColor = () => {
    if (confidence >= 0.8) {
      return 'bg-green-500'
    }
    if (confidence >= 0.6) {
      return 'bg-yellow-500'
    }
    return 'bg-red-500'
  }

  return (
    <div className="flex items-center space-x-4">
      <span className="font-medium text-neutral-700">可信度：</span>
      <div className="flex-1 bg-neutral-200 rounded-full h-2.5">
        <div className={`h-2.5 rounded-full ${getConfidenceColor()}`} style={{ width: `${confidence * 100}%` }} />
      </div>
      <span className="text-sm font-medium text-neutral-700">{(confidence * 100).toFixed(1)}%</span>
    </div>
  )
}

const KeyClaims: React.FC<{ claims: Phase3StepKeyClaim[] }> = ({ claims }) => {
  if (!claims.length) {
    return null
  }

  return (
    <div className={baseSectionClass}>
      <h4 className="font-semibold text-neutral-800 mb-3 flex items-center">
        <Icon name="key" size={18} strokeWidth={2} className="mr-2" />
        主要观点
      </h4>
      <div className="space-y-3">
        {claims.map((claim, index) => (
          <div key={index} className="bg-white rounded-lg p-4 border border-neutral-200">
            <div className="font-medium text-neutral-800 mb-2">{claim.claim}</div>
            {claim.supportingEvidence && (
              <div className="text-sm text-neutral-600 mt-2">
                <span className="font-medium">论据：</span>
                <div className="prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-600">
                  <ReactMarkdown>{claim.supportingEvidence}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

const NotableEvidence: React.FC<{ evidence: Phase3StepEvidence[] }> = ({ evidence }) => {
  if (!evidence.length) {
    return null
  }

  return (
    <div className={baseSectionClass}>
      <h4 className="font-semibold text-neutral-800 mb-3 flex items-center">
        <Icon name="chart" size={18} strokeWidth={2} className="mr-2" />
        重要发现
      </h4>
      <div className="space-y-3">
        {evidence.map((item, index) => (
          <div key={index} className="bg-white rounded-lg p-4 border border-neutral-200">
            <div className="flex items-start">
              <span className="inline-block bg-yellow-100 text-yellow-800 text-xs font-medium px-2.5 py-0.5 rounded mr-3 mt-1">
                {item.evidenceType}
              </span>
              <div className="text-neutral-700 flex-1 prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-700">
                <ReactMarkdown>{item.description}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const FiveWhysTable: React.FC<{ items: FiveWhyItem[] }> = ({ items }) => {
  if (!items.length) {
    return null
  }

  return (
    <div className={subSectionClass}>
      <h5 className="font-medium text-neutral-800 mb-3">Five Whys</h5>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white border border-neutral-300 rounded-lg">
          <thead>
            <tr className="bg-neutral-200">
              <th className="px-4 py-2 text-left text-sm font-semibold text-neutral-800 border-b border-neutral-300">
                问题
              </th>
              <th className="px-4 py-2 text-left text-sm font-semibold text-neutral-800 border-b border-neutral-300">
                回答
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={index} className={index % 2 === 0 ? 'bg-white' : 'bg-neutral-50'}>
                <td className="px-4 py-3 text-sm text-neutral-700 border-b border-neutral-200">
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-700">
                    <ReactMarkdown>{item.question}</ReactMarkdown>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-neutral-700 border-b border-neutral-200">
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-700">
                    <ReactMarkdown>{item.answer}</ReactMarkdown>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const AnalysisSection: React.FC<{ content: Phase3StepContentModel['analysis'] }> = ({ content }) => {
  const hasContent =
    content.fiveWhys.length > 0 || content.assumptions.length > 0 || content.uncertainties.length > 0

  if (!hasContent) {
    return null
  }

  return (
    <div className={baseSectionClass}>
      <h4 className="font-semibold text-neutral-800 mb-3 flex items-center">
        <Icon name="search" size={18} strokeWidth={2} className="mr-2" />
        Q&A
      </h4>
      <div className="space-y-4">
        <FiveWhysTable items={content.fiveWhys} />
        {!!content.assumptions.length && (
          <div className={subSectionClass}>
            <h5 className="font-medium text-neutral-800 mb-2">本分析有何假设？</h5>
            <ul className="list-disc list-inside space-y-1 text-neutral-700">
              {content.assumptions.map((item, index) => (
                <li key={index}>
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-700 prose-li:my-0">
                    <ReactMarkdown>{item}</ReactMarkdown>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!!content.uncertainties.length && (
          <div className={subSectionClass}>
            <h5 className="font-medium text-neutral-800 mb-2">有什么未能确定？</h5>
            <ul className="list-disc list-inside space-y-1 text-neutral-700">
              {content.uncertainties.map((item, index) => (
                <li key={index}>
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-strong:text-neutral-700 prose-li:my-0">
                    <ReactMarkdown>{item}</ReactMarkdown>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

const Phase3StepContent: React.FC<Phase3StepContentProps> = ({
  content,
  confidence,
  showRawData,
  onToggleRawData,
  rawStep,
}) => (
  <div className="space-y-6">
    {content.summary && (
      <div className={baseSectionClass}>
        <h4 className="font-semibold text-neutral-800 mb-2 flex items-center">
          <Icon name="edit" size={18} strokeWidth={2} className="mr-2" />
          摘要
        </h4>
        <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
          <ReactMarkdown>{content.summary}</ReactMarkdown>
        </div>
      </div>
    )}

    <KeyClaims claims={content.keyClaims} />
    <NotableEvidence evidence={content.notableEvidence} />

    {content.article && (
      <div className={baseSectionClass}>
        <h4 className="font-semibold text-neutral-800 mb-2 flex items-center">
          <Icon name="file" size={18} strokeWidth={2} className="mr-2" />
          深度文章
        </h4>
        <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
          <ReactMarkdown>{content.article}</ReactMarkdown>
        </div>
      </div>
    )}

    <AnalysisSection content={content.analysis} />

    {content.insights && (
      <div className="bg-yellow-50 rounded-lg p-4 border-l-4 border-yellow-500">
        <h4 className="font-semibold text-neutral-800 mb-2 flex items-center">
          <Icon name="lightbulb" size={18} strokeWidth={2} className="mr-2" />
          洞察
        </h4>
        <div className="prose prose-sm max-w-none prose-p:text-neutral-700 prose-p:my-2 prose-strong:text-neutral-700">
          <ReactMarkdown>{content.insights}</ReactMarkdown>
        </div>
      </div>
    )}

    {typeof confidence === 'number' && !Number.isNaN(confidence) && (
      <ConfidenceBar confidence={confidence} />
    )}

    {rawStep !== undefined && rawStep !== null && (
      <div className="border-t pt-4">
        <button
          onClick={onToggleRawData}
          className="text-sm text-neutral-500 hover:text-neutral-700 flex items-center"
        >
          <span className="mr-2">{showRawData ? '▼' : '▶'}</span>
          {showRawData ? '收起原始数据' : '查看原始数据'}
        </button>
        {showRawData && (
          <pre className="mt-2 text-xs bg-neutral-100 p-4 rounded overflow-auto max-h-96 border">
            {JSON.stringify(rawStep, null, 2)}
          </pre>
        )}
      </div>
    )}
  </div>
)

export default Phase3StepContent


