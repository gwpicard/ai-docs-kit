import hashlib
import shutil
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_docs_kit.model import Document, Format, Item, Section
from ai_docs_kit.render.chart_spec import resolve_chart
from ai_docs_kit.render.chooser import Chooser, ChooserError, load_chooser
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.kit import components_dir, lib_dir, library_dir
from ai_docs_kit.theme import Theme
from ai_docs_kit.theme.typst import render_theme_typ

M1_COMPONENTS: dict[tuple[Format, str], str] = {
    ("slides", "statement"): "statement",
    ("slides", "bullets"): "bullets",
    ("doc", "body"): "body",
    ("doc", "callout"): "callout",
}


CHART_COMPONENTS: frozenset[str] = frozenset({"chart", "doc-chart", "chart-table"})


class ComposeError(ValueError):
    pass


class ComposedSection(BaseModel):
    id: str
    component: str
    intent: str | None = None
    props: dict[str, Any]
    content: dict[str, Any] = Field(default_factory=dict)
    image_path: Path | None = Field(default=None, exclude=True)


class Composition(BaseModel):
    format: Format
    sections: list[ComposedSection]
    front: dict[str, str] = Field(default_factory=dict)
    version_date: date | None = None


def build_date() -> date:
    """Return the local calendar date for a new build."""
    return date.today()


def _british_date(day: date | None) -> str:
    if day is None:
        return ""
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    return f"{day.day} {months[day.month - 1]} {day.year}"


@cache
def default_chooser() -> Chooser:
    """Return the packaged chooser, read once."""
    return load_chooser()


def _chosen(section: Section, fmt: Format, chooser: Chooser, index: int, total: int) -> str | None:
    if section.component in chooser.names(fmt):
        return section.component
    return chooser.choose(section, fmt, index, total)


def component_for(section: Section, fmt: Format, index: int = 0, total: int = 1) -> str | None:
    """Return the component that draws `section` at `index` of `total` in format `fmt`, or None when there is none."""
    try:
        return _chosen(section, fmt, default_chooser(), index, total)
    except ChooserError:
        return None


def _component(section: Section, fmt: Format, chooser: Chooser, index: int, total: int) -> str:
    try:
        component = _chosen(section, fmt, chooser, index, total)
    except ChooserError as error:
        raise ComposeError(f"section {section.id}: {error}") from error
    if component is None:
        raise ComposeError(f"section {section.id}: prose sections are not supported yet")
    return component


def _item_props(item: Item) -> dict[str, Any]:
    props = {"head": item.head or "", "body": item.body, "cites": [c.key for c in item.citations]}
    if item.sub:
        props["sub"] = item.sub
    return props


def _compose_section(section: Section, fmt: Format, chooser: Chooser, index: int, total: int) -> ComposedSection:
    if not section.id:
        raise ComposeError(f"section {index + 1} (intent {section.intent!r}) has no id")
    props = {
        "id": section.id,
        "title": section.title or "",
        "items": [_item_props(item) for item in section.items],
        "paragraphs": list(section.paragraphs),
        "source_line": section.source_line or "",
    }
    if section.spoken is not None:
        props["spoken"] = section.spoken
    if fmt == "doc" and (section.content_order or (section.paragraphs and (section.items or section.data is not None))):
        props["content_order"] = section.ordered_content()
    component = _component(section, fmt, chooser, index, total)
    content = {
        "data": section.data,
        "image": "",
        "citations": [[{"key": c.key, "locator": c.locator} for c in item.citations] for item in section.items],
        "icons": [],
    }
    if component in CHART_COMPONENTS:
        content["chart"] = resolve_chart(section.data).model_dump(mode="json")
    return ComposedSection(id=section.id, component=component, intent=section.intent, props=props, content=content)


def _resolve_image(image: str | None, assets: list[Path]) -> Path | None:
    if image is None:
        return None
    for folder in assets:
        path = (folder / image).resolve()
        if path.is_relative_to(folder.resolve()) and path.is_file():
            return path
    raise ComposeError(
        f"image {image!r} not found inside the assets folders: {', '.join(str(folder) for folder in assets)}"
    )


