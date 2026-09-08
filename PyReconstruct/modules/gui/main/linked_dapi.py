"""Pure helpers for carrying tracked DAPI selections across sections."""

import colorsys

TRACKED_DAPI_GROUP = "multiplex_tracked_dapi"
DAPI_TRACE_TAG = "multiplex_dapi"
RNA_TRACE_TAGS = {"multiplex_rna_anchor", "multiplex_mapped_rna"}

# The first colors are hand-picked for strong separation on microscopy images.
# A golden-angle HSV fallback keeps the feature usable beyond this base palette.
LINKED_DAPI_PALETTE = (
    (180, 70, 255),   # purple
    (255, 140, 40),   # orange
    (30, 210, 230),   # cyan
    (110, 220, 70),   # green
    (245, 70, 180),   # magenta
    (255, 210, 45),   # gold
    (70, 125, 255),   # blue
    (245, 75, 75),    # red
    (35, 185, 145),   # teal
    (255, 135, 190),  # pink
    (180, 220, 50),   # yellow-green
    (175, 110, 55),   # brown
    (105, 80, 230),   # indigo
    (255, 105, 70),   # coral
    (80, 175, 255),   # sky blue
    (210, 95, 220),   # orchid
)


def is_dapi_trace(trace) -> bool:
    """Distinguish a DAPI trace from an RNA trace sharing an object name."""
    tags = {str(tag) for tag in getattr(trace, "tags", set())}
    if DAPI_TRACE_TAG in tags:
        return True
    return not bool(tags & RNA_TRACE_TAGS)


def is_tracked_dapi_trace(object_groups, trace) -> bool:
    """Return whether a trace belongs to a tracked-DAPI identity."""
    groups = object_groups.getObjectGroups(str(trace.name))
    return TRACKED_DAPI_GROUP in groups and is_dapi_trace(trace)


def visible_linked_traces(contours, name: str) -> list:
    """Return visible traces for one linked identity on the current section."""
    contour = contours.get(name)
    if contour is None:
        return []
    return [trace for trace in contour if not trace.hidden and is_dapi_trace(trace)]


def next_linked_track_color(existing_colors) -> tuple[int, int, int]:
    """Return an unused, visually distinct color for another linked track."""
    used = {tuple(color) for color in existing_colors}
    for color in LINKED_DAPI_PALETTE:
        if color not in used:
            return color

    index = len(LINKED_DAPI_PALETTE)
    while True:
        hue = (index * 0.618033988749895) % 1.0
        rgb = colorsys.hsv_to_rgb(hue, 0.72, 1.0)
        color = tuple(round(channel * 255) for channel in rgb)
        if color not in used:
            return color
        index += 1


def update_linked_track_colors(
    track_colors: dict[str, tuple[int, int, int]],
    name: str,
    selected: bool,
):
    """Add/remove one linked identity and return its display color, if active."""
    name = str(name)
    if selected and name not in track_colors:
        track_colors[name] = next_linked_track_color(track_colors.values())
    elif not selected:
        track_colors.pop(name, None)
    return track_colors.get(name)


def rename_linked_track_color(
    track_colors: dict[str, tuple[int, int, int]],
    old_name: str,
    new_name: str,
):
    """Move a linked identity's display color after an expert ROI rename."""
    old_name, new_name = str(old_name), str(new_name)
    color = track_colors.pop(old_name, None)
    if color is not None and new_name not in track_colors:
        track_colors[new_name] = color
    return track_colors.get(new_name)
