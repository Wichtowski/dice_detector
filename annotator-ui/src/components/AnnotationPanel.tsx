import type { Annotation, Config } from '../types'
 
interface Props {
  annotation: Annotation
  config: Config
  onUpdate: (updates: Partial<Annotation>) => void
}
 
export function AnnotationPanel({ annotation, config, onUpdate }: Props) {
  return (
    <div className="p-4 border-t border-gray-700 space-y-3">
      <h3 className="font-semibold text-sm text-gray-400">Selected Annotation</h3>
 
      <div>
        <label className="block text-xs text-gray-500 mb-1">Dice Type</label>
        <select
          value={annotation.dice_type}
          onChange={(e) => onUpdate({ dice_type: e.target.value })}
          className="w-full bg-gray-700 rounded p-2 text-sm"
        >
          {config.dice_types.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
 
      <div>
        <label className="block text-xs text-gray-500 mb-1">Value</label>
        <input
          type="number"
          value={annotation.value ?? ''}
          onChange={(e) => onUpdate({ value: e.target.value ? parseInt(e.target.value) : null })}
          className="w-full bg-gray-700 rounded p-2 text-sm"
          min={0}
          max={100}
        />
      </div>
 
      <div>
        <label className="block text-xs text-gray-500 mb-1">Orientation (°)</label>
        <input
          type="number"
          value={annotation.orientation_degrees ?? ''}
          onChange={(e) => onUpdate({ orientation_degrees: e.target.value ? parseFloat(e.target.value) : null })}
          className="w-full bg-gray-700 rounded p-2 text-sm"
          min={0}
          max={359}
          step={1}
        />
      </div>
 
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={annotation.ambiguous}
          onChange={(e) => onUpdate({ ambiguous: e.target.checked })}
          className="rounded"
        />
        <span>Ambiguous</span>
      </label>
 
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={annotation.has_6_9_marker ?? false}
          onChange={(e) => onUpdate({ has_6_9_marker: e.target.checked })}
          className="rounded"
        />
        <span>Has 6/9 marker</span>
      </label>
 
      {annotation.dice_type === 'D4' && (
        <div>
          <label className="block text-xs text-gray-500 mb-1">D4 Style</label>
          <select
            value={annotation.d4_style ?? ''}
            onChange={(e) => onUpdate({ d4_style: e.target.value || null })}
            className="w-full bg-gray-700 rounded p-2 text-sm"
          >
            <option value="">Unknown</option>
            {config.d4_styles.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}
 
      {annotation.dice_type === 'D20' && (
        <div>
          <label className="block text-xs text-gray-500 mb-1">Special Value</label>
          <select
            value={annotation.special_value ?? ''}
            onChange={(e) => onUpdate({ special_value: e.target.value || null })}
            className="w-full bg-gray-700 rounded p-2 text-sm"
          >
            <option value="">None</option>
            {config.special_values.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}
 
      <div className="text-xs text-gray-500 pt-2">
        BBox: {annotation.bbox.x}, {annotation.bbox.y} ({annotation.bbox.width}×{annotation.bbox.height})
      </div>
    </div>
  )
}
