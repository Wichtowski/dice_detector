import { useRef, useState, useCallback, useEffect } from 'react'

interface CropModalProps {
  imageUrl: string
  imageWidth: number
  imageHeight: number
  busy?: boolean
  onConfirm: (crop: { x: number; y: number; size: number }) => void
  onCancel: () => void
}

export function CropModal({
  imageUrl,
  imageWidth,
  imageHeight,
  busy,
  onConfirm,
  onCancel,
}: CropModalProps) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [scale, setScale] = useState(1)

  const initialSize = Math.min(imageWidth, imageHeight)
  const [crop, setCrop] = useState({
    x: Math.round((imageWidth - initialSize) / 2),
    y: Math.round((imageHeight - initialSize) / 2),
    size: initialSize,
  })

  // Keep display scale (rendered px / original px) in sync with layout.
  useEffect(() => {
    const el = imgRef.current
    if (!el) return
    const update = () => {
      if (el.clientWidth > 0) setScale(el.clientWidth / imageWidth)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [imageWidth])

  const startDrag = useCallback(
    (e: React.PointerEvent, mode: 'move' | 'resize') => {
      e.preventDefault()
      e.stopPropagation()
      const el = imgRef.current
      const s = el && el.clientWidth > 0 ? el.clientWidth / imageWidth : scale
      const startX = e.clientX
      const startY = e.clientY
      const start = { ...crop }

      const onMove = (ev: PointerEvent) => {
        const dx = (ev.clientX - startX) / s
        const dy = (ev.clientY - startY) / s
        if (mode === 'move') {
          const nx = Math.max(0, Math.min(imageWidth - start.size, start.x + dx))
          const ny = Math.max(0, Math.min(imageHeight - start.size, start.y + dy))
          setCrop({ x: Math.round(nx), y: Math.round(ny), size: start.size })
        } else {
          const maxSize = Math.min(imageWidth - start.x, imageHeight - start.y)
          const newSize = Math.max(20, Math.min(maxSize, start.size + Math.max(dx, dy)))
          setCrop({ x: start.x, y: start.y, size: Math.round(newSize) })
        }
      }
      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [crop, scale, imageWidth, imageHeight]
  )

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center p-4">
      <p className="text-white text-sm mb-2">
        Drag the box to move it, drag the corner to resize. Crop is locked to a square.
        Existing annotations are kept and remapped (boxes outside the crop are dropped).
      </p>
      <div className="relative inline-block" style={{ lineHeight: 0 }}>
        <img
          ref={imgRef}
          src={imageUrl}
          alt="crop"
          draggable={false}
          className="block max-h-[78vh] max-w-[90vw] select-none"
          onLoad={() => {
            const el = imgRef.current
            if (el && el.clientWidth > 0) setScale(el.clientWidth / imageWidth)
          }}
        />
        <div
          className="absolute border-2 border-blue-400 cursor-move"
          style={{
            left: crop.x * scale,
            top: crop.y * scale,
            width: crop.size * scale,
            height: crop.size * scale,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
          }}
          onPointerDown={(e) => startDrag(e, 'move')}
        >
          <div
            className="absolute w-4 h-4 bg-blue-400 rounded-sm cursor-nwse-resize"
            style={{ right: -8, bottom: -8 }}
            onPointerDown={(e) => startDrag(e, 'resize')}
          />
        </div>
      </div>
      <p className="text-xs text-gray-400 mt-2">
        {crop.size}×{crop.size}px (from {imageWidth}×{imageHeight})
      </p>
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => onConfirm(crop)}
          disabled={busy}
          className="bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded px-4 py-2 text-sm font-semibold"
        >
          {busy ? 'Cropping...' : 'Crop'}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 rounded px-4 py-2 text-sm font-semibold"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
