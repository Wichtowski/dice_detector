// Per-dice-type colors for easy visual association (type only, not value).
export const DICE_COLORS: Record<string, string> = {
  D4: '#f43f5e', // rose
  D6: '#f59e0b', // amber
  D8: '#84cc16', // lime
  D10: '#06b6d4', // cyan
  D12: '#a855f7', // violet
  D20: '#ec4899', // pink
  D100: '#14b8a6', // teal
}

export const DEFAULT_DICE_COLOR = '#22c55e'

export function diceColor(type: string): string {
  return DICE_COLORS[type] || DEFAULT_DICE_COLOR
}

// Pick black/white text for readable contrast on a hex background.
export function textColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return lum > 0.6 ? '#000000' : '#ffffff'
}
