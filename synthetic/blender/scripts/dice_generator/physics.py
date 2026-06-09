"""Rigid body physics utilities."""

from .config import GeneratorConfig

try:
    import bpy
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


def ensure_rigid_body_world():
    """Ensure rigid body world exists in the scene."""
    if not BLENDER_AVAILABLE:
        return

    if bpy.context.scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()


def setup_rigid_body(obj, config: GeneratorConfig, is_passive: bool = False):
    """Set up rigid body physics for an object.

    Args:
        obj: Blender object to add rigid body to.
        config: Generator configuration.
        is_passive: If True, object is static (walls/floor). If False, object is dynamic (dice).
    """
    if not BLENDER_AVAILABLE:
        return

    ensure_rigid_body_world()

    # Deselect all, select target
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Add rigid body if not present
    if obj.rigid_body is None:
        bpy.ops.rigidbody.object_add()

    rb = obj.rigid_body
    if is_passive:
        rb.type = "PASSIVE"
        rb.collision_shape = "MESH"
    else:
        rb.type = "ACTIVE"
        rb.collision_shape = "CONVEX_HULL"
        rb.friction = config.rigid_body_friction
        rb.restitution = config.rigid_body_bounciness
        rb.mass = 0.01

    obj.select_set(False)


def simulate_until_settled(config: GeneratorConfig) -> int:
    """Run physics simulation until dice settle.

    Returns:
        Frame number when simulation is considered settled.
    """
    if not BLENDER_AVAILABLE:
        return config.physics_end_frame

    scene = bpy.context.scene

    # Configure rigid body world cache
    rbw = scene.rigidbody_world
    if rbw:
        rbw.point_cache.frame_start = config.physics_start_frame
        rbw.point_cache.frame_end = config.physics_end_frame
        rbw.time_scale = config.physics_time_scale

    # Start from beginning
    scene.frame_set(config.physics_start_frame)

    # Step through frames
    settled_count = 0
    required_settled_frames = 10

    for frame in range(config.physics_start_frame, config.max_simulation_frames + 1):
        scene.frame_set(frame)

        # Check if all active rigid bodies have low velocity
        all_settled = True

        for obj in bpy.data.objects:
            if not obj.rigid_body or obj.rigid_body.type != "ACTIVE":
                continue

            # Check object movement between frames
            # Blender doesn't directly expose velocity, so we track position changes
            if not hasattr(obj, "_prev_location"):
                obj["_prev_location"] = list(obj.location)
                all_settled = False
                continue

            prev = obj.get("_prev_location", [0, 0, 0])
            curr = list(obj.location)

            # Calculate displacement
            displacement = sum((c - p) ** 2 for c, p in zip(curr, prev)) ** 0.5

            if displacement > config.settle_velocity_threshold:
                all_settled = False

            obj["_prev_location"] = curr

        if all_settled and frame > config.physics_start_frame + 20:
            settled_count += 1
            if settled_count >= required_settled_frames:
                # Clean up tracking data
                for obj in bpy.data.objects:
                    if "_prev_location" in obj:
                        del obj["_prev_location"]
                return frame
        else:
            settled_count = 0

    # Clean up tracking data
    for obj in bpy.data.objects:
        if "_prev_location" in obj:
            del obj["_prev_location"]

    return config.physics_end_frame


def clear_physics_cache():
    """Clear the rigid body physics cache."""
    if not BLENDER_AVAILABLE:
        return

    scene = bpy.context.scene
    if scene.rigidbody_world and scene.rigidbody_world.point_cache:
        scene.rigidbody_world.point_cache.frame_start = 1
        scene.frame_set(1)
