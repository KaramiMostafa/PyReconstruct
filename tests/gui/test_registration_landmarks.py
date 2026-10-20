"""Run with QT_QPA_PLATFORM=offscreen and the connector installed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tifffile import imwrite

from PyReconstruct.modules.gui.dialog.registration_landmarks import RegistrationLandmarkDialog
from PyReconstruct.modules.calc.image import point_2_pix
from PyReconstruct.modules.datatypes import Contour, Trace, Transform
from pyrecon_connector import load_registration_landmarks


class LandmarkWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.images = {}
        for section in (1, 2, 3):
            path = self.root / f"section.{section}.tif"
            imwrite(path, np.arange(240 * 320, dtype=np.uint16).reshape(240, 320))
            self.images[section] = path
        self.dialog = RegistrationLandmarkDialog(self.images)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.dirty = False
        self.dialog.close()
        self.app.processEvents()

    def click_pixel(self, pane, x, y):
        view = self.dialog.views[pane]
        position = view.mapFromScene(QPointF(x, y))
        self.assertTrue(view.viewport().rect().contains(position))
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=position)
        self.app.processEvents()

    def test_click_coordinates_survive_zoom_pan_and_section_switch(self):
        self.click_pixel(0, 40, 50)
        self.assertEqual(self.dialog.points[1]["point1"], (40, 50))
        view = self.dialog.views[1]
        view.scale(4, 4)
        view.centerOn(120, 90)
        self.click_pixel(1, 125, 95)
        self.assertEqual(self.dialog.points[2]["point1"], (125, 95))
        self.dialog.selectors[1].setCurrentIndex(2)
        self.app.processEvents()
        self.click_pixel(1, 40, 60)
        self.assertEqual(self.dialog.points[3]["point1"], (40, 60))
        self.assertEqual(self.dialog.points[2]["point1"], (125, 95))

    def test_drag_to_pan_does_not_create_a_landmark(self):
        view = self.dialog.views[0]
        view.scale(3, 3)
        start = view.viewport().rect().center()
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), start + QPointF(50, 10).toPoint())
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=start + QPointF(50, 10).toPoint())
        self.assertEqual(self.dialog.points[1], {})

    def test_reclick_moves_only_one_id_and_row_delete_is_section_specific(self):
        self.click_pixel(0, 30, 40)
        self.click_pixel(1, 35, 45)
        self.click_pixel(0, 31, 41)
        self.assertEqual(self.dialog.points[1], {"point1": (31, 41)})
        self.dialog.table.selectRow(0)
        self.dialog.delete_selected()
        self.assertEqual(self.dialog.points[1], {})
        self.assertEqual(self.dialog.points[2], {"point1": (35, 45)})

    def test_save_emits_registration_ready_path(self):
        points = {section: {"point1": (10., 10.), "point2": (200., 10.), "point3": (10., 150.)}
                  for section in self.images}
        self.dialog.replace_points(points)
        received = []
        self.dialog.csv_saved.connect(received.append)
        destination = self.root / "pixel_landmarks.csv"
        with patch(
            "PyReconstruct.modules.gui.dialog.registration_landmarks.QFileDialog.getSaveFileName",
            return_value=(str(destination), "CSV (*.csv)"),
        ):
            self.dialog.save_csv()
        self.assertEqual(received, [str(destination.resolve())])
        self.assertEqual(load_registration_landmarks(destination, self.images), points)
        self.assertFalse(self.dialog.dirty)

    def test_incomplete_correspondence_stays_open_and_does_not_write(self):
        self.click_pixel(0, 30, 40)
        destination = self.root / "invalid.csv"
        with patch(
            "PyReconstruct.modules.gui.dialog.registration_landmarks.QFileDialog.getSaveFileName",
            return_value=(str(destination), "CSV (*.csv)"),
        ):
            self.dialog.save_csv()
        self.assertFalse(destination.exists())
        self.assertTrue(self.dialog.isVisible())
        self.assertIn("at least 3", self.dialog.status.text())

    def test_project_trace_centres_match_core_pixel_conversion(self):
        sections = {}
        for number, path in self.images.items():
            trace = Trace("lm_1", (255, 0, 0))
            trace.points = [(0.11, 0.21), (0.13, 0.21), (0.13, 0.23), (0.11, 0.23)]
            sections[number - 1] = SimpleNamespace(
                src_fp=str(path), mag=0.002 * number,
                contours={"lm_1": Contour("lm_1", [trace])},
                tform=Transform([1.1, 0.1, 50, -0.1, 1.2, -20]),
            )
        self.dialog.series = SimpleNamespace(
            sections=sections, loadSection=sections.__getitem__,
        )
        with patch(
            "PyReconstruct.modules.gui.dialog.registration_landmarks.QInputDialog.getText",
            return_value=("lm_", True),
        ):
            self.dialog.use_project_landmarks()
        for number, section in sections.items():
            expected = point_2_pix(
                section.contours["lm_1"][0].getCentroid(), section.mag, 240, subpix=True,
            )
            np.testing.assert_allclose(self.dialog.points[number + 1]["lm_1"], expected)
        self.assertIn("converted to raw pixels", self.dialog.status.text())


if __name__ == "__main__":
    unittest.main()
