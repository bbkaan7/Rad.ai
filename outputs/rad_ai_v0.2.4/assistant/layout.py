"""Pure coordinate calculations shared by capture and calibration."""

from copy import deepcopy


def content_offset(profile, size, dpi):
    """Return the optional left dock offset, or None for an unknown layout."""
    if not profile.get("size"):
        return None
    scale = dpi / profile.get("reference_dpi", dpi)
    width, height = [round(value * scale) for value in profile["size"]]
    if abs(size[1] - height) > 2:
        return None
    if abs(size[0] - width) <= 2:
        return 0
    dock = round(profile.get("left_dock_width", 0) * scale)
    if dock and abs(size[0] - width - dock) <= 2:
        return size[0] - width
    return None


def calibration_profile(profile, size, dpi):
    """Preserve reference coordinates across DPI and known dock changes."""
    updated = deepcopy(profile)
    offset = content_offset(profile, size, dpi)
    changed = offset is None
    if changed:
        updated["size"] = list(size)
        updated["reference_dpi"] = dpi
        updated["regions"], updated["templates"] = {}, {}
        for key in ("incoming_color", "outgoing_color", "read_mode", "template_dpi",
                    "left_dock_width"):
            updated.pop(key, None)
        offset = 0
    return updated, offset, changed


def reference_region(region, offset, dpi, reference_dpi):
    x, y, width, height = region
    if x < offset:
        raise ValueError("Select an item inside the chat application, excluding the side advertisement.")
    scale = reference_dpi / dpi
    left, top = round((x - offset) * scale), round(y * scale)
    return [left, top, round((x - offset + width) * scale) - left,
            round((y + height) * scale) - top]
