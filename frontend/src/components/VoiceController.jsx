import React, { useState, useEffect, useRef } from 'react'
import { Mic, Volume2, Square } from 'lucide-react'

/**
 * VoiceController.jsx
 * ───────────────────────────────────────────────────────────────
 * Audio Communication Interface:
 * - Live Voice Streaming (STT directly streamed into textarea state)
 * - Auto-commits transcript on pause or manual stop
 * - Voice Output (TTS via Web Speech Synthesis)
 */

export default function VoiceController({ onVoiceQuery, onTranscript, isStreaming }) {
  const [isListening, setIsListening] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(true)
  const recognitionRef = useRef(null)
  const transcriptRef = useRef('')
  const onTranscriptRef = useRef(onTranscript)
  onTranscriptRef.current = onTranscript

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setSpeechSupported(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onstart = () => {
      setIsListening(true)
      transcriptRef.current = ''
    }

    recognition.onresult = (event) => {
      let finalTranscript = ''
      let interimTranscript = ''

      for (let i = 0; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        } else {
          interimTranscript += event.results[i][0].transcript
        }
      }

      const fullText = (finalTranscript + ' ' + interimTranscript).trim()
      transcriptRef.current = fullText

      // Live stream directly into chat input textarea!
      if (onTranscriptRef.current && fullText) {
        onTranscriptRef.current(fullText)
      }
    }

    recognition.onerror = (event) => {
      console.error('[VoiceController] STT Error:', event.error)
      if (event.error !== 'no-speech') {
        setIsListening(false)
      }
    }

    recognition.onend = () => {
      setIsListening(false)
      // Commit transcript if any was recorded
      const captured = transcriptRef.current.trim()
      if (captured && onTranscriptRef.current) {
        onTranscriptRef.current(captured)
      }
    }

    recognitionRef.current = recognition

    return () => {
      try {
        recognition.stop()
      } catch (e) {}
    }
  }, [])

  const toggleListening = () => {
    if (!speechSupported || isStreaming) return

    if (isListening) {
      try {
        recognitionRef.current?.stop()
      } catch (e) {}
      setIsListening(false)
      const captured = transcriptRef.current.trim()
      if (captured) {
        if (onTranscript) onTranscript(captured)
      }
    } else {
      transcriptRef.current = ''
      try {
        recognitionRef.current?.start()
        setIsListening(true)
      } catch (e) {
        console.error('[VoiceController] Start error:', e)
      }
    }
  }

  const handleSendTranscript = () => {
    const captured = transcriptRef.current.trim()
    if (captured && onVoiceQuery) {
      onVoiceQuery(captured)
      transcriptRef.current = ''
      setIsListening(false)
      try {
        recognitionRef.current?.stop()
      } catch (e) {}
    }
  }

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={toggleListening}
        disabled={isStreaming}
        aria-label={isListening ? 'Stop voice recording' : 'Start voice input'}
        className={`relative p-2 rounded-xl transition-all flex items-center justify-center ${
          isListening
            ? 'bg-danger text-white shadow-[0_0_15px_rgba(248,81,73,0.8)] animate-pulse'
            : 'bg-navy-700 hover:bg-navy-600 text-gray-300 hover:text-orange border border-navy-500'
        }`}
        title={isListening ? 'Stop voice recording' : 'Voice input'}
      >
        <Mic className="w-5 h-5" />
      </button>

      {/* Floating Status pill when speaking */}
      {isListening && (
        <div className="absolute bottom-full mb-3 right-0 w-72 bg-navy-800 border border-orange/60 rounded-xl p-3 shadow-2xl z-50 animate-in fade-in slide-in-from-bottom-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-mono text-orange font-bold uppercase tracking-wider flex items-center">
              <span className="w-2 h-2 rounded-full bg-danger animate-ping mr-1.5"></span>
              Listening...
            </span>
            <button
              onClick={handleSendTranscript}
              aria-label="Submit spoken query"
              className="text-[10px] font-mono bg-orange hover:bg-orange-light text-white px-2 py-0.5 rounded font-bold"
            >
              SEND ↵
            </button>
          </div>
          <p className="text-xs text-gray-300 font-sans italic bg-navy-900/80 p-2 rounded border border-navy-700 min-h-[32px] truncate">
            {transcriptRef.current || 'Speak now...'}
          </p>
        </div>
      )}
    </div>
  )
}

/**
 * TacticalTTSButton: Reads response aloud using Lucide Volume2 icon.
 */
export function TacticalTTSButton({ text }) {
  const [isPlaying, setIsPlaying] = useState(false)

  const handleSpeak = () => {
    if (!('speechSynthesis' in window)) return

    if (isPlaying) {
      window.speechSynthesis.cancel()
      setIsPlaying(false)
      return
    }

    window.speechSynthesis.cancel()
    const cleanText = text
      .replace(/REFERENCE:[^\n]+/g, '')
      .replace(/###/g, '')
      .replace(/[*_#]/g, '')
      .trim()

    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.rate = 1.05
    utterance.pitch = 0.95

    utterance.onstart = () => setIsPlaying(true)
    utterance.onend = () => setIsPlaying(false)
    utterance.onerror = () => setIsPlaying(false)

    window.speechSynthesis.speak(utterance)
  }

  return (
    <button
      onClick={handleSpeak}
      aria-label={isPlaying ? 'Stop listening' : 'Listen to response'}
      className={`text-xs px-2.5 py-1 rounded border transition-all flex items-center space-x-1.5 ${
        isPlaying
          ? 'bg-orange text-white border-orange shadow-[0_0_8px_rgba(232,120,10,0.5)]'
          : 'bg-navy-700/80 hover:bg-navy-600 text-gray-300 hover:text-orange border-navy-500'
      }`}
      title={isPlaying ? 'Stop audio' : 'Listen to response'}
    >
      {isPlaying ? (
        <Square className="w-3.5 h-3.5 fill-current" />
      ) : (
        <Volume2 className="w-3.5 h-3.5" />
      )}
      <span>{isPlaying ? 'Stop' : 'Listen'}</span>
    </button>
  )
}
