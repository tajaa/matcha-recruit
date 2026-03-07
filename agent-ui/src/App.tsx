import { useState, useEffect } from 'preact/hooks'
import { Login } from './components/Login'
import { Header } from './components/Header'
import { Toolbar } from './components/Toolbar'
import { ChatArea } from './components/ChatArea'
import { MessageInput } from './components/MessageInput'
import { Settings } from './components/Settings'
import { useHealth } from './hooks/useHealth'
import { useChat } from './hooks/useChat'
import { api } from './lib/api'

export function App() {
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const health = useHealth(authed)
  const chat = useChat()

  // Auto-login if token exists
  useEffect(() => {
    const token = sessionStorage.getItem('agent_token')
    if (token) {
      api
        .health()
        .then(() => setAuthed(true))
        .catch(() => sessionStorage.removeItem('agent_token'))
        .finally(() => setChecking(false))
    } else {
      setChecking(false)
    }
  }, [])

  const handleLogout = () => {
    sessionStorage.removeItem('agent_token')
    setAuthed(false)
  }

  const handleQuickAction = (action: string) => {
    if (action === 'emails') chat.fetchEmails()
    else if (action === 'briefing') chat.runBriefing()
    else if (action === 'help') chat.sendMessage('What can you help me with?')
  }

  if (checking) return null

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />
  }

  return (
    <div class="app">
      <Header health={health} onLogout={handleLogout} />
      <Toolbar
        loading={chat.loading}
        onEmails={chat.fetchEmails}
        onBriefing={chat.runBriefing}
        onClear={chat.clear}
        onSettings={() => setSettingsOpen(true)}
      />
      <ChatArea
        messages={chat.messages}
        loading={chat.loading}
        onDraft={chat.draftReply}
        onSchedule={chat.createEvent}
        onQuickAction={handleQuickAction}
      />
      <MessageInput loading={chat.loading} onSend={chat.sendMessage} />
      <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
