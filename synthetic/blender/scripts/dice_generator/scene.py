from .config import GeneratorConfig
from .parsers import parse_die_name, parse_face_marker_name

try:
    import bpy
    from mathutils import Vector
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False


def get_dice_collections(config: GeneratorConfig) -> list:
    """Get all dice collections (excluding utils)"""
    if not BLENDER_AVAILABLE:
        return []

    collections = []
    for coll_name in config.dice_collections:
        coll = bpy.data.collections.get(coll_name)
        if coll:
            collections.append(coll)
            continue

        for c in bpy.data.collections:
            if c.name.startswith(f"Collection {coll_name} -") or c.name.startswith(f"{coll_name} -"):
                collections.append(c)
                break

    return collections


def get_dice_from_collections(config: GeneratorConfig) -> list:
    """Get all dice objects from dice collections"""
    if not BLENDER_AVAILABLE:
        return []

    dice = []
    collections = get_dice_collections(config)

    for coll in collections:
        for obj in coll.objects:
            if obj.type != "MESH":
                continue

            parsed = parse_die_name(obj.name)
            if parsed and parsed.dice_type in config.dice_types:
                dice.append(obj)

    return dice


def get_die_markers(die_obj) -> list:
    """Get all face marker children of a die object"""
    markers = []
    for child in die_obj.children:
        if child.type == "EMPTY":
            parsed = parse_face_marker_name(child.name)
            if parsed:
                markers.append(child)
    return markers


def get_die_markers_recursive(die_obj) -> list:
    """Get all face markers recursively (checks all descendants)"""
    markers = []

    def search_children(obj):
        for child in obj.children:
            if child.type == "EMPTY":
                parsed = parse_face_marker_name(child.name)
                if parsed:
                    markers.append(child)
            search_children(child)

    search_children(die_obj)
    return markers


def find_top_marker(die_obj) -> tuple | None:
    """Find the marker with highest world Z position"""
    markers = get_die_markers(die_obj)
    if not markers:
        markers = get_die_markers_recursive(die_obj)
    if not markers:
        return None

    top_marker = max(markers, key=lambda m: m.matrix_world.translation.z)
    parsed = parse_face_marker_name(top_marker.name)
    return (top_marker, parsed)


def find_bottom_marker(die_obj) -> tuple | None:
    """Find the marker with lowest world Z position"""
    markers = get_die_markers(die_obj)
    if not markers:
        markers = get_die_markers_recursive(die_obj)
    if not markers:
        return None

    bottom_marker = min(markers, key=lambda m: m.matrix_world.translation.z)
    parsed = parse_face_marker_name(bottom_marker.name)
    return (bottom_marker, parsed)




def determine_rolled_value(die_obj, config: GeneratorConfig) -> tuple | None:
    """Determine the rolled value from face markers after physics simulation"""
    parsed_name = parse_die_name(die_obj.name)

    result = find_top_marker(die_obj)

    if not result:
        return None

    marker_obj, parsed_marker = result
    value = parsed_marker.value

    # D10: face showing 0 means value 10
    if parsed_name and parsed_name.dice_type == "D10" and value == 0:
        value = 10

    return (value, parsed_marker.special_suffix, marker_obj.name)


def compute_tray_spawn_bounds(config: GeneratorConfig) -> tuple[float, float, float, float]:
    """Compute spawn bounds from tray floor object in utils collection"""
    if config.spawn_area_mode == "manual_bounds" and config.manual_spawn_bounds:
        return tuple(config.manual_spawn_bounds)

    if not BLENDER_AVAILABLE:
        return (-0.1, 0.1, -0.1, 0.1)

    utils_coll = bpy.data.collections.get(config.tray_collection_name)
    if not utils_coll:
        for name in ["utils", "Utils"]:
            utils_coll = bpy.data.collections.get(name)
            if utils_coll:
                break

    # Search for tray object in collection
    tray_obj = None
    if utils_coll:
        print(f"  Searching '{utils_coll.name}' collection for tray floor:")
        for obj in utils_coll.objects:
            print(f"    - {obj.name} (type={obj.type})")
            if obj.type == "MESH" and obj.name.lower() == "tray":
                tray_obj = obj
                print(f"      ^ Found tray floor!")
                break

    # Fallback: try to find tray object globally
    if not tray_obj:
        tray_obj = bpy.data.objects.get("tray")
        if tray_obj:
            print(f"  Found tray object globally: {tray_obj.name}")

    if tray_obj and tray_obj.type == "MESH":
        return _compute_bounds_from_object(tray_obj, config.spawn_margin)

    print(f"  Warning: No tray floor found, using default bounds")
    return (-0.15, 0.15, -0.15, 0.15)


def _compute_bounds_from_object(obj, margin: float) -> tuple[float, float, float, float]:
    """Compute spawn bounds from a single object's bounding box."""
    x_coords = []
    y_coords = []

    for corner in obj.bound_box:
        world_corner = obj.matrix_world @ Vector(corner)
        x_coords.append(world_corner.x)
        y_coords.append(world_corner.y)

    raw_bounds = (min(x_coords), max(x_coords), min(y_coords), max(y_coords))
    print(f"  Tray bounds: x=[{raw_bounds[0]:.3f}, {raw_bounds[1]:.3f}], y=[{raw_bounds[2]:.3f}, {raw_bounds[3]:.3f}]")

    return (
        raw_bounds[0] + margin,
        raw_bounds[1] - margin,
        raw_bounds[2] + margin,
        raw_bounds[3] - margin,
    )


def duplicate_die_asset(source_die, new_name: str):
    """Duplicate a die object with all children (markers) and materials.

    Returns:
        New die object or None.
    """
    if not BLENDER_AVAILABLE:
        return None

    # Duplicate the die object
    new_die = source_die.copy()
    new_die.data = source_die.data.copy()
    new_die.name = new_name

    # Link to scene collection
    bpy.context.scene.collection.objects.link(new_die)

    # Duplicate children (markers)
    for child in source_die.children:
        new_child = child.copy()
        new_child.parent = new_die
        bpy.context.scene.collection.objects.link(new_child)

        # Maintain relative transform
        new_child.matrix_parent_inverse = child.matrix_parent_inverse.copy()

    return new_die


def clear_generated_objects(prefix: str = "Gen_"):
    """Remove all objects with the given prefix"""
    if not BLENDER_AVAILABLE:
        return

    to_remove = [obj for obj in bpy.data.objects if obj.name.startswith(prefix)]

    for obj in to_remove:
        for child in list(obj.children):
            bpy.data.objects.remove(child, do_unlink=True)
        bpy.data.objects.remove(obj, do_unlink=True)
