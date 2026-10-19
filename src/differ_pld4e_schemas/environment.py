from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section
from nomad.units import ureg
from pint.errors import UndefinedUnitError

from differ_pld4e_schemas import m_package

__all__ = ['ChamberEnvironment', 'm_package']

try:
    ureg.Unit('sccm')
except UndefinedUnitError:
    ureg.define('sccm = centimeter ** 3 / minute')


class ChamberEnvironment(ArchiveSection):
    """Manual and log-derived conditions inside the deposition chamber."""

    m_def = Section()
    base_pressure = Quantity(
        type=float,
        unit='Pa',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    working_gas = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    working_pressure = Quantity(
        type=float,
        unit='Pa',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    working_gas_flow = Quantity(
        type=float,
        unit='cm^3 / minute',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
