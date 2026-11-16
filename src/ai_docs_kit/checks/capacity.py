from ai_docs_kit.checks.engine import CheckContext, make_finding, register
from ai_docs_kit.checks.source import PROVENANCE
from ai_docs_kit.model import Finding, Remedy, Rule, Section
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.render.components import MEASURES, ComponentManifest, all_manifests
from ai_docs_kit.render.compose import component_for


def _findings(
    ctx: CheckContext, rule: Rule, section: Section, component: str, manifest: ComponentManifest
) -> list[Finding]:
    findings = []
    for name, (_, maximum) in manifest.capacity.items():
        measure = MEASURES.get(name)
        if measure is None:
            continue
        value = measure(section)
        if value > maximum:
            findings.append(
                make_finding(
                    rule,
                    ctx,
                    message=f"{name} value {value} exceeds maximum {maximum} for component {component}",
                    section_id=section.id,
                    role=name,
                    measured={"measure": name, "value": value, "max": maximum},
                )
            )
    return findings


@register("capacity")
class Capacity:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        manifests = all_manifests()
        total = len(ctx.doc.sections)
        findings = []
        for index, section in enumerate(ctx.doc.sections):
            component = (
                ctx.composition.sections[index].component
                if ctx.composition is not None
                else component_for(section, ctx.doc.format, index, total)
            )
            if component is not None and component in manifests:
                findings.extend(_findings(ctx, rule, section, component, manifests[component]))
        return findings


RULES: list[Rule] = [
    Rule(
        id="source.capacity",
        title="Section content fits the component capacity",
        origin="manual",
        strength="soft",
        status="active",
        severity="warning",
        tier="source",
        check={"kind": "capacity"},
        remedy=Remedy.model_validate({"class": "redraft", "hint": "reduce the content to fit the component"}),
        provenance=PROVENANCE,
    )
]
