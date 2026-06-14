from dataclasses import dataclass, field


@dataclass
class GeneratorConfig:
    output_dir: str = "data/generated/blender"
    num_images: int = 100
    image_width: int = 1280
    image_height: int = 720

    # Dice count distribution: list of (min, max, weight) ranges.
    # Weight = relative share of dataset for that range.
    dice_count_distribution: list[list] = field(
        default_factory=lambda: [
            [1, 3, 15],    # isolated dice — 15%
            [4, 8, 25],    # small group — 25%
            [9, 15, 35],   # medium cluster — 35%
            [16, 25, 20],  # crowded — 20%
            [26, 40, 5],   # very crowded — 5%
        ]
    )

    render_samples: int = 64
    enable_denoising: bool = True
    random_seed: int | None = None

    # Worker settings (for parallel generation)
    start_index: int = 0
    worker_id: int = 0
    skip_existing: bool = True

    # Resolution variety
    randomize_resolution: bool = True
    resolution_base: int = 1080  # base dimension for the longer side
    resolution_presets: list[str] = field(
        default_factory=lambda: ["16:9", "9:16", "1:1", "4:3", "3:4"]
    )

    # Dice collection settings
    dice_collections: list[str] = field(
        default_factory=lambda: [
            "1", "3", "4", "8", "9", "10", "11",
            "12", "13", "14", "15", "16", "17", "18", "19",
        ]
    )
    utils_collection: str = "utils"
    dice_types: list[str] = field(
        default_factory=lambda: ["D4", "D6", "D8", "D10", "D12", "D20", "D100"]
    )

    # Camera settings
    camera_mode: str = "randomized"  # "overhead" | "angled" | "randomized"
    camera_height_min: float = 0.4  # fallback if no tray found
    camera_height_max: float = 0.8  # fallback if no tray found
    camera_angle_min: float = 60.0  # degrees from horizontal
    camera_angle_max: float = 90.0  # 90 = top-down
    camera_target_location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_focal_length_min: float = 35.0
    camera_focal_length_max: float = 50.0
    camera_tray_padding: float = 1.1  # multiplier for extra margin around tray (1.0 = exact fit)
    camera_target_jitter: float = 0.15  # random offset of camera target as fraction of tray size

    # Light augmentation
    randomize_lighting: bool = True
    light_energy_min: float = 500.0
    light_energy_max: float = 3000.0
    light_color_temperature_min: float = 3500.0  # warm
    light_color_temperature_max: float = 7000.0  # cool

    # Asset scale
    asset_scale_factor: float = 1.0
    normalize_asset_scale: bool = False

    # Tray/spawn settings
    tray_collection_name: str = "utils"
    tray_floor_object_name: str | None = None
    tray_wall_object_prefix: str | None = None
    spawn_area_mode: str = "computed_from_tray"  # "computed_from_tray" | "manual_bounds"
    manual_spawn_bounds: tuple[float, float, float, float] | None = None  # (x_min, x_max, y_min, y_max)
    spawn_margin: float = 0.02
    spawn_height: float = 0.15

    # Physics settings
    physics_start_frame: int = 1
    physics_end_frame: int = 250
    settle_velocity_threshold: float = 0.001
    settle_angular_velocity_threshold: float = 0.01
    max_simulation_frames: int = 300
    physics_time_scale: float = 3.0
    rigid_body_friction: float = 0.5
    rigid_body_bounciness: float = 0.3
    random_initial_velocity: float = 0.5
    random_initial_angular_velocity: float = 2.0

    # D4 strategy
    d4_floor_strategy: str = "top_marker"  # "bottom_marker" | "top_marker"
    d4_barrel_strategy: str = "top_marker"

    # Annotation settings
    min_visibility: float = 0.8  # Minimum fraction of dice visible to include in annotations

    # Output options
    create_annotated_images: bool = False  # Create images with bboxes drawn
    indices: list[int] | None = None  # Specific image indices to generate (fills gaps)

    # Debug/fallback
    use_placeholder_mode: bool = False
    debug_interactive_mode: bool = False  # If True, updates viewport after each step

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratorConfig":
        valid_fields = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_dict(self) -> dict:
        return {
            k: getattr(self, k)
            for k in self.__dataclass_fields__
        }
