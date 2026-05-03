import React from 'react'

/**
 * StatusBadge.jsx
 * ───────────────────────────────────────────────────────────────
 * Renders a stylized badge based on detected problem type.
 * Priority keywords: EMERGENCY, FAULT, PROCEDURE, SPEC, COMPONENT, SYSTEM.
 */

const BADGE_CONFIG = {
  emergency: { label: 'EMERGENCY', color: 'bg-danger text-white', icon: '⚠️' },
  fault:     { label: 'FAULT DIAGNOSIS', color: 'bg-danger text-white', icon: '🔧' },
  procedure: { label: 'PROCEDURE', color: 'bg-orange text-white', icon: '📋' },
  spec:      { label: 'SPECIFICATION', color: 'bg-purple-600 text-white', icon: '📊' },
  system:    { label: 'SYSTEM OVERVIEW', color: 'bg-success text-white', icon: '🏢' },
  component: { label: 'COMPONENT', color: 'bg-blue-600 text-white', icon: '📦' },
  default:   { label: 'MAINTENANCE', color: 'bg-gray-600 text-white', icon: '⚙️' }
}

export default function StatusBadge({ text }) {
  const detectType = (t) => {
    const lower = t.toLowerCase()
    if (lower.includes('emergency')) return 'emergency'
    if (lower.includes('fault') || lower.includes('error')) return 'fault'
    if (lower.includes('procedure') || lower.includes('step')) return 'procedure'
    if (lower.includes('spec') || lower.includes('limit')) return 'spec'
    if (lower.includes('system')) return 'system'
    if (lower.includes('component') || lower.includes('part')) return 'component'
    return 'default'
  }

  const type = detectType(text)
  const { label, color, icon } = BADGE_CONFIG[type]

  return (
    <div className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${color}`}>
      <span className="mr-1">{icon}</span>
      {label}
    </div>
  )
}
