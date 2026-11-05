"""
The target databases. A target is a native NOMAD composite system: its
`chemical_formula` gives its elements, so NOMAD's search finds the target, and
the films, samples and runs made from it, by element.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import CompositeSystem
from nomad.metainfo import Datetime, MEnum, Quantity, Section
from nomad_material_processing.vapor_deposition.pvd.pld import (
    PLDTarget as NativePLDTarget,
)

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.composition import apply_formula, chemical_formula_quantity

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['PLDTarget', 'SputterTarget', 'Target', 'in_stock_quantity', 'm_package']

CIRCULAR = 'Circular'
RECTANGULAR = 'Rectangular'


def in_stock_quantity():
    """
    Whether a database entry (target, substrate type) can still be chosen. An
    entry that runs out is switched off rather than deleted, so the logbooks and
    samples that used it keep their links.
    """
    return Quantity(
        type=bool,
        default=True,
        description=(
            'Untick when it is used up or no longer available: new logbooks then '
            'no longer offer it. Logbooks that used it keep it.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )


class Target(CompositeSystem):
    """
    A target in a target database. The entry is named after the target material
    only: the position of a target in the system changes, so the target number
    is entered per run in the logbook.
    """

    m_def = Section()
    name = Quantity(
        type=str,
        description='Display name, e.g. Fe2O3. Defaults to the target material.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        description='Material as named in the lab, e.g. 8YSZ. Used in sample names.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    chemical_formula = chemical_formula_quantity()
    diameter = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    thickness = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    manufacturer = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    purity = Quantity(
        type=str,
        description='Target purity, for example 99.999%.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    purchase_date = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    in_stock = in_stock_quantity()

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.name and self.material:
            self.name = self.material
        apply_formula(self, archive, logger)
        super().normalize(archive, logger)


# Hidden in the entry editor: the composition follows from the formula.
GENERATED = ['components', 'elemental_composition', 'datetime']


class PLDTarget(Target, NativePLDTarget, EntryData):
    """
    A target in the PLD target database. Targets are added by super-users, in
    the NOMAD entry editor: the PLD logbook dashboard only lets you choose them.
    Enter the radius of a circular target, or the length and width of a
    rectangular one; the diameter follows from the radius.
    """

    m_def = Section(
        label='PLD Target',
        a_display={
            'visible': {'exclude': ['diameter', 'target_id', *GENERATED]},
            'order': [
                'name',
                'material',
                'chemical_formula',
                'lab_id',
                'shape',
                'radius',
                'length',
                'width',
                'thickness',
                'density',
                'purity',
                'manufacturer',
                'purchase_date',
                'engraving_picture',
                'in_stock',
                'description',
            ],
        },
    )
    # The native `target_id` is a generated identifier; the lab engraves its own.
    lab_id = Quantity(
        type=str,
        description='ID engraved on the back of the target.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity, label='Target ID'
        ),
    )
    shape = Quantity(
        type=MEnum(CIRCULAR, RECTANGULAR),
        default=CIRCULAR,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    radius = Quantity(
        type=float,
        unit='m',
        description='Radius of a circular target.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm'
        ),
    )
    length = Quantity(
        type=float,
        unit='m',
        description='Length of a rectangular target.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm'
        ),
    )
    width = Quantity(
        type=float,
        unit='m',
        description='Width of a rectangular target.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm'
        ),
    )
    density = Quantity(
        type=float,
        unit='kg/m**3',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='g/cm**3',
        ),
    )
    engraving_picture = Quantity(
        type=str,
        description='Optional picture of the ID engraved on the back of the target.',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(component=ELNComponentEnum.FileEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if self.shape == RECTANGULAR:
            # A rectangular target has no diameter, also not one left from a
            # radius entered before the shape was changed.
            self.diameter = None
            if self.length is None or self.width is None:
                logger.warning('Enter the length and width of a rectangular target.')
        elif self.radius is None:
            logger.warning('Enter the radius of a circular target.')
        else:
            self.diameter = 2 * self.radius


class SputterTarget(Target, EntryData):
    """
    A target in the sputter target database. Enter its diameter: the target
    positions of the SPS take targets of a given size.
    """

    m_def = Section(
        label='Sputter Target', a_display={'visible': {'exclude': GENERATED}}
    )
    diameter = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='inch'
        ),
    )
