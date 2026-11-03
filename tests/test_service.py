from pathlib import Path
import sys
import pytest
from anki.collection import Collection
from anki.decks import DeckId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import service


@pytest.fixture
def col(tmp_path):
    collection = Collection(str(tmp_path / "test.anki2"))
    yield collection
    collection.close()


def add_card(col, deck_name, text):
    did = col.decks.id(deck_name)
    note = col.new_note(col.models.current())
    note.fields[0] = text
    note.fields[1] = "answer"
    col.add_note(note, DeckId(did))
    return int(did)


def snapshot(col):
    return (col.db.all("select id,nid,did,ord,type,queue,due,ivl,factor,reps,lapses,left,odue,odid,flags,data from cards order by id"),
            col.db.all("select id,mid,flds,tags from notes order by id"),
            col.db.all("select * from revlog order by id"))


def test_archive_restore_preserves_collection(col):
    add_card(col, "University::金融", "one")
    did = add_card(col, "University::金融::章", "two")
    root = col.decks.id_for_name("University::金融")
    before = snapshot(col)
    service.archive(col, root)
    assert col.decks.id_for_name("University::金融") is None
    assert snapshot(col) == before
    assert service.rows(col)[0][2] == 2
    assert len(col.find_cards(service.scope(col))) == 0
    service.restore(col, root, "University::金融")
    assert col.decks.id_for_name("University::金融::章") == did
    assert snapshot(col) == before
    assert len(col.find_cards(service.scope(col))) == 2


def test_scope_and_conflict(col):
    add_card(col, "Active", "a")
    did = add_card(col, "Archived", "b")
    service.archive(col, did)
    assert len(col.find_cards(service.scope(col))) == 1
    assert len(col.find_cards("")) == 2
    col.decks.id("Archived")
    with pytest.raises(service.ArchiveError): service.restore(col, did, "Archived")
    assert service.rows(col)[0][5]
    service.restore(col, did, "Archived (Restored)")
    assert len(col.find_cards(service.scope(col))) == 2


def test_default_and_duplicate_are_rejected(col):
    with pytest.raises(service.ArchiveError): service.archive(col, 1)
    did = col.decks.id("Empty")
    service.archive(col, did)
    with pytest.raises(service.ArchiveError): service.archive(col, did)


def test_existing_container_is_not_reused(col):
    other = col.decks.id("~Anki Deck Archive")
    did = col.decks.id("Empty")
    service.archive(col, did)
    assert service.load(col)["container"] != other
    assert col.decks.id_for_name("~Anki Deck Archive") == other


def test_renamed_parent_and_reopened_collection(col, tmp_path):
    parent = col.decks.id("Before")
    did = col.decks.id("Before::Child")
    service.archive(col, did)
    col.decks.rename(parent, "After")
    path = col.path
    col.close()
    reopened = Collection(path)
    data = service.load(reopened)
    assert service.suggested_destination(reopened, data["items"][str(did)]) == "After::Child"
    service.restore(reopened, did, "After::Child")
    assert reopened.decks.id_for_name("After::Child") == did
    reopened.close()
    # Fixture's original handle is already closed.
    col.close = lambda: None


def test_invalid_and_orphan_metadata_refuses_stats(col):
    did = col.decks.id("Deck")
    service.archive(col, did)
    col.decks.rename(did, "Moved by user")
    with pytest.raises(service.ArchiveError): service.scope(col)
    with pytest.raises(service.ArchiveError): service.restore(col, did, "Elsewhere")
    col.set_config(service.KEY, {"version": 99})
    with pytest.raises(service.ArchiveError): service.load(col)


def test_unrecorded_container_contents_refuse_stats(col):
    did = col.decks.id("Deck")
    service.archive(col, did)
    root = service.deck(col, service.load(col)["container"])["name"]
    add_card(col, root + "::Unrelated", "x")
    with pytest.raises(service.ArchiveError): service.scope(col)


