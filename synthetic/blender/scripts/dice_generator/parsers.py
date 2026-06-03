import re
from dataclasses import dataclass


@dataclass
class ParsedDieName:
    material_number: int
    dice_type: str
    max_value: int
    variant: str | None = None  # "special", "floor", "barrel"


@dataclass
class ParsedMarkerName:
    dice_type: str
    value: int | str
    special_suffix: str | None = None


def parse_die_name(name: str) -> ParsedDieName | None:
    """Parse die object name like '1_D20', '2_D4_floor', '3_D20_special'.

    Examples:
        - 1_D20 -> material=1, dice_type=D20, max_value=20
        - 2_D4_floor -> material=2, dice_type=D4, max_value=4, variant=floor
        - 3_D20_special -> material=3, dice_type=D20, max_value=20, variant=special
    """
    pattern = r"^(\d+)_D(\d+)(?:_(special|floor|barrel))?$"
    match = re.match(pattern, name, re.IGNORECASE)
    if not match:
        return None

    material_number = int(match.group(1))
    max_value = int(match.group(2))
    variant = match.group(3).lower() if match.group(3) else None

    dice_type = f"D{max_value}"
    if max_value == 100:
        dice_type = "D100"

    return ParsedDieName(
        material_number=material_number,
        dice_type=dice_type,
        max_value=max_value,
        variant=variant,
    )


def parse_face_marker_name(name: str) -> ParsedMarkerName | None:
    """Parse face marker name like 'D20_face_14', 'D6_face_1.002', 'D20_14'.

    Supports formats:
        - D20_face_14 -> dice_type=D20, value=14
        - D20_face_14.001 -> dice_type=D20, value=14 (Blender duplicate suffix ignored)
        - D6_face_1 -> dice_type=D6, value=1
        - D20_14 -> dice_type=D20, value=14 (legacy format)
        - D20_20_star -> dice_type=D20, value=20, special_suffix=star
        - D100_face_00 -> dice_type=D100, value="00"
    """
    # Try format with "face": D20_face_14 or D20_face_14.001
    pattern_face = r"^D(\d+)_face_([\d]+)(?:\.\d+)?(?:_(.+))?$"
    match = re.match(pattern_face, name, re.IGNORECASE)

    if not match:
        # Try legacy format without "face": D20_14 or D20_14_star
        pattern_legacy = r"^D(\d+)_([\d]+)(?:\.\d+)?(?:_(.+))?$"
        match = re.match(pattern_legacy, name, re.IGNORECASE)

    if not match:
        return None

    max_value = int(match.group(1))
    value_str = match.group(2)
    special_suffix = match.group(3) if match.group(3) else None

    # Handle D100 values like "00", "10", etc. - keep as string
    if max_value == 100:
        value = value_str
    else:
        value = int(value_str)

    return ParsedMarkerName(
        dice_type=f"D{max_value}",
        value=value,
        special_suffix=special_suffix,
    )
