import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from PyReconstruct.modules.gui.dialog.cellpose_review import parse_sections, run_task


def test_sparse_sections_preserve_order_and_deduplicate():
    assert parse_sections("1-3,6,2,19,40") == [1, 2, 3, 6, 19, 40]


@pytest.mark.parametrize("value", ["", "3-1", "x", "-5", "1,,2", "1-999999999"])
def test_bad_sections(value):
    with pytest.raises(ValueError):
        parse_sections(value)


def test_worker_updates_gui_on_main_thread():
    from threading import get_ident
    app = QApplication.instance() or QApplication([])
    main = get_ident()
    def job(worker):
        assert get_ident() != main
        return worker.on_ui(get_ident)
    assert run_task(None, "Test worker", job) == main
