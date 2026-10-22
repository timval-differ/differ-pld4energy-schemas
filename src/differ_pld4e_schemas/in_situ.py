from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.metainfo import Quantity, Reference, Section, SubSection

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import Process
from differ_pld4e_schemas.pld_substrate import PLDSubstrate

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'InSituTechniques',
    'InSituTechniquesEntry',
    'LAEDS',
    'MIC',
    'OES',
    'RHEED',
    'SE',
    'SHG',
    'energy_axis',
    'm_package',
]


def _file(description):
    return Quantity(
        type=str,
        description=description,
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(component=ELNComponentEnum.FileEditQuantity),
    )


def energy_axis(number_of_channels, energy_offset, energy_per_channel):
    """E = E0 + channel_number * energy_per_channel, for channels 0..n-1."""
    return energy_offset + np.arange(number_of_channels) * energy_per_channel


class InSituTechnique(ArchiveSection):
    """Base for one in-situ diagnostic."""

    m_def = Section()
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )


class RHEED(InSituTechnique):
    """RHEED captures from the KSA 400 software."""

    m_def = Section(label='RHEED')
    pattern_native_file = _file('Pattern capture, native KSA 400 format (.img).')
    pattern_export_file = _file('Pattern capture, exported image (.png).')
    roi_intensity_native_file = _file(
        'ROI intensity map, native KSA 400 format (.kdt).'
    )
    roi_intensity_export_file = _file('ROI intensity map, exported (.txt).')


class MIC(InSituTechnique):
    """Magnification inferred curvature, from the EZ-Curve software."""

    m_def = Section(label='MIC')
    native_file = _file('Native EZ-Curve file (.ezc).')
    export_file = _file('Exported curvature data (.csv).')


class LAEDS(InSituTechnique, PlotSection):
    """
    Low-angle energy-dispersive spectrum (RSX1000, later RaySpec RSX2000).

    The .sp0 file stores intensity per channel, the energy per channel and the
    number of channels, but no energy axis. The axis is rebuilt as
    E = E0 + channel_number * energy_per_channel.
    """

    m_def = Section(label='LA-EDS')
    sp0_file = _file('Spectrum file (.sp0).')
    energy_offset = Quantity(
        type=float,
        unit='eV',
        description='Energy of channel 0 (E0).',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    energy_per_channel = Quantity(
        type=float,
        unit='eV',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    number_of_channels = Quantity(
        type=int,
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    intensity = Quantity(type=float, shape=['*'])
    energy = Quantity(type=float, shape=['*'], unit='eV')

    # TODO: read intensity, energy per channel and number of channels from the
    # .sp0 file once an example file is available. Keep the reader separate so it
    # can be swapped when the RSX2000 format arrives.

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if self.intensity is None or self.energy_per_channel is None:
            return
        if self.number_of_channels is None:
            self.number_of_channels = len(self.intensity)
        if self.number_of_channels != len(self.intensity):
            logger.warning('LA-EDS number of channels does not match the intensity.')
            return
        offset = self.energy_offset.to('eV').magnitude if self.energy_offset else 0
        self.energy = energy_axis(
            self.number_of_channels,
            offset,
            self.energy_per_channel.to('eV').magnitude,
        )
        import plotly.graph_objects as go

        figure = go.Figure(
            go.Scatter(x=self.energy.to('eV').magnitude, y=self.intensity)
        )
        figure.update_layout(
            xaxis_title='Energy (eV)', yaxis_title='Intensity (counts)'
        )
        self.figures = [PlotlyFigure(label='Spectrum', figure=figure.to_plotly_json())]


class SE(InSituTechnique):
    """Spectroscopic ellipsometry. File format still to be specified."""

    m_def = Section(label='SE')
    file = _file('SE data file.')


class OES(InSituTechnique):
    """Optical emission spectroscopy. File format still to be specified."""

    m_def = Section(label='OES')
    file = _file('OES data file.')


class SHG(InSituTechnique):
    """Second harmonic generation. File format still to be specified."""

    m_def = Section(label='SHG')
    file = _file('SHG data file.')


class InSituTechniques(ArchiveSection):
    """
    In-situ diagnostics. Not tied to a deposition step, so an older sample can be
    measured again, e.g. during post-processing.
    """

    m_def = Section()
    sample = Quantity(
        type=Reference(PLDSubstrate.m_def),
        description='Optional: the sample that was measured.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    process = Quantity(
        type=Reference(Process.m_def),
        description='Optional: the logbook (run) the measurement belongs to.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    rheed = SubSection(section_def=RHEED, repeats=True)
    mic = SubSection(section_def=MIC, repeats=True)
    se = SubSection(section_def=SE, repeats=True)
    la_eds = SubSection(section_def=LAEDS, repeats=True)
    oes = SubSection(section_def=OES, repeats=True)
    shg = SubSection(section_def=SHG, repeats=True)


class InSituTechniquesEntry(InSituTechniques, EntryData):
    """Stand-alone in-situ measurement, for samples outside a new deposition run."""

    m_def = Section(label='PLD In-situ Techniques')
