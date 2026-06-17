import { useState, useEffect } from 'react'
import { fetchStats, type Stats } from '../api'
import { diceColor } from '../diceColors'

interface StatsTrackerProps {
  refreshKey: number
}

export function StatsTracker({ refreshKey }: StatsTrackerProps) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    fetchStats().then(setStats).catch(() => setStats(null))
  }, [refreshKey])

  if (!stats) return null

  const totalGoal = stats.types.reduce((sum, t) => sum + t.goal, 0)
  const overallPct = totalGoal > 0 ? Math.min(100, (stats.total / totalGoal) * 100) : 0

  return (
    <div className="absolute top-3 right-3 z-20 w-64 bg-gray-800/95 backdrop-blur rounded-lg shadow-xl border border-gray-700 text-white">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-3 py-2 border-b border-gray-700"
      >
        <span className="text-sm font-semibold">
          Dataset · {stats.total}/{totalGoal}
        </span>
        <span className="text-xs text-gray-400">{collapsed ? '▼' : '▲'}</span>
      </button>

      {!collapsed && (
        <div className="p-3 space-y-2 max-h-[70vh] overflow-y-auto">
          <div className="h-1.5 bg-gray-700 rounded overflow-hidden">
            <div className="h-full bg-green-500" style={{ width: `${overallPct}%` }} />
          </div>

          {stats.types.map((t) => {
            const pct = t.goal > 0 ? Math.min(100, (t.count / t.goal) * 100) : 0
            const color = diceColor(t.type)
            const isOpen = expanded === t.type
            return (
              <div key={t.type} className="text-xs">
                <button
                  onClick={() => setExpanded(isOpen ? null : t.type)}
                  className="w-full flex items-center gap-2 py-0.5"
                >
                  <span
                    className="inline-block w-3 h-3 rounded-sm shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  <span className="font-semibold w-9 text-left">{t.type}</span>
                  <div className="flex-1 h-2 bg-gray-700 rounded overflow-hidden">
                    <div
                      className="h-full"
                      style={{ width: `${pct}%`, backgroundColor: color }}
                    />
                  </div>
                  <span className="tabular-nums text-gray-300 w-12 text-right">
                    {t.count}/{t.goal}
                  </span>
                </button>
                <div className="flex justify-between pl-5 text-[10px] text-gray-500">
                  <span>
                    faces {t.faces_covered}/{t.faces_total}
                    {t.faces_complete > 0 && (
                      <span className="text-green-400"> · {t.faces_complete} done</span>
                    )}
                  </span>
                  <span>{isOpen ? 'hide' : 'values'}</span>
                </div>

                {isOpen && (
                  <div className="grid grid-cols-5 gap-1 pl-5 mt-1 mb-1">
                    {Object.entries(t.values).map(([face, count]) => {
                      const full = count >= stats.per_face_goal
                      return (
                        <div
                          key={face}
                          title={`${t.type} = ${face}: ${count}/${stats.per_face_goal}`}
                          className={`text-center rounded px-0.5 py-0.5 tabular-nums ${
                            count === 0
                              ? 'bg-gray-700/50 text-gray-500'
                              : full
                              ? 'bg-green-600/40 text-green-300'
                              : 'bg-gray-700 text-gray-200'
                          }`}
                        >
                          <div className="text-[9px] leading-tight opacity-70">{face}</div>
                          <div className="text-[10px] leading-tight font-semibold">{count}</div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