def compose(doc: Document, chooser: Chooser | None = None, *, assets: list[Path] | None = None) -> Composition:
    """Map each section of `doc` to a component and its props, in order, using `chooser` or the default one."""
    chooser = default_chooser() if chooser is None else chooser
    total = len(doc.sections)
    sections = [_compose_section(section, doc.format, chooser, i, total) for i, section in enumerate(doc.sections)]
    if assets is not None:
        for section, composed in zip(doc.sections, sections, strict=True):
            composed.image_path = _resolve_image(section.image, assets)
    front = {key: value for key in ("title", "audience") if isinstance(value := doc.front.get(key), str)}
    return Composition(
        format=doc.format,
        sections=sections,
        front=front,
        version_date=build_date() if doc.format == "doc" and front.get("title", "").strip() else None,
    )


def _main_typ(comp: Composition) -> str:
    lines = ['#import "/lib/theme.typ": colour, page-setup']
    if comp.format == "doc" and comp.front.get("title", "").strip():
        lines += [
            '#import "/lib/theme.typ": doc-title-block',
            '#import "/lib/marks.typ": el-full-width',
        ]
    for name in dict.fromkeys(s.component for s in comp.sections):
        lines.append(f'#import "/components/{name}.typ": {name}')
    lines += [
        "",
        f'#show: page-setup.with("{comp.format}")',
        '#set text(fill: colour("ink"))',
        '#let hide-text = sys.inputs.at("hide-text", default: "0") == "1"',
        "#show text: it => if hide-text { text(fill: rgb(0, 0, 0, 0), it) } else { it }",
        "",
        '#let comp = json("/composition.json")',
    ]
    if comp.format == "doc" and comp.front.get("title", "").strip():
        front_id = "front"
        while front_id in {section.id for section in comp.sections}:
            front_id += "_"
        lines.append(f'#doc-title-block(comp.front, "{_british_date(comp.version_date)}", el-full-width, "{front_id}")')
    for i, section in enumerate(comp.sections):
        if i > 0 and comp.format == "slides":
            lines.append("#pagebreak()")
        lines.append(f"#let sec = comp.sections.at({i}).props + comp.sections.at({i}).content")
        lines.append(f"#{section.component}(sec)")
    return "\n".join(lines) + "\n"


def _apply_theme(theme: Theme, dest: Path) -> None:
    (dest / "lib" / "theme.typ").write_text(render_theme_typ(theme))
    shutil.copytree(theme.fonts_dir, dest / "fonts")


def font_paths(dest: Path) -> list[Path]:
    """Return the font folders of the render folder at `dest`, for Typst's `--font-path`."""
    fonts = dest / "fonts"
    return [fonts] if fonts.is_dir() else []


def _copy_images(comp: Composition, dest: Path) -> Composition:
    result = comp.model_copy(deep=True)
    for section in result.sections:
        if section.image_path is not None:
            data = section.image_path.read_bytes()
            name = hashlib.sha256(data).hexdigest()[:12] + section.image_path.suffix.lower()
            target = dest / "assets" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            section.content["image"] = f"/assets/{name}"
    return result


def assemble(comp: Composition, dest: Path, *, theme: Theme | None = None, library: Path | None = None) -> Path:
    """Write a render folder at `dest` that Typst compiles; return the path of `main.typ`.

    With a theme, `lib/theme.typ` is generated from its tokens and its fonts are copied to `fonts/`.
    """
    if dest.exists():
        raise FileExistsError(f"render folder already exists: {dest}")
    library = library_dir() if library is None else library
    all_manifests(library)
    shutil.copytree(lib_dir(), dest / "lib")
    if theme is not None:
        _apply_theme(theme, dest)
    shutil.copytree(components_dir(), dest / "components")
    for path in library.glob("*.typ"):
        shutil.copy2(path, dest / "components" / path.name)
    (dest / "composition.json").write_text(_copy_images(comp, dest).model_dump_json())
    main = dest / "main.typ"
    main.write_text(_main_typ(comp))
    return main
