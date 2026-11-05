"""
In-situ diagnostics. A measurement is a native NOMAD `Measurement` of one
sample, so NOMAD's search knows the techniques used as methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import (
    ActivityStep,
    BaseSection,
    CompositeSystemReference,
    Measurement,
    Process,
)
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.datamodel.results import ELN, Results
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.sample import Sample

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

AWAITING_DATA = 'awaiting data'
DATA_COMPLETE = 'complete'


def _files(description):
    # A list: e.g. several RHEED images of one measurement.
    return Quantity(
        type=str,
        shape=['*'],
        description=description,
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(component=ELNComponentEnum.FileEditQuantity),
    )


def energy_axis(number_of_channels, energy_offset, energy_per_channel):
    """E = E0 + channel_number * energy_per_channel, for channels 0..n-1."""
    return energy_offset + np.arange(number_of_channels) * energy_per_channel


class InSituTechnique(ArchiveSection):
    """
    Base for one in-situ diagnostic. Data files are often collected from other
    computers after the run, so a technique may be saved without them; it then
    shows as awaiting data until a file is added.
    """

    m_def = Section()
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    data_status = Quantity(
        type=MEnum(AWAITING_DATA, DATA_COMPLETE),
        description='Read-only: whether a data file has been added.',
    )

    def file_quantities(self) -> list:
        # Every list of data files is named `files` or `..._files`.
        return [
            quantity
            for name, quantity in self.m_def.all_quantities.items()
            if name == 'files' or name.endswith('_files')
        ]

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if any(self.m_get(quantity) for quantity in self.file_quantities()):
            self.data_status = DATA_COMPLETE
        else:
            self.data_status = AWAITING_DATA
            logger.warning(f'{self.m_def.label}: no data file has been added yet.')


class RHEED(InSituTechnique):
    """RHEED captures from the KSA 400 software."""

    m_def = Section(label='RHEED')
    pattern_native_files = _files('Pattern captures, native KSA 400 format (.img).')
    pattern_export_files = _files('Pattern captures, exported images (.png).')
    roi_intensity_native_files = _files(
        'ROI intensity maps, native KSA 400 format (.kdt).'
    )
    roi_intensity_export_files = _files('ROI intensity maps, exported (.txt).')


class MIC(InSituTechnique):
    """Magnification inferred curvature, from the EZ-Curve software."""

    m_def = Section(label='MIC')
    native_files = _files('Native EZ-Curve files (.ezc).')
    export_files = _files('Exported curvature data (.csv).')


class LAEDS(InSituTechnique, PlotSection):
    """
    Low-angle energy-dispersive spectrum (RSX1000, later RaySpec RSX2000).

    The .sp0 file stores intensity per channel, the energy per channel and the
    number of channels, but no energy axis. The axis is rebuilt as
    E = E0 + channel_number * energy_per_channel.
    """

    m_def = Section(label='LA-EDS')
    sp0_files = _files('Spectrum files (.sp0).')
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
    files = _files('SE data files.')


class OES(InSituTechnique):
    """Optical emission spectroscopy. File format still to be specified."""

    m_def = Section(label='OES')
    files = _files('OES data files.')


class SHG(InSituTechnique):
    """Second harmonic generation. File format still to be specified."""

    m_def = Section(label='SHG')
    files = _files('SHG data files.')


IN_SITU = 'In-situ diagnostics'
TECHNIQUES = ('rheed', 'mic', 'se', 'la_eds', 'oes', 'shg')


class MeasuredSample(CompositeSystemReference):
    """The sample of an in-situ measurement."""

    m_def = Section()
    reference = Quantity(
        type=Reference(Sample.m_def),
        description='The sample that was measured.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity, label='Sample'
        ),
    )


class InSituTechniques(Measurement):
    """
    In-situ diagnostics of one sample (`samples`). In a logbook a measurement
    names the process steps it was taken during; on its own (see
    `InSituTechniquesEntry`) an older sample can be measured again, e.g. during
    post-processing. The techniques used are added to the entry's methods.
    """

    m_def = Section()
    method = Quantity(type=str, default=IN_SITU)
    samples = SubSection(section_def=MeasuredSample, repeats=True)
    process_steps = Quantity(
        type=Reference(ActivityStep.m_def),
        shape=['*'],
        description='The process steps of the run the measurement was taken during.',
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

    def techniques_used(self) -> list[str]:
        sub_sections = self.m_def.all_sub_sections
        return [
            sub_sections[key].sub_section.label
            for key in TECHNIQUES
            if self.m_get_sub_sections(sub_sections[key])
        ]

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if archive.data is self:
            super().normalize(archive, logger)
        else:
            # In a logbook the entry's workflow is the run's, which the native
            # measurement would overwrite with its own.
            BaseSection.normalize(self, archive, logger)
            self._add_methods(archive, [self.method])
        self._add_methods(archive, self.techniques_used())

    @staticmethod
    def _add_methods(archive: EntryArchive, methods: list[str]) -> None:
        if archive.results is None:
            archive.results = Results(eln=ELN())
        if archive.results.eln is None:
            archive.results.eln = ELN()
        known = list(archive.results.eln.methods or [])
        archive.results.eln.methods = known + [m for m in methods if m not in known]


class InSituTechniquesEntry(InSituTechniques, EntryData):
    """Stand-alone in-situ measurement, for samples outside a new deposition run."""

    m_def = Section(label='PLD In-situ Techniques')

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.name:
            # NOMAD would otherwise take the entry name, which may not be set yet.
            self.name = ', '.join(self.techniques_used()) or IN_SITU
        super().normalize(archive, logger)
