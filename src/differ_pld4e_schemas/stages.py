from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = [
    'SCAN_AREAS',
    'SCAN_AXES',
    'SCAN_SIZES',
    'CartesianHeaterScan',
    'HeaterStagePosition',
    'PolarHeaterScan',
    'TargetStage',
    'm_package',
]

# Options of the "Define scan pattern" dialog of the system software. Only the
# values seen so far; the first one is the default.
SCAN_AXES = ('X',)
SCAN_AREAS = ('None', 'Square filled')
# Heater size and target size.
SCAN_SIZES = ('25mm / 1"',)


def choice(options, default=None, **kwargs):
    return Quantity(
        type=MEnum(*options),
        default=default or options[0],
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
        **kwargs,
    )


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
    start_y_position = _length()
    start_z_position = _length()
    target_select = _angle(description='Rotation of the target carousel.')
    scan_axis = choice(SCAN_AXES)
    area = choice(SCAN_AREAS, default='Square filled')
    scan_width_x = _length(description='Width of the target scan in x.')
    scan_width_y = _length(description='Height of the target scan in y.')
    spot_width = _length()
    spot_height = _length()
    x_offset = _length()
    y_offset = _length()
    scan_speed_x = _speed()
    scan_speed_y = _speed()
    target_size = choice(SCAN_SIZES)


class CartesianHeaterScan(ArchiveSection):
    """Cartesian scan of the heater (substrate) stage."""

    m_def = Section()
    area = choice(SCAN_AREAS)
    width_x = _length()
    height_z = _length()
    spot_width = _length()
    spot_height = _length()
    x_offset = _length()
    z_offset = _length()
    scan_speed_x = _speed()
    scan_speed_z = _speed()


class PolarHeaterScan(ArchiveSection):
    """Polar scan of the heater (substrate) stage."""

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
