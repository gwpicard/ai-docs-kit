"""Resolve chart data into an explainable, format-independent specification."""

import math
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel

DRAWN_TYPES = ("bar", "column")
MANY_CATEGORIES = 7
MAX_DECIMALS = 3

ChartType = Literal["bar", "column"]


class ChartColour(BaseModel):
    palette: str
    index: int


class ChartSeries(BaseModel):
    name: str
    values: list[float]
    labels: list[str]
    colour: ChartColour


class ChartScale(BaseModel):
    min: float
    max: float
    decimals: int


class TwinTable(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class ChartSpec(BaseModel):
    type: Literal["bar", "column", "unsupported"]
    reason: str
    requested: str | None
    chosen: ChartType | None
    categories: list[str]
    series: list[ChartSeries]
    scale: ChartScale
    unit: str | None
    legend: bool
    table: TwinTable | None = None


def format_value(value: float, decimals: int, unit: str | None) -> str:
    exact = Decimal(str(value))
    with localcontext() as context:
        context.prec = max(28, len(exact.as_tuple().digits) + exact.adjusted() + decimals + 2)
        rounded = exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if rounded.is_zero():
        rounded = abs(rounded)
    number = f"{rounded:,.{decimals}f}"
    symbols = {"GBP": "£", "USD": "$", "EUR": "€"}
    if unit in symbols:
        symbol = symbols[unit]
        return f"-{symbol}{number[1:]}" if number.startswith("-") else f"{symbol}{number}"
    if unit == "%":
        return f"{number}%"
    return f"{number} {unit}" if unit else number


def twin_table(spec: ChartSpec, category_label: str = "") -> TwinTable | None:
    """Return the chart's values as a table of the spec's own labels, or None when there are none."""
    if not spec.categories or not spec.series:
        return None
    return TwinTable(
        columns=[category_label, *(series.name for series in spec.series)],
        rows=[
            [category, *(series.labels[index] for series in spec.series)]
            for index, category in enumerate(spec.categories)
        ],
    )


_YEAR = r"(?:19|20)\d{2}"
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_TIME = re.compile(
    rf"(?:{_YEAR}|Q[1-4](?: {_YEAR})?|{_YEAR} ?Q[1-4]|"
    rf"{_YEAR}-\d{{2}}(?:-\d{{2}})?|{_MONTH}(?: {_YEAR})?)",
    re.IGNORECASE,
)


def _choose(data: Mapping[str, Any], categories: list[str], values: list[list[float]]) -> tuple[ChartType, str]:
    if data.get("time_series") is True:
        return "column", "declared time series"
    if data.get("ordered") is True:
        return "column", "declared ordered categories"
    if any(value < 0 for row in values for value in row):
        return "bar", "negative values read best as bars"
    if len(categories) >= 2 and all(_TIME.fullmatch(category) for category in categories):
        return "column", "time-like categories read left to right"
    if len(categories) >= MANY_CATEGORIES:
        return "bar", "7 or more categories need horizontal bars"
    return "bar", "categories compared side by side"


def _read_series(sources: list[Mapping[str, Any]], count: int) -> tuple[list[list[float]], str | None]:
    rows: list[list[float]] = []
    error = None
    for source in sources:
        raw = source.get("values", [])
        if not isinstance(raw, list):
            if error is None:
                error = f"values in series {str(source.get('name', ''))} are not a list"
            rows.append([])
            continue
        row: list[float] = []
        invalid = False
        for index in range(count):
            value = raw[index] if index < len(raw) else 0.0
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                if error is None:
                    error = f"value {value!r} in series {str(source.get('name', ''))} is not a finite number"
                invalid = True
            else:
                row.append(float(value))
        rows.append([] if invalid else row)
    return rows, error


def _given(source: Mapping[str, Any]) -> int:
    raw = source.get("values", [])
    return len(raw) if isinstance(raw, list) else 0


def _series(
    sources: list[Mapping[str, Any]], rows: list[list[float]], decimals: int, unit: str | None
) -> list[ChartSeries]:
    return [
        ChartSeries(
            name=str(source.get("name", "")),
            values=row,
            labels=[
                format_value(value, decimals, unit) if position < _given(source) else ""
                for position, value in enumerate(row)
            ],
            colour=ChartColour(palette="categorical", index=index),
        )
        for index, (source, row) in enumerate(zip(sources, rows, strict=True))
    ]


def _decimal_places(value: float) -> int:
    exponent = Decimal(str(value)).normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def resolve_chart(data: Mapping[str, Any] | None) -> ChartSpec:
    data = data or {}
    categories = [str(category) for category in data.get("categories") or []]
    sources = [source for source in data.get("series") or [] if isinstance(source, Mapping)]
    requested = str(data["type"]) if data.get("type") else None
    unit = str(data["unit"]) if data.get("unit") is not None else None
    rows, error = _read_series(sources, len(categories))
    if error or not categories or not sources:
        return ChartSpec(
            type="unsupported",
            reason=error or "no data to draw",
            requested=requested,
            chosen=None,
            categories=categories,
            series=_series(sources, rows, 0, unit),
            scale=ChartScale(min=0, max=1, decimals=0),
            unit=unit,
            legend=len(sources) >= 2,
        )

    chosen, reason = _choose(data, categories, rows)
    chart_type: Literal["bar", "column", "unsupported"] = chosen
    if requested in DRAWN_TYPES:
        chart_type = "bar" if requested == "bar" else "column"
        reason = "requested in the section"
    elif requested is not None:
        chart_type = "unsupported"
        reason = f"requested type {requested} cannot be drawn"
    values = [value for row in rows for value in row]
    decimals = min(MAX_DECIMALS, max(_decimal_places(value) for value in values))
    scale = ChartScale(min=min(0.0, *values), max=max(1.0, *values), decimals=decimals)
    spec = ChartSpec(
        type=chart_type,
        reason=reason,
        requested=requested,
        chosen=chosen,
        categories=categories,
        series=_series(sources, rows, decimals, unit),
        scale=scale,
        unit=unit,
        legend=len(sources) >= 2,
    )
    spec.table = twin_table(spec, str(data.get("category_label", "")))
    return spec
