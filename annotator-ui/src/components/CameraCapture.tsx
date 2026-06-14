import { useRef, useState, useCallback, useEffect } from 'react'

interface CameraCaptureProps {
  onCapture: (imageId: string) => void
}

export function CameraCapture({ onCapture }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [active, setActive] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>('')

  const refreshDevices = useCallback(async () => {
    const all = await navigator.mediaDevices.enumerateDevices()
    const cameras = all.filter((d) => d.kind === 'videoinput')
    setDevices(cameras)
    if (cameras.length > 0 && !selectedDevice) {
      setSelectedDevice(cameras[0].deviceId)
    }
    return cameras
  }, [selectedDevice])

  const startCamera = useCallback(async () => {
    setError(null)
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Camera API unavailable. Make sure you access this page via https:// or http://localhost (not 127.0.0.1).')
        return
      }
      // First request with loose constraints to trigger permission prompt
      const initialStream = await navigator.mediaDevices.getUserMedia({
        video: true,
      })
      // Stop the initial stream — we just needed the permission grant
      initialStream.getTracks().forEach((t) => t.stop())

      // Now enumerate devices (deviceIds are available after permission)
      const cameras = await refreshDevices()

      // Re-open with the selected (or first available) device
      const deviceId = selectedDevice || cameras[0]?.deviceId
      const constraints: MediaStreamConstraints = {
        video: deviceId
          ? { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
          : { width: { ideal: 1920 }, height: { ideal: 1080 } },
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setActive(true)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('NotFoundError') || msg.includes('not found') || msg.includes('Requested device not found')) {
        setError('No camera found. Please connect a camera and try again.')
      } else {
        setError(`Camera error: ${msg}`)
      }
    }
  }, [selectedDevice, refreshDevices])

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setActive(false)
  }, [])

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  const capture = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current) return
    setCapturing(true)
    setError(null)

    const video = videoRef.current
    const canvas = canvasRef.current
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(video, 0, 0)

    canvas.toBlob(async (blob) => {
      if (!blob) {
        setError('Failed to capture image')
        setCapturing(false)
        return
      }

      const formData = new FormData()
      formData.append('image', blob, 'capture.png')

      try {
        const res = await fetch('/api/camera/capture', { method: 'POST', body: formData })
        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'Upload failed')
        }
        const data = await res.json()
        onCapture(data.image_id)
      } catch (e) {
        setError(`Capture failed: ${e instanceof Error ? e.message : e}`)
      }
      setCapturing(false)
    }, 'image/png')
  }, [onCapture])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase text-gray-400">Camera</span>
        {devices.length > 1 && (
          <select
            className="bg-gray-700 text-xs rounded px-1 py-0.5 flex-1 min-w-0"
            value={selectedDevice}
            onChange={(e) => setSelectedDevice(e.target.value)}
            disabled={active}
          >
            {devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${devices.indexOf(d) + 1}`}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="relative bg-black rounded overflow-hidden" style={{ minHeight: active ? 160 : 0 }}>
        <video ref={videoRef} className="w-full" playsInline muted style={{ display: active ? 'block' : 'none' }} />
        <canvas ref={canvasRef} style={{ display: 'none' }} />
      </div>

      <div className="flex gap-2">
        {!active ? (
          <button
            onClick={startCamera}
            className="flex-1 bg-blue-600 hover:bg-blue-500 rounded px-3 py-1.5 text-sm font-semibold"
          >
            Start Camera
          </button>
        ) : (
          <>
            <button
              onClick={capture}
              disabled={capturing}
              className="flex-1 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded px-3 py-1.5 text-sm font-semibold"
            >
              {capturing ? 'Capturing...' : 'Capture'}
            </button>
            <button
              onClick={stopCamera}
              className="bg-red-600 hover:bg-red-500 rounded px-3 py-1.5 text-sm font-semibold"
            >
              Stop
            </button>
          </>
        )}
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
