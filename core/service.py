"""Archive and restore using deck IDs and Anki's collection APIs."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from anki.collection import SearchNode
from anki.decks import DeckCollapseScope, DeckId

KEY = "anki_deck_archive_v1"
STATS_KEY = "anki_deck_archive_exclude_from_stats_v1"


class ArchiveError(Exception):
    """An operation was refused to protect the collection."""


def exclude_from_stats(col):
    value = col.get_config(STATS_KEY, True)
    if not isinstance(value, bool):
        raise ArchiveError("The archive statistics setting is invalid.")
    return value


def set_exclude_from_stats(col, enabled):
    if not isinstance(enabled, bool):
        raise ArchiveError("The archive statistics setting is invalid.")
    return col.set_config(STATS_KEY, enabled)


def load(col):
    data = col.get_config(KEY, None)
    if data is None:
        return {"version": 1, "container": None, "items": {}}
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("items"), dict)
            or not isinstance(data.get("container"), (int, type(None)))):
        raise ArchiveError("Archive metadata is invalid or from a newer version. No changes were made.")
    for key, item in data["items"].items():
        if (not str(key).isdigit() or not isinstance(item, dict)
                or not isinstance(item.get("original"), str)
                or not isinstance(item.get("archived_at"), str)):
            raise ArchiveError("Archive metadata is invalid. No changes were made.")
    return data


def save(col, data):
    return col.set_config(KEY, data, undoable=True)


def deck(col, did):
    result = col.decks.get(DeckId(int(did)), default=False)
    if not result:
        raise ArchiveError("The deck no longer exists. Refresh and try again.")
    return result


def subtree(col, did):
    root = deck(col, did)
    return [root] + [deck(col, child_id) for _, child_id in col.decks.children(DeckId(did))]


def validate_archive(col, did):
    data = load(col)
    root = deck(col, did)
    if did == 1:
        raise ArchiveError("The Default deck cannot be archived.")
    container = data["container"]
    if container:
        archive = deck(col, container)
        if did == container or root["name"].casefold().startswith((archive["name"] + "::").casefold()):
            raise ArchiveError("This deck is already inside the archive.")
    decks = subtree(col, did)
    if any(d["dyn"] for d in decks):
        raise ArchiveError("Filtered decks and parents containing them cannot be archived.")
    if any(str(d["id"]) in data["items"] for d in decks):
        raise ArchiveError("This hierarchy contains an existing archive record. Resolve it first.")
    # Filtered-deck membership has special scheduler semantics; don't move it.
    ids = [int(d["id"]) for d in decks]
    placeholders = ",".join("?" for _ in ids)
    if col.db.scalar(f"select count() from cards where odid in ({placeholders})", *ids):
        raise ArchiveError("Cards from this deck are in a filtered deck. Empty the filtered deck first.")
    return root, len(decks), col.decks.card_count(DeckId(did), True)


def unique_container_name(col):
    base = "~Anki Deck Archive"
    name = base
    while col.decks.id_for_name(name):
        name = f"{base} {uuid4().hex[:8]}"
    return name


def archive(col, did):
    root, _, count = validate_archive(col, did)
    ids = {int(d["id"]) for d in subtree(col, did)}
    data = load(col)
    undo = col.add_custom_undo_entry("Archive Deck")
    if data["container"] is None:
        data["container"] = int(col.decks.id(unique_container_name(col)))
        col.decks.set_collapsed(DeckId(data["container"]), True, DeckCollapseScope.REVIEWER)
        save(col, data)
    container = deck(col, data["container"])
    if container["dyn"]:
        raise ArchiveError("Archive container is a filtered deck; no deck was moved.")
    parent_name = root["name"].rpartition("::")[0]
    parent_id = col.decks.id_for_name(parent_name) if parent_name else None
    destination = container["name"] + "::" + root["name"].split("::")[-1]
    if col.decks.id_for_name(destination):
        destination += " (" + str(did) + ")"
    if col.decks.id_for_name(destination):
        raise ArchiveError("The archive destination is occupied. No deck was moved.")
    data["items"][str(did)] = {"original": root["name"], "parent_id": int(parent_id) if parent_id else None,
                                "archived_at": datetime.now(timezone.utc).isoformat(), "destination": destination}
    # Write intent first. A failure or interruption leaves a recoverable record.
    save(col, data)
    col.decks.rename(DeckId(did), destination)
    if (deck(col, did)["name"] != destination
            or {int(d["id"]) for d in subtree(col, did)} != ids
            or col.decks.card_count(DeckId(did), True) != count):
        raise ArchiveError("The deck move could not be verified. Its record was retained for recovery.")
    return col.merge_undo_entries(undo)


def suggested_destination(col, item):
    original = item["original"]
    parent_id = item.get("parent_id")
    if parent_id:
        parent = col.decks.get(DeckId(parent_id), default=False)
        if parent:
            return parent["name"] + "::" + original.split("::")[-1]
    return original


def restore(col, did, destination):
    data = load(col)
    item = data["items"].get(str(did))
    if not item:
        raise ArchiveError("No archive record exists for this deck.")
    root = deck(col, did)
    ids = {int(d["id"]) for d in subtree(col, did)}
    count = col.decks.card_count(DeckId(did), True)
    container = deck(col, data["container"]) if data["container"] else None
    if not container or not root["name"].casefold().startswith((container["name"] + "::").casefold()):
        raise ArchiveError("The recorded deck is outside the archive. No changes were made; inspect it in Anki.")
    destination = destination.strip()
    if not destination or any(not part.strip() for part in destination.split("::")):
        raise ArchiveError("Enter a valid destination deck name.")
    if destination.casefold() == container["name"].casefold() or destination.casefold().startswith((container["name"] + "::").casefold()):
        raise ArchiveError("Choose a destination outside the archive.")
    if col.decks.id_for_name(destination):
        raise ArchiveError("That destination already exists. Choose another name.")
    undo = col.add_custom_undo_entry("Restore Deck")
    col.decks.rename(DeckId(did), destination)
    if (deck(col, did)["name"] != destination
            or {int(d["id"]) for d in subtree(col, did)} != ids
            or col.decks.card_count(DeckId(did), True) != count):
        raise ArchiveError("The restore could not be verified. The archive record was retained.")
    del data["items"][str(did)]
    save(col, data)
    return col.merge_undo_entries(undo)


def rows(col):
    data = load(col)
    container = col.decks.get(DeckId(data["container"]), default=False) if data["container"] else None
    result = []
    for key, item in data["items"].items():
        d = col.decks.get(DeckId(int(key)), default=False)
        inside = bool(d and container and d["name"].casefold().startswith((container["name"] + "::").casefold()))
        names = " ".join(name for name, _ in col.decks.children(DeckId(int(key)))) if d else ""
        result.append((int(key), item["original"], col.decks.card_count(DeckId(int(key)), True) if d else 0,
                       item["archived_at"], d["name"] if d else "Missing deck", inside, names))
    return result


def visibility_ids(col):
    """Return only a verified archive subtree; fail open on inconsistent metadata."""
    data = load(col)
    if data["container"] is None:
        if data["items"]:
            raise ArchiveError("Archive container metadata is missing.")
        return []
    container = deck(col, data["container"])
    prefix = container["name"] + "::"
    descendants = col.decks.children(DeckId(data["container"]))
    direct = {int(did) for name, did in descendants
              if name.casefold().startswith(prefix.casefold())
              and "::" not in name[len(prefix):]}
    if (direct != {int(key) for key in data["items"]}
            or col.decks.card_count(DeckId(data["container"]), False)):
        raise ArchiveError("Archive container contains unrecorded decks or cards.")
    return [int(data["container"])] + [int(did) for _, did in descendants]


def scope(col):
    data = load(col)
    if not data["items"]:
        return ""
    if not data["container"]:
        raise ArchiveError("Archive container metadata is missing. Inspect the archive before using statistics.")
    container = deck(col, data["container"])
    # Refuse a scope that could silently omit unrelated cards or include a moved archive.
    known = {int(k) for k in data["items"]}
    for row in rows(col):
        if not row[5]:
            raise ArchiveError("An archive record is missing or outside the container. Inspect the manager first.")
    direct = {int(d.id) for d in col.decks.all_names_and_ids() if d.name.casefold().startswith((container["name"] + "::").casefold()) and "::" not in d.name[len(container["name"])+2:]}
    if direct != known or col.decks.card_count(DeckId(data["container"]), False):
        raise ArchiveError("The archive container contains unrecorded decks or cards. Inspect it before using statistics.")
    return col.build_search_string(SearchNode(negated=SearchNode(deck=container["name"])))
