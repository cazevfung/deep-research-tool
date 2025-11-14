import React from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'
import { useUiStore } from '../../stores/uiStore'
import { getIconComponent, IconName } from '../common/Icon'

const Sidebar: React.FC = () => {
  const location = useLocation()
  const { sidebarOpen, toggleSidebar } = useUiStore()

  const navItems: Array<{ path: string; label: string; icon: IconName }> = [
    { path: '/', label: '研究指导', icon: 'book' },
    { path: '/links', label: '添加链接', icon: 'link' },
    { path: '/scraping', label: '内容收集', icon: 'download' },
    { path: '/research', label: '研究规划', icon: 'research' },
    { path: '/phase3', label: '深度研究', icon: 'chart' },
    { path: '/report', label: '研究报告', icon: 'file' },
  ]

  return (
    <>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={toggleSidebar}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-primary-500 text-neutral-white transform transition-transform duration-300 ease-in-out shadow-[4px_0_8px_rgba(0,0,0,0.1),4px_0_12px_rgba(0,0,0,0.05)] ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
        style={{ backgroundColor: '#FEC74A' }}
      >
        <div className="flex flex-col h-full">
          {/* Logo/Brand */}
          <div className="px-4 py-6 flex items-center justify-start">
            <img 
              src="/logo.png?v=2" 
              alt="有料到" 
              className="h-[108px] w-auto object-contain"
            />
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-2">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path
              const IconComponent = getIconComponent(item.icon)
              return (
                <RouterLink
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-black text-white'
                      : 'text-black hover:bg-neutral-600 hover:text-white'
                  }`}
                  onClick={() => {
                    // Close sidebar on mobile after navigation
                    if (window.innerWidth < 1024) {
                      toggleSidebar()
                    }
                  }}
                >
                  <IconComponent size={20} strokeWidth={2} className="flex-shrink-0" />
                  <span className="font-medium">{item.label}</span>
                </RouterLink>
              )
            })}
            
            {/* History Menu Item */}
            <div className="pt-4 mt-4">
              <RouterLink
                to="/history"
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  location.pathname === '/history'
                    ? 'bg-black text-white'
                    : 'text-black hover:bg-neutral-600 hover:text-white'
                }`}
                onClick={() => {
                  // Close sidebar on mobile after navigation
                  if (window.innerWidth < 1024) {
                    toggleSidebar()
                  }
                }}
              >
                {React.createElement(getIconComponent('book'), { size: 20, strokeWidth: 2, className: 'flex-shrink-0' })}
                <span className="font-medium">历史记录</span>
              </RouterLink>
            </div>
          </nav>
        </div>
      </aside>
    </>
  )
}

export default Sidebar


