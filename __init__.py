"""Anki Deck Archive entry point."""
from aqt import mw
from anki.buildinfo import version

if mw is not None and version in ("26.08.1", "26.8.1", "26.09", "26.9"):
    from .ui import install
    install()
elif mw is not None:
    from aqt.utils import showWarning
    from aqt import gui_hooks
    def unsupported():
        showWarning("Anki Deck Archive supports Anki 26.08.1 and 26.09 only. Integration is disabled for this version.")
    gui_hooks.profile_did_open.append(unsupported)
