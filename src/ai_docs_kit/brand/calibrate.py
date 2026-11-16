"""Compare mapped brand pages with their rendered specimens."""

import hashlib
import shutil
from functools import partial
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError

from ai_docs_kit.agents.client import Claude
from ai_docs_kit.agents.critic import BBox, CriticImage, _image_block
from ai_docs_kit.agents.prompts import system_blocks
from ai_docs_kit.brand.roles import load_roles, page_png
from ai_docs_kit.brand.specimen import SpecimenRender, _digest, component_pages, render_specimen
from ai_docs_kit.brand.work import work_dir
from ai_docs_kit.doctypes import Doctype
from ai_docs_kit.model import Format
from ai_docs_kit.theme.labels import token_paths
from ai_docs_kit.theme.loader import ThemeError, _check_families, _check_usage
from ai_docs_kit.theme.models import Tokens

Area = Literal["margins", "spacing", "hierarchy", "type-size", "colour", "alignment", "logo", "graphic", "other"]
Scalar = str | float | int


class TokenChange(BaseModel):
    token: str
    value: str


class CriticDifference(BaseModel):
    area: Area
    says: str
    brand_box: BBox | None
    specimen_box: BBox | None
    change: TokenChange | None


class CalibrationReport(BaseModel):
    differences: list[CriticDifference]


class Pair(BaseModel):
    component: str
    format: Format
    brand_file: str
    brand_page: int
    brand_png: str
    specimen_page: int
    specimen_png: str


class Difference(BaseModel):
    id: str
    component: str
    format: Format
    area: Area
    says: str
    brand_file: str
    brand_page: int
    specimen_page: int
    brand_box: BBox | None
    specimen_box: BBox | None
    token: str | None
    before: Scalar | None
    after: Scalar | None
    refused: str | None


def calibration_pairs(brand: Path, specimen: SpecimenRender) -> list[Pair]:
    pages = component_pages(specimen)
    pngs = {page.page: page.png for page in specimen.pages}
    pairs = []
    for mapping in load_roles(brand).mappings:
        if (
            mapping.format != specimen.format
            or mapping.component not in pages
            or Path(mapping.file).suffix.lower() != ".pdf"
        ):
            continue
        page = pages[mapping.component]
        pairs.append(
            Pair(
                component=mapping.component,
                format=mapping.format,
                brand_file=mapping.file,
                brand_page=mapping.page,
                brand_png=page_png(brand, mapping.file, mapping.page).relative_to(brand).as_posix(),
                specimen_page=page,
                specimen_png=pngs[page],
            )
        )
    return sorted(pairs, key=lambda pair: (pair.specimen_page, pair.brand_file, pair.brand_page))


def _tokens(theme_root: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((theme_root / "tokens.yaml").read_text(encoding="utf-8")))


