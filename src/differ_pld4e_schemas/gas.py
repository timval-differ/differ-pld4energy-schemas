from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['BackgroundGas', 'm_package']


class BackgroundGas(ArchiveSection):
    """One background gas fed into the chamber during a process step."""

    m_def = Section(label_quantity='gas')
    gas = Quantity(
        type=MEnum('Ar', 'O2', 'N2'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    flow_setpoint = Quantity(
        type=float,
        unit='cm^3 / minute',
        description='Set flow of the gas in sccm.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, label='Set flow (sccm)'
        ),
    )
    flow_readout = Quantity(
        type=float,
        unit='cm^3 / minute',
        description='Measured (read-out) flow of the gas in sccm.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Read-out flow (sccm)',
        ),
    )
    valve_position = Quantity(
        type=float,
        description='Position of the gas valve as shown on the controller (%).',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Valve position (%)',
        ),
    )
    valve_position_fixed = Quantity(
        type=bool,
        description='Whether the valve position was kept fixed during the step.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )
