try:
    import bpy
    from mathutils import Vector
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


def compute_object_bbox_2d(obj, camera, width: int, height: int, min_visibility: float = 0.8) -> dict | None:
    """Compute 2D bounding box for an object projected through camera.

    Uses actual mesh vertices for tight bbox (ignores children/markers).

    Args:
        obj: Blender object (die mesh).
        camera: Camera object.
        width: Render width in pixels.
        height: Render height in pixels.
        min_visibility: Minimum fraction of bbox that must be visible (0.0-1.0).

    Returns:
        Dict with x, y, width, height, visibility or None if not visible enough.
    """
    if not BLENDER_AVAILABLE:
        return None

    if not obj or not camera:
        return None

    # Only use MESH objects for bbox
    if obj.type != "MESH":
        return None

    # Get evaluated mesh to account for modifiers
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()

    if not mesh or len(mesh.vertices) == 0:
        eval_obj.to_mesh_clear()
        return None

    # Get world-space vertex positions
    world_verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    eval_obj.to_mesh_clear()

    # Project vertices to 2D
    camera_matrix = camera.matrix_world.normalized().inverted()
    projection_matrix = camera.calc_matrix_camera(depsgraph, x=width, y=height)

    coords_2d = []
    for vert in world_verts:
        point_camera = camera_matrix @ vert
        point_clip = projection_matrix @ point_camera.to_4d()

        if point_clip.w <= 0:
            continue  # Behind camera

        x = ((point_clip.x / point_clip.w) + 1) * width / 2
        y = (1 - (point_clip.y / point_clip.w)) * height / 2
        coords_2d.append((x, y))

    if not coords_2d:
        return None

    xs = [c[0] for c in coords_2d]
    ys = [c[1] for c in coords_2d]

    # Full bbox before clipping
    full_x_min = min(xs)
    full_y_min = min(ys)
    full_x_max = max(xs)
    full_y_max = max(ys)
    full_width = full_x_max - full_x_min
    full_height = full_y_max - full_y_min
    full_area = full_width * full_height

    if full_area <= 0:
        return None

    # Clipped bbox
    x_min = max(0, int(full_x_min))
    y_min = max(0, int(full_y_min))
    x_max = min(width, int(full_x_max))
    y_max = min(height, int(full_y_max))

    bbox_width = max(1, x_max - x_min)
    bbox_height = max(1, y_max - y_min)
    clipped_area = bbox_width * bbox_height

    # Calculate visibility percentage
    visibility = clipped_area / full_area if full_area > 0 else 0

    # Check minimum visibility threshold
    if visibility < min_visibility:
        return None

    return {
        "x": x_min,
        "y": y_min,
        "width": bbox_width,
        "height": bbox_height,
        "visibility": round(visibility, 3),
    }


def is_object_visible(obj, camera, width: int, height: int, min_visibility: float = 0.8) -> bool:
    """Check if object is sufficiently visible in camera view.

    Args:
        obj: Blender object.
        camera: Camera object.
        width: Render width.
        height: Render height.
        min_visibility: Minimum visibility fraction required.

    Returns:
        True if object meets visibility threshold.
    """
    bbox = compute_object_bbox_2d(obj, camera, width, height, min_visibility)
    return bbox is not None
