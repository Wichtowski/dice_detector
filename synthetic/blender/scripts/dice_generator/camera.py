import math
import random

from .config import GeneratorConfig

try:
    import bpy
    from mathutils import Vector
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


def randomize_camera(camera, config: GeneratorConfig):
    """Randomize camera position, rotation, and focal length"""
    if not BLENDER_AVAILABLE or not camera:
        return

    target = Vector(config.camera_target_location)

    if config.camera_mode == "overhead":
        _setup_overhead_camera(camera, target, config)
    elif config.camera_mode == "angled":
        _setup_angled_camera(camera, target, config)
    else:  # randomized
        _setup_randomized_camera(camera, target, config)

    # Randomize focal length
    focal = random.uniform(config.camera_focal_length_min, config.camera_focal_length_max)
    camera.data.lens = focal


def _setup_overhead_camera(camera, target: Vector, config: GeneratorConfig):
    """Set up pure top-down camera view."""
    height = random.uniform(config.camera_height_min, config.camera_height_max)

    # Add small random offset to target for variety
    offset_range = min(config.camera_height_min * 0.1, 2.0)
    offset_x = random.uniform(-offset_range, offset_range)
    offset_y = random.uniform(-offset_range, offset_range)

    camera.location = (target.x + offset_x, target.y + offset_y, target.z + height)
    # Point straight down with random Z rotation
    camera.rotation_euler = (0, 0, random.uniform(0, 2 * math.pi))


def _setup_angled_camera(camera, target: Vector, config: GeneratorConfig):
    """Set up camera at fixed angle (average of min/max)."""
    height = random.uniform(config.camera_height_min, config.camera_height_max)
    angle = math.radians((config.camera_angle_min + config.camera_angle_max) / 2)
    azimuth = random.uniform(0, 2 * math.pi)

    _position_camera_at_angle(camera, target, height, angle, azimuth)


def _setup_randomized_camera(camera, target: Vector, config: GeneratorConfig):
    """Set up camera with randomized height and angle."""
    height = random.uniform(config.camera_height_min, config.camera_height_max)
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
