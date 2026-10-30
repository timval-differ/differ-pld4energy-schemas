from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Datetime, Quantity, Section

from differ_pld4e_schemas import m_package

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['PLDTarget', 'Target', 'in_stock_quantity', 'm_package']


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


class Target(ArchiveSection):
    """Sputtering target material and geometry."""

    m_def = Section()
    material = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
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


class PLDTarget(Target, EntryData):
    """
    A target in the PLD target database. The entry is named after the target
    material only: the position of a target in the system changes, so the target
    number is entered per run in the logbook.
    """

    m_def = Section(label='PLD Target')
    name = Quantity(
        type=str,
        description='Display name, e.g. Fe2O3. Defaults to the target material.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    purchase_date = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    in_stock = in_stock_quantity()

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if not self.name and self.material:
            self.name = self.material
        if self.name and archive is not None and archive.metadata is not None:
            archive.metadata.entry_name = self.name
