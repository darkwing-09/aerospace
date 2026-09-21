import React, { useState, useEffect } from 'react'
import { Folder, Settings } from 'lucide-react'
import AircraftSelector from './AircraftSelector'

/**
 * TopBar.jsx
 * ───────────────────────────────────────────────────────────────
 * Main application navigation:
 * - Product branding & manual selector
 * - System ready status
 * - Manuals repository launcher
 * - Developer settings menu
 */

export default function TopBar({
  aircraftList,
  selectedAircraft,
  onSelectAircraft,
  onOpenDocManager,
  onOpenInspector,
}) {
  const [modelStatus, setModelStatus] = useState({ loaded: false, loading: false })

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch('/api/model/status')
        if (res.ok) {
          const data = await res.json()
          setModelStatus(data)
        }
      } catch (e) {}
    }

    checkStatus()
    const interval = setInterval(checkStatus, 4000)
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = () => {
    if (modelStatus.loaded) return 'bg-success shadow-[0_0_8px_rgba(63,185,80,0.6)]'
    if (modelStatus.loading) return 'bg-warning animate-pulse'
    return 'bg-danger'
  }

  const getStatusText = () => {
    if (modelStatus.loaded) return 'Ready'
    if (modelStatus.loading) return 'Starting up'
    return 'Offline'
  }

  return (
    <header className="h-16 border-b border-slate-border bg-navy-800 flex items-center justify-between px-6 shrink-0 z-40">
      {/* Left: Brand & Aircraft Selector */}
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 bg-orange flex items-center justify-center rounded-lg shadow-lg shadow-orange/30 transform rotate-45">
            <span className="text-white font-black text-xl -rotate-45">A</span>
          </div>
          <div>
            <div className="font-bold text-base tracking-tight leading-none text-gray-100 flex items-center space-x-1.5">
              <span>Aeromind</span>
            </div>
            <div className="text-[11px] text-gray-400 leading-none mt-1">
              Flight manual assistant
            </div>
          </div>
        </div>

        <AircraftSelector
          aircraftList={aircraftList}
          selected={selectedAircraft}
          onSelect={onSelectAircraft}
        />
      </div>

      {/* Right: Actions & Status */}
      <div className="flex items-center space-x-3">
        {/* Manuals Repository Launcher */}
        <button
          onClick={onOpenDocManager}
          aria-label="Open manuals repository"
          className="hidden sm:flex items-center space-x-1.5 bg-navy-700 hover:bg-navy-600 px-3 py-1.5 rounded-lg border border-navy-500 text-xs text-gray-300 hover:text-orange transition-all"
        >
          <Folder className="w-4 h-4 text-orange" />
          <span>Manuals</span>
        </button>

        {/* Settings / Developer Menu */}
        <button
          onClick={onOpenInspector}
          aria-label="Settings and developer traces"
          title="Settings & Developer Traces"
          className="hidden md:flex items-center space-x-1.5 bg-navy-700/60 hover:bg-navy-700 px-2.5 py-1.5 rounded-lg border border-navy-600 text-xs text-gray-400 hover:text-gray-200 transition-all"
        >
          <Settings className="w-4 h-4 text-gray-400" />
          <span>Settings</span>
        </button>

        {/* Status Pill */}
        <div className="flex items-center space-x-2 bg-navy-700/60 px-3 py-1.5 rounded-full border border-navy-600">
          <div className={`w-2 h-2 rounded-full ${getStatusColor()}`}></div>
          <span className="text-xs font-medium text-gray-300">
            {getStatusText()}
          </span>
        </div>
      </div>
    </header>
  )
}
