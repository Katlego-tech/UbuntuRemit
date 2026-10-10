"""Compliance health API endpoint -- docs/design/gateway.md §5."""

from typing import Annotated

from fastapi import APIRouter, Depends
from ubunturemit_asco.guardrails.entry import ENTRY_GATE_RULES
from ubunturemit_gateway.dependencies import GatewayDependencies, get_dependencies
from ubunturemit_gateway.models import ComplianceHealthResponse
from ubunturemit_gateway.routes.transfers import AUDIT_LOGGER

router = APIRouter(prefix="/api/compliance", tags=["Compliance"])


@router.get("/health", response_model=ComplianceHealthResponse)
def get_compliance_health(
    deps: Annotated[GatewayDependencies, Depends(get_dependencies)],
) -> ComplianceHealthResponse:
    missing = deps.missing()
    screener = deps.sanctions_screener
    return ComplianceHealthResponse(
        status="UNAVAILABLE" if missing else "OPERATIONAL",
        missing_dependencies=missing,
        rules_enforced=list(ENTRY_GATE_RULES),
        sanctions_list=screener.source.citation() if screener is not None else None,
        audit_log=type(AUDIT_LOGGER).__name__,
    )
