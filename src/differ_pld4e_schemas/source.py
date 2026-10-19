from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Reference, Section

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.target import Target

__all__ = ['SputterDepositionSource', 'm_package']


class SputterDepositionSource(ArchiveSection):
    """Sputtering source and electrical operating conditions."""

    m_def = Section()
    target = Quantity(
        type=Reference(Target.m_def),
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
        )
    cathode_voltage = Quantity(
        type=float,
        unit='V',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    cathode_current = Quantity(
        type=float,
        unit='A',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
