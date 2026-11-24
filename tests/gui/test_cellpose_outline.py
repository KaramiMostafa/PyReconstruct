"""Exercise the Cellpose dialog and connector together with deterministic label images."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PySide6.QtWidgets import QApplication, QWidget
from tifffile import imwrite

from PyReconstruct.modules.datatypes import Series, Trace, Transform
from PyReconstruct.modules.gui.dialog import QuickDialog
from PyReconstruct.modules.gui.main.main_window import MainWindow
from pyrecon_connector import segmentation_inapp


class CellposeOutlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        image = Path(tmp.name) / "section.tif"
        planes = np.arange(2 * 96 * 128, dtype=np.uint16).reshape(2, 96, 128)
        imwrite(image, planes, photometric="minisblack")
        self.host = QWidget()
        self.host.series = Series.new([str(image)], "test", 0.5, 1)
        self.host.field = Mock()
        section = self.host.field.section = self.host.series.loadSection(0)
        section.tform = Transform([0, -1, 60, 1, 0, 2])
        self.host.saveAllData = section.save
        self.host.seriesModified = Mock()
        self.outline = Trace("tissue", (255, 0, 0))
        # Raw-image polygon with a concave corner and a nonzero crop offset.
        points = [(30, 20), (90, 20), (90, 45), (60, 45), (60, 80), (30, 80)]
        self.outline.points = [(x * section.mag, (96 - y) * section.mag) for x, y in points]
        section.addTrace(self.outline)
        section.addSelectedTrace(self.outline)
        self.model = Mock()
        loader = patch.object(segmentation_inapp, "_load_cellpose_model", return_value=self.model)
        self.loader = loader.start()
        self.addCleanup(loader.stop)

    def run_dialog(self, area=None):
        def accept(dialog):
            fields = dialog.inputs
            self.assertEqual(fields[0].widget.currentText(), "Whole section")
            if area:
                fields[0].widget.setCurrentText(area)
            fields[3].widget.setText("1,0")
            self.assertTrue(dialog.accept(close=False))
            return dialog.responses, True

        with patch.object(QuickDialog, "exec", accept), patch(
            "PyReconstruct.modules.gui.main.main_window.notify"
        ) as message:
            MainWindow.runCellposeSAMSegmentation(self.host)
        return message.call_args.args[0]

    def test_concave_outline_masks_input_keeps_whole_cells_in_section_coordinates(self):
        def predict(image, **kwargs):
            self.assertEqual(image.shape, (61, 61, 2))
            self.assertEqual(kwargs["channel_axis"], -1)
            self.assertFalse(image[40, 40].any())  # outside the L
            labels = np.zeros(image.shape[:2], dtype=np.int32)
            labels[5:17, 5:17] = 1       # complete cell
            labels[35:50, 35:50] = 2     # outside, inside bounding box
            labels[20:31, 45:55] = 3     # crosses the concave boundary
            return labels

        self.model.eval.side_effect = predict
        self.assertIn("Created 1 ROI", self.run_dialog("Inside selected outline"))
        saved = self.host.series.loadSection(0)
        trace = saved.contours["cpsam_roi_00001"][0]
        self.assertEqual(set(trace.asPixels(0.5, 96)), {(35, 25), (46, 25), (35, 36), (46, 36)})
        self.assertEqual(saved.contours["tissue"][0].points, self.outline.points)

    def test_whole_section_default_with_an_outline_selected(self):
        self.model.eval.return_value = np.zeros((96, 128), dtype=np.int32)
        self.assertIn("Created 0 ROI", self.run_dialog())
        self.assertEqual(self.model.eval.call_args.args[0].shape, (96, 128, 2))

    def test_missing_or_open_outline_does_not_run_model(self):
        section = self.host.field.section
        section.selected_traces.clear()
        self.assertIn("exactly one closed outline", self.run_dialog("Inside selected outline"))
        self.outline.closed = False
        section.addSelectedTrace(self.outline)
        self.assertIn("exactly one closed outline", self.run_dialog("Inside selected outline"))
        self.loader.assert_not_called()
