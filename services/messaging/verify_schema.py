#!/usr/bin/env python3
"""CLI wrapper to run schema verification on services/messaging/schemas/."""

import sys

from ubunturemit_messaging.verify_schema import cli_main

if __name__ == "__main__":
    sys.exit(cli_main())
