"""Initialize Anki's documented statistics search control on page load.

The search form ID is explicitly marked as an external API in Anki 26.08.1
and 26.09. This applies a default; users can subsequently change the scope.
"""
from __future__ import annotations
import json
import logging
from aqt.qt import QLabel, QTimer
from .core import service

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 40


def search_script(query):
    # The Svelte component uses focus to select custom scope, input to update
    # its bound value and change to run the search. JSON escapes user names.
    return """(() => {
      const input = document.getElementById('statisticsSearchText');
      if (!input) return false;
      input.focus();
      input.value = %s;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.dispatchEvent(new Event('change', {bubbles: true}));
      return input.value === %s;
    })()""" % (json.dumps(query), json.dumps(query))


def setup_stats(dialog):
    """Use Anki's existing graphs with a clearly labelled default scope."""
    try:
        if not service.exclude_from_stats(dialog.mw.col):
            return
        search = service.scope(dialog.mw.col)
        if not search:
            return
    except Exception:
        log.exception("Cannot construct automatic statistics scope")
        label = QLabel("Archive filter could not be applied. Statistics may include archived cards.", dialog)
        label.setWordWrap(True)
        dialog.layout().insertWidget(0, label)
        return

    label = QLabel("Applying archive filter to statistics…", dialog)
    label.setWordWrap(True)
    dialog.layout().insertWidget(0, label)
    web = dialog.form.web
    generation = [0]
    alive = [True]
    def closed(*_):
        alive[0] = False
        generation[0] += 1
    dialog.finished.connect(closed)

    def on_load(ok):
        if not alive[0]:
            return
        generation[0] += 1
        current = generation[0]
        if not ok:
            label.setText("Archive filter could not be applied. Statistics may include archived cards.")
            return
        attempt(current, 0)

    def attempt(current, count):
        if not alive[0] or current != generation[0]:
            return
        def applied(ok):
            if not alive[0] or current != generation[0]:
                return
            if ok is True:
                label.setText("Archive filter applied on opening. Changing the search or scope can include archived cards.")
            elif count + 1 < MAX_ATTEMPTS:
                QTimer.singleShot(150, lambda: attempt(current, count + 1))
            else:
                label.setText("Archive filter could not be applied. Statistics may include archived cards.")
        web.evalWithCallback(search_script(search), applied)

    web.loadFinished.connect(on_load)
