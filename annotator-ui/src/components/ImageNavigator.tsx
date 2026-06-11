import type { ImageListItem } from '../types'
 
interface Props {
  images: ImageListItem[]
  currentId: string | null
  onSelect: (id: string) => void
  onPrev: () => void
  onNext: () => void
  page: number
  totalPages: number
  total: number
  onPageChange: (page: number) => void
  readOnly: boolean
}
 
export function ImageNavigator({
  images, currentId, onSelect, onPrev, onNext,
  page, totalPages, total, onPageChange, readOnly,
}: Props) {
  return (
    <div className="p-4 space-y-3">
      {readOnly && (
        <div className="text-xs text-yellow-400 bg-yellow-900/30 rounded px-2 py-1 text-center">
          Read-only — synthetic dataset
        </div>
      )}

      <div>
        <label className="block text-xs text-gray-500 mb-1">
          Image ({total} total)
        </label>
        <select
          value={currentId || ''}
          onChange={(e) => onSelect(e.target.value)}
          className="w-full bg-gray-700 rounded p-2 text-sm"
        >
          <option value="">Select...</option>
          {images.map((img) => (
            <option key={img.id} value={img.id}>
              {img.annotated ? '✓ ' : ''}{img.read_only ? '🔒 ' : ''}{img.name}
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

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-2">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:hover:bg-gray-700 rounded px-2 py-1 text-xs"
          >
            ‹
          </button>
          <span className="text-xs text-gray-400">
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:hover:bg-gray-700 rounded px-2 py-1 text-xs"
          >
            ›
          </button>
        </div>
      )}
 
      <p className="text-xs text-gray-500">Use arrow keys to navigate</p>
    </div>
  )
}
