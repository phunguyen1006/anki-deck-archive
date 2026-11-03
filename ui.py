"""Native desktop interface, built on Anki's hooks and Qt widgets."""
from __future__ import annotations

import logging
from datetime import datetime
import aqt
from aqt import gui_hooks, mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (QAction, QApplication, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                    QTableWidget, QTableWidgetItem, QVBoxLayout, Qt)
from aqt.utils import showInfo, showWarning, tooltip
from .core import service
from .statistics_integration import setup_stats

log = logging.getLogger(__name__)


def error(exc):
    log.exception("Archive operation failed", exc_info=(type(exc), exc, exc.__traceback__))
    message = str(exc) if isinstance(exc, service.ArchiveError) else "The operation could not be completed. Inspect the collection and archive manager before retrying."
    showWarning(message + "\n\nNo cards are intentionally deleted by this add-on.")


def query(parent, op, success):
    QueryOp(parent=parent, op=op, success=success).failure(error).with_progress().run_in_background()


def archive_action(did):
    def confirmed(info):
        root, decks, cards = info
        box = QMessageBox(mw)
        box.setWindowTitle("Archive Deck")
        box.setText(f'Archive "{root["name"]}"?\n\nDecks affected: {decks:,}\nCards affected: {cards:,}\n\nThe deck will move to the archive container. Cards and review history are retained. Automatic statistics filtering can be changed in Archived Deck Manager.')
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText("Archive")
        if box.exec() == QMessageBox.StandardButton.Yes:
            CollectionOp(mw, lambda col: service.archive(col, did)).success(lambda _: tooltip("Deck archived")).failure(error).run_in_background()
    query(mw, lambda col: service.validate_archive(col, did), confirmed)


def options(menu, did):
    menu.addSeparator()
    action = menu.addAction("Archive Deck")
    action.triggered.connect(lambda: archive_action(did))


