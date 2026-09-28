#!/usr/bin/env python3
"""Attribution gates. Each gate either abstains (`None`) or returns a complete
attribution; the engine runs them in order and the first match wins.

No module here may import `analyze_case` (one-way dependency), and no gate may
mutate the evidence or context it reads.
"""
from __future__ import annotations
