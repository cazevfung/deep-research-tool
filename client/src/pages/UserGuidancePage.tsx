import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'react-feather'
import { useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'
import { apiService } from '../services/api'

const UserGuidancePage: React.FC = () => {
  const navigate = useNavigate()
  const [userGuidance, setUserGuidance] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setSessionId } = useWorkflowStore()
  const { addNotification } = useUiStore()

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault()
    }
    setError(null)
    
    // Validate: guidance is required
    const trimmedGuidance = userGuidance.trim()
    if (!trimmedGuidance) {
      setError('请输入研究指导，此字段为必填项')
      return
    }
    
    setIsLoading(true)

    try {
      // Create session with user guidance (required)
      const response = await apiService.createSession(trimmedGuidance)
      
      if (response.session_id) {
        setSessionId(response.session_id)
        addNotification('会话已创建，请继续输入链接', 'success')
        navigate('/links') // Navigate to link input page
      } else {
        throw new Error('未返回会话ID')
      }
    } catch (err: any) {
      console.error('Error creating session:', err)
      setError(err.response?.data?.detail || err.message || '创建会话时出错')
      addNotification('创建会话失败，请重试', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Question Section */}
      <div className="pt-8 pb-8">
        <h1 className="text-2xl md:text-3xl font-semibold text-center text-gray-900 leading-relaxed max-w-3xl mx-auto">
          在本次研究开始之前，你想强调哪些问题重点或背景？
          <br />
          你希望有料到给你提供什么样的洞察？
        </h1>
      </div>

      {/* Input Section - Dialog Bubble */}
      <div className="max-w-2xl mx-auto mb-8">
        <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100">
          {error && (
            <div className="mb-4 text-sm text-red-600">
              {error}
            </div>
          )}
          <textarea
            value={userGuidance}
            onChange={(e) => setUserGuidance(e.target.value)}
            placeholder={`例如：\n• 重点关注技术实现细节\n• 分析用户反馈和评论\n• 对比不同方案的优缺点`}
            className="w-full min-h-[200px] p-4 border-0 bg-transparent text-base leading-relaxed placeholder:text-gray-400 focus:outline-none focus:ring-0 resize-none"
            rows={8}
            disabled={isLoading}
            onKeyDown={(e) => {
              // Allow Ctrl/Cmd + Enter to submit
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                handleSubmit()
              }
            }}
          />
        </div>
      </div>

      {/* Action Button - Circular */}
      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => handleSubmit()}
          disabled={isLoading || !userGuidance.trim()}
          className="w-16 h-16 rounded-full text-white shadow-xl hover:scale-110 transition-all duration-200 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          style={{ backgroundColor: '#FEC74A' }}
          aria-label="继续到链接输入"
        >
          {isLoading ? (
            <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <ArrowRight size={24} strokeWidth={2.5} />
          )}
        </button>
      </div>
    </div>
  )
}

export default UserGuidancePage

