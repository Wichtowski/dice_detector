import type { ImageInfo, ImageListItem, Config, Annotation } from './types'
 
const API_BASE = '/api'
 
export async function fetchImages(): Promise<ImageListItem[]> {
  const res = await fetch(`${API_BASE}/images`)
  const data = await res.json()
  return data.images
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
