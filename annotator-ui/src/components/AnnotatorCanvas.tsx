import { useState, useRef, useEffect, useCallback } from 'react'
import { Stage, Layer, Image, Rect, Transformer, Group, Label, Tag, Text } from 'react-konva'
import type { KonvaEventObject } from 'konva/lib/Node'
import type Konva from 'konva'
import type { Annotation, BBox, Config } from '../types'
import { diceColor, textColor } from '../diceColors'

const DICE_VALUE_RANGES: Record<string, number[]> = {
  D4: [1, 2, 3, 4],
  D6: [1, 2, 3, 4, 5, 6],
  D8: [1, 2, 3, 4, 5, 6, 7, 8],
  D10: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  D12: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  D20: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
  D100: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
}

interface Props {
  imageUrl: string
  imageWidth: number
  imageHeight: number
  annotations: Annotation[]
  selectedId: string | null
  config: Config | null
  confirmedIds?: Set<string>
  verifying?: boolean
  onSelect: (id: string | null) => void
  onAdd: (bbox: BBox, diceType: string, value: number | null) => void
  onUpdate: (id: string, updates: Partial<Annotation>) => void
  onConfirmDie?: (id: string) => void
  readOnly?: boolean
}
 
export function AnnotatorCanvas({
  imageUrl,
  imageWidth,
  imageHeight,
  annotations,
  selectedId,
  config,
  confirmedIds,
  verifying,
  onSelect,
  onAdd,
  onUpdate,
  onConfirmDie,
  readOnly,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 })
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState({ x: 0, y: 0 })
  const [drawRect, setDrawRect] = useState<BBox | null>(null)
  const transformerRef = useRef<Konva.Transformer>(null)
  const selectedRef = useRef<Konva.Rect>(null)

  // Zoom/pan state
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [panStart, setPanStart] = useState({ x: 0, y: 0 })
  // New bbox popup state
  const [pendingBBox, setPendingBBox] = useState<BBox | null>(null)
  const [pendingType, setPendingType] = useState('D6')
  const [pendingValue, setPendingValue] = useState<number | null>(null)
 
  useEffect(() => {
    const img = new window.Image()
    img.src = imageUrl
    img.onload = () => setImage(img)
    // Reset zoom/pan on image change
    setZoom(1)
    setOffset({ x: 0, y: 0 })
  }, [imageUrl])
 
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        setContainerSize({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight,
        })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])
 
  useEffect(() => {
    if (selectedId && transformerRef.current && selectedRef.current) {
      transformerRef.current.nodes([selectedRef.current])
      transformerRef.current.getLayer()?.batchDraw()
    }
  }, [selectedId, annotations])

  const baseScale = Math.min(
    containerSize.width / imageWidth,
    containerSize.height / imageHeight,
    1
  )
  const scale = baseScale * zoom

  const selectedAnnotation = annotations.find((a) => a.id === selectedId) || null
 
  const toImageCoords = (stageX: number, stageY: number) => ({
    x: Math.round((stageX - offset.x) / scale),
    y: Math.round((stageY - offset.y) / scale),
  })

  // Ctrl+scroll: zoom to cursor
  const handleWheel = useCallback((e: KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault()
    if (!e.evt.ctrlKey) return

    const stage = stageRef.current
    if (!stage) return

    const pointer = stage.getPointerPosition()
    if (!pointer) return

    const direction = e.evt.deltaY < 0 ? 1 : -1
    const factor = 1.15
    const newZoom = Math.max(0.5, Math.min(20, zoom * (direction > 0 ? factor : 1 / factor)))

    // Zoom toward cursor: adjust offset so the point under cursor stays fixed
    const mouseX = pointer.x
    const mouseY = pointer.y
    const newOffset = {
      x: mouseX - ((mouseX - offset.x) / zoom) * newZoom,
      y: mouseY - ((mouseY - offset.y) / zoom) * newZoom,
    }

    setZoom(newZoom)
    setOffset(newOffset)
  }, [zoom, offset])
 
  const handleMouseDown = (e: KonvaEventObject<MouseEvent>) => {
    // Middle mouse or Ctrl+left: pan
    if (e.evt.button === 1 || (e.evt.button === 0 && e.evt.ctrlKey)) {
      e.evt.preventDefault()
      setIsPanning(true)
      setPanStart({ x: e.evt.clientX - offset.x, y: e.evt.clientY - offset.y })
      return
    }

    if (readOnly || pendingBBox) return
    if (e.target !== e.target.getStage()?.findOne('Image')) {
      return
    }
    const pos = e.target.getStage()?.getPointerPosition()
    if (!pos) return
 
    onSelect(null)
    setIsDrawing(true)
    setDrawStart(toImageCoords(pos.x, pos.y))
    setDrawRect(null)
  }
 
  const handleMouseMove = (e: KonvaEventObject<MouseEvent>) => {
    if (isPanning) {
      setOffset({
        x: e.evt.clientX - panStart.x,
        y: e.evt.clientY - panStart.y,
      })
      return
    }

    if (!isDrawing) return
    const pos = e.target.getStage()?.getPointerPosition()
    if (!pos) return
 
    const end = toImageCoords(pos.x, pos.y)
    const x = Math.min(drawStart.x, end.x)
    const y = Math.min(drawStart.y, end.y)
    const width = Math.abs(end.x - drawStart.x)
    const height = Math.abs(end.y - drawStart.y)
 
    setDrawRect({ x, y, width, height })
  }
 
  const handleMouseUp = () => {
    if (isPanning) {
      setIsPanning(false)
      return
    }
    if (isDrawing && drawRect && drawRect.width > 10 && drawRect.height > 10) {
      setPendingBBox(drawRect)
      setPendingType(config?.dice_types[0] || 'D6')
      setPendingValue(null)
    }
    setIsDrawing(false)
    setDrawRect(null)
  }

  const confirmPending = () => {
    if (!pendingBBox) return
    onAdd(pendingBBox, pendingType, pendingValue)
    setPendingBBox(null)
  }

  const cancelPending = () => {
    setPendingBBox(null)
  }
 
  const handleRectClick = (id: string, e: KonvaEventObject<MouseEvent | TouchEvent>) => {
    e.cancelBubble = true
    onSelect(id)
  }
 
  const handleDragEnd = (id: string, e: KonvaEventObject<DragEvent>) => {
    const node = e.target
    onUpdate(id, {
      bbox: {
        x: Math.round((node.x() - offset.x) / scale),
        y: Math.round((node.y() - offset.y) / scale),
        width: Math.round(node.width() / scale),
        height: Math.round(node.height() / scale),
      },
    })
  }
 
  const handleTransformEnd = (id: string, e: KonvaEventObject<Event>) => {
    const node = e.target as Konva.Rect
    const scaleX = node.scaleX()
    const scaleY = node.scaleY()
    node.scaleX(1)
    node.scaleY(1)
 
    onUpdate(id, {
      bbox: {
        x: Math.round((node.x() - offset.x) / scale),
        y: Math.round((node.y() - offset.y) / scale),
        width: Math.round((node.width() * scaleX) / scale),
        height: Math.round((node.height() * scaleY) / scale),
      },
    })
  }
 
  return (
    <div ref={containerRef} className="w-full h-full relative">
      <Stage
        ref={stageRef}
        width={containerSize.width}
        height={containerSize.height}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <Layer>
          {image && (
            <Image
              image={image}
              x={offset.x}
              y={offset.y}
              width={imageWidth * scale}
              height={imageHeight * scale}
            />
          )}
 
          {annotations.map((ann) => {
            const isSelected = ann.id === selectedId
            const isConfirmed = confirmedIds?.has(ann.id) ?? false
            const color = diceColor(ann.dice_type)
            const boxX = ann.bbox.x * scale + offset.x
            const boxY = ann.bbox.y * scale + offset.y
            const boxW = ann.bbox.width * scale
            const labelText = `${ann.dice_type} ${ann.value ?? '?'}`
            const labelY = boxY - 22 >= 0 ? boxY - 22 : boxY + 2
            return (
              <Group key={ann.id}>
                <Rect
                  ref={isSelected ? selectedRef : undefined}
                  x={boxX}
                  y={boxY}
                  width={boxW}
                  height={ann.bbox.height * scale}
                  stroke={isConfirmed ? '#16a34a' : color}
                  strokeWidth={isSelected ? 4 : 2}
                  fill={isSelected ? `${color}40` : `${color}1a`}
                  draggable={!readOnly}
                  onClick={(e) => handleRectClick(ann.id, e)}
                  onTap={(e) => handleRectClick(ann.id, e)}
                  onDragEnd={(e) => handleDragEnd(ann.id, e)}
                  onTransformEnd={(e) => handleTransformEnd(ann.id, e)}
                />
                <Label x={boxX} y={labelY} listening={false}>
                  <Tag fill={color} cornerRadius={2} />
                  <Text
                    text={labelText}
                    fontSize={13}
                    fontStyle="bold"
                    padding={3}
                    fill={textColor(color)}
                  />
                </Label>
                {isConfirmed && (
                  <Label x={boxX + boxW - 18} y={boxY + 2} listening={false}>
                    <Tag fill="#16a34a" cornerRadius={8} />
                    <Text text="✓" fontSize={13} fontStyle="bold" padding={2} fill="#ffffff" />
                  </Label>
                )}
              </Group>
            )
          })}
 
          {(drawRect || pendingBBox) && (
            <Rect
              x={((drawRect || pendingBBox)!.x * scale + offset.x)}
              y={((drawRect || pendingBBox)!.y * scale + offset.y)}
              width={(drawRect || pendingBBox)!.width * scale}
              height={(drawRect || pendingBBox)!.height * scale}
              stroke="#f59e0b"
              strokeWidth={2}
              dash={[5, 5]}
            />
          )}
 
          {selectedId && !readOnly && (
            <Transformer
              ref={transformerRef}
              rotateEnabled={false}
              keepRatio={false}
              anchorSize={14}
              anchorCornerRadius={0}
              anchorStroke="#3b82f6"
              anchorFill="transparent"
              padding={8}
              anchorStyleFunc={(anchor) => {
                anchor.stroke('#3b82f6')
                anchor.strokeWidth(2)
                anchor.fill('rgba(59,130,246,0.15)')
                anchor.width(14)
                anchor.height(14)
                anchor.offsetX(7)
                anchor.offsetY(7)
              }}
              borderEnabled={false}
              boundBoxFunc={(oldBox, newBox) => {
                if (newBox.width < 10 || newBox.height < 10) return oldBox
                return newBox
              }}
            />
          )}
        </Layer>
      </Stage>

      {pendingBBox && (
        <div
          className="absolute z-50 bg-gray-800 border border-gray-600 rounded-lg shadow-xl p-3 space-y-2"
          style={{
            left: Math.min(
              pendingBBox.x * scale + offset.x + pendingBBox.width * scale / 2,
              containerSize.width - 200
            ),
            top: Math.min(
              pendingBBox.y * scale + offset.y + pendingBBox.height * scale + 8,
              containerSize.height - 140
            ),
          }}
        >
          <div className="flex gap-2">
            <select
              value={pendingType}
              onChange={(e) => {
                setPendingType(e.target.value)
                setPendingValue(null)
              }}
              className="bg-gray-700 text-white text-sm rounded px-2 py-1"
              autoFocus
            >
              {(config?.dice_types || ['D4', 'D6', 'D8', 'D10', 'D12', 'D20', 'D100']).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select
              value={pendingValue ?? ''}
              onChange={(e) => setPendingValue(e.target.value ? parseInt(e.target.value) : null)}
              className="bg-gray-700 text-white text-sm rounded px-2 py-1"
            >
              <option value="">Value</option>
              {(DICE_VALUE_RANGES[pendingType] || []).map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={confirmPending}
              className="flex-1 bg-green-600 hover:bg-green-500 text-white text-sm rounded px-3 py-1 font-semibold"
            >
              Add
            </button>
            <button
              onClick={cancelPending}
              className="bg-gray-600 hover:bg-gray-500 text-white text-sm rounded px-3 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {verifying && selectedAnnotation && !confirmedIds?.has(selectedAnnotation.id) && (
        <div
          className="absolute z-50"
          style={{
            left: Math.min(
              Math.max(selectedAnnotation.bbox.x * scale + offset.x, 0),
              containerSize.width - 160
            ),
            top: Math.min(
              selectedAnnotation.bbox.y * scale + offset.y +
                selectedAnnotation.bbox.height * scale + 8,
              containerSize.height - 48
            ),
          }}
        >
          <button
            onClick={() => onConfirmDie?.(selectedAnnotation.id)}
            className="bg-green-600 hover:bg-green-500 text-white text-sm rounded px-4 py-1.5 font-semibold shadow-xl"
          >
            Confirm {selectedAnnotation.dice_type} {selectedAnnotation.value ?? '?'}
          </button>
        </div>
      )}
    </div>
  )
}
 