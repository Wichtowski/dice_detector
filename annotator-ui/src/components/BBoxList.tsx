import type { Annotation } from '../types'
 
interface Props {
  annotations: Annotation[]
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  readOnly?: boolean
}
 
export function BBoxList({ annotations, selectedId, onSelect, onDelete, readOnly }: Props) {
  if (annotations.length === 0) {
    return (
      <div className="text-gray-500 text-sm">
        No annotations yet. Draw a box on the image.
      </div>
    )
  }
 
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-sm text-gray-400">
        Annotations ({annotations.length})
      </h3>
      {annotations.map((ann) => (
        <div
          key={ann.id}
          onClick={() => onSelect(ann.id)}
          className={`p-2 rounded cursor-pointer ${
            ann.id === selectedId
              ? 'bg-blue-600'
              : 'bg-gray-700 hover:bg-gray-600'
          }`}
        >
          <div className="flex justify-between items-center">
            <span className="font-medium">{ann.dice_type}</span>
            <span className="text-sm">= {ann.value ?? '?'}</span>
          </div>
          <div className="text-xs text-gray-400 flex justify-between mt-1">
            <span>{ann.bbox.width}×{ann.bbox.height}</span>
            {ann.ambiguous && <span className="text-yellow-400">⚠️</span>}
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete(ann.id)
            }}
            className="text-red-400 text-xs hover:text-red-300 mt-1"
            hidden={readOnly}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}