def test_undo_redo_restores_metadata_with_decks(col):
    did = col.decks.id("Deck")
    service.archive(col, did)
    col.undo()
    assert col.decks.id_for_name("Deck") == did
    assert not service.load(col)["items"]
    col.redo()
    assert str(did) in service.load(col)["items"]
    assert service.rows(col)[0][5]


def test_native_graph_counts_and_review_scope(col):
    import time
    active = add_card(col, "Active", "active")
    archived = add_card(col, 'Tiếng Việt "日本語"', "archived")
    active_card = col.db.scalar("select id from cards where did = ?", active)
    archived_card = col.db.scalar("select id from cards where did = ?", archived)
    now = int(time.time() * 1000)
    for offset, cid in enumerate((active_card, archived_card)):
        col.db.execute("insert into revlog values (?, ?, -1, 3, 10, 5, 2500, 1500, 1)", now + offset, cid)
    service.archive(col, archived)
    filtered = col._backend.graphs(search=service.scope(col), days=0)
    all_graphs = col._backend.graphs(search="", days=0)
    assert filtered.card_counts.including_inactive.newCards == 1
    assert all_graphs.card_counts.including_inactive.newCards == 2
    assert filtered.today.answer_count == 1
    assert all_graphs.today.answer_count == 2
    service.restore(col, archived, 'Tiếng Việt "日本語"')
    assert col._backend.graphs(search=service.scope(col), days=0).today.answer_count == 2


def test_fifteen_thousand_card_scope(col):
    active = add_card(col, "Active", "active")
    archived = add_card(col, "Archived", "archived")
    # Synthetic cards in an isolated collection exercise scope size, not note integrity.
    columns = [row[1] for row in col.db.all("pragma table_info(cards)")]
    originals = [col.db.first("select * from cards where did = ?", did) for did in (active, archived)]
    id_index = columns.index("id")
    existing_max = max(row[id_index] for row in originals)
    inserts = []
    for source, count in zip(originals, (4999, 9999)):
        for _ in range(count):
            row = list(source)
            existing_max += 1
            row[id_index] = existing_max
            inserts.append(tuple(row))
    col.db.executemany("insert into cards values (" + ",".join("?" for _ in columns) + ")", inserts)
    assert len(col.find_cards("")) == 15000
    service.archive(col, archived)
    assert len(col.find_cards(service.scope(col))) == 5000
    assert len(col.find_cards("")) == 15000
    service.restore(col, archived, "Archived")
    assert len(col.find_cards(service.scope(col))) == 15000


def test_failed_move_keeps_record_and_cards(col, monkeypatch):
    did = add_card(col, "Deck", "a")
    before = snapshot(col)
    def fail(*args, **kwargs):
        raise RuntimeError("simulated move failure")
    monkeypatch.setattr(col.decks, "rename", fail)
    with pytest.raises(RuntimeError): service.archive(col, did)
    assert snapshot(col) == before
    assert str(did) in service.load(col)["items"]
    assert not service.rows(col)[0][5]
    with pytest.raises(service.ArchiveError): service.scope(col)


def test_card_queue_states_are_unchanged(col):
    did = add_card(col, "Deck", "new")
    add_card(col, "Deck", "suspended")
    card_ids = col.find_cards("")
    col.db.execute("update cards set queue = -1 where id = ?", card_ids[0])
    before = snapshot(col)
    service.archive(col, did)
    assert snapshot(col) == before
    service.restore(col, did, "Deck")
    assert snapshot(col) == before


def test_visibility_hides_only_verified_archive_subtree(col):
    active = col.decks.id("Active")
    root = col.decks.id("Archive me")
    child = col.decks.id("Archive me::Child")
    assert service.visibility_ids(col) == []
    service.archive(col, root)
    container = service.load(col)["container"]
    assert set(service.visibility_ids(col)) == {container, root, child}
    assert active not in service.visibility_ids(col)
    service.restore(col, root, "Archive me")
    assert service.visibility_ids(col) == [container]


