import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/common/Card'
import Button from '../components/common/Button'
import Textarea from '../components/common/Textarea'
import { useWorkflowStore } from '../stores/workflowStore'
import { useUiStore } from '../stores/uiStore'
import { apiService } from '../services/api'

const LinkInputPage: React.FC = () => {
  const navigate = useNavigate()
  const [urls, setUrls] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasExistingSession, setHasExistingSession] = useState(false)
  const { 
    batchId, 
    setBatchId, 
    setCurrentPhase, 
    reset,
    validateState,
    scrapingStatus,
    researchAgentStatus,
    phase3Steps,
    finalReport,
    sessionId,  // Get session_id from store
    setSessionId  // Set session_id if returned from backend
  } = useWorkflowStore()
  const { addNotification } = useUiStore()

  // Check if there's an existing session when component mounts
  useEffect(() => {
    const validation = validateState()
    if (!validation.isValid) {
      console.warn('State validation errors detected:', validation.errors)
    }
    
    const hasActiveSession = batchId !== null && (
      scrapingStatus.total > 0 ||
      researchAgentStatus.goals !== null ||
      phase3Steps.length > 0 ||
      finalReport !== null
    )
    setHasExistingSession(hasActiveSession)
  }, [batchId, scrapingStatus, researchAgentStatus, phase3Steps, finalReport, validateState])

  const handleStartNewSession = () => {
    if (window.confirm('确定要开始新会话吗？当前会话的数据将被清除。')) {
      reset()
      setHasExistingSession(false)
      setUrls('')
      setError(null)
      addNotification('会话已清除，可以开始新的研究', 'info')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    
    // Check if there's an existing session
    if (hasExistingSession) {
      const confirmed = window.confirm(
        '检测到现有会话。开始新会话将清除当前会话的所有数据。\n\n是否继续？'
      )
      if (!confirmed) {
        return
      }
      // Reset state before starting new session
      reset()
      setHasExistingSession(false)
    }
    
    if (!urls.trim()) {
      setError('请输入至少一个URL')
      return
    }

    setIsLoading(true)

    try {
      // Parse URLs (one per line)
      const urlList = urls
        .split('\n')
        .map((url) => url.trim())
        .filter((url) => url.length > 0)

      // Validate URLs
      const urlPattern = /^https?:\/\/.+/i
      const invalidUrls = urlList.filter((url) => !urlPattern.test(url))
      
      if (invalidUrls.length > 0) {
        setError(`无效的URL格式: ${invalidUrls.join(', ')}`)
        setIsLoading(false)
        return
      }

      console.log('Formatting links:', urlList)
      console.log('API base URL:', '/api')
      console.log('Making request to:', '/api/links/format')
      
      // First, test if backend is reachable - use /api/health endpoint (proxied)
      try {
        console.log('Testing backend connectivity...')
        // Use /api/health which is guaranteed to be proxied correctly
        const healthCheck = await fetch('/api/health', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: AbortSignal.timeout(5000), // 5 second timeout for health check
        })
        
        // Check if response is actually JSON (not HTML)
        const contentType = healthCheck.headers.get('content-type')
        if (!contentType || !contentType.includes('application/json')) {
          console.warn('Backend health check returned non-JSON response:', contentType)
          setError(`后端服务器返回了非JSON响应。请确保后端正在运行在端口 3001。\n\n启动后端: python backend/run_server.py`)
          addNotification('后端服务器响应格式错误', 'error')
          setIsLoading(false)
          return
        }
        
        if (healthCheck.ok) {
          const healthData = await healthCheck.json()
          console.log('Backend health check passed:', healthData)
        } else {
          console.warn('Backend health check returned non-OK status:', healthCheck.status)
          setError(`后端服务器返回错误状态: ${healthCheck.status}`)
          addNotification(`后端服务器错误: ${healthCheck.status}`, 'error')
          setIsLoading(false)
          return
        }
      } catch (healthError: any) {
        console.error('Backend health check failed:', healthError)
        // Check if it's a JSON parsing error (means we got HTML instead)
        const isJsonError = healthError.message && healthError.message.includes('JSON')
        const errorMessage = isJsonError
          ? '后端服务器返回了HTML而不是JSON。请确保后端正在运行在端口 3001，并且Vite代理配置正确。\n\n启动后端: python backend/run_server.py'
          : healthError.name === 'TimeoutError' 
          ? '后端服务器无响应（超时）。请确保后端正在运行在端口 3001。\n\n启动后端: python backend/run_server.py\n\n或者从项目根目录运行:\ncd backend\npython run_server.py'
          : `无法连接到后端服务器: ${healthError.message}\n\n请确保后端正在运行在端口 3001。\n\n启动后端: python backend/run_server.py`
        setError(errorMessage)
        addNotification('无法连接到后端服务器，请检查后端是否运行', 'error')
        setIsLoading(false)
        return
      }
      
      // Format links and create batch (using existing session_id)
      const startTime = Date.now()
      let response
      try {
        response = await apiService.formatLinks(urlList, sessionId || undefined)
        const duration = Date.now() - startTime
        console.log(`Format links response received in ${duration}ms:`, response)
        
        // Update session_id if returned from backend (for backward compatibility)
        if (response.session_id && !sessionId) {
          setSessionId(response.session_id)
        }
      } catch (error: any) {
        const duration = Date.now() - startTime
        console.error(`Format links failed after ${duration}ms:`, error)
        console.error('Error details:', {
          message: error.message,
          response: error.response?.data,
          status: error.response?.status,
          code: error.code,
        })
        
        // Provide more helpful error messages
        if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
          setError('请求超时。请检查后端服务器是否正在运行。')
          addNotification('请求超时，请确保后端服务器正在运行', 'error')
        } else if (error.code === 'ERR_NETWORK' || error.message.includes('Network Error')) {
          setError('网络错误。无法连接到后端服务器。')
          addNotification('网络错误，请检查后端服务器是否运行', 'error')
        } else {
          const errorMsg = error.response?.data?.detail || error.message || '格式化链接时出错'
          setError(errorMsg)
          addNotification(`链接格式有误，请检查后重试`, 'error')
        }
        setIsLoading(false)
        return
      }
      
      if (response.batch_id) {
        console.log('Setting batchId:', response.batch_id)
        setBatchId(response.batch_id)
        setCurrentPhase('scraping')
        addNotification('链接格式化成功，开始抓取...', 'success')
        console.log('Navigating to /scraping')
        navigate('/scraping')
      } else {
        throw new Error('未返回批次ID')
      }
    } catch (err: any) {
      console.error('Error formatting links:', err)
      const errorMessage = err.response?.data?.detail || err.response?.data?.message || err.message || '格式化链接时出错'
      setError(errorMessage)
      addNotification(`链接格式有误，请检查后重试`, 'error')
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <Card
        title="输入链接"
        subtitle="请输入要研究的URL链接，每行一个"
      >
        {/* Existing Session Warning */}
        {hasExistingSession && (
          <div className="mb-6 bg-yellow-50 border border-yellow-300 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h4 className="font-semibold text-yellow-800 mb-1">检测到现有会话</h4>
                <p className="text-sm text-yellow-700 mb-3">
                  当前存在一个活跃的研究会话。开始新会话将清除所有现有数据。
                </p>
                {batchId && (
                  <p className="text-xs text-yellow-600 mb-2">
                    当前批次ID: {batchId}
                  </p>
                )}
              </div>
              <button
                onClick={handleStartNewSession}
                className="ml-4 px-4 py-2 bg-yellow-500 hover:bg-yellow-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                清除会话
              </button>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <Textarea
            label="URL链接"
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=...&#10;https://www.bilibili.com/video/..."
            rows={10}
            error={error || undefined}
            helperText="支持 YouTube、Bilibili、Reddit、Tieba 和文章链接"
            disabled={isLoading}
          />

          <div className="flex items-center justify-end space-x-4">
            {hasExistingSession && (
              <Button
                type="button"
                variant="secondary"
                onClick={handleStartNewSession}
                disabled={isLoading}
              >
                清除会话并开始新研究
              </Button>
            )}
            <Button
              type="submit"
              variant="primary"
              isLoading={isLoading}
              disabled={!urls.trim() || isLoading}
            >
              开始研究
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

export default LinkInputPage


