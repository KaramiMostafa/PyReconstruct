"""Pure selection logic for the non-modal DAPI feedback panel."""

from itertools import combinations


def entry_key(entry):
    return (
        int(entry["section"]),
        str(entry["name"]),
        round(float(entry["centroid"][0]), 6),
        round(float(entry["centroid"][1]), 6),
    )


def incorrect_pairs(entries):
    """Return every cross-section pair in a reviewed forbidden-match batch."""
    return [
        (first, second)
        for first, second in combinations(entries, 2)
        if int(first["section"]) != int(second["section"])
    ]


def correct_pair(entries):
    """Return one forced link only when exactly two different sections are given."""
    if len(entries) != 2:
        return None
    if int(entries[0]["section"]) == int(entries[1]["section"]):
        return None
    return entries[0], entries[1]
