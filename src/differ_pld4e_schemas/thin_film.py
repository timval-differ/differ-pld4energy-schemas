from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Reference, SubSection
from nomad_material_processing.general import (
    SubstrateReference as MaterialProcessingSubstrateReference,
)
from nomad_material_processing.general import (
    ThinFilm as MaterialProcessingThinFilm,
)
from nomad_material_processing.general import (
    ThinFilmReference as MaterialProcessingThinFilmReference,
)
from nomad_material_processing.general import (
    ThinFilmStack as MaterialProcessingThinFilmStack,
)

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import Entity
from differ_pld4e_schemas.substrate import Substrate
from differ_pld4e_schemas.target import Target

__all__ = ['ThinFilm', 'ThinFilmStack', 'm_package']


class ThinFilm(MaterialProcessingThinFilm):
    """A single thin-film layer produced by one deposition step."""

    m_def = Section()
    layer_name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    thickness = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    deposition_rate = Quantity(
        type=float,
        unit='m/s',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    composition = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    source_target = Quantity(type=Reference(Target.m_def))
    deposition_step_reference = Quantity(type=str)


class SputterThinFilmReference(MaterialProcessingThinFilmReference):
    reference = Quantity(type=ThinFilm)


class SputterSubstrateReference(MaterialProcessingSubstrateReference):
    reference = Quantity(type=Substrate)


class ThinFilmStack(MaterialProcessingThinFilmStack):
    """Output sample containing an ordered substrate and deposited layers."""

    m_def = Section()
    stack_name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    total_thickness = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    substrate = SubSection(section_def=SputterSubstrateReference)
    layers = SubSection(section_def=SputterThinFilmReference, repeats=True)
