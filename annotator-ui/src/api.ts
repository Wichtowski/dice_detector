import type { ImageInfo, PaginatedImages, Config, Annotation, BatchType } from './types'
 
const API_BASE = '/api'
 
export async function fetchImages(
  page = 1,
  perPage = 100,
  source?: string,
  toVerify = false,
  toValue = false,
  unannotated = false
): Promise<PaginatedImages> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
  if (source) params.set('source', source)
  if (toVerify) params.set('to_verify', 'true')
  if (toValue) params.set('to_value', 'true')
  if (unannotated) params.set('unannotated', 'true')
  const res = await fetch(`${API_BASE}/images?${params}`)
  return res.json()
}

export async function fetchBatchTypes(): Promise<BatchType[]> {
  const res = await fetch(`${API_BASE}/batch/types`)
  const data = await res.json()
  return data.types ?? []
}
 
export async function fetchImage(imageId: string): Promise<ImageInfo> {
  const res = await fetch(`${API_BASE}/images/${imageId}`)
  return res.json()
}
 
export async function fetchConfig(): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`)
  return res.json()
}
 
export async function saveAnnotations(
  imageId: string,
  annotations: Omit<Annotation, 'id'>[],
  isVerified = false
): Promise<{ status: string; path: string; count: number; is_verified: boolean }> {
  const res = await fetch(`${API_BASE}/annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_id: imageId, annotations, is_verified: isVerified }),
  })
  return res.json()
}

export async function commitBatch(
  imageId: string,
  annotations: Omit<Annotation, 'id'>[]
): Promise<{ status: string; count: number }> {
  const res = await fetch(`${API_BASE}/batch/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_id: imageId, annotations }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Commit failed')
  }
  return res.json()
}

export async function deleteImage(
  imageId: string
): Promise<{ status: string; image_id: string }> {
  const res = await fetch(`${API_BASE}/images/${imageId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Delete failed')
  }
  return res.json()
}

export async function cropImage(
  imageId: string,
  x: number,
  y: number,
  size: number
): Promise<{ status: string; width: number; height: number }> {
  const res = await fetch(`${API_BASE}/images/${imageId}/crop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x, y, size }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Crop failed')
  }
  return res.json()
}

export async function uploadImage(
  file: File
): Promise<{ status: string; image_id: string; filename: string }> {
  const formData = new FormData()
  formData.append('image', file, file.name)
  const res = await fetch(`${API_BASE}/images/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function scaleImage(
  imageId: string,
  size: number
): Promise<{ status: string; width: number; height: number }> {
  const res = await fetch(`${API_BASE}/images/${imageId}/scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ size }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Scale failed')
  }
  return res.json()
}

export interface TypeStat {
  type: string
  count: number
  goal: number
  faces_total: number
  faces_covered: number
  faces_complete: number
  values: Record<string, number>
}

export interface Stats {
  total: number
  per_face_goal: number
  types: TypeStat[]
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/stats`)
  return res.json()
}
