import math
import random

from .config import GeneratorConfig

try:
    import bpy
    from mathutils import Vector
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


def _compute_height_for_tray(tray_bounds, focal_length, image_width, image_height,
                              sensor_width=36.0, padding=1.1):
    """Compute camera height so the entire tray fits in frame.

    Uses pinhole camera model: visible_width = height * sensor_width / focal_length
    """
    tray_w = (tray_bounds[1] - tray_bounds[0]) * padding
    tray_h = (tray_bounds[3] - tray_bounds[2]) * padding

    aspect = image_width / image_height
    sensor_height = sensor_width / aspect

    # Height needed to fit each dimension
    h_for_w = tray_w * focal_length / sensor_width
    h_for_h = tray_h * focal_length / sensor_height

    return max(h_for_w, h_for_h)


def randomize_camera(camera, config: GeneratorConfig, tray_bounds=None):
    """Randomize camera position, rotation, and focal length.

    If tray_bounds is provided, camera height is computed automatically
    so the entire tray is visible. Otherwise falls back to config height values.
    """
    if not BLENDER_AVAILABLE or not camera:
        return

    # Pick focal length first (needed for auto-height calculation)
    focal = random.uniform(config.camera_focal_length_min, config.camera_focal_length_max)
    camera.data.lens = focal

    # Compute height: auto from tray bounds or fallback to config
    if tray_bounds:
        height = _compute_height_for_tray(
            tray_bounds, focal,
            config.image_width, config.image_height,
            camera.data.sensor_width, config.camera_tray_padding,
        )
        # Center target on tray with random jitter
        center_x = (tray_bounds[0] + tray_bounds[1]) / 2
        center_y = (tray_bounds[2] + tray_bounds[3]) / 2
        tray_w = tray_bounds[1] - tray_bounds[0]
        tray_h = tray_bounds[3] - tray_bounds[2]
        jitter = config.camera_target_jitter
        target = Vector((\
            center_x + random.gauss(0, tray_w * jitter),
            center_y + random.gauss(0, tray_h * jitter),
            0.0,
        ))
        print(f"  Auto camera: focal={focal:.1f}mm, height={height:.2f}m, target=({target.x:.2f}, {target.y:.2f})")
    else:
        height = random.uniform(config.camera_height_min, config.camera_height_max)
        target = Vector(config.camera_target_location)

    if config.camera_mode == "overhead":
        _setup_overhead_camera(camera, target, height)
    elif config.camera_mode == "angled":
        _setup_angled_camera(camera, target, config, height)
    else:  # randomized
        _setup_randomized_camera(camera, target, config, height)


def _setup_overhead_camera(camera, target: Vector, height: float):
    """Set up pure top-down camera view."""
    # Add small random offset for variety
    offset_range = min(height * 0.05, 2.0)
    offset_x = random.uniform(-offset_range, offset_range)
    offset_y = random.uniform(-offset_range, offset_range)

    camera.location = (target.x + offset_x, target.y + offset_y, target.z + height)
    # Point straight down with random Z rotation
    camera.rotation_euler = (0, 0, random.uniform(0, 2 * math.pi))


def _setup_angled_camera(camera, target: Vector, config: GeneratorConfig, height: float):
    """Set up camera at fixed angle (average of min/max)."""
    angle = math.radians((config.camera_angle_min + config.camera_angle_max) / 2)
    azimuth = random.uniform(0, 2 * math.pi)

    _position_camera_at_angle(camera, target, height, angle, azimuth)


def _setup_randomized_camera(camera, target: Vector, config: GeneratorConfig, height: float):
    """Set up camera with randomized height and angle."""
    angle = math.radians(random.uniform(config.camera_angle_min, config.camera_angle_max))
    azimuth = random.uniform(0, 2 * math.pi)

    if angle >= math.radians(89):
        # Near top-down, avoid gimbal issues
        camera.location = (target.x, target.y, target.z + height)
        camera.rotation_euler = (0, 0, azimuth)
    else:
        _position_camera_at_angle(camera, target, height, angle, azimuth)


def _position_camera_at_angle(camera, target: Vector, height: float, angle: float, azimuth: float):
    """Position camera at specified angle looking at target"""
    dist_horizontal = height / math.tan(angle) if angle > 0.01 else height * 10

    x = target.x + dist_horizontal * math.cos(azimuth)
    y = target.y + dist_horizontal * math.sin(azimuth)

    camera.location = (x, y, target.z + height)

    # Point at target
    direction = target - camera.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera.rotation_euler = rot_quat.to_euler()


def get_or_create_camera(name: str = "DiceCamera"):
    """Get existing camera or create a new one"""
    if not BLENDER_AVAILABLE:
        return None

    if bpy.context.scene.camera:
        return bpy.context.scene.camera

    camera = bpy.data.objects.get(name)
    if camera and camera.type == "CAMERA":
        bpy.context.scene.camera = camera
        return camera

    camera = bpy.data.objects.get("Camera")
    if camera and camera.type == "CAMERA":
        bpy.context.scene.camera = camera
        return camera

    # Create new camera
    bpy.ops.object.camera_add(location=(0, 0, 1))
    camera = bpy.context.active_object
    camera.name = name
    bpy.context.scene.camera = camera

    return camera
