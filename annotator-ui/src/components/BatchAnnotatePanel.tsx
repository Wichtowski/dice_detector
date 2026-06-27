import type { BatchType } from '../types'
import { diceColor } from '../diceColors'
import { DICE_VALUE_RANGES } from './AnnotatorCanvas'

interface Props {
  types: BatchType[]
  source: string | null
  diceType: string
  value: number | null
  hasTemplate: boolean
  hasImage: boolean
  canGoBack: boolean
  saving: boolean
  onSelectType: (bt: BatchType) => void
  onChangeType: () => void
  onSetValue: (v: number | null) => void
  onStampNext: () => void
  onSkip: () => void
  onBack: () => void
  onClearTemplate: () => void
}

export function BatchAnnotatePanel({
  types,
  source,
  diceType,
  value,
  hasTemplate,
  hasImage,
  canGoBack,
  saving,
  onSelectType,
  onChangeType,
  onSetValue,
  onStampNext,
  onSkip,
  onBack,
  onClearTemplate,
}: Props) {
  // Dice-type picker (shown until a type/folder is chosen).
  if (!source) {
    return (
      <div className="p-3 bg-emerald-950/50 border border-emerald-700 rounded space-y-2">
        <p className="font-semibold text-emerald-300 text-sm">Pick a dice type</p>
        {types.length === 0 ? (
          <p className="text-xs text-gray-400">
            No batch folders found under <code>data/web/batch/</code>. Add per-type
            folders like <code>d4</code>, <code>d6</code>, …
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {types.map((t) => {
              const remaining = t.total - t.annotated
              return (
                <button
                  key={t.source}
                  onClick={() => onSelectType(t)}
                  className="flex flex-col items-start rounded border border-gray-600 hover:border-emerald-500 bg-gray-800 px-2 py-1.5"
                >
                  <span className="font-bold" style={{ color: diceColor(t.dice_type) }}>
                    {t.dice_type}
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {remaining} left / {t.total}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  const current = types.find((t) => t.source === source)
  const remaining = current ? current.total - current.annotated : 0

  return (
    <div className="p-3 bg-emerald-950/50 border border-emerald-700 rounded space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold" style={{ color: diceColor(diceType) }}>
          {diceType}
        </span>
        <span className="text-gray-300">
          {remaining} left{current ? ` / ${current.total}` : ''}
        </span>
      </div>

      {!hasImage ? (
        <p className="text-xs text-emerald-400">All images stamped for {diceType}. 🎉</p>
      ) : !hasTemplate ? (
        <p className="text-xs text-gray-300">
          Draw a box around the die. It becomes a template reused on every next image.
        </p>
      ) : (
        <p className="text-xs text-gray-400">
          Drag/resize to adjust. Press <kbd className="bg-gray-700 px-1 rounded">Enter</kbd> to
          save &amp; advance.
        </p>
      )}

      {hasImage && hasTemplate && (
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">Value</p>
          <div className="grid grid-cols-5 gap-1">
            {(DICE_VALUE_RANGES[diceType] || []).map((v) => (
              <button
                key={v}
                onClick={() => onSetValue(value === v ? null : v)}
                className={`rounded px-1.5 py-1 text-xs font-semibold ${
                  value === v
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
                }`}
              >
                {v}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">Value carries to the next image.</p>
        </div>
      )}

      <button
        onClick={onStampNext}
        disabled={saving || !hasTemplate || !hasImage}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 rounded p-2 font-semibold text-sm"
      >
        {saving ? 'Saving...' : 'Save & Next (Enter)'}
      </button>

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={onBack}
          disabled={!canGoBack}
          className="bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 disabled:text-gray-500 rounded p-1.5 text-xs font-semibold"
        >
          ← Back
        </button>
        <button
          onClick={onSkip}
          disabled={!hasImage}
          className="bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 rounded p-1.5 text-xs font-semibold"
        >
          Skip →
        </button>
        <button
          onClick={onClearTemplate}
          disabled={!hasTemplate}
          className="bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 rounded p-1.5 text-xs font-semibold"
        >
          Clear box
        </button>
        <button
          onClick={onChangeType}
          className="bg-gray-600 hover:bg-gray-500 rounded p-1.5 text-xs font-semibold"
        >
          Change type
        </button>
      </div>
    </div>
  )
}
