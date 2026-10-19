from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['Target', 'm_package']


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