def _leaf(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        value = value[part]
    return value


def offered_tokens(theme_root: Path, fmt: Format) -> dict[str, Scalar]:
    data = _tokens(theme_root)
    prefixes = (f"pages.{fmt}.", f"type.scale.{fmt}.", "colour.roles.")
    return {
        path: value
        for path in token_paths(data)
        if (path.startswith(prefixes) or path == "spacing.unit")
        and isinstance((value := _leaf(data, path)), (str, int, float))
        and not isinstance(value, bool)
    }


def _number(value: str) -> Scalar:
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def check_change(theme_root: Path, fmt: Format, change: TokenChange) -> str | None:
    if change.token not in offered_tokens(theme_root, fmt):
        return f"Token is not offered: {change.token}"
    data = _tokens(theme_root)
    parts = change.token.split(".")
    parent = data
    for part in parts[:-1]:
        parent = parent[part]
    parent[parts[-1]] = _number(change.value)
    try:
        tokens = Tokens.model_validate(data)
        _check_usage(tokens)
        _check_families(tokens)
    except (ValidationError, ThemeError) as error:
        return str(error)
    return None


calibrate_blocks = partial(system_blocks, "calibrate")


def _content(brand: Path, pair: Pair, tokens: dict[str, Scalar], rejected: list[str]) -> list[dict[str, Any]]:
    def image(path: str) -> dict[str, Any]:
        return _image_block(CriticImage(brand / path, 0, 0, 0, ""))

    lines = [f"COMPONENT: {pair.component}", f"FORMAT: {pair.format}", "TOKENS (change only these):"]
    lines.extend(f"{path} = {value}" for path, value in tokens.items())
    if rejected:
        lines.append("REJECTED BY THE PERSON (do not raise again):")
        lines.extend(rejected)
    return [
        {"type": "text", "text": f"Image 1 = brand page {pair.brand_file} p{pair.brand_page}"},
        image(pair.brand_png),
        {"type": "text", "text": f"Image 2 = specimen {pair.component}"},
        image(pair.specimen_png),
        {"type": "text", "text": "\n".join(lines)},
    ]


def _difference(pair: Pair, item: CriticDifference, root: Path, tokens: dict[str, Scalar]) -> Difference:
    identity = f"{pair.component}|{pair.brand_file}|{pair.brand_page}|{item.area}|{item.says}"
    token = before = after = refused = None
    if item.change is not None:
        refused = check_change(root, pair.format, item.change)
        if refused is None:
            token = item.change.token
            before = tokens[token]
            after = _number(item.change.value)
    return Difference(
        id=hashlib.sha1(identity.encode()).hexdigest()[:12],
        component=pair.component,
        format=pair.format,
        area=item.area,
        says=item.says,
        brand_file=pair.brand_file,
        brand_page=pair.brand_page,
        specimen_page=pair.specimen_page,
        brand_box=item.brand_box,
        specimen_box=item.specimen_box,
        token=token,
        before=before,
        after=after,
        refused=refused,
    )


async def compare(
    claude: Claude, brand: Path, specimen: SpecimenRender, *, rejected: list[str] | None = None
) -> list[Difference]:
    root = Path(specimen.theme_root)
    tokens = offered_tokens(root, specimen.format)
    result: list[Difference] = []
    seen: set[str] = set()
    for pair in calibration_pairs(brand, specimen):
        report = await claude.call(
            "calibrate",
            CalibrationReport,
            system=calibrate_blocks(),
            content=_content(brand, pair, tokens, rejected or []),
            effort="medium",
        )
        for item in report.differences:
            difference = _difference(pair, item, root, tokens)
            if difference.id not in seen:
                result.append(difference)
                seen.add(difference.id)
    return result


MAX_ROUNDS = 4
Stop = Literal["no-differences", "nothing-to-change", "differences-grew", "max-rounds", "no-pairs"]
CorrectionState = Literal["proposed", "superseded", "dropped", "confirmed", "rejected"]


class Round(BaseModel):
    number: int
    specimen: str
    differences: list[Difference]
    applied: list[str]


class Correction(BaseModel):
    id: str
    component: str
    format: Format
    area: Area
    says: str
    token: str
    before: Scalar
    after: Scalar
    brand_file: str
    brand_page: int
    specimen_page: int
    round: int
    state: CorrectionState = "proposed"
    note: str | None = None
    person: str | None = None
    change: str | None = None


class CalibrationRun(BaseModel):
    schema_version: int = 1
    doctype: str
    format: Format
    base_sha256: str
    candidate: str
    rounds: list[Round]
    stopped: Stop
    corrections: list[Correction]
    remaining: list[Difference]


def run_folder(brand: Path, doctype_name: str) -> Path:
    return work_dir(brand) / "calibration" / doctype_name


def load_run(brand: Path, doctype_name: str) -> CalibrationRun | None:
    path = run_folder(brand, doctype_name) / "run.json"
    return CalibrationRun.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def save_run(brand: Path, run: CalibrationRun) -> None:
    folder = run_folder(brand, run.doctype)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")


def set_token_value(tokens_path: Path, token: str, value: Scalar) -> None:
    data = cast(dict[str, Any], yaml.safe_load(tokens_path.read_text(encoding="utf-8")))
    parts = token.split(".")
    parent = data
    for part in parts[:-1]:
        parent = parent[part]
    if parts[-1] not in parent:
        raise KeyError(token)
    parent[parts[-1]] = value
    tokens_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _apply_round(round_: Round, corrections: list[Correction], candidate: Path, committed: dict[str, Any]) -> None:
    seen: set[str] = set()
    for difference in round_.differences:
        token, after = difference.token, difference.after
        if token is None or after is None or token in seen:
            continue
        seen.add(token)
        set_token_value(candidate / "tokens.yaml", token, after)
        round_.applied.append(difference.id)
        for previous in corrections:
            if previous.token == token and previous.state == "proposed":
                previous.state = "superseded"
        corrections.append(
            Correction(
                id=difference.id,
                component=difference.component,
                format=difference.format,
                area=difference.area,
                says=difference.says,
                token=token,
                before=_leaf(committed, token),
                after=after,
                brand_file=difference.brand_file,
                brand_page=difference.brand_page,
                specimen_page=difference.specimen_page,
                round=round_.number,
            )
        )


def _rollback(corrections: list[Correction], number: int) -> None:
    for correction in corrections:
        if correction.round == number and correction.state == "proposed":
            correction.state = "dropped"
            previous = next(
                (
                    c
                    for c in reversed(corrections)
                    if c.token == correction.token and c.state == "superseded" and c.round < number
                ),
                None,
            )
            if previous is not None:
                previous.state = "proposed"


async def calibrate_brand(
    claude: Claude, brand: Path, doctype: Doctype, *, max_rounds: int = MAX_ROUNDS
) -> CalibrationRun:
    previous = load_run(brand, doctype.name)
    corrections = [c for c in previous.corrections if c.state == "rejected"] if previous else []
    rejected = [f"{c.says} ({c.token})" for c in corrections]
    candidate = run_folder(brand, doctype.name) / "theme"
    if candidate.exists():
        shutil.rmtree(candidate)
    shutil.copytree(
        brand / "theme",
        candidate,
        ignore=lambda folder, names: ["work"] if Path(folder) == brand / "theme" / "ingest" and "work" in names else [],
    )
    run = CalibrationRun(
        doctype=doctype.name,
        format=doctype.format,
        base_sha256=_digest(brand / "theme"),
        candidate=candidate.relative_to(brand).as_posix(),
        rounds=[],
        stopped="max-rounds",
        corrections=corrections,
        remaining=[],
    )
    corrections = run.corrections
    committed = _tokens(brand / "theme")
    backup = b""
    max_rounds = min(max_rounds, MAX_ROUNDS)  # the contract's ceiling holds whatever a caller asks for
    for number in range(1, max_rounds + 1):
        specimen = render_specimen(brand, doctype, theme_root=candidate)
        if number == 1 and not calibration_pairs(brand, specimen):
            run.stopped = "no-pairs"
            break
        differences = await compare(claude, brand, specimen, rejected=rejected)
        differences = [
            d
            for d in differences
            if not any(
                (d.component, d.token, d.after) == (c.component, c.token, c.after)
                for c in corrections
                if c.state == "rejected"
            )
        ]
        round_ = Round(number=number, specimen=specimen.folder, differences=differences, applied=[])
        run.rounds.append(round_)
        if number > 1 and len(differences) > len(run.rounds[-2].differences):
            (candidate / "tokens.yaml").write_bytes(backup)
            _rollback(corrections, number - 1)
            run.remaining = run.rounds[-2].differences
            run.stopped = "differences-grew"
            break
        run.remaining = differences
        if not differences:
            run.stopped = "no-differences"
            break
        if number == max_rounds:
            break
        if not any(d.token for d in differences):
            run.stopped = "nothing-to-change"
            break
        backup = (candidate / "tokens.yaml").read_bytes()
        _apply_round(round_, corrections, candidate, committed)
    save_run(brand, run)
    return run
