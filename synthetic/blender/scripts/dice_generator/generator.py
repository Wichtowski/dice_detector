import json
import logging
import math
import random
import traceback
from datetime import datetime
from pathlib import Path

from .bbox import (
    assign_pass_indices,
    compute_bboxes_from_index_pass,
    compute_object_bbox_2d,
    setup_object_index_pass,
)
from .camera import get_or_create_camera, randomize_camera
from .config import GeneratorConfig
from .parsers import parse_die_name, parse_face_marker_name
from .physics import clear_physics_cache, setup_rigid_body, simulate_until_settled
from .scene import (
    clear_generated_objects,
    compute_tray_raw_bounds,
    compute_tray_spawn_bounds,
    determine_rolled_value,
    duplicate_die_asset,
    get_dice_from_collections,
    get_die_markers,
    get_die_markers_recursive,
)

try:
    import bpy
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False

GENERATOR_VERSION = "2.0.0"
SIX_NINE_AMBIGUITY_DICES = ["D10", "D12", "D20"]


def _kelvin_to_rgb(kelvin: float) -> tuple[float, float, float]:
    """Convert color temperature in Kelvin to normalized RGB (simplified blackbody)."""
    temp = kelvin / 100.0

    # Red
    if temp <= 66:
        r = 1.0
    else:
        r = max(0.0, min(1.0, 1.292936186 * ((temp - 60) ** -0.1332047592)))

    # Green
    if temp <= 66:
        g = max(0.0, min(1.0, 0.390081579 * math.log(temp) - 0.631841444))
    else:
        g = max(0.0, min(1.0, 1.129890861 * ((temp - 60) ** -0.0755148492)))

    # Blue
    if temp >= 66:
        b = 1.0
    elif temp <= 19:
        b = 0.0
    else:
        b = max(0.0, min(1.0, 0.543206789 * math.log(temp - 10) - 1.19625408))

    return (r, g, b)


