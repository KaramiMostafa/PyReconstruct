"""Optional headless GUI integration test; run with the synapses environment.

QT_QPA_PLATFORM=offscreen python tests/gui/test_em_registration.py
The sibling connector must be installed in the same environment.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tifffile import imwrite

from PyReconstruct.modules.gui.dialog.em_registration import EMRegistrationDialog


class EMRegistrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("fixed", "moving"):
            imwrite(self.root / f"{name}.tif", np.arange(1024, dtype=np.uint16).reshape(32, 32))
        (self.root / "points.csv").write_text(
            "point,fixed_x,fixed_y,moving_x,moving_y\n"
            "a,3,3,3,3\nb,25,3,25,3\nc,3,25,3,25\n", encoding="utf-8",
        )
        self.dialog = EMRegistrationDialog()
        self.dialog.mode.setCurrentIndex(1)  # Keep exercising legacy pair mode.
        for key, name in (("fixed_image", "fixed.tif"), ("moving_image", "moving.tif"),
                          ("landmarks_csv", "points.csv")):
            self.dialog.fields[key].le.setText(str(self.root / name))
        self.dialog.fields["output_dir"].le.setText(str(self.root))
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        if self.dialog.worker is not None:
            self.dialog.worker.requestInterruption()
            self.wait_for_worker()
        self.dialog.close()
        self.app.processEvents()

    def wait_for_worker(self):
        deadline = time.monotonic() + 20
        while self.dialog.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(self.dialog.worker, "Registration worker did not finish")

    def test_run_button_produces_review_and_restores_controls(self):
        QTest.mouseClick(self.dialog.run_button, Qt.LeftButton)
        self.assertFalse(self.dialog.run_button.isEnabled())
        self.wait_for_worker()
        self.assertIsNotNone(self.dialog.result, self.dialog.status.text())
        self.assertTrue(self.dialog.run_button.isEnabled())
        self.assertTrue(self.dialog.open_button.isEnabled())
        self.assertFalse(self.dialog.preview.pixmap().isNull())
        self.assertTrue(Path(self.dialog.result["files"]["registered_image"]).is_file())

    def test_worker_error_is_displayed_without_closing_dialog(self):
        with patch("pyrecon_connector.run_em_registration", side_effect=ValueError("Bad landmarks")):
            self.dialog.start_registration()
            self.wait_for_worker()
        self.assertEqual(self.dialog.status.text(), "Bad landmarks")
        self.assertIsNone(self.dialog.result)
        self.assertTrue(self.dialog.run_button.isEnabled())
        self.assertFalse(self.dialog.open_button.isEnabled())

    def test_serial_mode_registers_whole_stack(self):
        folder = self.root / "serial"
        folder.mkdir()
        rows = ["point,slice,x,y"]
        for section in (1, 2, 3):
            imwrite(folder / f"section.{section}.tif", np.arange(1024, dtype=np.uint16).reshape(32, 32))
            rows.extend(f"{name},{section},{x},{y}" for name, x, y in
                        (("a", 3, 3), ("b", 25, 3), ("c", 3, 25)))
        (self.root / "serial.csv").write_text("\n".join(rows))
        self.dialog.mode.setCurrentIndex(0)
        self.dialog.fields["image_series"].le.setText(str(folder))
        self.dialog.fields["landmarks_csv"].le.setText(str(self.root / "serial.csv"))
        self.assertNotIn("fixed_image", self.dialog.options())
        QTest.mouseClick(self.dialog.run_button, Qt.LeftButton)
        self.wait_for_worker()
        self.assertIsNotNone(self.dialog.result, self.dialog.status.text())
        self.assertEqual(self.dialog.result["report"]["section_order"], [1, 2, 3])
        self.assertIn("Saved 3 sections", self.dialog.status.text())
        self.assertFalse(self.dialog.preview.pixmap().isNull())

    def test_close_requests_cancellation_and_waits_for_worker(self):
        def wait_for_cancel(**options):
            while not options["cancelled"]():
                time.sleep(0.01)
            raise RuntimeError("Registration cancelled.")

        with patch("pyrecon_connector.run_em_registration", side_effect=wait_for_cancel):
            self.dialog.start_registration()
            self.dialog.reject()
            self.assertIsNotNone(self.dialog.worker)
            self.wait_for_worker()
        self.assertFalse(self.dialog.isVisible())
        self.assertIsNone(self.dialog.result)


if __name__ == "__main__":
    unittest.main()
