"""Synthetic account/source/type collisions and canonical identity migration."""
from __future__ import annotations

import base64
import unittest
from dataclasses import replace

from gdt_tax.identity import (
    UNKNOWN,
    AttachmentKey,
    IdentityError,
    RecordKey,
    account_fingerprint,
    key_from_row,
    scope_targets,
)


class RecordKeyTests(unittest.TestCase):
    def test_roundtrip_preserves_remote_id_and_unicode_delimiters(self):
        for remote in ('G12.18-260120-123', 'a:b/c?d=e', 'mã "synthetic" 1'):
            key = RecordKey(account_fingerprint("synthetic-user"), "DVC", "DECLARATION", remote)
            self.assertEqual(RecordKey.parse(key.serialize()), key)
            self.assertEqual(RecordKey.parse(key.serialize()).remote_id, remote)
            self.assertNotIn("/", key.serialize())

    def test_every_identity_dimension_matters(self):
        key = RecordKey("account-a", "DVC", "DECLARATION", "same-id")
        keys = [key, replace(key, account_key="account-b"), replace(key, source="ETAX"),
                replace(key, document_kind="NOTICE"), replace(key, remote_id="other-id")]
        self.assertEqual(len({value.serialize() for value in keys}), 5)
        self.assertEqual(len({value.digest for value in keys}), 5)

    def test_unsupported_noncanonical_or_malformed_keys_fail_without_echoing_input(self):
        valid = RecordKey("a", "DVC", "DECLARATION", "id").serialize()
        for token in ("rk2.fake-secret", "rk1.@@fake-secret", valid + "=", "rk1." + base64.urlsafe_b64encode(b'{}').decode()):
            with self.assertRaises(IdentityError) as error:
                RecordKey.parse(token)
            self.assertNotIn("fake-secret", str(error.exception))

    def test_empty_control_and_wrong_field_types_are_rejected(self):
        for remote in ("", "id\nsecret", None, 123):
            with self.assertRaises(IdentityError):
                RecordKey("account", "DVC", "DECLARATION", remote)

    def test_account_fingerprint_is_stable_and_does_not_merge_case_variants(self):
        self.assertEqual(account_fingerprint("user"), account_fingerprint("user"))
        self.assertNotEqual(account_fingerprint("user"), account_fingerprint("User"))
        with self.assertRaises(IdentityError):
            account_fingerprint("")

    def test_legacy_metadata_keeps_unknown_ownership_and_source(self):
        key = key_from_row({"ma_ho_so": "same-id"}, "DECLARATION")
        self.assertEqual((key.account_key, key.source), (UNKNOWN, UNKNOWN))
        self.assertFalse(key.owned)
        self.assertEqual(key_from_row({"ctu_id": "same-id"}, "GNT").source, "GNT")

    def test_migration_identity_is_idempotent_and_retains_old_remote_fields(self):
        old = {"ma_ho_so": "same-id", "nguon": "ETAX", "tep_zip": "old.zip"}
        key = key_from_row(old, "DECLARATION")
        migrated = {**old, "record_key": key.serialize(), "account_key": key.account_key}
        self.assertEqual(key_from_row(migrated, "DECLARATION"), key)
        self.assertEqual(old["tep_zip"], migrated["tep_zip"])
        self.assertNotIn("account_key", old)

    def test_conflicting_serialized_and_plain_metadata_is_rejected(self):
        key = RecordKey("account", "DVC", "DECLARATION", "same-id")
        with self.assertRaisesRegex(IdentityError, "CONFLICT"):
            key_from_row({"record_key": key.serialize(), "ma_ho_so": "different-id"}, "DECLARATION")

    def test_scoped_selection_keeps_same_id_on_two_sources_separate(self):
        first = RecordKey("account", "DVC", "DECLARATION", "same-id")
        second = replace(first, source="ETAX")
        targets = scope_targets([first.serialize()], account_key="account", sources=["DVC", "ETAX"], document_kind="DECLARATION")
        self.assertIn(first.serialize(), targets)
        self.assertNotIn(second.serialize(), targets)
        with self.assertRaisesRegex(IdentityError, "AMBIGUOUS"):
            scope_targets(["same-id"], account_key="account", sources=["DVC", "ETAX"], document_kind="DECLARATION")

    def test_cross_account_and_kind_targets_fail_before_any_request(self):
        key = RecordKey("other-account", "DVC", "DECLARATION", "same-id")
        for target in (key, replace(key, account_key="account", document_kind="NOTICE")):
            with self.assertRaisesRegex(IdentityError, "SCOPE_MISMATCH"):
                scope_targets([target.serialize()], account_key="account", sources=["DVC"], document_kind="DECLARATION")
        self.assertEqual(scope_targets(["same-id"], account_key="account", sources=["DVC"], document_kind="DECLARATION"),
                         {RecordKey("account", "DVC", "DECLARATION", "same-id").serialize()})

    def test_attachment_identity_includes_parent_route_and_operation_dimensions(self):
        parent = RecordKey("account", "DVC", "DECLARATION", "parent")
        key = AttachmentKey(parent, "dvc", "same-notice-id")
        keys = [key, replace(key, source="tdt"), replace(key, parent=replace(parent, remote_id="other-parent")),
                replace(key, loai_tra_cuu="ETAX"), replace(key, loai_tbao="notice-kind")]
        self.assertEqual(len({value.serialize() for value in keys}), 5)
        for item in keys:
            self.assertEqual(AttachmentKey.parse(item.serialize()), item)
