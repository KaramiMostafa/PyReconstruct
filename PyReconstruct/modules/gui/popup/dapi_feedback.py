from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PyReconstruct.modules.gui.utils import notify

from .dapi_feedback_logic import correct_pair, entry_key, incorrect_pairs


class DAPITrackingFeedbackWidget(QDockWidget):
    """Persistent, non-modal collector for DAPI track-link feedback."""

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.mainwindow = mainwindow
        self.entries = []
        self.setFloating(True)
        self.setAllowedAreas(Qt.NoDockWidgetArea)
        self.setWindowTitle("DAPI Track Feedback (HIGH RISK)")
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        body = QWidget(self)
        layout = QVBoxLayout(body)

        warning = QLabel(
            "⚠ HIGH RISK: incorrect constraints can split or merge many cell "
            "identities and alter downstream mRNA mappings. Verify every ROI "
            "and section before saving."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #d02040; font-weight: bold;")
        layout.addWidget(warning)

        instructions = QLabel(
            "Leave this panel open. Click a tracked DAPI ROI in the main viewer, "
            "add it below, move to another section, and add the matching or "
            "incorrect ROI. Select two or more collected rows before marking. "
            "For an incorrect batch, every selected cross-section combination "
            "is saved as a forbidden match."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.current_selection = QLabel("Current selection: none")
        layout.addWidget(self.current_selection)

        add_button = QPushButton("Add selected DAPI ROI(s)")
        add_button.clicked.connect(self.addSelectedROIs)
        layout.addWidget(add_button)

        self.table = QTableWidget(0, 4, body)
        self.table.setHorizontalHeaderLabels(["Order", "Section", "Tracked ID", "Centroid (x, y)"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.notes = QLineEdit(body)
        self.notes.setPlaceholderText("Optional notes saved with these constraints")
        layout.addWidget(self.notes)

        verdicts = QHBoxLayout()
        incorrect = QPushButton("Mark selected links INCORRECT")
        incorrect.setStyleSheet("font-weight: bold; color: #d02040;")
        incorrect.clicked.connect(self.markIncorrect)
        correct = QPushButton("Mark one selected pair CORRECT")
        correct.clicked.connect(self.markCorrect)
        verdicts.addWidget(incorrect)
        verdicts.addWidget(correct)
        layout.addLayout(verdicts)

        management = QHBoxLayout()
        remove = QPushButton("Remove selected rows")
        remove.clicked.connect(self.removeSelectedRows)
        clear = QPushButton("Clear review list")
        clear.clicked.connect(self.clearEntries)
        management.addWidget(remove)
        management.addWidget(clear)
        layout.addLayout(management)

        self.status = QLabel("No feedback saved in this panel session.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.setWidget(body)
        self.resize(760, 520)
        self._positionNearParent()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refreshCurrentSelection)
        self.timer.start(250)
        self.show()

    def _positionNearParent(self):
        parent = self.mainwindow
        self.move(parent.x() + max(30, parent.width() - self.width() - 30), parent.y() + 80)

    def refreshCurrentSelection(self):
        field = getattr(self.mainwindow, "field", None)
        if field is None or field.section is None:
            self.current_selection.setText("Current selection: none")
            return
        selected = [
            trace for trace in field.section.selected_traces
            if field.isTrackedDAPITrace(trace)
        ]
        if not selected:
            self.current_selection.setText(
                f"Current selection on section {field.section.n}: no tracked DAPI ROI"
            )
            return
        names = ", ".join(str(trace.name) for trace in selected)
        self.current_selection.setText(
            f"Current selection on section {field.section.n}: {names}"
        )

    def addSelectedROIs(self):
        field = self.mainwindow.field
        selected = [
            trace for trace in field.section.selected_traces
            if field.isTrackedDAPITrace(trace)
        ]
        if not selected:
            notify("Select at least one tracked DAPI ROI in the main viewer first.")
            return
        added_rows = []
        for trace in selected:
            cx, cy = trace.getCentroid()
            entry = {
                "section": int(field.section.n),
                "name": str(trace.name),
                "centroid": [float(cx), float(cy)],
            }
            key = entry_key(entry)
            if any(entry_key(existing) == key for existing in self.entries):
                continue
            self.entries.append(entry)
            added_rows.append(len(self.entries) - 1)
        self.refreshTable()
        self.table.clearSelection()
        for row in added_rows:
            self.table.selectRow(row)
        self.status.setText(f"Added {len(added_rows)} ROI(s); {len(self.entries)} collected.")

    def refreshTable(self):
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            values = (
                str(row + 1),
                str(entry["section"]),
                entry["name"],
                f"{entry['centroid'][0]:.5f}, {entry['centroid'][1]:.5f}",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def selectedEntries(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [(row, self.entries[row]) for row in rows]

    def markIncorrect(self):
        selected = self.selectedEntries()
        if len(selected) < 2:
            notify("Select at least two collected rows to mark an incorrect link.")
            return
        pairs = incorrect_pairs([entry for _, entry in selected])
        if not pairs:
            notify("Selected feedback rows must include at least two different sections.")
            return
        self._savePairs(pairs, "incorrect", [row for row, _ in selected])

    def markCorrect(self):
        selected = self.selectedEntries()
        if len(selected) != 2:
            notify("Select exactly two collected rows for a correct forced link.")
            return
        pair = correct_pair([entry for _, entry in selected])
        if pair is None:
            notify("A track link must connect two different sections.")
            return
        self._savePairs([pair], "correct", [row for row, _ in selected])

    def _savePairs(self, pairs, verdict, rows):
        self.mainwindow.saveAllData()
        try:
            from pyrecon_connector import add_dapi_link_feedback_batch
            records = add_dapi_link_feedback_batch(
                self.mainwindow.series,
                pairs,
                verdict,
                notes=self.notes.text(),
            )
        except Exception as error:
            notify(f"Could not save DAPI link feedback:\n{error}")
            return
        self._removeRows(rows)
        self.notes.clear()
        self.status.setText(
            f"Saved {len(records)} {verdict} DAPI link constraint(s). "
            "Rerun Hungarian or Bayesian tracking with Apply saved expert feedback enabled."
        )

    def _removeRows(self, rows):
        for row in sorted(set(rows), reverse=True):
            self.entries.pop(row)
        self.refreshTable()

    def removeSelectedRows(self):
        self._removeRows([row for row, _ in self.selectedEntries()])

    def clearEntries(self):
        self.entries = []
        self.refreshTable()
        self.status.setText("Review list cleared; saved feedback was not deleted.")

    def closeEvent(self, event):
        self.timer.stop()
        self.mainwindow.dapi_feedback_widget = None
        event.accept()
