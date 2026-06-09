try:
    import bpy
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Compositor / Object Index pass helpers
# ---------------------------------------------------------------------------

def _get_compositor_tree():
    """Get the compositor node tree, handling Blender version differences."""
    scene = bpy.context.scene

    # Enable compositing
    if hasattr(scene, "use_nodes"):
        scene.use_nodes = True

    # Standard Blender <=4.x
    if hasattr(scene, "node_tree") and scene.node_tree is not None:
        return scene.node_tree

    # Blender 5.x+: try alternative compositor attributes
    for attr in ("compositor_node_tree", "compositor"):
        obj = getattr(scene, attr, None)
        if obj is not None:
            if hasattr(obj, "nodes"):
                return obj
            if hasattr(obj, "node_tree"):
                return obj.node_tree

    return None


def setup_object_index_pass():
    """Enable the Object Index render pass for pixel-perfect bboxes.

    Returns True if compositor is available for reading the pass.
    """
    if not BLENDER_AVAILABLE:
        return False

    scene = bpy.context.scene
    scene.view_layers[0].use_pass_object_index = True

    tree = _get_compositor_tree()
    if tree is None:
        print("  Note: Compositor not available, will use projection-based bboxes")
        return False

    # Ensure a Render Layers node exists
    has_rl = any(n.type == "R_LAYERS" for n in tree.nodes)
    if not has_rl:
        tree.nodes.new("CompositorNodeRLayers")

    return True


def assign_pass_indices(dice_list: list):
    """Assign unique pass_index to each die object (starting at 1)."""
    for i, die in enumerate(dice_list, start=1):
        die.pass_index = i


def compute_bboxes_from_index_pass(dice_list: list, width: int, height: int) -> dict:
    """Compute pixel-perfect 2D bounding boxes from the rendered Object Index pass.

    Returns:
        Dict mapping die object name -> bbox dict, or empty dict on failure.
    """
    if not BLENDER_AVAILABLE:
        return {}

    index_pixels = _read_index_pass(width, height)
    if index_pixels is None:
        return {}

    # Build mapping: pass_index -> die name
    index_to_die = {die.pass_index: die.name for die in dice_list if die.pass_index > 0}

    results = {}
    for pass_idx, die_name in index_to_die.items():
        mask = (index_pixels == pass_idx)
        if not np.any(mask):
            continue

        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]

        results[die_name] = {
            "x": int(x_min),
            "y": int(y_min),
            "width": int(x_max - x_min + 1),
            "height": int(y_max - y_min + 1),
            "area": int(np.count_nonzero(mask)),
            "visibility": 1.0,
        }

    return results


def _read_index_pass(width: int, height: int):
    """Read Object Index pass via a Viewer node in the compositor."""
    tree = _get_compositor_tree()
    if tree is None:
        return None

    # Find Render Layers node
    render_node = None
    for node in tree.nodes:
        if node.type == "R_LAYERS":
            render_node = node
            break
    if not render_node:
        return None

    # Find IndexOB output
    index_socket = None
    for output in render_node.outputs:
        if output.name == "IndexOB":
            index_socket = output
            break
    if not index_socket:
        print("  Warning: IndexOB output not found on Render Layers node")
        return None

    # Save existing viewer state
    existing_viewer = None
    saved_links = []
    for node in tree.nodes:
        if node.type == "VIEWER":
            existing_viewer = node
            break

    viewer = existing_viewer or tree.nodes.new("CompositorNodeViewer")
    if existing_viewer:
        saved_links = [
            (link.from_socket, link.to_socket)
            for link in tree.links if link.to_node == viewer
        ]

    # Disconnect existing viewer inputs, connect IndexOB
    for link in [l for l in tree.links if l.to_node == viewer]:
        tree.links.remove(link)
    tree.links.new(index_socket, viewer.inputs[0])

    # Re-composite (does NOT re-render the scene, just re-processes passes)
    bpy.ops.render.render(write_still=False)

    # Read the Viewer Node result
    viewer_image = bpy.data.images.get("Viewer Node")
    if not viewer_image:
        _restore_viewer(tree, viewer, existing_viewer, saved_links)
        return None

    pixels = np.zeros(width * height * 4, dtype=np.float32)
    viewer_image.pixels.foreach_get(pixels)

    # Index is in the R channel; Blender stores bottom-to-top
    index_2d = pixels.reshape(height, width, 4)[:, :, 0]
    index_2d = np.flipud(index_2d)
    index_2d = np.round(index_2d).astype(np.int32)

    _restore_viewer(tree, viewer, existing_viewer, saved_links)
    return index_2d


def _restore_viewer(tree, viewer, was_existing, saved_links):
    """Restore compositor viewer node to its original state."""
    for link in [l for l in tree.links if l.to_node == viewer]:
        tree.links.remove(link)
    for from_socket, to_socket in saved_links:
        tree.links.new(from_socket, to_socket)
    if not was_existing:
        tree.nodes.remove(viewer)


# ---------------------------------------------------------------------------
# Projection-based fallback (used when compositor is unavailable)
# ---------------------------------------------------------------------------

def compute_object_bbox_2d(obj, camera, width: int, height: int,
                           min_visibility: float = 0.5) -> dict | None:
    """Compute 2D bounding box by projecting evaluated mesh vertices through camera.

    Uses only actual mesh vertices (not bound_box) for a tight fit.
    Filters out dice that are mostly outside the frame.

    Args:
        min_visibility: Minimum fraction of the full bbox that must be within the
                        image frame (0.0-1.0). Default 0.5 = at least half visible.
    """
    if not BLENDER_AVAILABLE or not obj or not camera or obj.type != "MESH":
        return None

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)

    # Use only mesh vertices for tight bbox
    points = []
    try:
        mesh = eval_obj.to_mesh()
        if mesh and len(mesh.vertices) > 0:
            points = [eval_obj.matrix_world @ v.co for v in mesh.vertices]
        eval_obj.to_mesh_clear()
    except Exception:
        pass

    if not points:
        return None

    # Project to 2D
    coords_2d = []
    for pt in points:
        co = world_to_camera_view(scene, camera, pt)
        if co.z > 0:
            coords_2d.append((co.x * width, (1.0 - co.y) * height))

    if not coords_2d:
        return None

    xs = [c[0] for c in coords_2d]
    ys = [c[1] for c in coords_2d]

    # Full (unclipped) bbox
    full_x_min, full_x_max = min(xs), max(xs)
    full_y_min, full_y_max = min(ys), max(ys)
    full_w = full_x_max - full_x_min
    full_h = full_y_max - full_y_min
    full_area = full_w * full_h

    if full_area <= 0:
        return None

    # Clipped bbox (within image bounds)
    x_min = max(0, int(full_x_min))
    y_min = max(0, int(full_y_min))
    x_max = min(width, int(full_x_max))
    y_max = min(height, int(full_y_max))

    bbox_w = max(1, x_max - x_min)
    bbox_h = max(1, y_max - y_min)
    clipped_area = bbox_w * bbox_h

    # Check visibility: what fraction of the bbox is within the image
    visibility = clipped_area / full_area
    if visibility < min_visibility:
        return None

    return {
        "x": x_min,
        "y": y_min,
        "width": bbox_w,
        "height": bbox_h,
        "visibility": round(visibility, 3),
    }
