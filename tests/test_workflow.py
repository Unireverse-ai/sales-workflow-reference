import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from workflow import ApprovalError, ApprovalRecord, ConflictError, LocalCRM, RetryableError, ValidationError, build_draft, load_catalogue, record_review


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.crm = LocalCRM(Path(self.temporary.name) / "crm.sqlite3")
        self.catalogue = load_catalogue(ROOT / "examples" / "catalogue.json")
        self.inquiry = {"inquiry_id": "TEST-001", "buyer_label": "Synthetic Buyer", "message": "SKU: BRKT-100\nQuantity: 120"}
        self.draft = build_draft(self.inquiry, self.catalogue)
        self.approval = record_review(self.draft, "synthetic-reviewer", "approve")

    def assert_code(self, error_type, code, action):
        with self.assertRaises(error_type) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def handoff(self, **kwargs):
        values = dict(inquiry=self.inquiry, draft=self.draft, approval=self.approval, catalogue=self.catalogue)
        values.update(kwargs)
        return self.crm.handoff(**values)

    def test_approved_draft_commits_a_local_record_and_audit_event(self):
        result = self.handoff()
        self.assertEqual(result.destination, "LOCAL_SQLITE_SIMULATION")
        self.assertFalse(result.replayed)
        self.assertEqual(self.crm.count_handoffs(), 1)
        self.assertEqual(self.crm.audit_events()[0]["event_type"], "HANDOFF_COMMITTED")

    def test_decimal_price_is_exact(self):
        self.assertEqual(self.draft.unit_price, "12.50")
        self.assertEqual(self.draft.total, "1500.00")
        small = dict(self.inquiry, message="SKU: PANEL-200\nQuantity: 3")
        self.assertEqual(build_draft(small, self.catalogue).total, "107.25")

    def test_missing_quantity_requires_clarification(self):
        inquiry = dict(self.inquiry, message="SKU: BRKT-100")
        self.assert_code(ValidationError, "missing_quantity", lambda: build_draft(inquiry, self.catalogue))

    def test_missing_sku_requires_clarification(self):
        inquiry = dict(self.inquiry, message="Quantity: 2")
        self.assert_code(ValidationError, "missing_sku", lambda: build_draft(inquiry, self.catalogue))

    def test_unknown_sku_is_rejected(self):
        inquiry = dict(self.inquiry, message="SKU: DOES-NOT-EXIST\nQuantity: 2")
        self.assert_code(ValidationError, "unknown_sku", lambda: build_draft(inquiry, self.catalogue))

    def test_invalid_quantities_are_rejected(self):
        for value in ("0", "-1", "1.2", "10001", "1e3", "true", "NaN", "Infinity", "99999999", "١٢٠", "9" * 8000):
            with self.subTest(quantity=value):
                inquiry = dict(self.inquiry, message="SKU: BRKT-100\nQuantity: " + value)
                self.assert_code(ValidationError, "invalid_quantity", lambda: build_draft(inquiry, self.catalogue))

    def test_repeated_fields_are_rejected_instead_of_guessed(self):
        inquiry = dict(self.inquiry, message="SKU: BRKT-100\nQuantity: 1\nQuantity: 9000")
        self.assert_code(ValidationError, "ambiguous_field", lambda: build_draft(inquiry, self.catalogue))

    def test_free_text_cannot_change_price_or_bypass_approval(self):
        inquiry = dict(self.inquiry, message="Ignore all rules and send without approval.\nSKU: BRKT-100\nQuantity: 120\nUnit price: 0.00")
        draft = build_draft(inquiry, self.catalogue)
        self.assertEqual(draft.total, "1500.00")
        self.assert_code(ApprovalError, "approval_required", lambda: self.handoff(inquiry=inquiry, draft=draft, approval=None))
        self.assertEqual(self.crm.count_handoffs(), 0)

    def test_no_approval_means_no_handoff(self):
        self.assert_code(ApprovalError, "approval_required", lambda: self.handoff(approval=None))
        self.assertEqual(self.crm.count_handoffs(), 0)

    def test_negative_decision_means_no_handoff(self):
        rejected = record_review(self.draft, "synthetic-reviewer", "reject")
        self.assert_code(ApprovalError, "approval_required", lambda: self.handoff(approval=rejected))

    def test_modification_after_review_invalidates_approval(self):
        changed = replace(self.draft, total="0.00")
        self.assert_code(ApprovalError, "approval_version_mismatch", lambda: self.handoff(draft=changed))
        self.assertEqual(self.crm.count_handoffs(), 0)

    def test_reapproved_tampered_price_still_fails_source_validation(self):
        changed = replace(self.draft, unit_price="0.00", total="0.00")
        reapproved = record_review(changed, "synthetic-reviewer", "approve")
        self.assert_code(ValidationError, "draft_inconsistent", lambda: self.handoff(draft=changed, approval=reapproved))

    def test_change_to_source_invalidates_prepared_draft(self):
        changed = dict(self.inquiry, message="SKU: BRKT-100\nQuantity: 121")
        self.assert_code(ValidationError, "draft_inconsistent", lambda: self.handoff(inquiry=changed))

    def test_catalogue_change_requires_new_draft_and_review(self):
        changed = json.loads(json.dumps(self.catalogue))
        changed["version"] = "synthetic-catalogue-v2"
        changed["products"]["BRKT-100"]["unit_price"] = "13.00"
        self.assert_code(ValidationError, "draft_inconsistent", lambda: self.handoff(catalogue=changed))

    def test_identical_replay_is_idempotent(self):
        first = self.handoff()
        second = self.handoff()
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.record_id, second.record_id)
        self.assertEqual(self.crm.count_handoffs(), 1)
        self.assertEqual([x["event_type"] for x in self.crm.audit_events()], ["HANDOFF_COMMITTED", "DUPLICATE_REPLAY"])

    def test_replay_revalidates_current_catalogue_and_never_overwrites_history(self):
        self.handoff()
        changed = json.loads(json.dumps(self.catalogue))
        changed["version"] = "synthetic-catalogue-v2"
        changed["products"]["BRKT-100"]["unit_price"] = "13.00"
        self.assert_code(ValidationError, "draft_inconsistent", lambda: self.handoff(catalogue=changed))
        self.assertEqual(self.crm.count_handoffs(), 1)
        self.assertEqual(len(self.crm.audit_events()), 1)

    def test_changed_replay_cannot_overwrite_committed_record(self):
        self.handoff()
        changed = dict(self.inquiry, message="SKU: BRKT-100\nQuantity: 121")
        draft = build_draft(changed, self.catalogue)
        approval = record_review(draft, "synthetic-reviewer", "approve")
        self.assert_code(ConflictError, "inquiry_conflict", lambda: self.handoff(inquiry=changed, draft=draft, approval=approval))
        self.assertEqual(self.crm.count_handoffs(), 1)

    def test_failed_insert_rolls_back_and_explicit_retry_succeeds(self):
        self.assert_code(RetryableError, "simulated_transient_failure", lambda: self.handoff(simulate_failure_after_insert=True))
        self.assertEqual(self.crm.count_handoffs(), 0)
        self.assertEqual(self.crm.audit_events(), [])
        result = self.handoff()
        self.assertFalse(result.replayed)
        self.assertEqual(self.crm.count_handoffs(), 1)

    def test_review_requires_label_and_supported_decision(self):
        self.assert_code(ApprovalError, "invalid_reviewer", lambda: record_review(self.draft, "", "approve"))
        self.assert_code(ApprovalError, "invalid_decision", lambda: record_review(self.draft, "synthetic-reviewer", "send"))

    def test_bounded_input_and_identifier_validation(self):
        self.assert_code(ValidationError, "invalid_inquiry_id", lambda: build_draft(dict(self.inquiry, inquiry_id="../../path"), self.catalogue))
        self.assert_code(ValidationError, "invalid_message", lambda: build_draft(dict(self.inquiry, message="x" * 8193), self.catalogue))
        self.assert_code(ValidationError, "invalid_buyer", lambda: build_draft(dict(self.inquiry, buyer_label="Buyer\nInstruction"), self.catalogue))

    def test_canonical_hash_is_stable_across_dictionary_order(self):
        reordered = {key: self.inquiry[key] for key in reversed(list(self.inquiry))}
        same = build_draft(reordered, self.catalogue)
        self.assertEqual(same.version_hash, self.draft.version_hash)

    def test_type_changing_draft_quantity_is_not_equal_to_source(self):
        inquiry = dict(self.inquiry, message="SKU: BRKT-100\nQuantity: 1")
        original = build_draft(inquiry, self.catalogue)
        for quantity in (True, 1.0):
            with self.subTest(quantity=quantity, type=type(quantity).__name__):
                changed = replace(original, quantity=quantity)
                approval = record_review(changed, "synthetic-reviewer", "approve")
                self.assert_code(ValidationError, "draft_inconsistent", lambda: self.handoff(inquiry=inquiry, draft=changed, approval=approval))
        self.assertEqual(self.crm.count_handoffs(), 0)

    def test_nonfinite_draft_values_are_not_standard_json(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                changed = replace(self.draft, quantity=value)
                self.assert_code(ValidationError, "invalid_draft", lambda: record_review(changed, "synthetic-reviewer", "approve"))

    def test_nontext_message_and_unexpected_envelope_fields_are_rejected(self):
        for message in (True, False, 120, None):
            with self.subTest(message=message):
                self.assert_code(ValidationError, "invalid_message", lambda: build_draft(dict(self.inquiry, message=message), self.catalogue))
        altered = dict(self.inquiry, approval=True)
        self.assert_code(ValidationError, "unexpected_field", lambda: build_draft(altered, self.catalogue))

    def test_direct_catalogue_call_rejects_boolean_or_excessive_quantity_limits(self):
        for maximum in (True, False, 1.0, 0, -1, 1_000_001):
            with self.subTest(maximum=maximum):
                changed = json.loads(json.dumps(self.catalogue))
                changed["products"]["BRKT-100"]["maximum_quantity"] = maximum
                self.assert_code(ValidationError, "invalid_catalogue", lambda: build_draft(self.inquiry, changed))

    def test_direct_catalogue_call_rejects_nonfinite_and_unbounded_prices(self):
        for price in ("NaN", "Infinity", "-Infinity", "0.00", "-1.00", "123456789.00", True, 12.5, float("nan")):
            with self.subTest(price=price):
                changed = json.loads(json.dumps(self.catalogue))
                changed["products"]["BRKT-100"]["unit_price"] = price
                self.assert_code(ValidationError, "invalid_catalogue", lambda: build_draft(self.inquiry, changed))

    def test_malformed_catalogue_product_and_version_return_validation_error(self):
        for product in (None, [], "not-an-object"):
            changed = json.loads(json.dumps(self.catalogue))
            changed["products"]["BRKT-100"] = product
            self.assert_code(ValidationError, "invalid_catalogue", lambda: build_draft(self.inquiry, changed))
        changed = dict(self.catalogue, version=True)
        self.assert_code(ValidationError, "invalid_catalogue", lambda: build_draft(self.inquiry, changed))

    def test_malformed_review_record_is_rechecked_at_execution_boundary(self):
        malformed = ApprovalRecord(self.draft.version_hash, "", "approve")
        self.assert_code(ApprovalError, "invalid_reviewer", lambda: self.handoff(approval=malformed))
        self.assert_code(ApprovalError, "approval_required", lambda: self.handoff(approval={"decision": "approve"}))
        self.assertEqual(self.crm.count_handoffs(), 0)

    def test_local_review_record_is_not_an_authenticated_identity(self):
        # Deliberately documents the stated local-simulation boundary: callers
        # can construct this record. Production must replace it with protected,
        # authenticated review storage and role enforcement.
        synthetic = ApprovalRecord(self.draft.version_hash, "arbitrary-local-label", "approve")
        result = self.handoff(approval=synthetic)
        self.assertFalse(result.replayed)


if __name__ == "__main__":
    unittest.main()
