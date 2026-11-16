"""Claude roles and page evidence for brand ingestion."""

import os
from pathlib import Path
from typing import Any

from ai_docs_kit.agents.cassette import Cassette, Transport
from ai_docs_kit.agents.client import AnthropicTransport, CassetteTransport, Claude, image_block
from ai_docs_kit.agents.ledger import Ledger
from ai_docs_kit.brand.pages import PageEntry
from ai_docs_kit.config import ProjectConfig, load_project_config

BRAND_ROLES = ("brand.segment", "brand.extract", "brand.synthesise")


def brand_models(config: ProjectConfig) -> dict[str, str]:
    models = config.models
    return {
        **models,
        "brand.segment": models.get("brand.segment", models.get("triage", ProjectConfig().models["triage"])),
        "brand.extract": models.get("brand.extract", models["critic"]),
        "brand.synthesise": models.get("brand.synthesise", models["critic"]),
    }


def brand_transport(brand: Path) -> Transport:
    path = brand / "theme/ingest/work/cassette.json"
    if os.environ.get("DOCLA_LIVE") != "1":
        return CassetteTransport(Cassette(path, "replay"))
    transport = AnthropicTransport()
    if os.environ.get("DOCLA_RECORD") == "1":
        return CassetteTransport(Cassette(path, "record", transport=transport))
    return transport


def brand_claude(brand: Path) -> Claude:
    config = load_project_config(Path.cwd())
    return Claude(
        brand_transport(brand),
        Ledger(brand / "theme/ingest/work/ledger.jsonl", config.prices, None),
        brand_models(config),
    )


def page_blocks(entry: PageEntry, brand: Path) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": f'<page file="{entry.file}" number="{entry.page}">\n{entry.text}\n</page>'},
        image_block(brand / entry.png),
    ]
