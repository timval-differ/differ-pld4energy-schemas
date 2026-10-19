from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity
from nomad_material_processing.general import Substrate as MaterialProcessingSubstrate

from differ_pld4e_schemas import m_package

__all__ = ['Substrate', 'm_package']


class Substrate(MaterialProcessingSubstrate):
    """Physical substrate loaded into the sputtering chamber."""

    sample_id = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        description='Chemical formula or name of the substrate material.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    size = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    shape = Quantity(
        type=MEnum('Circular', 'Square', 'Rectangular', 'Other'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    supplier = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    position = Quantity(
        type=str,
        description='Holder position identifier.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    rotation_speed = Quantity(
        type=float,
        unit='rpm',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
