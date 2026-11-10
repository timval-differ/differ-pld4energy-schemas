"""
Exported files read whatever their encoding, decimal mark and units, and
values that cannot be right are reported.
"""

import numpy as np
import pytest
from helpers import ENTRY_CREATE_TIME
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

from differ_pld4e_schemas.in_situ import (
    AWAITING_DATA,
    LAEDS,
    CurvatureData,
    read_columns,
    split_header,
)
from differ_pld4e_schemas.laser import LaserCalibration


def _normalize(section):
    logger = CapturingLogger()
    section.normalize(
        EntryArchive(metadata=EntryMetadata(entry_create_time=ENTRY_CREATE_TIME)),
        logger,
    )
    return [(call[0], call[1][0]) for call in logger.calls]


def test_decimal_commas_in_columns():
    _, columns = read_columns(['0,5\t1,25e3', '1,5\t2'])
    assert np.allclose(columns, [[0.5, 1.5], [1250, 2]])
    # In a comma-separated file a comma separates the columns.
    _, columns = read_columns(['1,2', '3,4'], ',')
    assert np.allclose(columns, [[1, 3], [2, 4]])


def test_unit_of_a_header():
    assert split_header('Sagittal Bow (µm)') == ('Sagittal Bow', 'µm')
    assert split_header('Time') == ('Time', None)


def _mic(header, row):
    warned = []
    data = CurvatureData.read('x.csv', [header, row], warned.append)
    return data, warned


def test_mic_columns_are_converted_from_the_units_of_the_export():
    data, warned = _mic(
        'Time (ms);Sagittal Curvature (1/m);Sagittal Stress x Thickness (MPa·µm);'
        'Sagittal Bow (nm)',
        '1500;0,002;3;40',
    )
    assert data.time[0].to('s').magnitude == pytest.approx(1.5)
    assert data.sagittal_curvature[0].to('1/km').magnitude == pytest.approx(2)
    assert data.sagittal_stress_thickness[0].to('GPa*nm').magnitude == pytest.approx(3)
    assert data.sagittal_bow[0].to('um').magnitude == pytest.approx(0.04)
    assert warned == []


def test_mic_column_without_a_unit_is_read_in_the_default_unit_with_a_warning():
    data, warned = _mic('Time (s);Sagittal Bow', '1;2')
    assert data.sagittal_bow[0].to('um').magnitude == pytest.approx(2)
    assert len(warned) == 1
    assert 'Sagittal Bow' in warned[0]


def test_mic_column_in_a_unit_that_does_not_fit_is_refused():
    with pytest.raises(ValueError, match='not a unit of'):
        _mic('Time (s);Sagittal Bow (kg)', '1;2')


def test_la_eds_number_of_channels_follows_the_intensity():
    laeds = LAEDS(
        intensity=[1.0, 2.0, 3.0], number_of_channels=5, energy_per_channel=10
    )
    records = _normalize(laeds)
    assert laeds.number_of_channels == 3  # noqa: PLR2004
    assert len(laeds.energy) == 3  # noqa: PLR2004
    assert any('does not match' in message for _, message in records)


def test_la_eds_without_energy_per_channel_has_no_old_axis():
    laeds = LAEDS(intensity=[1.0, 2.0], energy=[0.0, 1.0])
    _normalize(laeds)
    assert laeds.energy is None
    assert not laeds.figures


def test_la_eds_files_that_are_not_read_are_reported():
    laeds = LAEDS(sp0_files=['spectrum.sp0'])
    records = _normalize(laeds)
    assert laeds.data_status == AWAITING_DATA
    assert any('.sp0 files are not read' in message for _, message in records)


def test_impossible_transmission_is_reported():
    calibration = LaserCalibration(energy_before_chamber=0.4, energy_after_chamber=0.5)
    records = _normalize(calibration)
    assert calibration.transmission_window_1 > 100  # noqa: PLR2004
    assert any(
        'cannot be' in message for level, message in records if level == 'warning'
    )


def test_transmission_that_can_no_longer_be_calculated_is_kept_as_entered():
    calibration = LaserCalibration(transmission_window_1=80.0)
    records = _normalize(calibration)
    assert calibration.transmission_window_1 == pytest.approx(80)
    assert calibration.transmission_window_1_manual is True
    assert any('kept as entered' in message for _, message in records)


def test_commas_in_a_file_with_decimal_points_are_not_decimal_commas():
    # A comma next to numbers with a decimal point may group thousands: not read
    # as 1.234 (the line is then not numbers, and the file is refused).
    with pytest.raises(ValueError):
        read_columns(['0.5\t1.0', '1,234\t2.0'])
