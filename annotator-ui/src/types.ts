export interface BBox {
  x: number
  y: number
  width: number
  height: number
}
 
export interface Annotation {
  id: string
  bbox: BBox
  dice_type: string
  value: number | null
  orientation_degrees: number | null
  ambiguous: boolean
  ambiguity_reasons: string[]
  has_6_9_marker: boolean | null
  d4_style: string | null
  special_value: string | null
}
 
export interface ImageInfo {
  id: string
  name: string
  width: number
  height: number
  url: string
  annotations: Omit<Annotation, 'id'>[]
  read_only: boolean
  source: string
}

export interface ImageListItem {
  id: string
  name: string
  annotated: boolean
  read_only: boolean
  source: string
}

export interface PaginatedImages {
  images: ImageListItem[]
  page: number
  per_page: number
  total: number
  total_pages: number
}
