from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Datetime, Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['Entity', 'Process', 'ProcessStep', 'm_package']


class Entity(ArchiveSection):
    """An object that persists through time while maintaining its identity."""

    m_def = Section()
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    datetime = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    lab_id = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    description = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )


class ProcessStep(ArchiveSection):
    """One step in a process."""

    m_def = Section()
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    start_time = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    description = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    duration = Quantity(
        type=float,
        unit='s',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


class Process(ArchiveSection):
    """A process consisting of ordered process steps."""

    m_def = Section()
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    datetime = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    lab_id = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    description = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    end_time = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
    operator_name = Quantity(
        type=str,
        description='The person who carried out the process.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    operator_email = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
