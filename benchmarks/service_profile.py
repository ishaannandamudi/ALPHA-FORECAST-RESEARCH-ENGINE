"""Bounded offline measurement; native fixture setup is excluded, no production SLA."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.service_demo import demo


def main() -> None:
    with TemporaryDirectory(prefix="afre-service-profile-") as work:
        steps, measures = demo(Path(work))
    report = {
        "engine": "0.25.0",
        "store": "1.24",
        "api": "1.0",
        "native_fixture": True,
        "asserted_demo_steps": len(steps),
        "measurements": measures,
        "units": "seconds except storage_bytes and max_numerical_error",
        "limitations": "bounded synthetic offline measurements; no production SLA",
    }
    Path("docs/service-profile.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
