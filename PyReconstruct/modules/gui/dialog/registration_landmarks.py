"""Separate raw-pixel landmark window; project coordinates never enter the viewer."""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QGraphicsItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class PixelLandmarkView(QGraphicsView):
    point_clicked = Signal(float, float)
    coordinate_hovered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.width_pixels = self.height_pixels = 0
        self.markers = []
        self.press_position = None
        self.dragged = False

    def set_image(self, array):
        self.scene().clear()
        self.markers.clear()
        self.height_pixels, self.width_pixels = array.shape
        image = QImage(array.data, self.width_pixels, self.height_pixels,
                       array.strides[0], QImage.Format_Grayscale8).copy()
        item = self.scene().addPixmap(QPixmap.fromImage(image))
        # Pixel centres are integer coordinates, independent of fit/zoom/pan.
        item.setOffset(-0.5, -0.5)
        self.scene().setSceneRect(-0.5, -0.5, self.width_pixels, self.height_pixels)
        self.fit_image()

    def fit_image(self):
        if self.width_pixels:
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def pixel_at(self, position):
        point = self.mapToScene(position)
        x, y = math.floor(point.x() + 0.5), math.floor(point.y() + 0.5)
        if 0 <= x < self.width_pixels and 0 <= y < self.height_pixels:
            return x, y
        return None

    def mousePressEvent(self, event):
        self.press_position = event.position().toPoint() if event.button() == Qt.LeftButton else None
        self.dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self.press_position is not None and (position - self.press_position).manhattanLength() > 3:
            self.dragged = True
        pixel = self.pixel_at(position)
        self.coordinate_hovered.emit(f"X = {pixel[0]}, Y = {pixel[1]} px" if pixel else "Outside image")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        position = event.position().toPoint()
        click = (event.button() == Qt.LeftButton and self.press_position is not None
                 and not self.dragged and (position - self.press_position).manhattanLength() <= 3)
        super().mouseReleaseEvent(event)
        self.press_position = None
        if click:
            pixel = self.pixel_at(position)
            if pixel is not None:
                self.point_clicked.emit(*pixel)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        if 0.005 <= self.transform().m11() * factor <= 64:
            self.scale(factor, factor)
        event.accept()

    def show_landmarks(self, entries, active):
        for marker in self.markers:
            self.scene().removeItem(marker)
        self.markers.clear()
        for name, (x, y) in entries.items():
            color = QColor("#ffd343" if name == active else "#21e0ef")
            marker = self.scene().addEllipse(-5, -5, 10, 10, QPen(color, 2))
            marker.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            marker.setAcceptedMouseButtons(Qt.NoButton)
            marker.setPos(QPointF(x, y))
            text = self.scene().addSimpleText(name)
            text.setBrush(color)
            text.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            text.setAcceptedMouseButtons(Qt.NoButton)
            text.setPos(QPointF(x, y))
            self.markers.extend((marker, text))


