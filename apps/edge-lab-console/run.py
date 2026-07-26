"""Local launcher for the simulated Tomato edge-lab console."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).parents[2]
    sources = (
        root / "apps" / "edge-lab-console" / "src",
        root / "packages" / "device-protocol" / "src",
        root / "packages" / "experiment-engine" / "src",
        root / "packages" / "policy-engine" / "src",
        root / "services" / "edge-agent" / "src",
    )
    for source in reversed(sources):
        sys.path.insert(0, str(source))
    from tomato_sentinel_edge_console.__main__ import main as console_main

    return console_main()


if __name__ == "__main__":
    raise SystemExit(main())