def test_visibility_refuses_unrecorded_or_moved_decks(col):
    root = col.decks.id("Archive me")
    service.archive(col, root)
    container = service.deck(col, service.load(col)["container"])["name"]
    extra = col.decks.id(container + "::Unrecorded")
    with pytest.raises(service.ArchiveError): service.visibility_ids(col)
    col.decks.rename(extra, "Unrecorded")
    col.decks.rename(root, "Manually moved")
    with pytest.raises(service.ArchiveError): service.visibility_ids(col)


def test_browser_hook_scopes_css_and_fails_open(col, monkeypatch):
    import importlib
    import types
    package = types.ModuleType("ada_test_package")
    package.__path__ = [str(Path(__file__).resolve().parents[1])]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    ui = importlib.import_module("ada_test_package.ui")
    monkeypatch.setattr(ui, "mw", types.SimpleNamespace(col=col))
    active = col.decks.id("Active")
    archived = col.decks.id("Archived")
    service.archive(col, archived)
    container = service.load(col)["container"]
    content = types.SimpleNamespace(stats="original", tree="untouched")
    ui.browser_content(None, content)
    assert content.tree == "untouched"
    assert f'tr.deck[id="{archived}"]' in content.stats
    assert f'tr.deck[id="{container}"]' in content.stats
    assert f'tr.deck[id="{active}"]' not in content.stats
    col.decks.rename(archived, "Manually moved")
    content = types.SimpleNamespace(stats="original", tree="untouched")
    ui.browser_content(None, content)
    assert "<style>" not in content.stats
    assert "needs attention" in content.stats


def test_statistics_preference_persists_per_collection(col):
    assert service.exclude_from_stats(col) is True
    service.set_exclude_from_stats(col, False)
    assert service.exclude_from_stats(col) is False
    service.set_exclude_from_stats(col, True)
    assert service.exclude_from_stats(col) is True
    col.set_config(service.STATS_KEY, "invalid")
    with pytest.raises(service.ArchiveError):
        service.exclude_from_stats(col)


def test_statistics_hook_applies_scope_and_reports_failure(col, monkeypatch):
    import importlib
    import types
    package = types.ModuleType("ada_stats_test")
    package.__path__ = [str(Path(__file__).resolve().parents[1])]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    integration = importlib.import_module("ada_stats_test.statistics_integration")
    class Signal:
        def connect(self, callback): self.callback = callback
    class Label:
        def __init__(self, text, parent): self.text = text
        def setWordWrap(self, value): pass
        def setText(self, text): self.text = text
    class Layout:
        def insertWidget(self, index, label): self.label = label
    class Web:
        def __init__(self): self.loadFinished = Signal(); self.result = True
        def evalWithCallback(self, script, callback):
            self.script = script
            callback(self.result)
    class Dialog:
        def __init__(self):
            self.mw = types.SimpleNamespace(col=col)
            self.form = types.SimpleNamespace(web=Web())
            self.finished = Signal()
            self.box = Layout()
        def layout(self): return self.box
    monkeypatch.setattr(integration, "QLabel", Label)
    did = add_card(col, "Archived", "card")
    service.archive(col, did)
    dialog = Dialog()
    integration.setup_stats(dialog)
    dialog.form.web.loadFinished.callback(True)
    assert "statisticsSearchText" in dialog.form.web.script
    assert service.scope(col) in dialog.form.web.script.replace('\\"', '"')
    assert "filter applied" in dialog.box.label.text
    dialog.form.web.loadFinished.callback(False)
    assert "could not be applied" in dialog.box.label.text
    service.set_exclude_from_stats(col, False)
    no_filter = Dialog()
    integration.setup_stats(no_filter)
    assert not hasattr(no_filter.box, "label")
