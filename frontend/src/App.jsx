import React, { useRef } from 'react'
import TopBar from './components/TopBar'
import ChatPanel from './components/ChatPanel'
import PdfViewer from './components/PdfViewer'
import useAircraft from './hooks/useAircraft'
import useChat from './hooks/useChat'

/**
 * App.jsx
 * ───────────────────────────────────────────────────────────────
 * Root component. Implements the split-pane layout and wires 
 * the Chat hook to the PDF viewer's ref.
 */

function App() {
  const pdfRef = useRef(null)
  
  const { 
    aircraft, 
    selectedAircraft, 
    setSelectedAircraft, 
    loading: aircraftLoading 
  } = useAircraft()

  const { 
    messages, 
    sendMessage, 
    isStreaming, 
    clearChat 
  } = useChat(
    selectedAircraft?.id, 
    (page) => pdfRef.current?.jumpToPage(page)
  )

  if (aircraftLoading) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-navy-800 text-orange">
        <div className="w-12 h-12 border-4 border-navy-600 border-t-orange rounded-full animate-spin mb-4"></div>
        <div className="font-mono text-xs tracking-widest uppercase animate-pulse">Initializing Avionics…</div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden select-none">
      <TopBar 
        aircraftList={aircraft}
        selectedAircraft={selectedAircraft}
        onSelectAircraft={setSelectedAircraft}
      />

      <main className="flex-1 flex overflow-hidden">
        {/* Left: Chat */}
        <ChatPanel 
          messages={messages}
          onSend={sendMessage}
          isStreaming={isStreaming}
          onPageClick={(p) => pdfRef.current?.jumpToPage(p)}
          onClear={clearChat}
          selectedAircraft={selectedAircraft}
        />

        {/* Right: PDF Viewer */}
        <PdfViewer 
          ref={pdfRef}
          aircraftId={selectedAircraft?.id}
          aircraftName={selectedAircraft?.name}
        />
      </main>
    </div>
  )
}

export default App
