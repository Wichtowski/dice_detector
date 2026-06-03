# Dice Annotator UI
 
React + TypeScript web interface for annotating dice images with bounding boxes and metadata.
 
## Features
 
- Draw bounding boxes with mouse drag
- Select, move, and resize boxes with handles
- Edit dice type, value, orientation per annotation
- Mark annotations as ambiguous
- Navigate images with arrow keys
- Save with Ctrl+S
- Delete selected annotation with Delete/Backspace
- Preserves original image coordinates (not scaled canvas coordinates)
 
## Development
 
### Prerequisites
 
- Node.js 18+
- Backend API running (see below)
 
### Install dependencies
 
```bash
cd annotator-ui
npm install
```
 
### Run dev server
 
```bash
npm run dev
```
 
Opens at http://localhost:5173 (proxies API calls to backend)
 
### Build for production
 
```bash
npm run build
```
 
Output in `dist/` directory.
 
## Backend
 
The FastAPI backend serves images and saves annotations.
 
### Run backend only (serves built frontend from dist/)
 
```bash
python -m dice_detector.training.annotator_api --images data/images --output data/annotations
```
 
Opens at http://localhost:8765
 
### Run backend with dev UI
 
```bash
python -m dice_detector.training.annotator_api --images data/images --output data/annotations --dev-ui http://localhost:5173
```
 
### CLI options
 
| Option | Default | Description |
|--------|---------|-------------|
| `--images` | `data/images` | Directory containing images to annotate |
| `--output` | `data/annotations` | Directory to save annotation JSON files |
| `--host` | `127.0.0.1` | Host to bind |
| `--port` | `8765` | Port to bind |
| `--dev-ui` | None | URL of Vite dev server for development |
 
## Annotation Format
 
Annotations are saved as JSON files compatible with the `ImageAnnotation` model:
 
```json
{
  "image_path": "data/images/example.jpg",
  "image_width": 1920,
  "image_height": 1080,
  "dice": [
    {
      "bbox": { "x": 100, "y": 200, "width": 80, "height": 80 },
      "dice_type": "D20",
      "value": 17,
      "orientation_degrees": 45.0,
      "ambiguous": false,
      "ambiguity_reasons": [],
      "has_6_9_marker": true,
      "d4_style": null,
      "special_value": null
    }
  ],
  "source": "manual",
  "timestamp": "2024-01-15T10:30:00"
}
```
 