import { useState, useEffect, useCallback, useRef } from 'react'
import type { Annotation, ImageInfo, ImageListItem, Config, PaginatedImages } from './types'
import { fetchImages, fetchImage, fetchConfig, saveAnnotations, deleteImage, cropImage, uploadImage, scaleImage } from './api'
import { AnnotatorCanvas } from './components/AnnotatorCanvas.tsx'
import { AnnotationPanel } from './components/AnnotationPanel.tsx'
import { ImageNavigator } from './components/ImageNavigator'
import { BBoxList } from './components/BBoxList'
import { CameraCapture } from './components/CameraCapture'
import { CropModal } from './components/CropModal'
import { StatsTracker } from './components/StatsTracker'
import { DICE_COLORS } from './diceColors'

function generateId(): string {
  return Math.random().toString(36).substring(2, 9)
}

const SCALE_PRESETS = [320, 416, 512, 640, 768, 1024, 1280]

export default function App() {
  const [images, setImages] = useState<ImageListItem[]>([])
  const [currentImage, setCurrentImage] = useState<ImageInfo | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [originalAnnotations, setOriginalAnnotations] = useState<Annotation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalImages, setTotalImages] = useState(0)
  const [totalAnnotated, setTotalAnnotated] = useState(0)
  const [totalVerified, setTotalVerified] = useState(0)
  const [readOnly, setReadOnly] = useState(false)
  const [isVerified, setIsVerified] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [confirmedIds, setConfirmedIds] = useState<Set<string>>(new Set())
  const [view, setView] = useState<'annotate' | 'verify'>('annotate')
  const [cropTarget, setCropTarget] = useState<ImageInfo | null>(null)
  const [cropping, setCropping] = useState(false)
  const [showScaleMenu, setShowScaleMenu] = useState(false)
  const [scaling, setScaling] = useState(false)
  const [statsVersion, setStatsVersion] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const toVerify = view === 'verify'

  const applyPageData = useCallback((data: PaginatedImages) => {
    setImages(data.images)
    setPage(data.page)
    setTotalPages(data.total_pages)
    setTotalImages(data.total)
    setTotalAnnotated(data.total_annotated)
    setTotalVerified(data.total_verified)
  }, [])

  const loadPage = useCallback(async (p: number) => {
    const data = await fetchImages(p, 100, undefined, toVerify)
    applyPageData(data)
  }, [toVerify, applyPageData])

  useEffect(() => {
    fetchConfig().then(setConfig)
    loadPage(1)
  }, [])

  const loadImage = useCallback(async (imageId: string) => {
    const info = await fetchImage(imageId)
    setCurrentImage({ ...info, url: `${info.url}?t=${Date.now()}` })
    const loaded = info.annotations.map((a) => ({ ...a, id: generateId() }))
    setAnnotations(loaded)
    setOriginalAnnotations(loaded)
    setSelectedId(null)
    setReadOnly(info.read_only ?? false)
    setIsVerified(info.is_verified ?? false)
    // Keep verification mode active across images; just reset per-image progress.
    setVerifying(toVerify && !(info.read_only ?? false))
    setConfirmedIds(new Set())
    setShowScaleMenu(false)
  }, [toVerify])

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
      const data = await fetchImages(page - 1, 100, undefined, toVerify)
      applyPageData(data)
      if (data.images.length > 0) {
        loadImage(data.images[data.images.length - 1].id)
      }
    }
  }, [currentIndex, images, loadImage, page, toVerify, applyPageData])

  const goToNext = useCallback(async () => {
    if (currentIndex < images.length - 1) {
      loadImage(images[currentIndex + 1].id)
    } else if (page < totalPages) {
      const data = await fetchImages(page + 1, 100, undefined, toVerify)
      applyPageData(data)
      if (data.images.length > 0) {
        loadImage(data.images[0].id)
      }
    }
  }, [currentIndex, images, loadImage, page, totalPages, toVerify, applyPageData])

  const handlePageChange = useCallback(async (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    const data = await fetchImages(newPage, 100, undefined, toVerify)
    applyPageData(data)
    if (data.images.length > 0) {
      loadImage(data.images[0].id)
    }
  }, [totalPages, loadImage, toVerify, applyPageData])

  const doSave = useCallback(async (verify: boolean) => {
    if (!currentImage || readOnly) return
    setSaving(true)
    try {
      const toSave = annotations.map(({ id: _, ...rest }) => rest)
      const result = await saveAnnotations(currentImage.id, toSave, verify)
      setIsVerified(verify)
      setMessage(verify ? `Verified ${result.count} annotations` : `Saved ${result.count} annotations`)
      setStatsVersion((v) => v + 1)
      const prevItem = images.find((img) => img.id === currentImage.id)
      if (prevItem && !prevItem.annotated) setTotalAnnotated((n) => n + 1)
      if (prevItem) {
        if (verify && !prevItem.verified) setTotalVerified((n) => n + 1)
        else if (!verify && prevItem.verified) setTotalVerified((n) => Math.max(0, n - 1))
      }
      setImages((prev) =>
        prev.map((img) =>
          img.id === currentImage.id ? { ...img, annotated: true, verified: verify } : img
        )
      )
      setTimeout(() => setMessage(null), 2000)
      if (toVerify && verify) {
        // Verified image leaves the to-verify list; reload and continue.
        const data = await fetchImages(1, 100, undefined, true)
        applyPageData(data)
        if (data.images.length > 0) {
          loadImage(data.images[0].id)
        } else {
          setCurrentImage(null)
          setAnnotations([])
          setSelectedId(null)
        }
      } else {
        goToNext()
      }
    } catch (e) {
      setMessage('Save failed!')
    }
    setSaving(false)
  }, [currentImage, annotations, readOnly, goToNext, images, toVerify, applyPageData, loadImage])

  const switchView = useCallback(async (next: 'annotate' | 'verify') => {
    if (next === view) return
    setView(next)
    setSelectedId(null)
    setConfirmedIds(new Set())
    setVerifying(next === 'verify')
    const data = await fetchImages(1, 100, undefined, next === 'verify')
    applyPageData(data)
    if (data.images.length > 0) {
      loadImage(data.images[0].id)
    } else {
      setCurrentImage(null)
      setAnnotations([])
    }
  }, [view, applyPageData, loadImage])

  const handleSave = useCallback(() => doSave(isVerified), [doSave, isVerified])

  const confirmSelectedDie = useCallback(() => {
    if (!selectedId) return
    setConfirmedIds((prev) => new Set(prev).add(selectedId))
  }, [selectedId])

  // Finalize verification once every die is confirmed
  useEffect(() => {
    if (
      verifying &&
      annotations.length > 0 &&
      confirmedIds.size >= annotations.length &&
      annotations.every((a) => confirmedIds.has(a.id))
    ) {
      setVerifying(false)
      setConfirmedIds(new Set())
      doSave(true)
    }
  }, [verifying, confirmedIds, annotations, doSave])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'ArrowLeft') goToPrev()
      if (e.key === 'ArrowRight') goToNext()
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId && !readOnly && !verifying) {
        setAnnotations((prev) => prev.filter((a) => a.id !== selectedId))
        setSelectedId(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSave, goToPrev, goToNext, selectedId, readOnly, verifying])

  const handleAddAnnotation = (bbox: Annotation['bbox'], diceType: string, value: number | null) => {
    const newAnn: Annotation = {
      id: generateId(),
      bbox,
      dice_type: diceType,
      value,
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

  const handleDeleteImage = useCallback(async () => {
    if (!currentImage || readOnly) return
    if (!confirm(`Delete image "${currentImage.name}"? This cannot be undone.`)) return
    try {
      await deleteImage(currentImage.id)
      setCurrentImage(null)
      setAnnotations([])
      setSelectedId(null)
      setStatsVersion((v) => v + 1)
      await loadPage(page)
    } catch (e) {
      setMessage(`Delete failed: ${e instanceof Error ? e.message : e}`)
    }
  }, [currentImage, readOnly, page, loadPage])

  const openCrop = useCallback(async (imageId: string) => {
    try {
      const info = await fetchImage(imageId)
      setCropTarget({ ...info, url: `${info.url}?t=${Date.now()}` })
    } catch (e) {
      setMessage(`Could not open crop: ${e instanceof Error ? e.message : e}`)
    }
  }, [])

  const handleCropConfirm = useCallback(
    async (crop: { x: number; y: number; size: number }) => {
      if (!cropTarget) return
      const id = cropTarget.id
      setCropping(true)
      try {
        // Persist any unsaved annotations on the open image so the backend
        // can remap them into the cropped coordinate space.
        if (currentImage && currentImage.id === id && !readOnly) {
          const toSave = annotations.map(({ id: _, ...rest }) => rest)
          await saveAnnotations(id, toSave, isVerified)
        }
        await cropImage(id, crop.x, crop.y, crop.size)
        setCropTarget(null)
        await loadPage(page)
        await loadImage(id)
        setStatsVersion((v) => v + 1)
        setMessage('Image cropped')
        setTimeout(() => setMessage(null), 2000)
      } catch (e) {
        setMessage(`Crop failed: ${e instanceof Error ? e.message : e}`)
      }
      setCropping(false)
    },
    [cropTarget, page, loadPage, loadImage, currentImage, readOnly, annotations, isVerified]
  )

  const handleScale = useCallback(
    async (size: number) => {
      if (!currentImage || readOnly) return
      const id = currentImage.id
      setShowScaleMenu(false)
      setScaling(true)
      try {
        // Persist unsaved annotations so the backend scales them too.
        const toSave = annotations.map(({ id: _, ...rest }) => rest)
        await saveAnnotations(id, toSave, isVerified)
        const res = await scaleImage(id, size)
        await loadPage(page)
        await loadImage(id)
        setStatsVersion((v) => v + 1)
        setMessage(`Scaled to ${res.width}×${res.height}`)
        setTimeout(() => setMessage(null), 2000)
      } catch (e) {
        setMessage(`Scale failed: ${e instanceof Error ? e.message : e}`)
      }
      setScaling(false)
    },
    [currentImage, readOnly, annotations, isVerified, page, loadPage, loadImage]
  )

  const handleUploadFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      try {
        let lastId: string | null = null
        for (const file of Array.from(files)) {
          const res = await uploadImage(file)
          lastId = res.image_id
        }
        await loadPage(page)
        if (lastId) await openCrop(lastId)
      } catch (e) {
        setMessage(`Upload failed: ${e instanceof Error ? e.message : e}`)
      }
    },
    [page, loadPage, openCrop]
  )

  const selectedAnnotation = annotations.find((a) => a.id === selectedId) || null

  return (
    <div className="flex h-screen text-white">
      <div className="w-72 bg-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">Dice Annotator</h1>
        </div>

        <div className="flex border-b border-gray-700">
          <button
            onClick={() => switchView('annotate')}
            className={`flex-1 p-2 text-sm font-semibold ${
              view === 'annotate'
                ? 'bg-gray-700 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Annotate
          </button>
          <button
            onClick={() => switchView('verify')}
            className={`flex-1 p-2 text-sm font-semibold ${
              view === 'verify'
                ? 'bg-blue-700 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Verify ({Math.max(0, totalAnnotated - totalVerified)})
          </button>
        </div>

        {view === 'annotate' && (
          <div className="p-4 border-b border-gray-700 space-y-3">
            <CameraCapture
              onCapture={(imageId) => {
                loadPage(page).then(() => openCrop(imageId))
              }}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                handleUploadFiles(e.target.files)
                e.target.value = ''
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full bg-indigo-600 hover:bg-indigo-500 rounded px-3 py-1.5 text-sm font-semibold"
            >
              Upload Image
            </button>
          </div>
        )}

        <ImageNavigator
          images={images}
          currentId={currentImage?.id || null}
          onSelect={loadImage}
          onPrev={goToPrev}
          onNext={goToNext}
          page={page}
          totalPages={totalPages}
          total={totalImages}
          totalAnnotated={totalAnnotated}
          totalVerified={totalVerified}
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

        <div className="px-4 py-2 border-t border-gray-700">
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {Object.entries(DICE_COLORS).map(([type, color]) => (
              <span key={type} className="flex items-center gap-1 text-xs">
                <span
                  className="inline-block w-3 h-3 rounded-sm"
                  style={{ backgroundColor: color }}
                />
                {type}
              </span>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-gray-700">
          {view === 'annotate' && !readOnly && (
            <>
              <div className="flex items-center justify-between mb-2 text-sm">
                {isVerified ? (
                  <span className="text-green-400 font-semibold">✓ Verified</span>
                ) : (
                  <span className="text-yellow-400 font-semibold">● Unverified</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded p-2 font-semibold"
                >
                  {saving ? 'Saving...' : 'Save (Ctrl+S)'}
                </button>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    onClick={() => { setAnnotations(originalAnnotations); setSelectedId(null) }}
                    className="bg-gray-600 hover:bg-gray-500 rounded p-2 font-semibold text-sm"
                    title="Reset to saved state"
                  >
                    Reset
                  </button>
                  <button
                    onClick={() => currentImage && openCrop(currentImage.id)}
                    className="bg-amber-600 hover:bg-amber-500 rounded p-2 font-semibold text-sm"
                    title="Crop image (square)"
                  >
                    Crop
                  </button>
                  <div className="relative">
                    <button
                      onClick={() => setShowScaleMenu((v) => !v)}
                      disabled={scaling}
                      className="w-full bg-purple-600 hover:bg-purple-500 disabled:bg-gray-600 rounded p-2 font-semibold text-sm"
                      title="Scale image down to a preset size"
                    >
                      {scaling ? '...' : 'Scale'}
                    </button>
                    {showScaleMenu && (
                      <div className="absolute bottom-full right-0 mb-1 w-32 bg-gray-700 rounded shadow-lg border border-gray-600 z-10 overflow-hidden">
                        <p className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-gray-400 border-b border-gray-600">
                          Longest side
                        </p>
                        {SCALE_PRESETS.map((size) => {
                          const longest = Math.max(currentImage?.width ?? 0, currentImage?.height ?? 0)
                          const disabled = size >= longest
                          return (
                            <button
                              key={size}
                              onClick={() => handleScale(size)}
                              disabled={disabled}
                              className="w-full text-left px-3 py-1.5 text-sm hover:bg-purple-600 disabled:text-gray-500 disabled:hover:bg-transparent disabled:cursor-not-allowed"
                              title={disabled ? 'Image is already this size or smaller' : `Scale to ${size}px`}
                            >
                              {size}px
                              {size === 640 && <span className="text-[10px] text-purple-300 ml-1">YOLO</span>}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={handleDeleteImage}
                    className="col-span-3 bg-red-700 hover:bg-red-600 rounded p-2 font-semibold text-sm"
                    title="Delete image"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </>
          )}

          {view === 'verify' && currentImage && (
            <div className="p-3 bg-blue-950/50 border border-blue-700 rounded space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-blue-300">Verifying</span>
                <span className="text-gray-300">
                  {confirmedIds.size} / {annotations.length} confirmed
                </span>
              </div>
              {selectedAnnotation ? (
                confirmedIds.has(selectedAnnotation.id) ? (
                  <p className="text-xs text-green-400">
                    ✓ {selectedAnnotation.dice_type} {selectedAnnotation.value ?? '?'} confirmed
                  </p>
                ) : (
                  <button
                    onClick={confirmSelectedDie}
                    className="w-full bg-green-600 hover:bg-green-500 rounded p-2 text-sm font-semibold"
                  >
                    Confirm {selectedAnnotation.dice_type} {selectedAnnotation.value ?? '?'}
                  </button>
                )
              ) : (
                <p className="text-xs text-gray-400">Click a die to confirm it.</p>
              )}
              <button
                onClick={goToNext}
                className="w-full bg-gray-600 hover:bg-gray-500 rounded p-1.5 text-xs"
              >
                Skip image
              </button>
            </div>
          )}
          {message && (
            <p className="text-center text-sm text-green-400 mt-2">{message}</p>
          )}
        </div>
      </div>

      <div className="flex-1 bg-gray-950 overflow-hidden relative">
        <StatsTracker refreshKey={statsVersion} />
        {currentImage ? (
          <AnnotatorCanvas
            imageUrl={currentImage.url}
            imageWidth={currentImage.width}
            imageHeight={currentImage.height}
            annotations={annotations}
            selectedId={selectedId}
            config={config}
            confirmedIds={confirmedIds}
            verifying={verifying}
            onSelect={setSelectedId}
            onAdd={handleAddAnnotation}
            onUpdate={handleUpdateAnnotation}
            onConfirmDie={(id) => setConfirmedIds((prev) => new Set(prev).add(id))}
            readOnly={readOnly || verifying}
          />
        ) : view === 'verify' ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-gray-400">
            <p className="text-2xl font-semibold text-green-400 mb-2">All verified 🎉</p>
            <p className="text-sm">No annotated images left to verify.</p>
          </div>
        ) : null}
      </div>

      {cropTarget && (
        <CropModal
          imageUrl={cropTarget.url}
          imageWidth={cropTarget.width}
          imageHeight={cropTarget.height}
          busy={cropping}
          onConfirm={handleCropConfirm}
          onCancel={() => setCropTarget(null)}
        />
      )}
    </div>
  )
}