class BlenderDiceGenerator:
    """Generates synthetic dice dataset using prepared Blender assets."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.images_dir = self.output_dir / "images"
        self.images_annotated_dir = self.output_dir / "images_annotated"
        self.annotations_dir = self.output_dir / "annotations"
        self.labels_dir = self.output_dir / "labels"
        self.metadata_dir = self.output_dir / "metadata"
        self.logs_dir = self.output_dir / "logs"

        if config.random_seed is not None:
            random.seed(config.random_seed)

        self.available_dice = []
        self.spawn_bounds = None
        self.tray_bounds = None
        self.generated_dice = []
        self.visible_source_dice = []  # Source dice that are visible (not hidden)
        self._compositor_available = False
        self.logger = None

    def _setup_logging(self):
        """Set up file logging for errors."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        worker_suffix = f"_w{self.config.worker_id}" if self.config.worker_id > 0 else ""
        log_file = self.logs_dir / f"generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}{worker_suffix}.log"

        self.logger = logging.getLogger("dice_generator")
        self.logger.setLevel(logging.DEBUG)

        # File handler for all logs
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(fh)

        # Console handler for info+
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.logger.addHandler(ch)

        self.logger.info(f"Logging to {log_file}")

    def initialize(self) -> bool:
        """Initialize generator with scene data.

        Returns:
            True if initialization successful.
        """
        if not BLENDER_AVAILABLE:
            print("Error: Blender modules not available")
            return False

        # Discover available dice assets
        self.available_dice = get_dice_from_collections(self.config)
        if not self.available_dice:
            print("Error: No dice assets found in collections")
            print(f"  Searched collections: {self.config.dice_collections}")
            print(f"  Searched dice types: {self.config.dice_types}")
            return False

        print(f"Found {len(self.available_dice)} dice assets:")
        total_markers = 0
        for die in self.available_dice:
            parsed = parse_die_name(die.name)
            markers = get_die_markers(die)
            if not markers:
                markers = get_die_markers_recursive(die)
            total_markers += len(markers)
            variant_str = f" ({parsed.variant})" if parsed and parsed.variant else ""
            children_info = f", {len(die.children)} children" if die.children else ""
            print(f"  {die.name}: {parsed.dice_type if parsed else '?'}{variant_str}, {len(markers)} markers{children_info}")

            # Debug: show first few children if no markers found
            if not markers and die.children:
                for child in list(die.children)[:3]:
                    print(f"    Child: {child.name} (type={child.type})")

        if total_markers == 0:
            print("  WARNING: No face markers found on any dice! Value detection will fail.")
            print("  Expected marker names like: D20_14, D6_3, D4_2, etc.")

        # Compute tray bounds (raw for camera, with margin for spawning)
        self.tray_bounds = compute_tray_raw_bounds(self.config)
        self.spawn_bounds = compute_tray_spawn_bounds(self.config)
        print(f"Spawn bounds: x=[{self.spawn_bounds[0]:.3f}, {self.spawn_bounds[1]:.3f}], "
              f"y=[{self.spawn_bounds[2]:.3f}, {self.spawn_bounds[3]:.3f}]")

        # Set up render settings
        self._setup_render_settings()

        # Enable Object Index pass for pixel-perfect bboxes
        self._compositor_available = setup_object_index_pass()

        # Set up tray physics
        self._setup_tray_physics()

        return True

    def _setup_render_settings(self):
        """Configure Blender render settings."""
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.render.resolution_x = self.config.image_width
        scene.render.resolution_y = self.config.image_height
        scene.cycles.samples = self.config.render_samples

        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.05
        scene.cycles.max_bounces = 4
        scene.cycles.diffuse_bounces = 2
        scene.cycles.glossy_bounces = 2
        scene.cycles.transmission_bounces = 4

        # Use GPU if available
        scene.cycles.device = "GPU"
        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs:
            prefs.preferences.compute_device_type = "HIP"  # AMD
            prefs.preferences.get_devices()
            for device in prefs.preferences.devices:
                device.use = True

        if self.config.enable_denoising:
            scene.cycles.use_denoising = True

    def _setup_tray_physics(self):
        """Set up passive rigid bodies for tray walls/floor."""
        utils_coll = bpy.data.collections.get(self.config.tray_collection_name)
        if not utils_coll:
            return

        for obj in utils_coll.objects:
            if obj.type == "MESH" and obj.rigid_body is None:
                setup_rigid_body(obj, self.config, is_passive=True)

    def _hide_source_dice_collections(self):
        """Hide all source dice collections so only generated dice are visible."""
        for coll_name in self.config.dice_collections:
            coll = bpy.data.collections.get(coll_name)
            if coll:
                # Hide collection from render and viewport
                coll.hide_render = True
                coll.hide_viewport = True
                print(f"  Hidden collection: {coll_name}")

                # Also hide in view layer if it exists
                view_layer = bpy.context.view_layer
                layer_coll = self._find_layer_collection(view_layer.layer_collection, coll_name)
                if layer_coll:
                    layer_coll.exclude = True

                # Hide all individual objects in the collection
                for obj in coll.objects:
                    obj.hide_render = True
                    obj.hide_viewport = True

    def _sample_dice_count(self) -> int:
        """Sample a dice count from the configured distribution."""
        dist = self.config.dice_count_distribution
        ranges = [(r[0], r[1]) for r in dist]
        weights = [r[2] for r in dist]
        chosen = random.choices(ranges, weights=weights, k=1)[0]
        return random.randint(chosen[0], chosen[1])

    def _randomize_source_dice_visibility(self):
        """Randomly show source dice with class-balanced selection.

        Samples dice count from the configured distribution to produce
        varied scene densities (isolated, clustered, crowded).
        Balances selection across all dice types via round-robin so each
        class gets roughly equal representation across the dataset.
        """
        self.visible_source_dice = []
        num_visible = self._sample_dice_count()

        # Group all available dice by type
        by_type = {}
        for d in self.available_dice:
            parsed = parse_die_name(d.name)
            if parsed:
                dtype = parsed.dice_type
                by_type.setdefault(dtype, []).append(d)

        target = min(num_visible, len(self.available_dice))

        # Round-robin across types to ensure balance
        types = list(by_type.keys())
        random.shuffle(types)
        visible_dice = []
        type_idx = 0
        while len(visible_dice) < target and types:
            dtype = types[type_idx % len(types)]
            available = [d for d in by_type[dtype] if d not in visible_dice]
            if available:
                visible_dice.append(random.choice(available))
            else:
                types.remove(dtype)
                if not types:
                    break
                type_idx = type_idx % len(types)
                continue
            type_idx += 1

        # First hide all source dice
        for die in self.available_dice:
            die.hide_render = True
            die.hide_viewport = True
            # Also hide children (markers)
            for child in die.children:
                child.hide_render = True
                child.hide_viewport = True

        # Compute center oscillation offset for this render
        x_min, x_max, y_min, y_max = self.spawn_bounds
        center_x = (x_min + x_max) / 2
        center_y = (y_min + y_max) / 2
        span_x = (x_max - x_min) / 2
        span_y = (y_max - y_min) / 2

        # Random shift of the cluster center (slight offset from tray center)
        shift_x = random.gauss(0, span_x * 0.15)
        shift_y = random.gauss(0, span_y * 0.15)

        # Then show selected ones and randomize their positions
        for die in visible_dice:
            die.hide_render = False
            die.hide_viewport = False
            self.visible_source_dice.append(die)

            # Position oscillating around center with gaussian spread
            die.location.x = center_x + shift_x + random.gauss(0, span_x * 0.35)
            die.location.y = center_y + shift_y + random.gauss(0, span_y * 0.35)
            # Clamp to spawn bounds
            die.location.x = max(x_min, min(x_max, die.location.x))
            die.location.y = max(y_min, min(y_max, die.location.y))
            die.location.z = self.config.spawn_height  # Drop from spawn height

            # Randomize rotation
            die.rotation_euler.x = random.uniform(0, 2 * math.pi)
            die.rotation_euler.y = random.uniform(0, 2 * math.pi)
            die.rotation_euler.z = random.uniform(0, 2 * math.pi)

            # Show children too
            for child in die.children:
                child.hide_render = False
                child.hide_viewport = False

        print(f"  Showing {len(visible_dice)}/{len(self.available_dice)} source dice")

    def _randomize_resolution(self):
        """Randomize image resolution from configured presets."""
        if not self.config.randomize_resolution:
            return

        preset = random.choice(self.config.resolution_presets)
        base = self.config.resolution_base

        ratio_map = {
            "16:9": (base * 16 // 9, base),
            "9:16": (base, base * 16 // 9),
            "1:1": (base, base),
            "4:3": (base * 4 // 3, base),
            "3:4": (base, base * 4 // 3),
        }

        w, h = ratio_map.get(preset, (1920, 1080))
        scene = bpy.context.scene
        scene.render.resolution_x = w
        scene.render.resolution_y = h
        # Update config so camera height computation uses correct aspect
        self.config.image_width = w
        self.config.image_height = h

    def _randomize_lighting(self):
        """Randomize scene lighting for augmentation."""
        if not self.config.randomize_lighting:
            return

        for obj in bpy.data.objects:
            if obj.type != "LIGHT":
                continue

            light = obj.data

            # Randomize energy
            light.energy = random.uniform(
                self.config.light_energy_min,
                self.config.light_energy_max,
            )

            # Randomize color temperature (warm to cool)
            temp = random.uniform(
                self.config.light_color_temperature_min,
                self.config.light_color_temperature_max,
            )
            # Convert temperature to RGB (simplified blackbody approximation)
            light.color = _kelvin_to_rgb(temp)

    def _find_layer_collection(self, layer_coll, name: str):
        """Recursively find a layer collection by name."""
        if layer_coll.name == name:
            return layer_coll
        for child in layer_coll.children:
            result = self._find_layer_collection(child, name)
            if result:
                return result
        return None

    def generate_dataset(self):
        """Generate the complete dataset."""
        self._ensure_dirs()
        self._setup_logging()

        if not self.initialize():
            self.logger.error("Failed to initialize generator")
            return

        num_images = self.config.num_images
        indices = self.config.indices or list(range(self.config.start_index, self.config.start_index + num_images))
        dist = self.config.dice_count_distribution
        self.logger.info(f"Dice count distribution:")
        total_weight = sum(r[2] for r in dist)
        for r in dist:
            pct = r[2] / total_weight * 100
            self.logger.info(f"  {r[0]:2d}-{r[1]:2d} dice: {pct:.0f}%")
        self.logger.info(f"Generating {len(indices)} images...")

        successful = 0
        errors = []
        for i, global_index in enumerate(indices):
            try:
                self._generate_single_image(global_index)
                successful += 1
                if (i + 1) % 10 == 0:
                    self.logger.info(f"[Worker {self.config.worker_id}] Progress: {i + 1}/{len(indices)} images ({successful} successful)")

            except Exception as e:
                error_msg = f"[Worker {self.config.worker_id}] Error generating image {global_index}: {e}\n{traceback.format_exc()}"
                self.logger.error(error_msg)
                errors.append({"image_index": global_index, "error": str(e), "traceback": traceback.format_exc()})

        self._save_generation_metadata(successful, errors)
        self.logger.info(f"[Worker {self.config.worker_id}] Dataset generation complete: {successful}/{len(indices)} images")

    def _ensure_dirs(self):
        """Create output directories."""
        self.images_dir.mkdir(parents=True, exist_ok=True)
        if self.config.create_annotated_images:
            self.images_annotated_dir.mkdir(parents=True, exist_ok=True)
        self.annotations_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _generate_single_image(self, index: int):
        """Generate a single image with annotations."""
        image_id = f"render_{index:06d}"
        image_path = self.images_dir / f"{image_id}.png"
        annotation_path = self.annotations_dir / f"{image_id}.json"

        if self.config.skip_existing and image_path.exists() and annotation_path.exists():
            self.logger.debug(f"Skipping {image_id} (already exists)")
            return

        # Randomize resolution for this image
        self._randomize_resolution()

        # Randomize lighting
        self._randomize_lighting()

        # Clear physics cache for fresh simulation
        clear_physics_cache()

        # Randomize which source dice are visible and their positions
        self._randomize_source_dice_visibility()

        self._update_viewport("Randomized source dice visibility")

        # Set up rigid bodies for visible dice
        for die in self.visible_source_dice:
            if die.rigid_body is None:
                setup_rigid_body(die, self.config, is_passive=False)

        # Run physics simulation to settle dice
        self._update_viewport("Running physics simulation...")
        settled_frame = simulate_until_settled(self.config)
        bpy.context.scene.frame_set(settled_frame)
        self._update_viewport(f"Physics settled at frame {settled_frame}")

        # Randomize camera
        camera = get_or_create_camera()
        if camera:
            randomize_camera(camera, self.config, tray_bounds=self.tray_bounds)
            bpy.context.scene.camera = camera

        # Assign unique pass indices for pixel-perfect bbox detection
        assign_pass_indices(self.visible_source_dice)

        # Render
        bpy.context.scene.render.filepath = str(image_path)
        bpy.ops.render.render(write_still=True)

        # Compute pixel-perfect bboxes from rendered Object Index pass
        bbox_map = {}
        if self._compositor_available:
            bbox_map = compute_bboxes_from_index_pass(
                self.visible_source_dice,
                self.config.image_width,
                self.config.image_height,
            )

        # Fallback: use projection-based bboxes for dice not covered by index pass
        if not bbox_map:
            camera = bpy.context.scene.camera
            for die in self.visible_source_dice:
                bbox = compute_object_bbox_2d(
                    die, camera, self.config.image_width, self.config.image_height,
                )
                if bbox:
                    bbox_map[die.name] = bbox

        # Collect annotations using pixel-perfect bboxes
        dice_annotations = self._collect_source_dice_annotations(bbox_map)

        # Save annotation (JSON + YOLO labels)
        self._save_annotation(image_id, dice_annotations)
        self._save_yolo_label(image_id, dice_annotations)

        # Create annotated image with bboxes (only if enabled)
        if self.config.create_annotated_images:
            self._create_annotated_image(image_path, image_id, dice_annotations)

    def _update_viewport(self, message: str = ""):
        """Update Blender viewport in interactive mode."""
        if not self.config.debug_interactive_mode:
            return

        # Force viewport update
        bpy.context.view_layer.update()

        # Redraw all areas
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

        if message:
            print(f"  [DEBUG] {message}")

    def _clear_generated_dice(self):
        """Remove all generated dice from the scene."""
        clear_generated_objects("Gen_Die_")
        self.generated_dice = []

    def _place_random_die(self):
        """Place a random die in the scene above the tray."""
        if not self.available_dice:
            return

        # Select random source die
        source_die = random.choice(self.available_dice)

        # Create unique name
        die_id = len(self.generated_dice)
        new_name = f"Gen_Die_{die_id:04d}"

        # Duplicate
        new_die = duplicate_die_asset(source_die, new_name)
        if not new_die:
            return

        self.generated_dice.append(new_name)

        # Random position within spawn bounds
        x_min, x_max, y_min, y_max = self.spawn_bounds
        x = random.uniform(x_min, x_max)
        y = random.uniform(y_min, y_max)
        z = self.config.spawn_height

        new_die.location = (x, y, z)

        # Random rotation
        new_die.rotation_euler = (
            random.uniform(0, 2 * math.pi),
            random.uniform(0, 2 * math.pi),
            random.uniform(0, 2 * math.pi),
        )

        # Set up rigid body
        setup_rigid_body(new_die, self.config, is_passive=False)

    def _collect_source_dice_annotations(self, bbox_map: dict) -> list[dict]:
        """Collect annotations for visible source dice using pixel-perfect bboxes.

        Args:
            bbox_map: Dict mapping die name -> bbox dict from index pass.
        """
        annotations = []

        for die in self.visible_source_dice:
            # Only annotate dice that are actually visible in the render
            bbox = bbox_map.get(die.name)
            if not bbox:
                continue  # Not visible in render (occluded, out of frame, etc.)

            if bbox["width"] < 5 or bbox["height"] < 5:
                continue  # Too small to be useful

            # Parse die name to get type and material
            parsed_die = parse_die_name(die.name)
            if not parsed_die:
                continue

            # Determine value from marker
            value_result = determine_rolled_value(die, self.config)
            if not value_result:
                print(f"  Warning: Could not determine value for {die.name}")
                continue

            value, special_value, marker_name = value_result

            # Compute orientation (Z rotation in degrees)
            orientation = math.degrees(die.rotation_euler.z) % 360

            # Check for ambiguity
            ambiguous = False
            ambiguity_reasons = []

            if value in (6, 9) and parsed_die.dice_type in SIX_NINE_AMBIGUITY_DICES:
                ambiguity_reasons.append("possible_6_9_confusion")
                ambiguous = True

            annotations.append({
                "bbox": bbox,
                "dice_type": parsed_die.dice_type,
                "material_number": parsed_die.material_number,
                "value": value,
                "special_value": special_value,
                "orientation_degrees": round(orientation, 1),
                "ambiguous": ambiguous,
                "ambiguity_reasons": ambiguity_reasons,
                "source_object": die.name,
                "top_marker": marker_name,
                "variant": parsed_die.variant,
            })

        return annotations

    def _create_annotated_image(self, image_path: Path, image_id: str, annotations: list):
        """Create annotated image with bounding boxes drawn."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            print("  Warning: PIL not available, skipping annotated image")
            return

        try:
            img = Image.open(image_path)
            draw = ImageDraw.Draw(img)

            # Try to load a font, fall back to default
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 14)
            except (OSError, RuntimeError):
                font = ImageFont.load_default()

            # Color map for dice types
            colors = {
                "D4": "#FF6B6B",
                "D6": "#4ECDC4",
                "D8": "#45B7D1",
                "D10": "#96CEB4",
                "D12": "#FFEAA7",
                "D20": "#DDA0DD",
                "D100": "#98D8C8",
            }

            for ann in annotations:
                bbox = ann["bbox"]
                dice_type = ann["dice_type"]
                value = ann["value"]
                variant = ann.get("variant")

                color = colors.get(dice_type, "#FFFFFF")

                # Draw rectangle
                x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
                draw.rectangle([x, y, x + w, y + h], outline=color, width=2)

                # Build label with variant info
                label = f"{dice_type}: {value}"
                if variant:
                    label += f" ({variant})"
                draw.text((x, y - 16), label, fill=color, font=font)

            # Save annotated image
            annotated_path = self.images_annotated_dir / f"{image_id}.png"
            img.save(annotated_path)

        except Exception as e:
            print(f"  Warning: Failed to create annotated image: {e}")

    def _collect_annotations(self) -> list[dict]:
        """Collect annotations for all generated dice after physics."""
        annotations = []
        camera = bpy.context.scene.camera
        width = self.config.image_width
        height = self.config.image_height

        for obj_name in self.generated_dice:
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                continue

            # Determine rolled value from markers
            value_result = determine_rolled_value(obj, self.config)
            if not value_result:
                print(f"  Warning: Could not determine value for {obj_name}")
                continue

            value, special_value, marker_name = value_result

            # Parse marker to get dice type
            parsed_marker = parse_face_marker_name(marker_name)
            if not parsed_marker:
                continue

            dice_type = parsed_marker.dice_type

            # Get material number from original source
            material_number = self._get_material_number(obj)

            # Compute 2D bbox
            bbox = compute_object_bbox_2d(obj, camera, width, height)
            if not bbox:
                continue

            # Compute orientation (Z rotation in degrees)
            orientation = math.degrees(obj.rotation_euler.z) % 360

            # Check for ambiguity
            ambiguous = False
            ambiguity_reasons = []

            if value in (6, 9) and dice_type in SIX_NINE_AMBIGUITY_DICES:
                ambiguity_reasons.append("possible_6_9_confusion")
                ambiguous = True

            annotations.append({
                "bbox": bbox,
                "dice_type": dice_type,
                "material_number": material_number,
                "value": value,
                "special_value": special_value,
                "orientation_degrees": round(orientation, 1),
                "ambiguous": ambiguous,
                "ambiguity_reasons": ambiguity_reasons,
                "source_object": obj_name,
                "top_marker": marker_name,
            })

        return annotations

    def _get_material_number(self, obj) -> int:
        """Get material number by finding the original source die."""
        if not obj.data:
            return 1

        # Search collections for matching mesh data
        for coll_name in self.config.dice_collections:
            coll = bpy.data.collections.get(coll_name)
            if not coll:
                continue

            for coll_obj in coll.objects:
                if coll_obj.data and coll_obj.data.name == obj.data.name:
                    parsed = parse_die_name(coll_obj.name)
                    if parsed:
                        return parsed.material_number

        return 1

    def _save_annotation(self, image_id: str, dice_annotations: list):
        """Save annotation to JSON file."""
        camera = bpy.context.scene.camera

        annotation = {
            "image_path": f"images/{image_id}.png",
            "image_width": self.config.image_width,
            "image_height": self.config.image_height,
            "dice": dice_annotations,
            "source": "blender",
            "metadata": {
                "camera": {
                    "location": list(camera.location) if camera else None,
                    "rotation": list(camera.rotation_euler) if camera else None,
                    "focal_length": camera.data.lens if camera else None,
                },
                "physics": {
                    "friction": self.config.rigid_body_friction,
                    "bounciness": self.config.rigid_body_bounciness,
                },
                "generator_version": GENERATOR_VERSION,
                "timestamp": datetime.now().isoformat(),
            },
        }

        annotation_path = self.annotations_dir / f"{image_id}.json"
        with open(annotation_path, "w") as f:
            json.dump(annotation, f, indent=2)

    # Class index mapping for YOLO labels
    DICE_TYPE_TO_CLASS = {
        "D4": 0, "D6": 1, "D8": 2, "D10": 3, "D12": 4, "D20": 5, "D100": 6,
    }

    def _save_yolo_label(self, image_id: str, dice_annotations: list):
        """Save YOLO-format label file (.txt) alongside JSON annotation."""
        img_w = self.config.image_width
        img_h = self.config.image_height
        lines = []

        for die in dice_annotations:
            class_id = self.DICE_TYPE_TO_CLASS.get(die["dice_type"])
            if class_id is None:
                continue

            bbox = die["bbox"]
            x_center = (bbox["x"] + bbox["width"] / 2) / img_w
            y_center = (bbox["y"] + bbox["height"] / 2) / img_h
            width = bbox["width"] / img_w
            height = bbox["height"] / img_h

            # Clamp to valid range
            x_center = max(0.0, min(1.0, x_center))
            y_center = max(0.0, min(1.0, y_center))
            width = max(0.001, min(1.0, width))
            height = max(0.001, min(1.0, height))

            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

        label_path = self.labels_dir / f"{image_id}.txt"
        label_path.write_text("\n".join(lines) + "\n" if lines else "")

    def _save_generation_metadata(self, num_generated: int, errors: list | None = None):
        """Save metadata about the generation run."""
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "worker_id": self.config.worker_id,
            "num_images_requested": self.config.num_images,
            "num_images_generated": num_generated,
            "start_index": self.config.start_index,
            "num_errors": len(errors) if errors else 0,
            "generator_version": GENERATOR_VERSION,
            "config": self.config.to_dict(),
            "available_dice": [die.name for die in self.available_dice],
            "spawn_bounds": self.spawn_bounds,
        }

        suffix = f"_worker{self.config.worker_id}" if self.config.worker_id > 0 else ""
        metadata_path = self.metadata_dir / f"generation_metadata{suffix}.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Save errors to separate file if any
        if errors:
            errors_path = self.logs_dir / f"errors{suffix}.json"
            with open(errors_path, "w") as f:
                json.dump({"errors": errors}, f, indent=2)
