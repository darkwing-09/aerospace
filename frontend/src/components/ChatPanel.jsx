import React, { useState, useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble'

/**
 * ChatPanel.jsx
 * ───────────────────────────────────────────────────────────────
 * Left-side interactive panel. Manages message list, input,
 * and streaming display.
 */

export default function ChatPanel({ 
  messages, 
  onSend, 
  isStreaming, 
  onPageClick,
  onClear,
  selectedAircraft
}) {
  const [input, setInput] = useState('')
  const scrollRef = useRef(null)

  // Auto-scroll to bottom on new tokens/messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isStreaming])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return
    onSend(input)
    setInput('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  return (
    <div className="flex flex-col h-full bg-navy-800 border-r border-slate-border w-[40%] shrink-0">
      {/* Messages Area */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-2 scroll-smooth"
      >
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-8 opacity-40">
            <div className="w-16 h-16 bg-navy-600 rounded-full flex items-center justify-center mb-4">
               <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h3 className="font-bold text-lg mb-2">AeroMind Intelligence</h3>
            <p className="text-sm">
              Ask any maintenance or operational query about the <span className="text-orange font-bold">{selectedAircraft?.name}</span>.
            </p>
            <div className="mt-6 text-[10px] space-y-1 font-mono uppercase tracking-widest">
              <div>System: Ready</div>
              <div>Buffer: Clean</div>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble 
            key={idx} 
            message={msg} 
            onPageClick={onPageClick}
          />
        ))}

        {isStreaming && messages[messages.length-1]?.role !== 'assistant' && (
          <div className="flex justify-start mb-4">
            <div className="bg-slate-panel border border-slate-border rounded-lg px-4 py-3">
              <div className="flex space-x-1">
                <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce"></div>
                <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.2s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.4s]"></div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-navy-800/80 backdrop-blur-md border-t border-slate-border">
        <div className="mb-2 flex justify-between items-center px-1">
          <span className="text-[10px] font-bold text-gray-500 tracking-widest uppercase">
            {selectedAircraft?.name} Terminal
          </span>
          <button 
            onClick={onClear}
            className="text-[9px] font-bold text-gray-500 hover:text-danger transition-colors uppercase tracking-tighter"
          >
            Clear Log
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="relative">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask maintenance query…"
            className="w-full bg-navy-700 border border-slate-border focus:border-orange rounded-xl pl-4 pr-12 py-3 text-sm resize-none h-24 focus:ring-0 transition-all outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className={`absolute bottom-3 right-3 p-2 rounded-lg transition-all ${
              input.trim() && !isStreaming 
                ? 'bg-orange text-white shadow-lg shadow-orange/20' 
                : 'bg-navy-600 text-gray-500 cursor-not-allowed'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>
        </form>
        <div className="mt-2 text-center">
          <p className="text-[9px] text-gray-600">
            AeroMind AI can make mistakes. Verify critical steps in the PDF manual.
          </p>
        </div>
      </div>
    </div>
  )
}
