import { useState, useEffect, useCallback } from 'react'
import type { Annotation, ImageInfo, ImageListItem, Config } from './types'
import { fetchImages, fetchImage, fetchConfig, saveAnnotations } from './api'
import { AnnotatorCanvas } from './components/AnnotatorCanvas.tsx'
import { AnnotationPanel } from './components/AnnotationPanel.tsx'
import { ImageNavigator } from './components/ImageNavigator'
import { BBoxList } from './components/BBoxList'
import { CameraCapture } from './components/CameraCapture'

function generateId(): string {
  return Math.random().toString(36).substring(2, 9)
}

export default function App() {
  const [images, setImages] = useState<ImageListItem[]>([])
  const [currentImage, setCurrentImage] = useState<ImageInfo | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalImages, setTotalImages] = useState(0)
  const [readOnly, setReadOnly] = useState(false)

  const loadPage = useCallback(async (p: number) => {
    const data = await fetchImages(p)
    setImages(data.images)
    setPage(data.page)
    setTotalPages(data.total_pages)
    setTotalImages(data.total)
  }, [])

  useEffect(() => {
    fetchConfig().then(setConfig)
    loadPage(1)
  }, [])

  const loadImage = useCallback(async (imageId: string) => {
    const info = await fetchImage(imageId)
    setCurrentImage(info)
    setAnnotations(
      info.annotations.map((a) => ({ ...a, id: generateId() }))
    )
    setSelectedId(null)
    setReadOnly(info.read_only ?? false)
  }, [])

  useEffect(() => {
    if (images.length > 0 && !currentImage) {
      loadImage(images[0].id)
    }
  }, [images, currentImage, loadImage])

  const currentIndex = currentImage
    ? images.findIndex((img) => img.id === currentImage.id)
    : -1

  const goToPrev = useCallback(async () => {
    if (currentIndex > 0) {
      loadImage(images[currentIndex - 1].id)
    } else if (page > 1) {
      const data = await fetchImages(page - 1)
      setImages(data.images)
      setPage(data.page)
      setTotalPages(data.total_pages)
      setTotalImages(data.total)
      if (data.images.length > 0) {
        loadImage(data.images[data.images.length - 1].id)
      }
    }
  }, [currentIndex, images, loadImage, page])

  const goToNext = useCallback(async () => {
    if (currentIndex < images.length - 1) {
      loadImage(images[currentIndex + 1].id)
    } else if (page < totalPages) {
      const data = await fetchImages(page + 1)
      setImages(data.images)
      setPage(data.page)
      setTotalPages(data.total_pages)
      setTotalImages(data.total)
      if (data.images.length > 0) {
        loadImage(data.images[0].id)
      }
    }
  }, [currentIndex, images, loadImage, page, totalPages])

  const handlePageChange = useCallback(async (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    const data = await fetchImages(newPage)
    setImages(data.images)
    setPage(data.page)
    setTotalPages(data.total_pages)
    setTotalImages(data.total)
    if (data.images.length > 0) {
      loadImage(data.images[0].id)
    }
  }, [totalPages, loadImage])

  const handleSave = useCallback(async () => {
    if (!currentImage || readOnly) return
    setSaving(true)
    try {
      const toSave = annotations.map(({ id: _, ...rest }) => rest)
      const result = await saveAnnotations(currentImage.id, toSave)
      setMessage(`Saved ${result.count} annotations`)
      setImages((prev) =>
        prev.map((img) =>
          img.id === currentImage.id ? { ...img, annotated: true } : img
        )
      )
      setTimeout(() => setMessage(null), 2000)
    } catch (e) {
      setMessage('Save failed!')
    }
    setSaving(false)
  }, [currentImage, annotations, readOnly])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'ArrowLeft') goToPrev()
      if (e.key === 'ArrowRight') goToNext()
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId && !readOnly) {
        setAnnotations((prev) => prev.filter((a) => a.id !== selectedId))
        setSelectedId(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSave, goToPrev, goToNext, selectedId])

  const handleAddAnnotation = (bbox: Annotation['bbox']) => {
    const newAnn: Annotation = {
      id: generateId(),
      bbox,
      dice_type: config?.dice_types[0] || 'D6',
      value: null,
      orientation_degrees: null,
      ambiguous: false,
      ambiguity_reasons: [],
      has_6_9_marker: null,
      d4_style: null,
      special_value: null,
    }
    setAnnotations((prev) => [...prev, newAnn])
    setSelectedId(newAnn.id)
  }

  const handleUpdateAnnotation = (id: string, updates: Partial<Annotation>) => {
    setAnnotations((prev) =>
      prev.map((a) => (a.id === id ? { ...a, ...updates } : a))
    )
  }

  const handleDeleteAnnotation = (id: string) => {
    setAnnotations((prev) => prev.filter((a) => a.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const selectedAnnotation = annotations.find((a) => a.id === selectedId) || null

  return (
    <div className="flex h-screen text-white">
      <div className="w-72 bg-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">Dice Annotator</h1>
        </div>

        <div className="p-4 border-b border-gray-700">
          <CameraCapture
            onCapture={(imageId) => {
              loadPage(page).then(() => loadImage(imageId))
            }}
          />
        </div>

        <ImageNavigator
          images={images}
          currentId={currentImage?.id || null}
          onSelect={loadImage}
          onPrev={goToPrev}
          onNext={goToNext}
          page={page}
          totalPages={totalPages}
          total={totalImages}
          onPageChange={handlePageChange}
          readOnly={readOnly}
        />

        <div className="flex-1 overflow-y-auto p-4 border-t border-gray-700">
          <BBoxList
            annotations={annotations}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onDelete={handleDeleteAnnotation}
            readOnly={readOnly}
          />
        </div>

        {config && selectedAnnotation && (
          <AnnotationPanel
            annotation={selectedAnnotation}
            config={config}
            onUpdate={(updates) => handleUpdateAnnotation(selectedId!, updates)}
            readOnly={readOnly}
          />
        )}

        <div className="p-4 border-t border-gray-700">
          {!readOnly && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded p-2 font-semibold"
            >
              {saving ? 'Saving...' : 'Save (Ctrl+S)'}
            </button>
          )}
          {message && (
            <p className="text-center text-sm text-green-400 mt-2">{message}</p>
          )}
        </div>
      </div>

      <div className="flex-1 bg-gray-950 overflow-hidden">
        {currentImage && (
          <AnnotatorCanvas
            imageUrl={currentImage.url}
            imageWidth={currentImage.width}
            imageHeight={currentImage.height}
            annotations={annotations}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAdd={handleAddAnnotation}
            onUpdate={handleUpdateAnnotation}
            readOnly={readOnly}
          />
        )}
      </div>
    </div>
  )
}
