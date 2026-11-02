"""
Process steps shared by the PVD systems (PLD and sputtering): the chamber
atmosphere of a step, heating and cooling down. Each system makes its own step
classes from these, so that a logbook only offers the steps of its system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Section, SubSection

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import ProcessStep
from differ_pld4e_schemas.gas import ATMOSPHERES, BACKGROUND_GAS, UHV, BackgroundGas

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['CoolDownStep', 'GasProcessStep', 'HeatingStep', 'm_package']


def temperature_quantity(**kwargs):
    return Quantity(
        type=float,
        unit='K',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='celsius'
        ),
        **kwargs,
    )


def ramp_rate_quantity():
    return Quantity(
        type=float,
        unit='K / minute',
        description='Ramp rate; 1 K/min equals 1 °C/min.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


def heater_output_quantity():
    return Quantity(
        type=float,
        description='Heater output (%) once the temperature setpoint is reached.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, label='Heater output (%)'
        ),
    )


class GasProcessStep(ProcessStep):
    """
    A process step with its chamber pressure and background gases. Use
    `description` for comments.
    """

    m_def = Section()
    pressure = Quantity(
        type=float,
        unit='Pa',
        description='Chamber pressure during the step.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mbar'
        ),
    )
    atmosphere = Quantity(
        type=MEnum(*ATMOSPHERES),
        default=BACKGROUND_GAS,
        description='UHV: no background gas, only the chamber pressure is recorded.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    background_gases = SubSection(section_def=BackgroundGas, repeats=True)
    valve_position = Quantity(
        type=float,
        description='Position of the gas valve (shared by all gases), in %.',
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

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if self.atmosphere == UHV and self.background_gases:
            logger.warning(
                f'Step "{self.name or self.m_def.label}" is in UHV but lists '
                'background gases.'
            )


class HeatingStep(GasProcessStep):
    m_def = Section(label='Heating step')
    ramp_rate = ramp_rate_quantity()
    temperature_setpoint = temperature_quantity()
    heater_output = heater_output_quantity()


class CoolDownStep(GasProcessStep):
    m_def = Section(label='Cool-down step')
    ramp_rate = ramp_rate_quantity()
    temperature_setpoint = temperature_quantity()
