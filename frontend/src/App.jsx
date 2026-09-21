import React, { useRef, useState } from 'react'
import TopBar from './components/TopBar'
import ChatPanel from './components/ChatPanel'
import PdfViewer from './components/PdfViewer'
import UniversalDocumentManager from './components/UniversalDocumentManager'
import PromptInspectorModal from './components/PromptInspectorModal'
import useAircraft from './hooks/useAircraft'
import useChat from './hooks/useChat'

/**
 * App.jsx
 * ───────────────────────────────────────────────────────────────
 * Root Application Container:
 * - Multi-Agent SLM Orchestration Layout
 * - ColPali Visual RAG Synchronized Split-Pane
 * - Neutral Multi-Document Support
 */

function App() {
  const pdfRef = useRef(null)
  const [isDocManagerOpen, setIsDocManagerOpen] = useState(false)
  const [isInspectorOpen, setIsInspectorOpen] = useState(false)

  const {
    aircraft,
    selectedAircraft,
    setSelectedAircraft,
    loading: aircraftLoading,
  } = useAircraft()

  const {
    messages,
    sendMessage,
    isStreaming,
    agentStatus,
    dagPlan,
    mathSteps,
    clearChat,
  } = useChat(
    selectedAircraft?.id,
    (page) => pdfRef.current?.jumpToPage(page)
  )

  if (aircraftLoading) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-navy-800 text-orange">
        <div className="w-12 h-12 border-4 border-navy-600 border-t-orange rounded-full animate-spin mb-4"></div>
        <div className="font-mono text-xs tracking-widest uppercase animate-pulse">
          Starting Aeromind Platform…
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden select-none bg-[#0a0d12]">
      {/* Top Bar Header */}
      <TopBar
        aircraftList={aircraft}
        selectedAircraft={selectedAircraft}
        onSelectAircraft={setSelectedAircraft}
        onOpenDocManager={() => setIsDocManagerOpen(true)}
        onOpenInspector={() => setIsInspectorOpen(true)}
      />

      {/* Main Split-Pane */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left: Chat & Multi-Agent Intelligence */}
        <ChatPanel
          messages={messages}
          onSend={sendMessage}
          isStreaming={isStreaming}
          agentStatus={agentStatus}
          dagPlan={dagPlan}
          mathSteps={mathSteps}
          onPageClick={(p) => pdfRef.current?.jumpToPage(p)}
          onClear={clearChat}
          selectedAircraft={selectedAircraft}
          onSelectAircraft={setSelectedAircraft}
          onOpenDocManager={() => setIsDocManagerOpen(true)}
          onOpenInspector={() => setIsInspectorOpen(true)}
        />

        {/* Right: PDF Viewer & ColPali Synchronizer */}
        <PdfViewer
          ref={pdfRef}
          aircraftId={selectedAircraft?.id}
          aircraftName={selectedAircraft?.name}
        />
      </main>

      {/* Universal Document Repository Modal */}
      <UniversalDocumentManager
        isOpen={isDocManagerOpen}
        onClose={() => setIsDocManagerOpen(false)}
        onSelectDocument={(doc) => {
          setSelectedAircraft({
            id: doc.id,
            name: doc.name,
            total_pages: doc.total_pages || 1,
            accent_color: '#e8780a',
          })
        }}
      />

      {/* LangSmith Traces & Prompt Inspector Modal */}
      <PromptInspectorModal
        isOpen={isInspectorOpen}
        onClose={() => setIsInspectorOpen(false)}
      />
    </div>
  )
}

export default App
