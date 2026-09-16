"""
core/storage
────────────
Backward-compatible facade for DotGhostBoard storage engine.
Preserves identical public API while delegating to specialized repositories.
"""

from .database import (
    _DEFAULT_HOME,
    _USER_DATA,
    DB_PATH,
    THUMB_DIR,
    CAPTURES_DIR,
    _db,
    get_db_path,
    get_thumb_dir,
    get_captures_dir,
)

from .migrations import init_db

from .repositories.clips import (
    _get_file_hash,
    add_item,
    increment_copy_count,
    reset_copy_count,
    get_all_items,
    get_item_by_content,
    get_item_by_id,
    search_items,
    toggle_pin,
    update_item_field,
    update_preview,
    update_sort_order,
    export_items_txt,
    export_items_json,
    export_items,
    delete_item,
    delete_unpinned_items,
    mark_secret,
    encrypt_item,
    decrypt_item,
    decrypt_item_permanent,
    get_secret_items,
    encrypt_all_text_items,
    decrypt_all_secret_items,
    reencrypt_all_secret_items,
    clean_old_captures,
)

from .repositories.stats import (
    get_today_stats,
    get_stats,
)

from .repositories.tags import (
    _parse_tags,
    _serialize_tags,
    get_tags,
    add_tag,
    remove_tag,
    get_items_by_tag,
    get_all_tags,
    rename_tag,
    delete_tag,
)

from .repositories.collections import (
    create_collection,
    delete_collection,
    get_collections,
    get_collection_by_id,
    rename_collection,
    move_to_collection,
    get_items_by_collection,
)

from .repositories.peers import (
    add_trusted_peer,
    get_trusted_peer,
    get_all_trusted_peers,
    remove_trusted_peer,
    is_peer_trusted,
)

__all__ = [
    # Paths & Connection
    "_DEFAULT_HOME",
    "_USER_DATA",
    "DB_PATH",
    "THUMB_DIR",
    "CAPTURES_DIR",
    "_db",
    "get_db_path",
    "get_thumb_dir",
    "get_captures_dir",
    "init_db",
    # Clips
    "_get_file_hash",
    "add_item",
    "increment_copy_count",
    "reset_copy_count",
    "get_all_items",
    "get_item_by_content",
    "get_item_by_id",
    "search_items",
    "toggle_pin",
    "update_item_field",
    "update_preview",
    "update_sort_order",
    "export_items_txt",
    "export_items_json",
    "export_items",
    "delete_item",
    "delete_unpinned_items",
    "mark_secret",
    "encrypt_item",
    "decrypt_item",
    "decrypt_item_permanent",
    "get_secret_items",
    "encrypt_all_text_items",
    "decrypt_all_secret_items",
    "reencrypt_all_secret_items",
    "clean_old_captures",
    # Stats
    "get_today_stats",
    "get_stats",
    # Tags
    "_parse_tags",
    "_serialize_tags",
    "get_tags",
    "add_tag",
    "remove_tag",
    "get_items_by_tag",
    "get_all_tags",
    "rename_tag",
    "delete_tag",
    # Collections
    "create_collection",
    "delete_collection",
    "get_collections",
    "get_collection_by_id",
    "rename_collection",
    "move_to_collection",
    "get_items_by_collection",
    # Peers
    "add_trusted_peer",
    "get_trusted_peer",
    "get_all_trusted_peers",
    "remove_trusted_peer",
    "is_peer_trusted",
]