class RegistrationLandmarkDialog(QDialog):
    csv_saved = Signal(str)

    def __init__(self, images, parent=None, *, series=None, pair_sections=None):
        super().__init__(parent)
        self.setWindowTitle("Registration landmarks — raw image pixels")
        self.resize(1150, 800)
        self.images = dict(images)
        self.sections = list(images)
        self.series = series
        self.pair_sections = pair_sections
        self.points = {section: {} for section in images}
        self.dirty = False
        self.saved_path = None
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Coordinates here are PIXELS: (0, 0) is the top-left pixel centre; X goes right, "
            "Y goes down. Project alignment and µm calibration do not affect this window.\n"
            "Select a landmark ID, click the same feature in both images, then choose New landmark. "
            "For a stack, change the section selectors to continue. Click again to move that ID. "
            "Wheel: zoom; drag: pan; Fit: show the whole image."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Landmark ID"))
        self.landmark_id = QComboBox()
        self.landmark_id.setEditable(True)
        self.landmark_id.addItem("point1")
        self.landmark_id.currentTextChanged.connect(self.refresh_markers)
        toolbar.addWidget(self.landmark_id, 1)
        new_button = QPushButton("New landmark")
        new_button.clicked.connect(self.new_landmark)
        toolbar.addWidget(new_button)
        fit_button = QPushButton("Fit both images")
        fit_button.clicked.connect(self.fit_views)
        toolbar.addWidget(fit_button)
        self.project_button = QPushButton("Use project landmarks…")
        self.project_button.setEnabled(series is not None)
        self.project_button.setToolTip("Convert named landmark trace centres from µm to original-image pixels.")
        self.project_button.clicked.connect(self.use_project_landmarks)
        toolbar.addWidget(self.project_button)
        layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Horizontal)
        self.selectors, self.views, self.coordinate_labels = [], [], []
        for pane in range(2):
            container = QWidget()
            column = QVBoxLayout(container)
            selector = QComboBox()
            for section, path in images.items():
                selector.addItem(f"Slice {section} — {Path(path).name}", section)
            selector.setCurrentIndex(min(pane, len(images) - 1))
            column.addWidget(selector)
            view = PixelLandmarkView()
            column.addWidget(view, 1)
            label = QLabel("Move the pointer over the image to see pixel coordinates")
            column.addWidget(label)
            self.selectors.append(selector)
            self.views.append(view)
            self.coordinate_labels.append(label)
            selector.currentIndexChanged.connect(lambda _index, p=pane: self.load_pane(p))
            view.point_clicked.connect(lambda x, y, p=pane: self.place_point(p, x, y))
            view.coordinate_hovered.connect(label.setText)
            splitter.addWidget(container)
        layout.addWidget(splitter, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Landmark ID", "Slice", "X (px)", "Y (px)"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(160)
        self.table.cellClicked.connect(self.select_table_point)
        layout.addWidget(self.table)
        self.status = QLabel("Place at least 3 non-collinear matching IDs on every adjacent pair; spread landmarks over the image.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        delete_button = QPushButton("Delete selected rows")
        delete_button.clicked.connect(self.delete_selected)
        buttons.addWidget(delete_button)
        load_button = QPushButton("Load pixel CSV…")
        load_button.clicked.connect(self.load_csv)
        buttons.addWidget(load_button)
        buttons.addStretch()
        save_button = QPushButton("Save CSV and use for registration…")
        save_button.clicked.connect(self.save_csv)
        buttons.addWidget(save_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        for pane in range(2):
            self.load_pane(pane)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_views)

    def load_pane(self, pane):
        from pyrecon_connector import get_registration_image
        try:
            section = self.selectors[pane].currentData()
            self.views[pane].set_image(get_registration_image(self.images[section]))
            self.refresh_markers()
        except Exception as exc:
            # Do not leave a previous section's pixels under a new section label.
            self.views[pane].scene().clear()
            self.views[pane].markers.clear()
            self.views[pane].width_pixels = self.views[pane].height_pixels = 0
            self.status.setText(str(exc))

    def fit_views(self):
        for view in self.views:
            view.fit_image()

    def refresh_markers(self):
        if not hasattr(self, "views"):
            return
        for selector, view in zip(self.selectors, self.views):
            if view.width_pixels:
                view.show_landmarks(self.points[selector.currentData()], self.landmark_id.currentText().strip())

    def new_landmark(self):
        names = {name for entries in self.points.values() for name in entries}
        names.add(self.landmark_id.currentText())
        index = 1
        while f"point{index}" in names:
            index += 1
        name = f"point{index}"
        self.landmark_id.addItem(name)
        self.landmark_id.setCurrentText(name)

    def place_point(self, pane, x, y):
        name = self.landmark_id.currentText().strip()
        if not name:
            self.status.setText("Enter a landmark ID before clicking.")
            return
        section = self.selectors[pane].currentData()
        self.points[section][name] = (x, y)
        if self.landmark_id.findText(name) < 0:
            self.landmark_id.addItem(name)
        self.dirty = True
        self.refresh_table()
        self.status.setText(f"{name}, slice {section}: X = {x:g}, Y = {y:g} px. Use this ID for the same feature in other sections.")

    def refresh_table(self):
        self.table.setRowCount(0)
        for section in self.sections:
            for name, (x, y) in sorted(self.points[section].items()):
                row = self.table.rowCount()
                self.table.insertRow(row)
                for column, value in enumerate((name, str(section), f"{x:.6f}", f"{y:.6f}")):
                    self.table.setItem(row, column, QTableWidgetItem(value))
        self.refresh_markers()

    def select_table_point(self, row, _column):
        self.landmark_id.setCurrentText(self.table.item(row, 0).text())
        section = int(self.table.item(row, 1).text())
        if section not in [selector.currentData() for selector in self.selectors]:
            self.selectors[1].setCurrentIndex(self.selectors[1].findData(section))

    def delete_selected(self):
        rows = {item.row() for item in self.table.selectedItems()}
        for row in rows:
            name = self.table.item(row, 0).text()
            section = int(self.table.item(row, 1).text())
            del self.points[section][name]
        if rows:
            self.dirty = True
            self.refresh_table()

    def replace_points(self, points):
        self.points = {section: dict(points.get(section, {})) for section in self.images}
        names = sorted({name for entries in self.points.values() for name in entries})
        self.landmark_id.blockSignals(True)
        self.landmark_id.clear()
        self.landmark_id.addItems(names or ["point1"])
        self.landmark_id.blockSignals(False)
        self.dirty = True
        self.refresh_table()

    def confirm_replace(self):
        if not self.dirty:
            return True
        return QMessageBox.question(self, "Replace landmarks?", "Replace the unsaved landmarks in this window?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def load_csv(self):
        from pyrecon_connector import load_registration_landmarks
        path, _ = QFileDialog.getOpenFileName(self, "Load zero-based, top-left pixel landmarks", "", "CSV (*.csv)")
        if not path or not self.confirm_replace():
            return
        try:
            self.replace_points(load_registration_landmarks(path, self.images, pair_sections=self.pair_sections))
            self.status.setText("Loaded pixel coordinates. Review the markers and save a registration CSV.")
        except Exception as exc:
            self.status.setText(str(exc))

    def use_project_landmarks(self):
        from pyrecon_connector import get_project_landmarks
        prefix, accepted = QInputDialog.getText(
            self, "Project landmark names",
            "Prefix of landmark traces (e.g. lm_1, lm_2…). One trace per ID per image.\n"
            "Trace centres will be converted from µm using their source-image calibration:",
            text="lm_",
        )
        if not accepted or not self.confirm_replace():
            return
        try:
            self.replace_points(get_project_landmarks(self.series, self.images, prefix=prefix.strip()))
            self.status.setText("Project trace centres converted to raw pixels. Check the displayed markers, then save.")
        except Exception as exc:
            self.status.setText(str(exc))

    def save_csv(self):
        from pyrecon_connector import save_registration_landmarks
        path, _ = QFileDialog.getSaveFileName(
            self, "Save zero-based, top-left pixel landmarks", "registration_landmarks_pixels.csv", "CSV (*.csv)",
        )
        if not path:
            return
        try:
            self.saved_path = save_registration_landmarks(path, self.points, self.images, overwrite=True)
            self.dirty = False
            self.csv_saved.emit(self.saved_path)
            self.accept()
        except Exception as exc:
            self.status.setText(str(exc))

    def reject(self):
        if self.dirty and QMessageBox.question(
            self, "Discard unsaved landmarks?", "Close without saving the landmark changes?",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Discard:
            return
        super().reject()
