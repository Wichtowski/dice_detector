interface Props {
  onSave: () => void
  saving: boolean
  message: string | null
}
 
export function Toolbar({ onSave, saving, message }: Props) {
  return (
    <div className="p-4 border-t border-gray-700">
      <button
        onClick={onSave}
        disabled={saving}
        className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded p-2 font-semibold"
      >
        {saving ? 'Saving...' : 'Save (Ctrl+S)'}
      </button>
      {message && (
        <p className="text-center text-sm text-green-400 mt-2">{message}</p>
      )}
      <p className="text-xs text-gray-500 mt-2 text-center">
        Delete: Del/Backspace | Navigate: ←→
      </p>
    </div>
  )
}
