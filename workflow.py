"""Synthetic sales workflow reference. Standard library only; no external I/O."""

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional


class WorkflowError(Exception):
    """A bounded, reviewable workflow failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ValidationError(WorkflowError):
    pass


class ApprovalError(WorkflowError):
    pass


class ConflictError(WorkflowError):
    pass


class RetryableError(WorkflowError):
    pass


def canonical_json(value: Any) -> str:
    # ASCII escaping also gives lone Unicode surrogates a deterministic encoding.
    # Reject NaN/Infinity rather than emitting non-standard JSON tokens.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuoteDraft:
    inquiry_id: str
    buyer_label: str
    sku: str
    quantity: int
    currency: str
    unit_price: str
    total: str
    catalogue_version: str
    source_hash: str
    status: str = "DRAFT_REQUIRES_REVIEW"

    @property
    def version_hash(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class ApprovalRecord:
    draft_hash: str
    reviewer_label: str
    decision: str


@dataclass(frozen=True)
class HandoffResult:
    record_id: str
    inquiry_id: str
    draft_hash: str
    replayed: bool
    destination: str = "LOCAL_SQLITE_SIMULATION"


def validate_catalogue(catalogue: Dict[str, Any]) -> None:
    """Validate both file-loaded and directly supplied trusted catalogue objects."""
    if not isinstance(catalogue, dict):
        raise ValidationError("invalid_catalogue", "Catalogue must be an object.")
    version = catalogue.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version) or catalogue.get("currency") != "EUR":
        raise ValidationError("invalid_catalogue", "A bounded version identifier and EUR currency are required.")
    products = catalogue.get("products")
    if not isinstance(products, dict) or not 1 <= len(products) <= 1000:
        raise ValidationError("invalid_catalogue", "Between one and 1000 synthetic products are required.")
    for sku, product in products.items():
        if not isinstance(product, dict):
            raise ValidationError("invalid_catalogue", "Each product must be an object.")
        price_text = product.get("unit_price")
        maximum = product.get("maximum_quantity")
        valid = (
            isinstance(sku, str)
            and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", sku)
            and isinstance(price_text, str)
            and re.fullmatch(r"[0-9]{1,8}\.[0-9]{2}", price_text)
            and Decimal(price_text) > 0
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and 0 < maximum <= 1_000_000
        )
        if not valid:
            raise ValidationError("invalid_catalogue", "Invalid product pricing or quantity limit.")


def load_catalogue(path: Path) -> Dict[str, Any]:
    try:
        catalogue = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValidationError("invalid_catalogue", "Catalogue must contain valid JSON.") from error
    validate_catalogue(catalogue)
    return catalogue


def build_draft(inquiry: Dict[str, Any], catalogue: Dict[str, Any]) -> QuoteDraft:
    """Parse only SKU/Quantity lines. Free text never controls policy or pricing."""
    validate_catalogue(catalogue)
    if not isinstance(inquiry, dict):
        raise ValidationError("invalid_inquiry", "Inquiry must be an object.")
    if set(inquiry) - {"inquiry_id", "buyer_label", "message"}:
        raise ValidationError("unexpected_field", "Only inquiry_id, buyer_label and message are supported.")
    inquiry_id = inquiry.get("inquiry_id")
    buyer = inquiry.get("buyer_label")
    message = inquiry.get("message")
    if not isinstance(inquiry_id, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,63}", inquiry_id):
        raise ValidationError("invalid_inquiry_id", "A bounded synthetic inquiry identifier is required.")
    if not isinstance(buyer, str) or not buyer.strip() or len(buyer) > 120 or any(c in buyer for c in "\r\n"):
        raise ValidationError("invalid_buyer", "A short, single-line buyer label is required.")
    if not isinstance(message, str) or len(message) > 8192:
        raise ValidationError("invalid_message", "Message must be text of at most 8192 characters.")
    fields: Dict[str, str] = {}
    for line in message.splitlines():
        match = re.fullmatch(r"\s*(SKU|Quantity)\s*:\s*(.*?)\s*", line, re.IGNORECASE)
        if match:
            key = match.group(1).lower()
            if key in fields:
                raise ValidationError("ambiguous_field", "Repeated structured fields require clarification.")
            fields[key] = match.group(2)
    for required in ("sku", "quantity"):
        if not fields.get(required):
            raise ValidationError("missing_" + required, "Missing structured field: " + required)
    sku = fields["sku"].upper()
    product = catalogue["products"].get(sku)
    if product is None:
        raise ValidationError("unknown_sku", "SKU is absent from the synthetic catalogue.")
    raw_quantity = fields["quantity"]
    if not re.fullmatch(r"[0-9]{1,7}", raw_quantity):
        raise ValidationError("invalid_quantity", "Quantity must be a positive whole number within the catalogue limit.")
    quantity = int(raw_quantity)
    if not 0 < quantity <= product["maximum_quantity"]:
        raise ValidationError("invalid_quantity", "Quantity is outside the synthetic catalogue limit.")
    unit_price = Decimal(product["unit_price"])
    total = unit_price * quantity
    return QuoteDraft(
        inquiry_id=inquiry_id,
        buyer_label=buyer.strip(),
        sku=sku,
        quantity=quantity,
        currency=catalogue["currency"],
        unit_price=format(unit_price, ".2f"),
        total=format(total, ".2f"),
        catalogue_version=catalogue["version"],
        source_hash=digest(inquiry),
    )


def record_review(draft: QuoteDraft, reviewer_label: str, decision: str) -> ApprovalRecord:
    """Bind an explicit decision to a draft. This function does NOT authenticate a person."""
    if not isinstance(reviewer_label, str) or not reviewer_label.strip() or len(reviewer_label) > 120 or any(c in reviewer_label for c in "\r\n"):
        raise ApprovalError("invalid_reviewer", "An explicit reviewer label is required.")
    if decision not in ("approve", "reject"):
        raise ApprovalError("invalid_decision", "Decision must be approve or reject.")
    return ApprovalRecord(checked_draft_hash(draft), reviewer_label.strip(), decision)


def checked_draft_hash(draft: QuoteDraft) -> str:
    if not isinstance(draft, QuoteDraft):
        raise ValidationError("invalid_draft", "A QuoteDraft object is required.")
    try:
        return draft.version_hash
    except (TypeError, ValueError) as error:
        raise ValidationError("invalid_draft", "Draft must have a standard JSON representation.") from error


class LocalCRM:
    """A transactional local simulation, not a CRM/ERP integration."""

    def __init__(self, database: Path):
        self.database = Path(database)
        with sqlite3.connect(str(self.database)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS crm_handoffs ("
                "inquiry_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, "
                "draft_hash TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "event_type TEXT NOT NULL, inquiry_id TEXT NOT NULL, details TEXT NOT NULL)"
            )

    def handoff(
        self,
        inquiry: Dict[str, Any],
        draft: QuoteDraft,
        approval: Optional[ApprovalRecord],
        catalogue: Dict[str, Any],
        simulate_failure_after_insert: bool = False,
    ) -> HandoffResult:
        if not isinstance(approval, ApprovalRecord) or approval.decision != "approve":
            raise ApprovalError("approval_required", "A positive review decision is required before handoff.")
        # Validate the review shape at the execution boundary too. This remains
        # a forgeable local simulation, not proof of a human's identity.
        valid_review = record_review(draft, approval.reviewer_label, approval.decision)
        if approval.draft_hash != valid_review.draft_hash:
            raise ApprovalError("approval_version_mismatch", "Draft changed after review; a new decision is required.")
        # Rebuild from source and the trusted catalogue; do not trust submitted prices.
        expected = build_draft(inquiry, catalogue)
        # Dataclass equality considers True == 1 and 1.0 == 1. Compare the exact
        # canonical JSON fingerprint so type-changing edits are rejected too.
        if draft.version_hash != expected.version_hash:
            raise ValidationError("draft_inconsistent", "Draft differs from source or the current catalogue.")
        with sqlite3.connect(str(self.database)) as connection:
            # Serialize read+write decisions, so competing callers cannot both create a record.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT record_id, draft_hash FROM crm_handoffs WHERE inquiry_id = ?", (draft.inquiry_id,)
            ).fetchone()
            if existing:
                if existing[1] != draft.version_hash:
                    raise ConflictError("inquiry_conflict", "Inquiry identifier already has a different committed draft.")
                connection.execute(
                    "INSERT INTO audit_events(event_type, inquiry_id, details) VALUES (?, ?, ?)",
                    ("DUPLICATE_REPLAY", draft.inquiry_id, canonical_json({"draft_hash": draft.version_hash})),
                )
                return HandoffResult(existing[0], draft.inquiry_id, draft.version_hash, True)
            record_id = "local-" + draft.inquiry_id.lower()
            payload = {"draft": asdict(draft), "review": asdict(approval), "simulation": True}
            connection.execute(
                "INSERT INTO crm_handoffs(inquiry_id, record_id, draft_hash, payload) VALUES (?, ?, ?, ?)",
                (draft.inquiry_id, record_id, draft.version_hash, canonical_json(payload)),
            )
            if simulate_failure_after_insert:
                raise RetryableError("simulated_transient_failure", "Injected local failure; transaction is rolled back.")
            connection.execute(
                "INSERT INTO audit_events(event_type, inquiry_id, details) VALUES (?, ?, ?)",
                (
                    "HANDOFF_COMMITTED",
                    draft.inquiry_id,
                    canonical_json({"draft_hash": draft.version_hash, "reviewer_label": approval.reviewer_label}),
                ),
            )
            return HandoffResult(record_id, draft.inquiry_id, draft.version_hash, False)

    def count_handoffs(self) -> int:
        with sqlite3.connect(str(self.database)) as connection:
            return connection.execute("SELECT COUNT(*) FROM crm_handoffs").fetchone()[0]

    def audit_events(self):
        with sqlite3.connect(str(self.database)) as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, inquiry_id, details FROM audit_events ORDER BY sequence"
            ).fetchall()
        return [dict(sequence=r[0], event_type=r[1], inquiry_id=r[2], details=json.loads(r[3])) for r in rows]
