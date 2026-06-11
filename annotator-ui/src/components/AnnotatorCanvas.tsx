import { useState, useRef, useEffect } from 'react'
import { Stage, Layer, Image, Rect, Transformer } from 'react-konva'
import type { KonvaEventObject } from 'konva/lib/Node'
import type Konva from 'konva'
import type { Annotation, BBox } from '../types'
 
interface Props {
  imageUrl: string
  imageWidth: number
  imageHeight: number
  annotations: Annotation[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  onAdd: (bbox: BBox) => void
  onUpdate: (id: string, updates: Partial<Annotation>) => void
  readOnly?: boolean
}
 
export function AnnotatorCanvas({
  imageUrl,
  imageWidth,
  imageHeight,
  annotations,
  selectedId,
  onSelect,
  onAdd,
  onUpdate,
  readOnly,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 })
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState({ x: 0, y: 0 })
  const [drawRect, setDrawRect] = useState<BBox | null>(null)
  const transformerRef = useRef<Konva.Transformer>(null)
  const selectedRef = useRef<Konva.Rect>(null)
 
  useEffect(() => {
    const img = new window.Image()
    img.src = imageUrl
    img.onload = () => setImage(img)
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
 
  const scale = Math.min(
    containerSize.width / imageWidth,
    containerSize.height / imageHeight,
    1
  )
 
  const toImageCoords = (x: number, y: number) => ({
    x: Math.round(x / scale),
    y: Math.round(y / scale),
  })
 
  const handleMouseDown = (e: KonvaEventObject<MouseEvent>) => {
    if (readOnly) return
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
    if (isDrawing && drawRect && drawRect.width > 10 && drawRect.height > 10) {
      onAdd(drawRect)
    }
    setIsDrawing(false)
    setDrawRect(null)
  }
 
  const handleRectClick = (id: string, e: KonvaEventObject<MouseEvent | TouchEvent>) => {
    e.cancelBubble = true
    onSelect(id)
  }
 
  const handleDragEnd = (id: string, e: KonvaEventObject<DragEvent>) => {
    const node = e.target
    onUpdate(id, {
      bbox: {
        x: Math.round(node.x() / scale),
        y: Math.round(node.y() / scale),
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
        x: Math.round(node.x() / scale),
        y: Math.round(node.y() / scale),
        width: Math.round((node.width() * scaleX) / scale),
        height: Math.round((node.height() * scaleY) / scale),
      },
    })
  }
 
  return (
    <div ref={containerRef} className="w-full h-full">
      <Stage
        width={containerSize.width}
        height={containerSize.height}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <Layer>
          {image && (
            <Image
              image={image}
              width={imageWidth * scale}
              height={imageHeight * scale}
            />
          )}
 
          {annotations.map((ann) => (
            <Rect
              key={ann.id}
              ref={ann.id === selectedId ? selectedRef : undefined}
              x={ann.bbox.x * scale}
              y={ann.bbox.y * scale}
              width={ann.bbox.width * scale}
              height={ann.bbox.height * scale}
              stroke={ann.id === selectedId ? '#3b82f6' : '#22c55e'}
              strokeWidth={2}
              fill={ann.id === selectedId ? 'rgba(59,130,246,0.2)' : 'rgba(34,197,94,0.1)'}
              draggable={!readOnly}
              onClick={(e) => handleRectClick(ann.id, e)}
              onTap={(e) => handleRectClick(ann.id, e)}
              onDragEnd={(e) => handleDragEnd(ann.id, e)}
              onTransformEnd={(e) => handleTransformEnd(ann.id, e)}
            />
          ))}
 
          {drawRect && (
            <Rect
              x={drawRect.x * scale}
              y={drawRect.y * scale}
              width={drawRect.width * scale}
              height={drawRect.height * scale}
              stroke="#f59e0b"
              strokeWidth={2}
              dash={[5, 5]}
            />
          )}
 
          {selectedId && !readOnly && (
            <Transformer
              ref={transformerRef}
              boundBoxFunc={(oldBox, newBox) => {
                if (newBox.width < 10 || newBox.height < 10) return oldBox
                return newBox
              }}
            />
          )}
        </Layer>
      </Stage>
    </div>
  )
}
 