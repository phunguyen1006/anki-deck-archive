# Anki Deck Archive

Archive a regular Anki deck without exporting its cards, and restore it when you need it again. The add-on hides the archive from the main deck list and can automatically apply an active-card filter when you open Anki's modern Statistics window.

> **Experimental:** Back up your collection and test with a separate profile first. Automatic filtering, hiding, sync, and desktop integration still have the limitations described below. This project is not affiliated with Anki or Ankitects.

## Compatibility

- Anki Desktop **26.08.1 and 26.09**. Integration is disabled on other versions.
- Regular decks and subdecks. The Default deck, filtered decks, and a deck with cards currently in a filtered deck cannot be archived.
- AnkiMobile, AnkiDroid, AnkiWeb and third-party statistics add-ons do not run this add-on's UI or statistics integration.

## Install or update

1. Make a complete collection backup: in Anki choose **File → Export**, export the full collection including scheduling and media, and keep the backup outside the profile. Anki's automatic backups are useful as well.
2. Download `AnkiDeckArchive.ankiaddon` from [Releases](../../releases) and install it via **Tools → Add-ons → Install from file** (or open the file in Windows).
3. Restart Anki. Installing the add-on does not automatically move any decks.

## Archive and restore

1. On the main deck list, open a deck's gear menu and select **Archive Deck**.
2. Check the deck and card counts, and confirm. The deck hierarchy moves into an internal archive container. The add-on hides its rows from the main deck list when its metadata is consistent.
3. Open **Tools → Archived Deck Manager**, or the **Archived Decks** link on the deck list. Select a row and use **View Cards** or **Restore**. Search and column sorting are available.
4. Review the proposed restore location. If the name is occupied, choose a different one; the add-on will not intentionally overwrite another deck.

Archive operates on whole decks, not individual cards. Cards remain in the collection and can still be found in Browse. Don't manually add unrelated cards or decks to the archive container. If its records are inconsistent, it remains visible and the manager may mark a row **needs attention**.

## Statistics

In **Archived Deck Manager**, leave **Automatically exclude archived decks when opening Statistics** checked (the default). After archiving, open Anki's normal modern **Stats** window: the add-on applies a custom search excluding the archive and displays a notice above the graphs. To change this default, toggle the checkbox in the manager; the setting applies to the collection and is saved in collection configuration.

To see **All Statistics**, choose **Collection** in the Statistics window. You may also edit its search normally. Reopen Statistics after changing the archive or setting. If the filter cannot be applied or archive metadata is inconsistent, the window displays a warning; do not assume the graphs exclude archived cards. The legacy Stats window (Shift-click), deck-list daily summary, third-party dashboards and mobile statistics are not modified.

The scope uses current deck membership: a card's earlier reviews follow its current deck, not the deck it belonged to when reviewed. Whole-collection statistics may include review history of deleted cards, while a filtered search cannot assign that history to a current card. Individual graphs and every edge case have not all been validated. The fallback **Tools → Active Statistics** provides the search for manual use if needed.

## Data, sync and safety

The add-on renames deck hierarchies using Anki's deck API; it does not intentionally delete cards, reset scheduling, suspend cards, or edit review history. Changes in parent deck limits can affect due-count aggregation. Manually studying archived cards still affects their schedules.

Archive records and the statistics preference are stored in collection configuration, which Anki sends during sync. Real multi-device sync and conflict recovery have not been tested. Avoid archive or restore operations on multiple devices concurrently: finish and sync on one device, then sync the other before making changes. Mobile clients may show the archive container. Keep backups.

## Troubleshooting and removal

- **No menu or warning about version:** confirm your Anki version and restart it after installation.
- **Archive visible or a row needs attention:** a deck may have been moved, removed, or added to the container outside the add-on. Inspect the manager and restore from a known-good backup if necessary; no records are automatically discarded.
- **Statistics warning:** the automatic filter did not apply. Use Anki's search manually only after checking archive integrity.
- **Uninstall:** restore archived decks first, sync, then remove the add-on in **Tools → Add-ons** and restart. Uninstalling does not itself restore or delete archived decks.

## Development

In an isolated Python environment install `anki==26.8.1`, `aqt==26.8.1`, and `pytest`; run `python -m pytest -q` and `python build.py`. The builder uses a fixed allowlist and validates the `.ankiaddon` ZIP. See [research](docs/technical-research.md), [architecture](docs/architecture.md), [compatibility](docs/compatibility.md), [test results](docs/test-results.md), and [contributing](CONTRIBUTING.md).

Released under the [MIT License](LICENSE).