class Manager(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("Archived Deck Manager")
        self.resize(760, 430)
        self.setMinimumSize(520, 300)
        self.entries = []
        layout = QVBoxLayout(self)
        label = QLabel("Search archived decks:")
        self.search = QLineEdit()
        label.setBuddy(self.search)
        layout.addWidget(label)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Deck Name", "Cards", "Archived"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.exclude = QCheckBox("Automatically exclude archived decks when opening Statistics")
        self.exclude.setToolTip("Applies an active-card search when Statistics opens. You can still change the scope in Statistics.")
        self.exclude.setEnabled(False)
        self.exclude.toggled.connect(self.set_exclude)
        layout.addWidget(self.exclude)
        buttons = QHBoxLayout()
        restore = QPushButton("Restore")
        view = QPushButton("View Cards")
        refresh = QPushButton("Refresh")
        close = QPushButton("Close")
        for button in (restore, view, refresh): buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.search.textChanged.connect(self.render)
        restore.clicked.connect(self.restore)
        view.clicked.connect(self.view)
        refresh.clicked.connect(self.refresh)
        close.clicked.connect(self.reject)
        self.search.setFocus()
        self.refresh()

    def refresh(self):
        query(self, lambda col: (service.rows(col), service.exclude_from_stats(col)), self.loaded)

    def loaded(self, result):
        rows, enabled = result
        self.entries = rows
        self.exclude.blockSignals(True)
        self.exclude.setChecked(enabled)
        self.exclude.blockSignals(False)
        self.exclude.setEnabled(True)
        self.render()

    def set_exclude(self, enabled):
        self.exclude.setEnabled(False)
        def saved(_):
            self.exclude.setEnabled(True)
        def failed(exc):
            error(exc)
            self.refresh()
        CollectionOp(self, lambda col: service.set_exclude_from_stats(col, enabled)).success(saved).failure(failed).run_in_background()

    def render(self):
        term = self.search.text().casefold()
        entries = [r for r in self.entries if term in (r[1] + " " + r[4] + " " + r[6]).casefold()]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        for index, row in enumerate(entries):
            did, name, count, stamp, path, inside, _ = row
            label = name if inside else name + " — needs attention"
            cells = [QTableWidgetItem(label), QTableWidgetItem(), QTableWidgetItem(stamp[:10])]
            cells[0].setData(Qt.ItemDataRole.UserRole, did)
            cells[0].setToolTip(path)
            cells[1].setData(Qt.ItemDataRole.DisplayRole, count)
            for col, cell in enumerate(cells): self.table.setItem(index, col, cell)
        self.table.setSortingEnabled(True)
        self.summary.setText(f"{len(self.entries):,} archived records; {sum(r[2] for r in self.entries):,} cards. " + ("Select Refresh after collection changes." if self.entries else "Decks you archive will appear here."))

    def selected(self):
        index = self.table.currentRow()
        item = self.table.item(index, 0) if index >= 0 else None
        if not item:
            showInfo("Select an archived deck first.", parent=self)
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def restore(self):
        did = self.selected()
        if did is None: return
        def choose(result):
            destination, occupied = result
            prompt = "Restore to this deck name:"
            if occupied:
                prompt = "The original destination is occupied. Choose another name:"
                destination += " (Restored)"
            name, ok = QInputDialog.getText(self, "Restore Deck", prompt, text=destination)
            if ok and name.strip():
                CollectionOp(self, lambda col: service.restore(col, did, name)).success(self.restored).failure(error).run_in_background()
        def plan(col):
            data = service.load(col)
            item = data["items"].get(str(did))
            if not item: raise service.ArchiveError("The archive record no longer exists.")
            destination = service.suggested_destination(col, item)
            return destination, bool(col.decks.id_for_name(destination))
        query(self, plan, choose)

    def restored(self, _):
        tooltip("Deck restored")
        self.refresh()

    def view(self):
        did = self.selected()
        if did is None: return
        def build(col):
            from anki.collection import SearchNode
            return col.build_search_string(SearchNode(deck=service.deck(col, did)["name"]))
        def open_browser(search):
            browser = aqt.dialogs.open("Browser", mw)
            browser.search_for(search)
        query(self, build, open_browser)


def open_manager():
    dialog = Manager()
    dialog.exec()


def statistics():
    def ready(search):
        QApplication.clipboard().setText(search)
        if search:
            msg = ("The Active Statistics search has been copied. In Anki's Statistics window, select the custom search field and paste it to view active cards. "
                   "Clear the search and choose Collection to view All Statistics.\n\n" + search +
                   "\n\nFiltered graphs follow the current deck membership. Deleted-card history and collection-wide figures can differ; third-party statistics are unaffected.")
        else:
            msg = "There are no archived decks. In Statistics, choose Collection for both Active and All Statistics."
        showInfo(msg, parent=mw, title="Active Statistics")
        mw.onStats()
    query(mw, service.scope, ready)


def browser_content(browser, content):
    try:
        count = len(service.load(mw.col)["items"])
        ids = service.visibility_ids(mw.col)
        if ids:
            # Scope CSS to exact Anki-generated deck row IDs, before the page renders.
            # No generated HTML is parsed or replaced. Invalid metadata fails open.
            selectors = ",".join(f'tr.deck[id="{did}"]' for did in ids)
            content.stats += f"<style>{selectors} {{ display: none; }}</style>"
        content.stats += f'<div><a href="#" onclick="pycmd(\'ada:manager\'); return false;">Archived Decks ({count})</a></div>'
    except Exception:
        log.exception("Unable to hide archive; leaving deck rows visible")
        content.stats += '<div><a href="#" onclick="pycmd(\'ada:manager\'); return false;">Archived Decks (needs attention)</a></div>'


def bridge(handled, message, context):
    if message == "ada:manager" and context is mw.deckBrowser:
        open_manager()
        return (True, None)
    return handled


def install():
    manager = QAction("Archived Deck Manager", mw)
    manager.triggered.connect(open_manager)
    mw.form.menuTools.addAction(manager)
    stats = QAction("Active Statistics", mw)
    stats.triggered.connect(statistics)
    mw.form.menuTools.addAction(stats)
    gui_hooks.deck_browser_will_show_options_menu.append(options)
    gui_hooks.deck_browser_will_render_content.append(browser_content)
    gui_hooks.webview_did_receive_js_message.append(bridge)
    gui_hooks.stats_dialog_will_show.append(setup_stats)
