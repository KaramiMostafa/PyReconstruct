import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "PyReconstruct/modules/gui/main/linked_dapi.py"
)
SPEC = importlib.util.spec_from_file_location("linked_dapi", MODULE_PATH)
linked_dapi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(linked_dapi)


class Groups:
    def __init__(self, memberships):
        self.memberships = memberships

    def getObjectGroups(self, name):
        return self.memberships.get(name, set())


class Trace:
    def __init__(self, name, hidden=False, tags=()):
        self.name = name
        self.hidden = hidden
        self.tags = set(tags)


class LinkedDAPIHighlightTests(unittest.TestCase):
    def test_only_tracked_dapi_is_linkable(self):
        groups = Groups({
            "cell_00168": {"multiplex_tracked_dapi"},
            "rna_00168": {"multiplex_rna_anchor"},
        })
        self.assertTrue(
            linked_dapi.is_tracked_dapi_trace(groups, Trace("cell_00168"))
        )
        self.assertFalse(
            linked_dapi.is_tracked_dapi_trace(groups, Trace("rna_00168"))
        )

    def test_rna_trace_sharing_tracked_name_is_not_linked(self):
        groups = Groups({"cell_00168": {"multiplex_tracked_dapi"}})
        rna = Trace("cell_00168", tags={"multiplex_rna_anchor"})
        self.assertFalse(linked_dapi.is_tracked_dapi_trace(groups, rna))

    def test_mapped_rna_is_linkable_but_anchor_rna_is_not(self):
        groups = Groups({})
        mapped = Trace("mapped_rna_a001_cell", tags={"multiplex_mapped_rna"})
        anchor = Trace("rna_anchor", tags={"multiplex_rna_anchor"})
        self.assertTrue(linked_dapi.is_linkable_multiplex_trace(groups, mapped))
        self.assertFalse(linked_dapi.is_linkable_multiplex_trace(groups, anchor))

    def test_returns_same_identity_on_next_section(self):
        target = Trace("cell_00168")
        other = Trace("cell_00177")
        contours = {"cell_00168": [target], "cell_00177": [other]}
        self.assertEqual(
            linked_dapi.visible_linked_traces(contours, "cell_00168"),
            [target],
        )

    def test_missing_section_does_not_select_an_unrelated_cell(self):
        contours = {"cell_00177": [Trace("cell_00177")]}
        self.assertEqual(
            linked_dapi.visible_linked_traces(contours, "cell_00168"),
            [],
        )

    def test_hidden_matching_trace_is_not_selected(self):
        contours = {"cell_00168": [Trace("cell_00168", hidden=True)]}
        self.assertEqual(
            linked_dapi.visible_linked_traces(contours, "cell_00168"),
            [],
        )

    def test_mixed_contour_highlights_only_dapi_trace(self):
        dapi = Trace("cell_00168", tags={"multiplex_dapi"})
        rna = Trace("cell_00168", tags={"multiplex_rna_anchor"})
        contours = {"cell_00168": [dapi, rna]}
        self.assertEqual(
            linked_dapi.visible_linked_traces(contours, "cell_00168"),
            [dapi],
        )

    def test_visible_mapped_rna_is_restored_across_sections(self):
        mapped = Trace("mapped_rna_a001_cell", tags={"multiplex_mapped_rna"})
        anchor = Trace("mapped_rna_a001_cell", tags={"multiplex_rna_anchor"})
        contours = {"mapped_rna_a001_cell": [mapped, anchor]}
        self.assertEqual(
            linked_dapi.visible_linked_traces(contours, "mapped_rna_a001_cell"),
            [mapped],
        )

    def test_feedback_classification_uses_trace_tags_for_shared_name(self):
        groups = Groups({
            "shared_cell": {"multiplex_dapi", "multiplex_rna_anchor"},
        })
        dapi = Trace("shared_cell", tags={"multiplex_dapi"})
        rna = Trace("shared_cell", tags={"multiplex_rna_anchor"})
        self.assertTrue(linked_dapi.is_multiplex_roi(groups, dapi, "dapi"))
        self.assertFalse(linked_dapi.is_multiplex_roi(groups, dapi, "rna"))
        self.assertTrue(linked_dapi.is_multiplex_roi(groups, rna, "rna"))
        self.assertFalse(linked_dapi.is_multiplex_roi(groups, rna, "dapi"))

    def test_multiple_tracks_receive_distinct_colors(self):
        colors = {}
        for index in range(24):
            linked_dapi.update_linked_track_colors(colors, f"cell_{index}", True)
        self.assertEqual(len(colors), 24)
        self.assertEqual(len(set(colors.values())), 24)

    def test_one_track_can_be_removed_without_clearing_others(self):
        colors = {}
        linked_dapi.update_linked_track_colors(colors, "cell_00168", True)
        linked_dapi.update_linked_track_colors(colors, "cell_00177", True)
        linked_dapi.update_linked_track_colors(colors, "cell_00168", False)
        self.assertNotIn("cell_00168", colors)
        self.assertIn("cell_00177", colors)

    def test_renamed_track_keeps_its_color(self):
        colors = {}
        original = linked_dapi.update_linked_track_colors(
            colors, "cell_00177", True
        )
        renamed = linked_dapi.rename_linked_track_color(
            colors, "cell_00177", "cell_00168"
        )
        self.assertEqual(renamed, original)
        self.assertEqual(colors, {"cell_00168": original})

    def test_mapped_feedback_updates_saved_status_color(self):
        mapped = Trace("mapped_rna_1", tags={"multiplex_mapped_rna", "review"})
        self.assertEqual(
            linked_dapi.apply_mapped_feedback_style(mapped, "correct"),
            (40, 200, 100),
        )
        self.assertIn("expert_approved", mapped.tags)
        self.assertNotIn("review", mapped.tags)
        self.assertEqual(
            linked_dapi.apply_mapped_feedback_style(mapped, "incorrect"),
            (230, 60, 60),
        )
        self.assertIn("expert_rejected", mapped.tags)
        self.assertNotIn("expert_approved", mapped.tags)


if __name__ == "__main__":
    unittest.main()
