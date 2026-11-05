"""
The chemical composition of targets and substrates, so that NOMAD's search
knows their elements and formula.

Lab names such as 8YSZ or STO are not formulas: NOMAD would read them as other
elements (8YSZ as Y, S and an unknown Z). The formula is therefore entered
separately and checked; the name stays the display name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.atomutils import Formula
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections.v1 import (
    ElementalComposition,
    elemental_composition_from_formula,
)
from nomad.datamodel.results import Material, Results
from nomad.metainfo import Quantity

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['apply_formula', 'chemical_formula_quantity', 'elements_of', 'parse_formula']

FORMULA_EXAMPLES = 'e.g. SrTiO3, Fe2O3 or (Y2O3)0.08(ZrO2)0.92 for 8YSZ'


def chemical_formula_quantity():
    return Quantity(
        type=str,
        description=f'Chemical formula, {FORMULA_EXAMPLES}. Not a lab name such '
        'as YSZ or STO: NOMAD finds the entry by the elements of this formula.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity, label='Chemical formula'
        ),
    )


def parse_formula(text: str | None) -> Formula | None:
    """The formula, or None if it is empty or names unknown elements."""
    if not text or not text.strip():
        return None
    try:
        formula = Formula(text.strip(), unknown='keep')
    except ValueError:
        return None
    if set(formula.ase_formula.count()) - Formula.symbols:
        return None
    return formula


def apply_formula(section, archive: EntryArchive, logger: BoundLogger) -> None:
    """
    Set the `elemental_composition` of a target or substrate from its
    `chemical_formula`, and the material of the entry (elements and formulas)
    when the section is the entry itself.
    """
    if not section.chemical_formula:
        logger.warning(f'Enter the chemical formula ({FORMULA_EXAMPLES}).')
        return
    formula = parse_formula(section.chemical_formula)
    if formula is None:
        logger.error(
            f'"{section.chemical_formula}" is not a chemical formula; enter one '
            f'with element symbols, {FORMULA_EXAMPLES}.'
        )
        section.elemental_composition = []
        return
    section.elemental_composition = elemental_composition_from_formula(formula)
    if archive is None or archive.data is not section:
        return
    if archive.results is None:
        archive.results = Results()
    if archive.results.material is None:
        archive.results.material = Material()
    formula.populate(archive.results.material, overwrite=True)


def elements_of(system) -> list[ElementalComposition]:
    """
    The elements of a target or substrate, without their fractions: a sample
    or a run mixes several, whose fractions would not add up.
    """
    return [
        ElementalComposition(element=item.element)
        for item in getattr(system, 'elemental_composition', None) or []
        if item.element
    ]
