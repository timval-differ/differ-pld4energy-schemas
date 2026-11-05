from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import Process, ProcessStep
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


def _single_file():
    """
    One file, as saved before a technique took several files of a format. It
    is moved into the list of the same name plus `s` on normalization.
    """
    return Quantity(
        type=str,
        description='Superseded by the list of files of the same name.',
        a_browser={'adaptor': 'RawFileAdaptor'},
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

    def _move_single_files(self) -> None:
        """Move a file saved as `..._file` into the list `..._files`."""
        quantities = self.m_def.all_quantities
        for quantity in self.file_quantities():
            single = quantities.get(quantity.name[:-1])
            if single is None or not self.m_get(single):
                continue
            files = list(self.m_get(quantity) or [])
            if self.m_get(single) not in files:
                files.insert(0, self.m_get(single))
            self.m_set(quantity, files)
            self.m_set(single, None)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        self._move_single_files()
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
    pattern_native_file = _single_file()
    pattern_export_file = _single_file()
    roi_intensity_native_file = _single_file()
    roi_intensity_export_file = _single_file()


class MIC(InSituTechnique):
    """Magnification inferred curvature, from the EZ-Curve software."""

    m_def = Section(label='MIC')
    native_files = _files('Native EZ-Curve files (.ezc).')
    export_files = _files('Exported curvature data (.csv).')
    native_file = _single_file()
    export_file = _single_file()


class LAEDS(InSituTechnique, PlotSection):
    """
    Low-angle energy-dispersive spectrum (RSX1000, later RaySpec RSX2000).

    The .sp0 file stores intensity per channel, the energy per channel and the
    number of channels, but no energy axis. The axis is rebuilt as
    E = E0 + channel_number * energy_per_channel.
    """

    m_def = Section(label='LA-EDS')
    sp0_files = _files('Spectrum files (.sp0).')
    sp0_file = _single_file()
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
    file = _single_file()


class OES(InSituTechnique):
    """Optical emission spectroscopy. File format still to be specified."""

    m_def = Section(label='OES')
    files = _files('OES data files.')
    file = _single_file()


class SHG(InSituTechnique):
    """Second harmonic generation. File format still to be specified."""

    m_def = Section(label='SHG')
    files = _files('SHG data files.')
    file = _single_file()


class InSituTechniques(ArchiveSection):
    """
    In-situ diagnostics of one sample. In a logbook a measurement names the
    process steps it was taken during; on its own (see `InSituTechniquesEntry`)
    an older sample can be measured again, e.g. during post-processing.
    """

    m_def = Section()
    sample = Quantity(
        type=Reference(Sample.m_def),
        description='The sample that was measured.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    process_steps = Quantity(
        type=Reference(ProcessStep.m_def),
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


class InSituTechniquesEntry(InSituTechniques, EntryData):
    """Stand-alone in-situ measurement, for samples outside a new deposition run."""

    m_def = Section(label='PLD In-situ Techniques')
