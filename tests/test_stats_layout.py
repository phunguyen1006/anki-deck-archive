"""Regression checks for the native Statistics notice layout."""
import importlib
import os
import sys
import types
from pathlib import Path

import pytest
import aqt  # QtWebEngine must be imported before QApplication is created.
from aqt.qt import QApplication, QDialog, QVBoxLayout, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def integration(monkeypatch):
    package = types.ModuleType("ada_layout_test")
    package.__path__ = [str(Path(__file__).resolve().parents[1])]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    return importlib.import_module("ada_layout_test.statistics_integration")


@pytest.mark.parametrize("width,height", [(420, 360), (800, 600), (1366, 768)])
@pytest.mark.parametrize("failure", [False, True])
def test_statistics_notice_stays_compact(app, integration, monkeypatch, width, height, failure):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    web = QWidget(dialog)
    layout.addWidget(web)
    dialog.form = types.SimpleNamespace(web=web)
    dialog.mw = types.SimpleNamespace(col=object())
    monkeypatch.setattr(integration.service, "exclude_from_stats", lambda col: True)
    if failure:
        def fail(col):
            raise ValueError("simulated invalid archive")
        monkeypatch.setattr(integration.service, "scope", fail)
    else:
        monkeypatch.setattr(integration.service, "scope", lambda col: '-deck:"Archive"')
        class Signal:
            def connect(self, callback): self.callback = callback
        web.loadFinished = Signal()
        web.evalWithCallback = lambda script, callback: callback(True)
    integration.setup_stats(dialog)
    label = layout.itemAt(0).widget()
    dialog.resize(width, height)
    dialog.show()
    app.processEvents()
    if not failure:
        web.loadFinished.callback(True)
        app.processEvents()
    assert label.height() <= max(label.sizeHint().height(), label.heightForWidth(width)) + 2
    assert web.height() > height * 0.7
    dialog.resize(width, height + 240)
    app.processEvents()
    assert web.height() > (height + 240) * 0.7
    dialog.close()
