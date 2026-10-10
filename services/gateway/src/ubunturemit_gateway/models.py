"""Data transfer schemas for the gateway -- docs/design/gateway.md §5."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class QuoteRequest(BaseModel):
    source_currency: str = Field(..., description="ISO 4217 source currency (e.g. ZAR)")
    target_currency: str = Field(..., description="ISO 4217 target currency (e.g. GHS)")
    send_amount_minor_units: int = Field(..., gt=0, description="Amount in source minor units")


class QuoteResponse(BaseModel):
    source_currency: str
    target_currency: str
    send_amount_minor_units: int
    recipient_receives_minor_units: int
    exchange_rate: Decimal
    fee_minor_units: int
    estimated_seconds: Decimal
    available_rails: list[str]


class TransferInitiationRequest(BaseModel):
    source_currency: str
    target_currency: str
    send_amount_minor_units: int
    sender_name: str
    sender_account: str
    sender_bic: str
    sender_country: str
    sender_national_id: str
    # The entry gate's KYC tiers. Required: a defaulted or coerced tier is an invented
    # KYC fact, and it would choose the single-transfer limit the gate applies.
    sender_kyc_tier: Literal["L1", "L2", "L3"]
    sender_is_pep: bool = False
    recipient_name: str
    recipient_account: str
    recipient_bic: str
    recipient_country: str
    recipient_national_id: str
    purpose: str
    source_of_funds: str
    # Compliance inputs the institution's own records hold. Required: the gateway has no
    # transfer history or account register of its own, and a default here would be a
    # fabricated fact fed to the velocity and account-age checks.
    sender_prior_transfers_30d_count: int = Field(..., ge=0)
    sender_prior_transfers_30d_minor_units: int = Field(..., ge=0)
    recipient_account_age_days: int = Field(..., ge=0)


class TransferResponse(BaseModel):
    transfer_id: str
    reference: str
    status: str
    outcome: str
    selected_rail: str | None
    fee_minor_units: int
    settlement_seconds: Decimal | None
    cited_rules: list[str] = []
    reason: str = ""


class ComplianceHealthResponse(BaseModel):
    """What the deployment can actually do -- every field derived from its wiring."""

    status: str  # "OPERATIONAL" only when no source is missing, else "UNAVAILABLE"
    missing_dependencies: list[str]
    rules_enforced: list[str]  # the rule IDs the deterministic entry gate can cite
    sanctions_list: str | None  # the loaded list's citation, or None when none is loaded
    limit_table: str | None  # the loaded limit table's citation, or None
    audit_log: str | None  # the audit sink in use, by type; None when none is configured
    # No persistent screening history exists yet (T050a), so there is nothing to count.
    rejection_rate_24h: float | None = None
    total_screened_24h: int | None = None
