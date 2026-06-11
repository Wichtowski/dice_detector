import type { ImageInfo, PaginatedImages, Config, Annotation } from './types'
 
const API_BASE = '/api'
 
export async function fetchImages(page = 1, perPage = 100, source?: string): Promise<PaginatedImages> {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
  if (source) params.set('source', source)
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
  annotations: Omit<Annotation, 'id'>[]
): Promise<{ status: string; path: string; count: number }> {
  const res = await fetch(`${API_BASE}/annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_id: imageId, annotations }),
  })
  return res.json()
}
