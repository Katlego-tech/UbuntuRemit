"""UbuntuRemit Rails Service.

No rail adapter ships yet: T052-T054 (Ripple, PAPSS, SWIFT) are blocked on sandbox
credentials. A RailRouter is built from adapters it is given, never from defaults.
"""

from ubunturemit_rails.base import (
    RailAdapter,
    RailStatus,
    RailSubmissionResult,
)
from ubunturemit_rails.router import (
    RailRouter,
    SettlementExhaustionError,
)

__all__ = [
    "RailAdapter",
    "RailRouter",
    "RailStatus",
    "RailSubmissionResult",
    "SettlementExhaustionError",
]
