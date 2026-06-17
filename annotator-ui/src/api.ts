import type { ImageInfo, PaginatedImages, Config, Annotation } from './types'
 
const API_BASE = '/api'
 
export async function fetchImages(page = 1, perPage = 100, source?: string, toVerify = false): Promise<PaginatedImages> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
  if (source) params.set('source', source)
  if (toVerify) params.set('to_verify', 'true')
  const res = await fetch(`${API_BASE}/images?${params}`)
  return res.json()
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
