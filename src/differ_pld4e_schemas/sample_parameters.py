from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['SampleParameters', 'm_package']


class SampleParameters(Section):
    """Sample-specific parameters recorded for a deposition step."""

    sample_id = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    sample_temperature = Quantity(
        type=float,
        unit='K',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    sample_bias_voltage = Quantity(
        type=float,
        unit='V',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    sample_holder = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
