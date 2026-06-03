import type { ImageListItem } from '../types'
 
interface Props {
  images: ImageListItem[]
  currentId: string | null
  onSelect: (id: string) => void
  onPrev: () => void
  onNext: () => void
}
 
export function ImageNavigator({ images, currentId, onSelect, onPrev, onNext }: Props) {
  return (
    <div className="p-4 space-y-3">
      <div>
        <label className="block text-xs text-gray-500 mb-1">Image ({images.length})</label>
        <select
          value={currentId || ''}
          onChange={(e) => onSelect(e.target.value)}
          className="w-full bg-gray-700 rounded p-2 text-sm"
        >
          <option value="">Select...</option>
          {images.map((img) => (
            <option key={img.id} value={img.id}>
              {img.annotated ? '✓ ' : ''}{img.name}
            </option>
          ))}
        </select>
      </div>
 
      <div className="flex gap-2">
        <button
          onClick={onPrev}
          className="flex-1 bg-gray-700 hover:bg-gray-600 rounded p-2 text-sm"
        >
          ← Prev
        </button>
        <button
          onClick={onNext}
          className="flex-1 bg-gray-700 hover:bg-gray-600 rounded p-2 text-sm"
        >
          Next →
        </button>
      </div>
 
      <p className="text-xs text-gray-500">Use arrow keys to navigate</p>
    </div>
  )
}
