import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dice_detector.models import (
    AmbiguityReason,
    BoundingBox,
    D4Style,
    DiceAnnotation,
    DiceType,
    ImageAnnotation,
    SpecialValue,
)


class BBoxData(BaseModel):
    x: int
    y: int
    width: int
    height: int


class AnnotationData(BaseModel):
    bbox: BBoxData
    dice_type: str
    value: Optional[int] = None
    orientation_degrees: Optional[float] = None
    ambiguous: bool = False
    ambiguity_reasons: list[str] = []
    has_6_9_marker: Optional[bool] = None
    d4_style: Optional[str] = None
    special_value: Optional[str] = None


class SaveAnnotationsRequest(BaseModel):
    image_id: str
    annotations: list[AnnotationData]


class AnnotatorAPI:
    def __init__(self, images_dir: str, output_dir: str, extra_sources: dict[str, dict] | None = None):
        self.images_dir = Path(images_dir)
        self.output_dir = Path(output_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Extra image sources: {"name": {"images": path, "annotations": path}}
        self.sources = {
            "default": {"images": self.images_dir, "annotations": self.output_dir}
        }
        if extra_sources:
            for name, paths in extra_sources.items():
                self.sources[name] = {
                    "images": Path(paths["images"]),
                    "annotations": Path(paths["annotations"]),
                }
        self.current_source = "default"

    def create_app(self, dev_ui_url: Optional[str] = None) -> FastAPI:
        app = FastAPI(title="Dice Annotation API")

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/images")
        def list_images():
            images = self._get_image_list()
            result = []
            for img in images:
                ann_path = self.output_dir / f"{img.stem}.json"
                result.append({
                    "id": img.stem,
                    "name": img.name,
                    "annotated": ann_path.exists(),
                })
            return {"images": result}

        @app.get("/api/images/{image_id}")
        def get_image_info(image_id: str):
            img_path = self._find_image(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                raise HTTPException(500, "Failed to read image")
            h, w = img.shape[:2]

            annotations = self._load_annotations(image_id)

            return {
                "id": image_id,
                "name": img_path.name,
                "width": w,
                "height": h,
                "url": f"/api/images/{image_id}/file",
                "annotations": annotations,
            }

        @app.get("/api/images/{image_id}/file")
        def get_image_file(image_id: str):
            img_path = self._find_image(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")
            return FileResponse(img_path)

        @app.post("/api/annotations")
        def save_annotations(req: SaveAnnotationsRequest):
            img_path = self._find_image(req.image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                raise HTTPException(500, "Failed to read image")
            h, w = img.shape[:2]

            dice_annotations = []
            for ann in req.annotations:
                ambiguity_reasons = []
                for r in ann.ambiguity_reasons:
                    try:
                        ambiguity_reasons.append(AmbiguityReason(r))
                    except ValueError:
                        pass

                dice_ann = DiceAnnotation(
                    bbox=BoundingBox(
                        x=ann.bbox.x,
                        y=ann.bbox.y,
                        width=ann.bbox.width,
                        height=ann.bbox.height,
                    ),
                    dice_type=DiceType(ann.dice_type) if ann.dice_type else DiceType.UNKNOWN,
                    value=ann.value,
                    orientation_degrees=ann.orientation_degrees,
                    ambiguous=ann.ambiguous,
                    ambiguity_reasons=ambiguity_reasons,
                    d4_style=D4Style(ann.d4_style) if ann.d4_style else None,
                    has_6_9_marker=ann.has_6_9_marker,
                    special_value=SpecialValue(ann.special_value) if ann.special_value else None,
                )
                dice_annotations.append(dice_ann)

            image_annotation = ImageAnnotation(
                image_path=str(img_path),
                image_width=w,
                image_height=h,
                dice=dice_annotations,
                source="manual",
                timestamp=datetime.now().isoformat(),
            )

            out_path = self.output_dir / f"{req.image_id}.json"
            with open(out_path, "w") as f:
                f.write(image_annotation.model_dump_json(indent=2))

            return {"status": "saved", "path": str(out_path), "count": len(dice_annotations)}

        @app.get("/api/config")
        def get_config():
            return {
                "dice_types": [t.value for t in DiceType if t != DiceType.UNKNOWN],
                "ambiguity_reasons": [r.value for r in AmbiguityReason],
                "special_values": [s.value for s in SpecialValue],
                "d4_styles": [s.value for s in D4Style],
            }

        dist_dir = Path(__file__).parent.parent.parent.parent / "annotator-ui" / "dist"
        if dist_dir.exists() and not dev_ui_url:
            app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")
        elif not dev_ui_url:
            @app.get("/")
            def root():
                return {"message": "Annotator API running. Build frontend or use --dev-ui"}

        return app

    def _get_image_list(self) -> list[Path]:
        extensions = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
        images = []
        for ext in extensions:
            images.extend(self.images_dir.glob(f"*{ext}"))
            images.extend(self.images_dir.glob(f"*{ext.upper()}"))
        return sorted(images)

    def _find_image(self, image_id: str) -> Optional[Path]:
        for img in self._get_image_list():
            if img.stem == image_id:
                return img
        return None

    def _load_annotations(self, image_id: str) -> list[dict]:
        ann_path = self.output_dir / f"{image_id}.json"
        if not ann_path.exists():
            return []

        with open(ann_path) as f:
            data = json.load(f)

        annotations = []
        for d in data.get("dice", []):
            bbox = d.get("bbox", {})
            annotations.append({
                "bbox": {
                    "x": bbox.get("x", 0),
                    "y": bbox.get("y", 0),
                    "width": bbox.get("width", 0),
                    "height": bbox.get("height", 0),
                },
                "dice_type": d.get("dice_type", "UNKNOWN"),
                "value": d.get("value"),
                "orientation_degrees": d.get("orientation_degrees"),
                "ambiguous": d.get("ambiguous", False),
                "ambiguity_reasons": d.get("ambiguity_reasons", []),
                "d4_style": d.get("d4_style"),
                "has_6_9_marker": d.get("has_6_9_marker"),
                "special_value": d.get("special_value"),
            })
        return annotations


def main():
    parser = argparse.ArgumentParser(description="Dice Annotation Tool API")
    parser.add_argument("--images", type=str, default="data/images")
    parser.add_argument("--output", type=str, default="data/annotations")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev-ui", type=str, default=None, help="Vite dev server URL")
    args = parser.parse_args()

    api = AnnotatorAPI(args.images, args.output)
    app = api.create_app(dev_ui_url=args.dev_ui)

    print(f"Starting Annotator API at http://{args.host}:{args.port}")
    print(f"Images: {args.images}")
    print(f"Output: {args.output}")
    if args.dev_ui:
        print(f"Dev UI: {args.dev_ui}")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
