"""Data transfer schemas for FastAPI Gateway -- docs/design/frontend-web.md §4, §6."""

from decimal import Decimal
from typing import Any

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
    sender_kyc_tier: str = "TIER_3"
    sender_is_pep: bool = False
    recipient_name: str
    recipient_account: str
    recipient_bic: str
    recipient_country: str
    recipient_national_id: str
    purpose: str
    source_of_funds: str


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
    status: str
    engine_version: str
    rules_enforced: list[str]
    sanctions_list_status: str
    audit_log_status: str
    rejection_rate_24h: float
    total_screened_24h: int


class WalletAccount(BaseModel):
    currency: str
    balance_minor_units: int
    institution_nostro_bic: str


class WalletResponse(BaseModel):
    institution_name: str
    accounts: list[WalletAccount]
    recent_settlements: list[dict[str, Any]]


class SessionResponse(BaseModel):
    institution_id: str
    institution_name: str
    country: str
    kyc_tier: str
    status: str
