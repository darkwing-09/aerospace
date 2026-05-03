import React, { useState, useEffect } from 'react'
import AircraftSelector from './AircraftSelector'

/**
 * TopBar.jsx
 * ───────────────────────────────────────────────────────────────
 * Main application header. Displays logo, aircraft selector,
 * and live model load status indicator.
 */

export default function TopBar({ 
  aircraftList, 
  selectedAircraft, 
  onSelectAircraft 
}) {
  const [modelStatus, setModelStatus] = useState({ loaded: false, loading: false })

  // Poll model status every 3s
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
    const interval = setInterval(checkStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = () => {
    if (modelStatus.loaded) return 'bg-success shadow-[0_0_8px_rgba(63,185,80,0.5)]'
    if (modelStatus.loading) return 'bg-warning animate-pulse'
    return 'bg-danger'
  }

  const getStatusText = () => {
    if (modelStatus.loaded) return 'MODEL READY'
    if (modelStatus.loading) return 'LOADING MODEL…'
    return 'MODEL OFFLINE'
  }

  return (
    <header className="h-16 border-b border-slate-border bg-navy-800 flex items-center justify-between px-6 shrink-0 z-40">
      <div className="flex items-center space-x-8">
        {/* LOGO */}
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 bg-orange flex items-center justify-center rounded transform rotate-45">
            <span className="text-white font-black text-xl -rotate-45">A</span>
          </div>
          <div>
            <div className="font-black text-lg tracking-tighter leading-none">AEROMIND</div>
            <div className="text-[10px] text-orange font-bold tracking-widest leading-none">AI AVIATION PLATFORM</div>
          </div>
        </div>

        {/* SELECTOR */}
        <AircraftSelector 
          aircraftList={aircraftList}
          selected={selectedAircraft}
          onSelect={onSelectAircraft}
        />
      </div>

      <div className="flex items-center space-x-6">
        {/* MODEL STATUS */}
        <div className="flex items-center space-x-2 bg-navy-700/50 px-3 py-1.5 rounded-full border border-navy-500">
          <div className={`w-2 h-2 rounded-full ${getStatusColor()}`}></div>
          <span className="text-[10px] font-bold text-gray-300 tracking-wider">
            {getStatusText()}
          </span>
        </div>

        {/* TECH DEBT / INFO */}
        <div className="text-right hidden md:block">
          <div className="text-[10px] text-gray-500 font-mono">NODE: LOCAL_LLM_01</div>
          <div className="text-[10px] text-gray-500 font-mono uppercase">Region: IN-WEST-01</div>
        </div>
      </div>
    </header>
  )
}
