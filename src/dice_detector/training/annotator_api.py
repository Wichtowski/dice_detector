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

        # Extra image sources: {"name": {"images": path, "annotations": path, "read_only": bool}}
        self.sources: dict[str, dict] = {
            "default": {"images": self.images_dir, "annotations": self.output_dir, "read_only": False}
        }
        if extra_sources:
            for name, paths in extra_sources.items():
                self.sources[name] = {
                    "images": Path(paths["images"]),
                    "annotations": Path(paths["annotations"]),
                    "read_only": paths.get("read_only", False),
                }

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
        def list_images(page: int = 1, per_page: int = 100, source: Optional[str] = None):
            all_images = self._get_all_image_list(source)
            total = len(all_images)
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            end = start + per_page
            page_images = all_images[start:end]
            return {
                "images": page_images,
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
            }

        @app.get("/api/images/{image_id}")
        def get_image_info(image_id: str):
            source_name, img_path = self._find_image_with_source(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                raise HTTPException(500, "Failed to read image")
            h, w = img.shape[:2]

            source = self.sources[source_name]
            annotations = self._load_annotations_from(image_id, source["annotations"])

            return {
                "id": image_id,
                "name": img_path.name,
                "width": w,
                "height": h,
                "url": f"/api/images/{image_id}/file",
                "annotations": annotations,
                "read_only": source.get("read_only", False),
                "source": source_name,
            }

        @app.get("/api/images/{image_id}/file")
        def get_image_file(image_id: str):
            img_path = self._find_image(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")
            return FileResponse(img_path)

        @app.post("/api/annotations")
        def save_annotations(req: SaveAnnotationsRequest):
            source_name, img_path = self._find_image_with_source(req.image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            if self.sources[source_name].get("read_only", False):
                raise HTTPException(403, "This image source is read-only")

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

    def _get_source_images(self, source_name: str) -> list[Path]:
        extensions = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
        images_dir = self.sources[source_name]["images"]
        images = []
        for ext in extensions:
            images.extend(images_dir.glob(f"*{ext}"))
            images.extend(images_dir.glob(f"*{ext.upper()}"))
        return sorted(images)

    def _get_all_image_list(self, source_filter: Optional[str] = None) -> list[dict]:
        result = []
        sources = [source_filter] if source_filter and source_filter in self.sources else list(self.sources.keys())
        for source_name in sources:
            source = self.sources[source_name]
            ann_dir = source["annotations"]
            read_only = source.get("read_only", False)
            for img in self._get_source_images(source_name):
                ann_path = ann_dir / f"{img.stem}.json"
                result.append({
                    "id": img.stem,
                    "name": img.name,
                    "annotated": ann_path.exists(),
                    "read_only": read_only,
                    "source": source_name,
                })
        return result

    def _find_image_with_source(self, image_id: str) -> tuple[str, Optional[Path]]:
        for source_name in self.sources:
            for img in self._get_source_images(source_name):
                if img.stem == image_id:
                    return source_name, img
        return "default", None

    def _find_image(self, image_id: str) -> Optional[Path]:
        _, path = self._find_image_with_source(image_id)
        return path

    def _load_annotations_from(self, image_id: str, ann_dir: Path) -> list[dict]:
        ann_path = ann_dir / f"{image_id}.json"
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

    def _load_annotations(self, image_id: str) -> list[dict]:
        return self._load_annotations_from(image_id, self.output_dir)


def main():
    parser = argparse.ArgumentParser(description="Dice Annotation Tool API")
    parser.add_argument("--images", type=str, default="data/images")
    parser.add_argument("--output", type=str, default="data/annotations")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev-ui", type=str, default=None, help="Vite dev server URL")
    parser.add_argument(
        "--extra-source",
        type=str,
        action="append",
        default=[],
        help="Extra image source: name:images_dir:annotations_dir[:ro]",
    )
    args = parser.parse_args()

    extra_sources = {}
    for src in args.extra_source:
        parts = src.split(":")
        if len(parts) >= 3:
            extra_sources[parts[0]] = {
                "images": parts[1],
                "annotations": parts[2],
                "read_only": len(parts) > 3 and parts[3] == "ro",
            }

    api = AnnotatorAPI(args.images, args.output, extra_sources=extra_sources or None)
    app = api.create_app(dev_ui_url=args.dev_ui)

    print(f"Starting Annotator API at http://{args.host}:{args.port}")
    print(f"Images: {args.images}")
    print(f"Output: {args.output}")
    if args.dev_ui:
        print(f"Dev UI: {args.dev_ui}")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
