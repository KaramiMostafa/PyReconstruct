import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "PyReconstruct/modules/gui/popup/dapi_feedback_logic.py"
)
SPEC = importlib.util.spec_from_file_location("dapi_feedback_logic", MODULE_PATH)
logic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(logic)


def entry(section, name):
    return {"section": section, "name": name, "centroid": [section, 0]}


class DAPIFeedbackLogicTests(unittest.TestCase):
    def test_pair_key_uses_centroid_to_distinguish_same_name(self):
        first = entry(14, "cell_1")
        second = entry(14, "cell_1")
        second["centroid"] = [99, 0]
        self.assertNotEqual(logic.entry_key(first), logic.entry_key(second))

    def test_incorrect_batch_forbids_all_cross_section_combinations(self):
        entries = [entry(13, "a"), entry(14, "b"), entry(15, "c")]
        self.assertEqual(len(logic.incorrect_pairs(entries)), 3)

    def test_incorrect_batch_ignores_same_section_combinations(self):
        entries = [entry(14, "a"), entry(14, "b"), entry(15, "c")]
        self.assertEqual(len(logic.incorrect_pairs(entries)), 2)

    def test_correct_feedback_requires_exactly_two_sections(self):
        self.assertIsNotNone(logic.correct_pair([entry(13, "a"), entry(14, "b")]))
        self.assertIsNone(logic.correct_pair([entry(14, "a"), entry(14, "b")]))
        self.assertIsNone(logic.correct_pair([entry(13, "a"), entry(14, "b"), entry(15, "c")]))


if __name__ == "__main__":
    unittest.main()
