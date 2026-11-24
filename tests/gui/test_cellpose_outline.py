"""Exercise the Cellpose dialog and connector together with deterministic label images."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from tifffile import imwrite

from PyReconstruct.modules.datatypes import Series, Trace, Transform
from PyReconstruct.modules.backend.func.state_manager import SeriesStates
from PyReconstruct.modules.gui.dialog import QuickDialog
from PyReconstruct.modules.gui.dialog.cellpose_review import CellposeReview
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
        self.host.field.series_states = SeriesStates(self.host.series)
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

    def tearDown(self):
        # Dispose the test window on Qt's GUI thread, not in Python cyclic GC.
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def run_dialog(self, area=None, action=None):
        def accept(dialog):
            fields = dialog.inputs
            self.assertEqual(fields[0].widget.currentText(), "Whole section")
            if area:
                fields[0].widget.setCurrentText(area)
            fields[3].widget.setText("1,0")
            self.assertTrue(dialog.accept(close=False))
            return dialog.responses, True

        def review(dialog):
            dialog.preview()
            self.assertIsNotNone(dialog.prediction, dialog.status.text())
            self.assertFalse(any(name.startswith("dapi_") for name in self.host.series.loadSection(0).contours))
            if action:
                action(dialog)
            else:
                dialog.apply_results()
            return dialog.result()

        with patch.object(QuickDialog, "exec", accept), patch.object(CellposeReview, "exec", review), patch(
            "PyReconstruct.modules.gui.main.main_window.notify"
        ) as message:
            MainWindow.runCellposeSAMSegmentation(self.host)
        return message.call_args.args[0] if message.called else ""

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
        trace = saved.contours["dapi_s0_00001"][0]
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

    def test_changed_threshold_disables_apply_and_close_writes_nothing(self):
        self.model.eval.return_value = np.ones((96, 128), dtype=np.int32)
        def change(dialog):
            dialog.cellprob.setValue(-1)
            self.assertFalse(dialog.apply_button.isEnabled())
            dialog.apply_results()
            dialog.preview()
            self.assertTrue(dialog.apply_button.isEnabled())
            self.assertEqual(self.model.eval.call_args.kwargs["cellprob_threshold"], -1)
            dialog.reject()
        self.assertEqual(self.run_dialog(action=change), "")
        self.assertEqual(set(self.host.series.loadSection(0).contours), {"tissue"})
        self.loader.assert_called_once()

    def test_batch_reuses_preview_and_skips_missing_image_section_and_existing_layer(self):
        s = self.host.series
        for n in (2, 3, 4):
            s.sections[n] = f"test.{n}"
            image = "absent.tif" if n == 3 else "section.tif"
            from PyReconstruct.modules.datatypes import Section
            Section.new("test", n, image, .5, 1, s.getwdir())
        section = s.loadSection(4)
        imported = self.outline.copy()
        imported.name = "imported"
        imported.tags.add("multiplex_dapi")
        section.addTrace(imported)
        section.save()
        self.host.field.series_states = SeriesStates(s)
        self.model.eval.return_value = np.ones((96, 128), dtype=np.int32)
        def batch(dialog):
            dialog.targets.setText("0-4")
            dialog.apply_results()
        msg = self.run_dialog(action=batch)
        self.assertIn("Created 2 ROIs across 2 processed", msg)
        for reason in ("1: missing section", "3: image not found", "4: layer already"):
            self.assertIn(reason, msg)
        self.assertEqual(self.model.eval.call_count, 2)
        self.loader.assert_called_once()
        self.assertEqual(set(s.loadSection(4).contours), {"imported"})
        self.assertEqual(self.host.field.series_states.canUndo(0)[0], True)
        self.host.field.series_states.undoState()
        self.assertEqual(set(s.loadSection(0).contours), {"tissue"})
        self.assertFalse(s.loadSection(2).contours)

    def test_existing_rna_survives_dapi_apply_and_layer_rerun_is_skipped(self):
        s = self.host.series
        anchor = self.outline.copy()
        anchor.name = "rna_s0_00001"
        anchor.tags.add("multiplex_rna_anchor")
        self.host.field.section.addTrace(anchor)
        self.model.eval.return_value = np.ones((96, 128), dtype=np.int32)
        def apply_twice(dialog):
            dialog.apply_results()
        self.assertIn("Created 1 ROI", self.run_dialog(action=apply_twice))
        saved = s.loadSection(0)
        self.assertEqual(saved.contours[anchor.name][0].points, anchor.points)
        self.assertEqual(saved.contours["dapi_s0_00001"][0].tags, {"multiplex_dapi"})
        dialog = CellposeReview(self.host, dict(channels=[1], min_area=25), "dapi", None)
        self.host.field.section = saved
        dialog.preview()
        self.assertIn("skipped by default", dialog.status.text())
        dialog.apply_results()
        self.assertIn("Created 0 ROIs", dialog.summary)
        self.assertEqual(len(s.loadSection(0).contours), 3)

    def test_training_dialog_requires_approval_and_passes_exact_reviewed_sections(self):
        def fill(dialog):
            fields = dialog.inputs
            fields[1].widget.setText("0,6")
            fields[2].widget.setText("1")
            fields[3].widget.le.setText(self.host.series.getwdir())
            fields[6].widget.layout().itemAt(0).widget().setChecked(self.approved)
            self.assertTrue(dialog.accept(close=False))
            return dialog.responses, True
        with patch.object(QuickDialog, "exec", fill), patch(
            "PyReconstruct.modules.gui.main.main_window.notify"
        ) as notice, patch("pyrecon_connector.train_reviewed_cellpose", return_value="/model/weights") as train:
            self.approved = False
            MainWindow.trainReviewedCellpose(self.host)
            train.assert_not_called()
            self.approved = True
            MainWindow.trainReviewedCellpose(self.host)
            self.assertEqual(train.call_args.args[1:4], ([0, 6], "dapi", [1]))
            self.assertIn("/model/weights", notice.call_args.args[0])

    def test_visible_review_autopreviews_then_closes_without_saving(self):
        self.model.eval.return_value = np.ones((96, 128), dtype=np.int32)
        dialog = CellposeReview(self.host, dict(channels=[0]), "dapi", None)
        observed = []
        timer = QTimer(dialog)
        def inspect():
            if dialog.prediction is not None:
                observed.append((dialog.apply_button.isEnabled(), len(dialog.scene.items())))
                timer.stop()
                dialog.reject()
        timer.timeout.connect(inspect)
        timer.start(5)
        timeout = QTimer(dialog)
        timeout.setSingleShot(True)
        timeout.timeout.connect(dialog.reject)
        timeout.start(5000)
        dialog.exec()
        timeout.stop()
        self.assertEqual(observed, [(True, 1)])
        self.assertIsNone(dialog.session)
        self.assertFalse(self.host.series.loadSection(0).contours)
