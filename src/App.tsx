import { useState } from 'react'
import Dashboard from './components/Dashboard'
import History from './components/History'
import OnboardingWizard from './components/OnboardingWizard'
import Settings from './components/Settings'
import { ToastProvider } from './components/Toast'
import { useTheme } from './hooks/useTheme'
import { useSettings } from './hooks/useSettings'

export type Page = 'dashboard' | 'history' | 'settings'

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: 'dashboard', label: '控制台', icon: '🏠' },
  { id: 'history', label: '操作历史', icon: '📋' },
  { id: 'settings', label: '设置', icon: '⚙️' },
]

const ONBOARDING_KEY = 'fileorganizer_onboarded'

function AppInner() {
  const [page, setPage] = useState<Page>('dashboard')
  const { theme, toggleTheme } = useTheme()
  const { settings } = useSettings()
  const [showOnboarding, setShowOnboarding] = useState(() => {
    // Show onboarding if no API key configured yet
    return !localStorage.getItem(ONBOARDING_KEY) && !settings.aiConfig?.apiKey
  })

  const handleOnboardingComplete = () => {
    localStorage.setItem(ONBOARDING_KEY, '1')
    setShowOnboarding(false)
  }

  return (
    <div className={`flex h-screen w-full ${theme === 'dark' ? 'bg-gray-900 text-gray-100' : 'bg-white text-gray-900'}`}>
      {showOnboarding && <OnboardingWizard onComplete={handleOnboardingComplete} />}

      {/* Sidebar */}
      <aside className={`w-52 flex flex-col pt-10 border-r ${
        theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'
      }`}>
        <div className="px-4 mb-6">
          <h1 className="text-lg font-bold">FileOrganizer</h1>
          <p className={`text-xs mt-0.5 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-400'}`}>智能文件整理助手</p>
        </div>

        <nav className="flex-1 px-2 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className={`w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                page === item.id
                  ? 'bg-blue-50 text-blue-700 font-medium dark:bg-blue-900 dark:text-blue-300'
                  : theme === 'dark'
                  ? 'text-gray-300 hover:bg-gray-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        {/* Theme toggle */}
        <div className="px-4 pb-4">
          <button
            onClick={toggleTheme}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
              theme === 'dark' ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'
            }`}
          >
            {theme === 'dark' ? '☀️ 切换亮色' : '🌙 切换暗色'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className={`flex-1 overflow-auto ${theme === 'dark' ? 'bg-gray-900' : 'bg-white'}`}>
        {page === 'dashboard' && <Dashboard onNavigate={setPage} />}
        {page === 'history' && <History />}
        {page === 'settings' && <Settings />}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  )
}
