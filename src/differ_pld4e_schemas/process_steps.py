"""
Process steps shared by the PVD systems (PLD and sputtering): the chamber
atmosphere of a step, heating and cooling down. Each system makes its own step
classes from these, so that a logbook only offers the steps of its system.

The steps are native vapour deposition steps (nomad-material-processing). What
is entered stays in our own quantities and sub-sections; on normalization the
native `environment` (pressure and gas flows) is filled from them, and for the
steps that use a target its `sources` (see the PLD and SPS steps).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import PureSubstanceSection
from nomad.metainfo import Datetime, MEnum, Quantity, Section, SubSection
from nomad_material_processing.vapor_deposition.general import (
    ChamberEnvironment,
    GasFlow,
    Pressure,
    Temperature,
    VolumetricFlowRate,
)
from nomad_material_processing.vapor_deposition.pvd.general import (
    PVDSampleParameters,
    PVDStep,
)

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.gas import ATMOSPHERES, BACKGROUND_GAS, UHV, BackgroundGas

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = ['CoolDownStep', 'GasProcessStep', 'HeatingStep', 'SetpointStep', 'm_package']

# The gas valve is set in steps from 0 (closed) to 1000 (open).
VALVE_POSITION_MAX = 1000
# Laser heating modes of the SA-PLD: PID follows a temperature setpoint (°C),
# power a power setpoint (%).
LASER_HEATING_PID = 'Laser heating (PID)'
LASER_HEATING_POWER = 'Laser heating (power)'
HEATING_MODES = (LASER_HEATING_PID, LASER_HEATING_POWER)


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


def heating_mode_quantity():
    return Quantity(
        type=MEnum(*HEATING_MODES),
        description='Whether the laser heater follows a temperature setpoint (PID) '
        'or a power setpoint.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )


def substrate_temperature_parameters(temperature) -> list:
    """The native sample parameters of a step at a substrate temperature."""
    if temperature is None:
        return []
    return [
        PVDSampleParameters(
            substrate_temperature=Temperature(
                set_value=[temperature.to('K').magnitude], set_time=[0]
            )
        )
    ]


class GasProcessStep(PVDStep):
    """
    A process step with its chamber pressure and background gases. Use
    `comment` for comments.
    """

    m_def = Section()
    end_time = Quantity(
        type=Datetime,
        description='Together with `start_time`, finds the step in the system logs.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.DateTimeEditQuantity),
    )
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
        description='Position of the gas valve (shared by all gases), from 0 to '
        f'{VALVE_POSITION_MAX}.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            minValue=0,
            maxValue=VALVE_POSITION_MAX,
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
        self.environment = self._environment()

    def _environment(self) -> ChamberEnvironment | None:
        """The native chamber environment: pressure and gas flows (set values)."""
        gases = self.background_gases if self.atmosphere != UHV else []
        flows = [
            GasFlow(
                gas=PureSubstanceSection(name=gas.gas, molecular_formula=gas.gas),
                flow_rate=VolumetricFlowRate(
                    set_value=[gas.flow_setpoint.to('m^3/s').magnitude],
                    set_time=[0],
                    value=[gas.flow_readout.to('m^3/s').magnitude]
                    if gas.flow_readout is not None
                    else None,
                    time=[0] if gas.flow_readout is not None else None,
                ),
            )
            for gas in gases or []
            if gas.gas and gas.flow_setpoint is not None
        ]
        if self.pressure is None and not flows:
            return None
        pressure = (
            Pressure(set_value=[self.pressure.to('Pa').magnitude], set_time=[0])
            if self.pressure is not None
            else None
        )
        return ChamberEnvironment(pressure=pressure, gas_flow=flows)


class SetpointStep(GasProcessStep):
    """A step that brings or keeps the samples at a temperature setpoint."""

    m_def = Section()
    temperature_setpoint = temperature_quantity()

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        self.sample_parameters = substrate_temperature_parameters(
            self.temperature_setpoint
        )


class HeatingStep(SetpointStep):
    m_def = Section(label='Heating step')
    ramp_rate = ramp_rate_quantity()
    heater_output = heater_output_quantity()


class CoolDownStep(SetpointStep):
    m_def = Section(label='Cool-down step')
    ramp_rate = ramp_rate_quantity()
