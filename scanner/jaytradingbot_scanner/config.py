from __future__ import annotations

import json
from pathlib import Path

from .models import Cycle, Leg, RouterKind, ScanPolicy


def load_config(path: str) -> tuple[str, ScanPolicy, list[Cycle]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    policy = ScanPolicy(**raw["policy"])
    cycles: list[Cycle] = []
    for item in raw["cycles"]:
        legs = tuple(
            Leg(kind=RouterKind(leg["kind"]), **{k: v for k, v in leg.items() if k != "kind"})
            for leg in item["legs"]
        )
        cycles.append(Cycle(legs=legs, **{k: v for k, v in item.items() if k != "legs"}))
    return raw["aave_provider"], policy, cycles
