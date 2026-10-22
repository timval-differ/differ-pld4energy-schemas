from __future__ import annotations

from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Section

from differ_pld4e_schemas import m_package

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'LaserCalibration',
    'LaserParameters',
    'm_package',
    'transmission_window_1',
]

DEFAULT_TRANSMISSION_WINDOW_2 = 92.0

LASER_CALIBRATION_INSTRUCTIONS = (
    'Set the attenuator position 100% open, laser frequency 1 Hz, HV NGR mode with '
    'HV = 22 kV, Energy = 500 mJ. Mask size of 5x18 mm.'
)


def transmission_window_1(energy_before, energy_after, transmission_window_2):
    """
    Transmission of the 1st window in %, or None if it cannot be computed.

    Both windows are in the beam path between the two energy readings, so
    E_after = E_before * T1 * T2 and T1 = E_after / (E_before * T2).
    """
    if energy_before is None or energy_after is None or not transmission_window_2:
        return None
    if not energy_before.magnitude:
        return None
    energy_ratio = (energy_after / energy_before).to('').magnitude
    return energy_ratio / (transmission_window_2 / 100) * 100


class LaserCalibration(ArchiveSection):
    """Laser energy calibration done before the run (laser details)."""

    m_def = Section(description=LASER_CALIBRATION_INSTRUCTIONS)
    energy_before_chamber = Quantity(
        type=float,
        unit='J',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mJ'
        ),
    )
    energy_after_chamber = Quantity(
        type=float,
        unit='J',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mJ'
        ),
    )
    transmission_window_2 = Quantity(
        type=float,
        default=DEFAULT_TRANSMISSION_WINDOW_2,
        description='Transmission of the 2nd window in %.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Transmission 2nd window (%)',
        ),
    )
    transmission_window_1 = Quantity(
        type=float,
        description="""
        Transmission of the 1st window in %. Calculated as
        E_after / (E_before x T2) unless entered manually.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Transmission 1st window (%)',
        ),
    )
    transmission_window_1_manual = Quantity(
        type=bool,
        default=False,
        description='Tick to keep a manually entered 1st window transmission.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if self.transmission_window_2 is None:
            self.transmission_window_2 = DEFAULT_TRANSMISSION_WINDOW_2
        if self.transmission_window_1_manual and self.transmission_window_1 is not None:
            return
        if (
            self.energy_before_chamber is not None
            and self.energy_before_chamber.magnitude == 0
        ):
            logger.warning('Laser energy before chamber is 0, cannot compute T1.')
            return
        transmission = transmission_window_1(
            self.energy_before_chamber,
            self.energy_after_chamber,
            self.transmission_window_2,
        )
        if transmission is not None:
            self.transmission_window_1 = transmission


class LaserParameters(ArchiveSection):
    """Laser and optics settings used in a pre-ablation or deposition step."""

    m_def = Section()
    laser_mode = Quantity(
        type=MEnum('HV NGR', 'HV PGR', 'EGY PGR', 'EGY NGR'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    laser_voltage = Quantity(
        type=float,
        unit='V',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='kV'
        ),
    )
    magnification = Quantity(
        type=MEnum('5X', '10X'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    mask_size = Quantity(
        type=MEnum('3x12', '4x12', '3x15', '4x15', '4x2 (5 slits)'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    spot_size = Quantity(
        type=float,
        unit='m^2',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm^2'
        ),
    )
    laser_fluence = Quantity(
        type=float,
        unit='J / m^2',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='J/cm^2'
        ),
    )
    laser_energy = Quantity(
        type=float,
        unit='J',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mJ'
        ),
    )
    attenuator_position = Quantity(
        type=float,
        description='Attenuator position in %.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Attenuator position (%)',
        ),
    )
    laser_frequency = Quantity(
        type=float,
        unit='Hz',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    number_of_laser_pulses = Quantity(
        type=int,
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
