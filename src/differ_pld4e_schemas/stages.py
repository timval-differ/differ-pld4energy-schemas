from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = [
    'CartesianHeaterScan',
    'HeaterStagePosition',
    'PolarHeaterScan',
    'SubstrateStageScan',
    'TargetStage',
    'm_package',
]


def _length(**kwargs):
    return Quantity(
        type=float,
        unit='m',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm'
        ),
        **kwargs,
    )


def _speed(**kwargs):
    return Quantity(
        type=float,
        unit='m / s',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mm/s'
        ),
        **kwargs,
    )


def _angle(**kwargs):
    return Quantity(
        type=float,
        unit='degree',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
        **kwargs,
    )


class HeaterStagePosition(ArchiveSection):
    """Start position of the heater (substrate) stage."""

    m_def = Section()
    x = _length()
    y = _length()
    z = _length()
    tilt = _angle()
    spin = _angle()


class TargetStage(ArchiveSection):
    """Start position and scan of the target stage."""

    m_def = Section()
    start_x_position = _length()
    x_offset = _length()
    start_y_position = _length()
    y_offset = _length()
    start_z_position = _length()
    scan_width_x = _length(description='Width of the target scan in x.')
    scan_width_y = _length(description='Width of the target scan in y.')
    scan_speed_x = _speed()
    scan_speed_y = _speed()


class SubstrateStageScan(ArchiveSection):
    """Scan of the substrate stage (SA-PLD)."""

    m_def = Section()
    scan_width_x = _length()
    scan_width_y = _length()
    scan_speed_x = _speed()
    scan_speed_y = _speed()


class CartesianHeaterScan(ArchiveSection):
    """Cartesian scan of the heater (substrate) stage (LA-PLD)."""

    m_def = Section()
    x_offset = _length()
    y_offset = _length()
    scan_rate = _speed()
    rotation_rate = Quantity(
        type=float,
        unit='rpm',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


class PolarHeaterScan(ArchiveSection):
    """Polar scan of the heater (substrate) stage (LA-PLD)."""

    m_def = Section()
    radius_start = _length()
    radius_stop = _length()
    pulse_spacing = _length()
    max_laser_frequency = Quantity(
        type=float,
        unit='Hz',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    number_of_scans = Quantity(
        type=int,
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
