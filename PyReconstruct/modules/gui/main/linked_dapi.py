"""Pure helpers for carrying a tracked DAPI selection across sections."""

TRACKED_DAPI_GROUP = "multiplex_tracked_dapi"
DAPI_TRACE_TAG = "multiplex_dapi"
RNA_TRACE_TAGS = {"multiplex_rna_anchor", "multiplex_mapped_rna"}


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
