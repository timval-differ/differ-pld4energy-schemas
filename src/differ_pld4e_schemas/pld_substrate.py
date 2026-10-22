from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Reference, Section

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.substrate import Substrate

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['NewSubstrate', 'PLDSubstrate', 'm_package', 'sample_user_id']

SUBSTRATE_MATERIALS = ('Si', 'SrTiO3 (001)', 'glass', 'F:TiO2')
PVD_SYSTEMS = ('SA-PLD', 'LA-PLD')


def sample_user_id(system, date, run_number, sample_number):
    """`{system}_{date}_{run}_{sample number}`, or None while a part is missing."""
    if not system or date is None or not run_number or not sample_number:
        return None
    return f'{system}_{date:%Y-%m-%d}_{run_number}_{sample_number}'


class PLDSubstrate(Substrate, EntryData):
    """A substrate in the PLD substrate database (one entry per substrate)."""

    m_def = Section(label='PLD Substrate')
    pvd_system = Quantity(
        type=MEnum(*PVD_SYSTEMS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    run_number = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    sample_number = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    substrate_material = Quantity(
        type=MEnum(*SUBSTRATE_MATERIALS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    sample_user_id = Quantity(
        type=str,
        description='Generated as {system}_{date}_{run number}_{sample number}.',
    )
    sample_uuid = Quantity(
        type=str,
        description='Generated unique identifier, e.g. for a QR code label.',
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.sample_uuid:
            self.sample_uuid = str(uuid.uuid4())
        self.sample_user_id = (
            sample_user_id(
                self.pvd_system, self.datetime, self.run_number, self.sample_number
            )
            or self.sample_user_id
        )
        if self.sample_user_id and not self.lab_id:
            self.lab_id = self.sample_user_id
        if self.substrate_material:
            self.material = self.substrate_material
        super().normalize(archive, logger)


class NewSubstrate(ArchiveSection):
    """
    A substrate created from the logbook. On save an own PLD Substrate entry is
    created for it and linked in `substrate`, so later steps, recipes and
    in-situ measurements can refer to it.
    """

    m_def = Section(label_quantity='sample_name')
    sample_name = Quantity(
        type=str,
        description='Suggested format: Substrate_ThinFilm-thickness_next_layer.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    run_number = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    sample_number = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    size = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    substrate_material = Quantity(
        type=MEnum(*SUBSTRATE_MATERIALS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    sample_user_id = Quantity(
        type=str,
        description='Generated as {system}_{date}_{run number}_{sample number}.',
    )
    sample_uuid = Quantity(
        type=str,
        description='Read-only: generated unique identifier, e.g. for a QR code label.',
    )
    substrate = Quantity(
        type=Reference(PLDSubstrate.m_def),
        description='The PLD Substrate entry created for this substrate.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )

    def to_substrate(self, system, date) -> PLDSubstrate:
        return PLDSubstrate(
            name=self.sample_name,
            pvd_system=system,
            datetime=date,
            run_number=self.run_number,
            sample_number=self.sample_number,
            size=self.size,
            substrate_material=self.substrate_material,
            description=self.comments,
            sample_user_id=self.sample_user_id,
            sample_uuid=self.sample_uuid,
        )
