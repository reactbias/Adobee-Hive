"""Simulated traveller traffic for the demo map. Every search here runs the real discovery code;
only the travellers are made up. The UI labels the result as simulated."""

import contextlib
import random
from datetime import date, timedelta

from . import hive, waiting

FEATURE_POOL = [
    ("dog-friendly", 8),
    ("late check-in", 7),
    ("quiet", 6),
    ("breakfast", 6),
    ("parking", 4),
    ("family rooms", 4),
    ("ev charging", 3),
    ("sauna", 3),
    ("accessible", 3),
    # asked for, offered by nobody in the seed data
    ("vegan breakfast", 5),
    ("bike rental", 2),
    ("pool", 2),
    ("pet sitting", 2),
    ("coworking", 3),
]
WAIT_SHARE = 0.6  # of unserved simulated travellers, how many ask their agent to wait
NEAR = ["basel sbb", "messe basel", "marktplatz", "badischer bahnhof", None]


def run(n: int = 40, seed: int | None = None) -> dict:
    """Run n random traveller searches through hive.discover and return the resulting demand map.

    Pass a seed for repeatable traffic (the tests do).
    """
    rng = random.Random(seed)
    names, weights = zip(*FEATURE_POOL, strict=False)
    for _ in range(n):
        start = date.today() + timedelta(days=rng.randint(3, 60))
        ask = {
            "features": sorted(set(rng.choices(names, weights=weights, k=rng.randint(1, 3)))),
            "near": rng.choice(NEAR),
            "max_price_chf": rng.choice([None, 150, 200, 250]),
            "check_in": start.isoformat(),
            "check_out": (start + timedelta(days=rng.randint(1, 4))).isoformat(),
            "guests": rng.choice([1, 1, 2, 2, 3]),
        }
        found = hive.discover(kind="hotel", **ask)
        if not found["matches"] and rng.random() < WAIT_SHARE:  # some travellers ask to be told
            with contextlib.suppress(hive.HiveError):  # e.g. the Hive is full of standing requests
                waiting.leave(**ask)
    return hive.demand_map()
