import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
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
    is_verified: bool = False


class CropRequest(BaseModel):
    x: int
    y: int
    size: int


class ScaleRequest(BaseModel):
    size: int


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

        # Optional annotation goals override: {"per_face_goal": int, "type_goals": {"D6": 60, ...}}
        self.annotation_goals: dict = {}
        goals_path = Path("data/annotation_goals.json")
        if goals_path.exists():
            try:
                with open(goals_path) as f:
                    self.annotation_goals = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.annotation_goals = {}

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
        def list_images(page: int = 1, per_page: int = 100, source: Optional[str] = None, to_verify: bool = False):
            all_images = self._get_all_image_list(source)
            total = len(all_images)
            total_annotated = sum(1 for img in all_images if img["annotated"])
            total_verified = sum(1 for img in all_images if img["verified"])
            if to_verify:
                all_images = [
                    img for img in all_images
                    if img["annotated"] and not img["verified"] and not img["read_only"]
                ]
            filtered_total = len(all_images)
            total_pages = max(1, (filtered_total + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            end = start + per_page
            page_images = all_images[start:end]
            return {
                "images": page_images,
                "page": page,
                "per_page": per_page,
                "total": filtered_total if to_verify else total,
                "total_annotated": total_annotated,
                "total_verified": total_verified,
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

            ann_path = Path(source["annotations"]) / f"{image_id}.json"
            is_verified = False
            if ann_path.exists():
                try:
                    with open(ann_path) as f:
                        is_verified = json.load(f).get("is_verified", False)
                except (json.JSONDecodeError, OSError):
                    is_verified = False

            return {
                "id": image_id,
                "name": img_path.name,
                "width": w,
                "height": h,
                "url": f"/api/images/{image_id}/file",
                "annotations": annotations,
                "read_only": source.get("read_only", False),
                "source": source_name,
                "is_verified": is_verified,
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
                is_verified=req.is_verified,
            )

            out_dir = Path(self.sources[source_name]["annotations"])
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{req.image_id}.json"
            with open(out_path, "w") as f:
                f.write(image_annotation.model_dump_json(indent=2))

            # Auto-generate YOLO label
            labels_dir = out_dir.parent / "labels"
            labels_dir.mkdir(parents=True, exist_ok=True)
            yolo_lines = []
            type_map = {"D4": 0, "D6": 1, "D8": 2, "D10": 3, "D12": 4, "D20": 5, "D100": 6}
            for ann in req.annotations:
                cid = type_map.get(ann.dice_type)
                if cid is None:
                    continue
                xc = (ann.bbox.x + ann.bbox.width / 2) / w
                yc = (ann.bbox.y + ann.bbox.height / 2) / h
                bw = ann.bbox.width / w
                bh = ann.bbox.height / h
                xc = max(0.0, min(1.0, xc))
                yc = max(0.0, min(1.0, yc))
                bw = max(0.001, min(1.0, bw))
                bh = max(0.001, min(1.0, bh))
                yolo_lines.append(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
            label_path = labels_dir / f"{req.image_id}.txt"
            label_path.write_text("\n".join(yolo_lines) + "\n" if yolo_lines else "")

            return {"status": "saved", "path": str(out_path), "count": len(dice_annotations), "is_verified": req.is_verified}

        @app.get("/api/config")
        def get_config():
            return {
                "dice_types": [t.value for t in DiceType if t != DiceType.UNKNOWN],
                "ambiguity_reasons": [r.value for r in AmbiguityReason],
                "special_values": [s.value for s in SpecialValue],
                "d4_styles": [s.value for s in D4Style],
            }

        @app.get("/api/stats")
        def get_stats():
            # Expected value faces per dice type (for goal/coverage tracking).
            faces_map: dict[str, list[int]] = {
                "D4": [1, 2, 3, 4],
                "D6": [1, 2, 3, 4, 5, 6],
                "D8": list(range(1, 9)),
                "D10": list(range(0, 10)),
                "D12": list(range(1, 13)),
                "D20": list(range(1, 21)),
                "D100": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
            }
            per_face_goal = self.annotation_goals.get("per_face_goal", 10)
            type_goal_override = self.annotation_goals.get("type_goals", {})

            # Aggregate counts across every source's annotation JSONs.
            type_counts: dict[str, int] = {t: 0 for t in faces_map}
            value_counts: dict[str, dict[int, int]] = {t: {} for t in faces_map}
            seen_paths: set[str] = set()
            total = 0
            for source in self.sources.values():
                ann_dir = Path(source["annotations"])
                if not ann_dir.exists():
                    continue
                for ann_path in ann_dir.glob("*.json"):
                    key = str(ann_path.resolve())
                    if key in seen_paths:
                        continue
                    seen_paths.add(key)
                    try:
                        with open(ann_path) as f:
                            data = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue
                    for die in data.get("dice", []):
                        dtype = die.get("dice_type", "UNKNOWN")
                        if dtype not in type_counts:
                            continue
                        type_counts[dtype] += 1
                        total += 1
                        val = die.get("value")
                        if val is not None:
                            value_counts[dtype][int(val)] = value_counts[dtype].get(int(val), 0) + 1

            types = []
            for dtype, faces in faces_map.items():
                vc = value_counts[dtype]
                # Merge expected faces with any out-of-range values that were annotated.
                all_faces = sorted(set(faces) | set(vc.keys()))
                values = {str(fv): vc.get(fv, 0) for fv in all_faces}
                faces_covered = sum(1 for fv in faces if vc.get(fv, 0) > 0)
                faces_complete = sum(1 for fv in faces if vc.get(fv, 0) >= per_face_goal)
                goal = type_goal_override.get(dtype, len(faces) * per_face_goal)
                types.append({
                    "type": dtype,
                    "count": type_counts[dtype],
                    "goal": goal,
                    "faces_total": len(faces),
                    "faces_covered": faces_covered,
                    "faces_complete": faces_complete,
                    "values": values,
                })

            return {
                "total": total,
                "per_face_goal": per_face_goal,
                "types": types,
            }

        @app.post("/api/camera/capture")
        async def camera_capture(image: UploadFile = File(...)):
            web_images_dir = Path("data/web/images")
            web_ann_dir = Path("data/web/annotations")
            web_images_dir.mkdir(parents=True, exist_ok=True)
            web_ann_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"capture_{timestamp}.png"
            save_path = web_images_dir / filename

            contents = await image.read()
            save_path.write_bytes(contents)

            image_id = save_path.stem

            # Register web source if not already present
            if "web" not in self.sources:
                self.sources["web"] = {
                    "images": web_images_dir,
                    "annotations": web_ann_dir,
                    "read_only": False,
                }

            return {"status": "saved", "image_id": image_id, "filename": filename}

        @app.post("/api/images/upload")
        async def upload_image(image: UploadFile = File(...)):
            web_images_dir = Path("data/web/images")
            web_ann_dir = Path("data/web/annotations")
            web_images_dir.mkdir(parents=True, exist_ok=True)
            web_ann_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            orig = Path(image.filename or "upload.png")
            ext = orig.suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                ext = ".png"
            filename = f"upload_{timestamp}{ext}"
            save_path = web_images_dir / filename

            contents = await image.read()
            save_path.write_bytes(contents)

            if "web" not in self.sources:
                self.sources["web"] = {
                    "images": web_images_dir,
                    "annotations": web_ann_dir,
                    "read_only": False,
                }

            return {"status": "saved", "image_id": save_path.stem, "filename": filename}

        @app.post("/api/images/{image_id}/crop")
        def crop_image(image_id: str, req: CropRequest):
            source_name, img_path = self._find_image_with_source(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            if self.sources[source_name].get("read_only", False):
                raise HTTPException(403, "This image source is read-only")

            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                raise HTTPException(500, "Failed to read image")
            h, w = img.shape[:2]

            x = max(0, min(int(req.x), w - 1))
            y = max(0, min(int(req.y), h - 1))
            size = max(1, min(int(req.size), w - x, h - y))
            cropped = img[y:y + size, x:x + size]
            if not cv2.imwrite(str(img_path), cropped):
                raise HTTPException(500, "Failed to write cropped image")

            nh, nw = cropped.shape[:2]

            # Remap existing annotations into the cropped coordinate space.
            ann_dir = Path(self.sources[source_name]["annotations"])
            ann_path = ann_dir / f"{image_id}.json"
            if ann_path.exists():
                try:
                    with open(ann_path) as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    data = None
                if data is not None:
                    kept = []
                    for die in data.get("dice", []):
                        bbox = die.get("bbox", {})
                        # Intersect die bbox with the crop region, then shift.
                        bx0 = bbox.get("x", 0)
                        by0 = bbox.get("y", 0)
                        bx1 = bx0 + bbox.get("width", 0)
                        by1 = by0 + bbox.get("height", 0)
                        ix0 = max(bx0, x)
                        iy0 = max(by0, y)
                        ix1 = min(bx1, x + size)
                        iy1 = min(by1, y + size)
                        if ix1 <= ix0 or iy1 <= iy0:
                            continue  # die fully outside crop
                        die["bbox"] = {
                            "x": int(ix0 - x),
                            "y": int(iy0 - y),
                            "width": int(ix1 - ix0),
                            "height": int(iy1 - iy0),
                        }
                        kept.append(die)
                    data["dice"] = kept
                    data["image_width"] = nw
                    data["image_height"] = nh
                    with open(ann_path, "w") as f:
                        json.dump(data, f, indent=2)

                    # Regenerate YOLO label from the remapped annotations.
                    labels_dir = ann_dir.parent / "labels"
                    labels_dir.mkdir(parents=True, exist_ok=True)
                    type_map = {"D4": 0, "D6": 1, "D8": 2, "D10": 3, "D12": 4, "D20": 5, "D100": 6}
                    lines = []
                    for die in kept:
                        cid = type_map.get(die.get("dice_type"))
                        if cid is None:
                            continue
                        b = die["bbox"]
                        xc = (b["x"] + b["width"] / 2) / nw
                        yc = (b["y"] + b["height"] / 2) / nh
                        bw = b["width"] / nw
                        bh = b["height"] / nh
                        xc = max(0.0, min(1.0, xc))
                        yc = max(0.0, min(1.0, yc))
                        bw = max(0.001, min(1.0, bw))
                        bh = max(0.001, min(1.0, bh))
                        lines.append(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
                    (labels_dir / f"{image_id}.txt").write_text(
                        "\n".join(lines) + "\n" if lines else ""
                    )

            return {"status": "cropped", "width": nw, "height": nh}

        @app.post("/api/images/{image_id}/scale")
        def scale_image(image_id: str, req: ScaleRequest):
            source_name, img_path = self._find_image_with_source(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            if self.sources[source_name].get("read_only", False):
                raise HTTPException(403, "This image source is read-only")

            target = int(req.size)
            if target < 16:
                raise HTTPException(400, "Target size too small")

            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                raise HTTPException(500, "Failed to read image")
            h, w = img.shape[:2]

            # Scale so the longest side equals the target, preserving aspect ratio.
            longest = max(w, h)
            ratio = target / longest
            nw = max(1, round(w * ratio))
            nh = max(1, round(h * ratio))
            interp = cv2.INTER_AREA if ratio < 1 else cv2.INTER_CUBIC
            resized = cv2.resize(img, (nw, nh), interpolation=interp)
            if not cv2.imwrite(str(img_path), resized):
                raise HTTPException(500, "Failed to write scaled image")

            sx = nw / w
            sy = nh / h

            # Scale existing annotations by the resize ratios.
            ann_dir = Path(self.sources[source_name]["annotations"])
            ann_path = ann_dir / f"{image_id}.json"
            if ann_path.exists():
                try:
                    with open(ann_path) as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    data = None
                if data is not None:
                    for die in data.get("dice", []):
                        bbox = die.get("bbox", {})
                        die["bbox"] = {
                            "x": int(round(bbox.get("x", 0) * sx)),
                            "y": int(round(bbox.get("y", 0) * sy)),
                            "width": int(round(bbox.get("width", 0) * sx)),
                            "height": int(round(bbox.get("height", 0) * sy)),
                        }
                    data["image_width"] = nw
                    data["image_height"] = nh
                    with open(ann_path, "w") as f:
                        json.dump(data, f, indent=2)

                    # Regenerate YOLO label (normalized coords are unchanged,
                    # but rewrite for consistency with the new dimensions).
                    labels_dir = ann_dir.parent / "labels"
                    labels_dir.mkdir(parents=True, exist_ok=True)
                    type_map = {"D4": 0, "D6": 1, "D8": 2, "D10": 3, "D12": 4, "D20": 5, "D100": 6}
                    lines = []
                    for die in data.get("dice", []):
                        cid = type_map.get(die.get("dice_type"))
                        if cid is None:
                            continue
                        b = die["bbox"]
                        xc = (b["x"] + b["width"] / 2) / nw
                        yc = (b["y"] + b["height"] / 2) / nh
                        bw = b["width"] / nw
                        bh = b["height"] / nh
                        xc = max(0.0, min(1.0, xc))
                        yc = max(0.0, min(1.0, yc))
                        bw = max(0.001, min(1.0, bw))
                        bh = max(0.001, min(1.0, bh))
                        lines.append(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
                    (labels_dir / f"{image_id}.txt").write_text(
                        "\n".join(lines) + "\n" if lines else ""
                    )

            return {"status": "scaled", "width": nw, "height": nh}

        @app.delete("/api/images/{image_id}")
        def delete_image(image_id: str):
            source_name, img_path = self._find_image_with_source(image_id)
            if not img_path:
                raise HTTPException(404, "Image not found")

            if self.sources[source_name].get("read_only", False):
                raise HTTPException(403, "This image source is read-only")

            # Delete image file
            img_path.unlink(missing_ok=True)

            # Delete annotation file if it exists
            ann_dir = Path(self.sources[source_name]["annotations"])
            ann_path = ann_dir / f"{image_id}.json"
            ann_path.unlink(missing_ok=True)

            return {"status": "deleted", "image_id": image_id}

        @app.post("/api/convert-labels")
        def convert_labels_to_yolo(source: Optional[str] = None):
            """Convert JSON annotations to YOLO .txt labels for all sources."""
            sources = [source] if source and source in self.sources else list(self.sources.keys())
            total = 0
            for src_name in sources:
                src = self.sources[src_name]
                if src.get("read_only", False):
                    continue
                ann_dir = Path(src["annotations"])
                # Labels go next to images dir's parent / labels, or annotations/../labels
                labels_dir = ann_dir.parent / "labels"
                labels_dir.mkdir(parents=True, exist_ok=True)
                for ann_path in sorted(ann_dir.glob("*.json")):
                    try:
                        with open(ann_path) as f:
                            data = json.load(f)
                        img_w = data["image_width"]
                        img_h = data["image_height"]
                        lines = []
                        for die in data.get("dice", []):
                            dice_type = die.get("dice_type", "UNKNOWN")
                            class_id = {
                                "D4": 0, "D6": 1, "D8": 2, "D10": 3,
                                "D12": 4, "D20": 5, "D100": 6,
                            }.get(dice_type)
                            if class_id is None:
                                continue
                            bbox = die["bbox"]
                            xc = (bbox["x"] + bbox["width"] / 2) / img_w
                            yc = (bbox["y"] + bbox["height"] / 2) / img_h
                            w = bbox["width"] / img_w
                            h = bbox["height"] / img_h
                            xc = max(0.0, min(1.0, xc))
                            yc = max(0.0, min(1.0, yc))
                            w = max(0.001, min(1.0, w))
                            h = max(0.001, min(1.0, h))
                            lines.append(f"{class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
                        label_path = labels_dir / f"{ann_path.stem}.txt"
                        label_path.write_text("\n".join(lines) + "\n" if lines else "")
                        total += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
            return {"status": "converted", "total": total}

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
                annotated = ann_path.exists()
                verified = False
                if annotated:
                    try:
                        with open(ann_path) as f:
                            verified = json.load(f).get("is_verified", False)
                    except (json.JSONDecodeError, OSError):
                        verified = False
                result.append({
                    "id": img.stem,
                    "name": img.name,
                    "annotated": annotated,
                    "verified": verified,
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
