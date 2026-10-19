from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection

from differ_pld4e_schemas.base_sections import Process, ProcessStep

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

from differ_pld4e_schemas.environment import ChamberEnvironment
from differ_pld4e_schemas.normalizers import normalize_deposition
from differ_pld4e_schemas.sample_parameters import SampleParameters
from differ_pld4e_schemas.source import SputterDepositionSource
from differ_pld4e_schemas.substrate import Substrate
from differ_pld4e_schemas.thin_film import ThinFilm, ThinFilmStack


class SputterDepositionStep(ProcessStep):
    """One sputtering operation that produces a thin-film layer."""

    m_def = Section()
    deposition_time = Quantity(
        type=float,
        unit='s',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    sputtering_technique = Quantity(
        type=MEnum('DC', 'RF', 'Pulsed_DC', 'Magnetron', 'Reactive', 'CoSputtering'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    general_remarks = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    source = SubSection(section_def=SputterDepositionSource.m_def)
    sample_parameters = SubSection(section_def=SampleParameters.m_def)
    chamber_environment = SubSection(section_def=ChamberEnvironment.m_def)
    deposited_layer = SubSection(section_def=ThinFilm.m_def)


class Deposition(Process, EntryData):
    """A complete sputter deposition run and its resulting sample."""

    m_def = Section()
    substrate = Quantity(type=Reference(Substrate.m_def))
    resulting_stack = Quantity(type=Reference(ThinFilmStack.m_def))
    steps = SubSection(section_def=SputterDepositionStep.m_def, repeats=True)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        normalize_deposition(self, archive, logger)
