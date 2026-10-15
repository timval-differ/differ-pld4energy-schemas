from importlib import import_module

from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Reference, SubSection

try:
    Entity = import_module('nomad_material_processing.sample').Entity
except ImportError:
    Entity = import_module('nomad_material_processing.vapor_deposition.general').Entity

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.substrate import Substrate
from differ_pld4e_schemas.target import Target

__all__ = ['ThinFilm', 'ThinFilmStack', 'm_package']


class ThinFilm(Entity):
    """A single thin-film layer produced by one deposition step."""

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


class ThinFilmStack(Entity):
    """Output sample containing an ordered substrate and deposited layers."""

    stack_name = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    total_thickness = Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    substrate = Quantity(type=Reference(Substrate.m_def))
    layers = SubSection(section_def=ThinFilm.m_def, repeats=True)
