from __future__ import annotations

import json
from pathlib import Path

from sag_video.chamber import BrandContract, DraftPlan
from sag_video.models import ShortsGenerateRequest
from sag_video.rendering import RenderSpecification


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "packages" / "media-contracts" / "schema"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    contracts = {
        "brand-contract.schema.json": BrandContract.model_json_schema(),
        "draft-plan.schema.json": DraftPlan.model_json_schema(),
        "shorts-generate.schema.json": ShortsGenerateRequest.model_json_schema(),
        "render-spec.schema.json": RenderSpecification.model_json_schema(),
    }
    for filename, schema in contracts.items():
        (OUTPUT / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"exported {len(contracts)} contracts to {OUTPUT}")


if __name__ == "__main__":
    main()
