"""Wallet and account balances API endpoint -- docs/design/frontend-web.md §4."""

from fastapi import APIRouter
from ubunturemit_gateway.models import WalletAccount, WalletResponse

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


@router.get("", response_model=WalletResponse)
def get_wallet_overview() -> WalletResponse:
    return WalletResponse(
        institution_name="Standard Bank of South Africa (SBSA)",
        accounts=[
            WalletAccount(
                currency="ZAR",
                balance_minor_units=4500000000,  # 45,000,000.00 ZAR
                institution_nostro_bic="SBICZAJJXXX",
            ),
            WalletAccount(
                currency="USD",
                balance_minor_units=250000000,  # 2,500,000.00 USD
                institution_nostro_bic="SBICUS33XXX",
            ),
            WalletAccount(
                currency="GHS",
                balance_minor_units=180000000,  # 1,800,000.00 GHS
                institution_nostro_bic="GHBKGHACXXX",
            ),
        ],
        recent_settlements=[
            {
                "reference": "UB-SETTL-901",
                "rail": "RIPPLE",
                "amount": "250,000.00 ZAR",
                "recipient": "Kwame Mensah (Ghana)",
                "status": "DELIVERED",
                "settlement_seconds": 3.2,
                "timestamp": "2026-08-31T10:45:12Z",
            },
            {
                "reference": "UB-SETTL-902",
                "rail": "PAPSS",
                "amount": "120,000.00 ZAR",
                "recipient": "Amina Bello (Nigeria)",
                "status": "DELIVERED",
                "settlement_seconds": 11.0,
                "timestamp": "2026-08-31T10:30:00Z",
            },
        ],
    )
