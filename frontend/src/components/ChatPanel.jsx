import React, { useState, useRef, useEffect } from 'react'
import { Plane, ArrowDown, ArrowRight } from 'lucide-react'
import MessageBubble from './MessageBubble'
import AgentActivityHUD from './AgentActivityHUD'
import VoiceController from './VoiceController'

/**
 * ChatPanel.jsx
 * ───────────────────────────────────────────────────────────────
 * Left-side interactive intelligence panel:
 * - Live Agent Activity HUD
 * - Multimodal Message List with Intelligent Scroll Retention
 * - Floating Jump-to-Bottom Quick Action
 * - Tactical Voice Input
 * - Quick Action Defense Prompts
 */

export default function ChatPanel({
  messages,
  onSend,
  isStreaming,
  agentStatus,
  dagPlan,
  mathSteps,
  onPageClick,
  onClear,
  selectedAircraft,
  onOpenDocManager,
  onOpenInspector,
}) {
  const [input, setInput] = useState('')
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false)
  const scrollRef = useRef(null)
  const isNearBottomRef = useRef(true)

  const lastMsgContent =
    messages.length > 0 ? messages[messages.length - 1]?.content : ''

  // Track user scroll position
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    const isAtBottom = distanceFromBottom < 80
    isNearBottomRef.current = isAtBottom
    setUserHasScrolledUp(!isAtBottom)
  }

  // Auto-scroll ONLY when user has NOT scrolled up
  useEffect(() => {
    if (scrollRef.current && isNearBottomRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lastMsgContent, messages.length, agentStatus])

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      })
      isNearBottomRef.current = true
      setUserHasScrolledUp(false)
    }
  }

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!input.trim() || isStreaming) return
    isNearBottomRef.current = true
    setUserHasScrolledUp(false)
    onSend(input)
    setInput('')
    setTimeout(scrollToBottom, 50)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  const handleVoiceQuery = (voiceText) => {
    if (voiceText.trim() && !isStreaming) {
      isNearBottomRef.current = true
      setUserHasScrolledUp(false)
      onSend(voiceText)
      setTimeout(scrollToBottom, 50)
    }
  }

  const quickPrompts = [
    'Emergency engine relight checklist and cockpit switch sequence',
    'Calculate fuel endurance for 2400 kg with afterburner at 10000m',
    'Show cockpit hydraulic pressure gauges and landing gear indicators',
    'Calculate TAS for Mach 1.8 at 11000m altitude',
  ]

  return (
    <div className="flex flex-col h-full bg-navy-800 border-r border-slate-border w-[45%] shrink-0 relative">
      {/* Live Dynamic DAG HUD (Active when planning or streaming) */}
      <AgentActivityHUD
        agentStatus={agentStatus}
        isStreaming={isStreaming}
        dagPlan={dagPlan}
        mathSteps={mathSteps}
      />

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-2 relative"
      >
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-6 py-10 opacity-90">
            <div className="w-16 h-16 bg-navy-700/80 rounded-2xl flex items-center justify-center mb-4 border border-navy-600 shadow-xl">
              <Plane className="w-8 h-8 text-orange" />
            </div>
            <h3 className="font-bold text-base text-gray-100 mb-1">
              AeroMind Defense Intelligence Platform
            </h3>
            <p className="text-xs text-gray-400 max-w-sm mb-6 leading-relaxed">
              Tactical aerospace operations platform for flight systems, cockpit schematics,
              avionics calculations, and NATO checklist verification.
            </p>

            {/* Quick Action Prompt Chips */}
            <div className="w-full space-y-2 max-w-md">
              <div className="text-[10px] font-mono text-orange uppercase font-bold tracking-wider text-left mb-1">
                Suggested Tactical Inquiries:
              </div>
              {quickPrompts.map((qp, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    isNearBottomRef.current = true
                    setUserHasScrolledUp(false)
                    onSend(qp)
                    setTimeout(scrollToBottom, 50)
                  }}
                  aria-label={`Ask suggested inquiry: ${qp}`}
                  className="w-full text-left text-xs font-mono p-2.5 rounded-xl bg-navy-700/60 hover:bg-navy-600/80 border border-navy-600 hover:border-orange/60 text-gray-300 transition-all flex items-center justify-between group shadow-sm"
                >
                  <span className="truncate mr-2">› {qp}</span>
                  <span className="text-orange opacity-0 group-hover:opacity-100 transition-opacity">
                    ↵
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble
            key={idx}
            message={msg}
            onPageClick={onPageClick}
            onOpenInspector={onOpenInspector}
          />
        ))}

        {isStreaming && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="flex justify-start mb-4">
            <div className="bg-slate-panel border border-slate-border rounded-xl px-4 py-3 shadow-lg">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-orange rounded-full animate-ping"></div>
                <span className="text-xs font-mono text-gray-400">
                  Compiling tactical intelligence briefing…
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Floating Jump to Bottom Action Pill */}
      {userHasScrolledUp && (
        <button
          onClick={scrollToBottom}
          aria-label="Jump to latest message"
          className="absolute bottom-36 left-1/2 -translate-x-1/2 z-20 flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-navy-700/95 hover:bg-orange border border-orange/50 text-orange hover:text-white text-[11px] font-mono font-bold shadow-2xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          <ArrowDown className="w-3.5 h-3.5" />
          <span>Jump to Latest</span>
          {isStreaming && (
            <span className="w-1.5 h-1.5 rounded-full bg-orange animate-ping"></span>
          )}
        </button>
      )}

      {/* Input Bar Area */}
      <div className="p-4 bg-navy-800/90 backdrop-blur-md border-t border-slate-border shrink-0">
        <div className="mb-2 flex justify-between items-center px-1">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-medium text-gray-300">
              {selectedAircraft?.name ? `${selectedAircraft.name} manual` : 'Flight manual'}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            <button

              onClick={onOpenDocManager}
              aria-label="Add a manual to document repository"
              className="text-xs text-gray-400 hover:text-orange transition-colors flex items-center space-x-1"
            >
              <span>Add a manual</span>
            </button>
            <button
              onClick={onClear}
              aria-label="Clear chat log"
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              Clear chat
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="relative">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a procedure, a calculation, or a diagram..."
            className="w-full bg-navy-700/90 border border-slate-border focus:border-orange rounded-xl pl-4 pr-24 py-3 text-xs md:text-sm resize-none h-24 focus:ring-0 transition-all outline-none text-gray-100 placeholder-gray-500 font-sans"
          />

          {/* Action buttons inside textarea */}
          <div className="absolute bottom-3 right-3 flex items-center space-x-2">
            {/* Voice Input STT */}
            <VoiceController
              onVoiceQuery={handleVoiceQuery}
              onTranscript={(text) => setInput(text)}
              isStreaming={isStreaming}
            />

            {/* Send Button */}
            <button
              type="submit"
              disabled={!input.trim() || isStreaming}
              aria-label="Send message"
              className={`p-2 rounded-xl transition-all ${input.trim() && !isStreaming
                ? 'bg-orange hover:bg-orange-light text-white shadow-lg shadow-orange/30'
                : 'bg-navy-600 text-gray-500 cursor-not-allowed'
                }`}
            >
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        </form>

        <div className="mt-2 text-center">
          <p className="text-[11px] text-gray-500">
            Aeromind • Grounded in official flight manuals
          </p>
        </div>
      </div>
    </div>
  )
}
