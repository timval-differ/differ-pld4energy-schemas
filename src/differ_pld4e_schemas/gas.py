from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['BackgroundGas', 'm_package']

GASES = ('Ar', 'O2', 'N2')
UHV = 'UHV'
BACKGROUND_GAS = 'Background gas'
ATMOSPHERES = (BACKGROUND_GAS, UHV)


class BackgroundGas(ArchiveSection):
    """
    One background gas fed into the chamber during a process step. All gases of
    a step share one valve, so its position is recorded on the step.
    """

    m_def = Section(label_quantity='gas')
    gas = Quantity(
        type=MEnum(*GASES),
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
