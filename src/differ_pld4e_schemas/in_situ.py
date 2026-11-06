"""
In-situ diagnostics. A measurement is a native NOMAD `Measurement` of one
sample, so NOMAD's search knows the techniques used as methods.
"""

from __future__ import annotations

from copy import deepcopy
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


MAX_POINTS = 5000


def read_columns(lines, delimiter=None) -> tuple[list[str] | None, np.ndarray]:
    """
    The header (if any) and the data columns of an exported text file: one row
    per line, columns separated by `delimiter` (white space if None). A line
    that is not numbers before the data is the header; blank lines are skipped.
    Returns the header names and an array of one row per column.
    """
    header, rows = None, []
    for number, line in enumerate(lines, 1):
        parts = [part.strip() for part in line.strip().split(delimiter)]
        if not line.strip():
            continue
        try:
            values = [float(part) for part in parts]
        except ValueError:
            if rows:
                raise ValueError(f'line {number} is not numbers') from None
            header = parts
            continue
        if rows and len(values) != len(rows[0]):
            raise ValueError(
                f'line {number} has {len(values)} columns instead of {len(rows[0])}'
            )
        rows.append(values)
    if not rows or len(rows[0]) < 2:  # noqa: PLR2004
        raise ValueError('no columns of data found')
    return header, np.array(rows).T


def block_size(number_of_points: int, max_points: int = MAX_POINTS) -> int:
    """The number of samples averaged into one, to keep at most `max_points`."""
    return max(1, -(-number_of_points // max_points))


def block_mean(values: np.ndarray, size: int) -> np.ndarray:
    """The mean of each block of `size` samples (of the last axis)."""
    if size == 1:
        return values
    length = values.shape[-1]
    blocks = -(-length // size)
    padded = np.full((*values.shape[:-1], blocks * size), np.nan)
    padded[..., :length] = values
    return np.nanmean(padded.reshape(*values.shape[:-1], blocks, size), axis=-1)


# The categorical colors of the dashboard's charts, in fixed order per series.
SERIES_COLORS = (
    '#2a78d6',
    '#eb6834',
    '#1baf7a',
    '#eda100',
    '#e87ba4',
    '#008300',
    '#6250d6',
    '#e34948',
)


def line_figure(label, time, series, y_title) -> PlotlyFigure:
    """One line per (name, values) of `series` against the time in s."""
    import plotly.graph_objects as go

    figure = go.Figure()
    for index, (name, values) in enumerate(series):
        figure.add_trace(
            go.Scatter(
                x=time,
                y=values,
                name=name,
                mode='lines',
                line={'width': 2, 'color': SERIES_COLORS[index % len(SERIES_COLORS)]},
            )
        )
    figure.update_layout(
        xaxis_title='Time (s)',
        yaxis_title=y_title,
        hovermode='x unified',
        showlegend=True,
    )
    return PlotlyFigure(label=label, figure=figure.to_plotly_json())


def _file_name(path: str) -> str:
    return path.rsplit('/', maxsplit=1)[-1]


class ExportedData(ArchiveSection):
    """
    Data read from one exported file. Long series are averaged over blocks of
    `averaged_samples` samples, to at most 5000 points; the file keeps every
    sample.
    """

    m_def = Section()
    file = Quantity(type=str, a_browser={'adaptor': 'RawFileAdaptor'})
    averaged_samples = Quantity(
        type=int,
        description='Number of samples of the file averaged into each point.',
    )
    time = Quantity(type=float, shape=['*'], unit='s')


class ROIIntensity(ArchiveSection):
    """The intensity in one region of interest (ROI) over time."""

    m_def = Section(label='ROI intensity')
    roi = Quantity(
        type=int, description='Number of the ROI, in the order of the export.'
    )
    intensity = Quantity(
        type=float,
        shape=['*'],
        description='Intensity in the ROI as exported by KSA 400 (arbitrary units).',
    )


class ROIIntensityMap(ExportedData):
    """
    The ROI intensities of one exported file of KSA 400 (.txt): columns
    separated by white space, the time in s and then one column per ROI.
    """

    m_def = Section(label='ROI intensity map')
    rois = SubSection(section_def=ROIIntensity, repeats=True)

    @classmethod
    def read(cls, path: str, lines) -> ROIIntensityMap:
        _, columns = read_columns(lines)
        size = block_size(columns.shape[1])
        columns = block_mean(columns, size)
        return cls(
            file=path,
            averaged_samples=size,
            time=columns[0],
            rois=[
                ROIIntensity(roi=number, intensity=intensity)
                for number, intensity in enumerate(columns[1:], 1)
            ],
        )

    def figures(self) -> list[PlotlyFigure]:
        series = [(f'ROI {roi.roi}', roi.intensity) for roi in self.rois or []]
        return [
            line_figure(
                f'RHEED ROI intensity: {_file_name(self.file)}',
                self.time.to('s').magnitude,
                series,
                'Intensity (a.u.)',
            )
        ]


def _technique_exports(technique, archive, logger, files, reader) -> list:
    """Each file of `files` read with `reader(path, lines)`; unreadable ones are
    reported and skipped."""
    exports = []
    for path in files or []:
        try:
            with archive.m_context.raw_file(path, 'r') as lines:
                exports.append(reader(path, lines))
        except (NotImplementedError, OSError, ValueError) as error:
            logger.warning(f'{technique.m_def.label}: could not read {path}: {error}')
    return exports


class RHEED(InSituTechnique, PlotSection):
    """
    RHEED captures from the KSA 400 software. The exported ROI intensity maps
    (.txt) are read into `roi_intensities` and plotted.
    """

    m_def = Section(label='RHEED')
    pattern_native_files = _files('Pattern captures, native KSA 400 format (.img).')
    pattern_export_files = _files('Pattern captures, exported images (.png).')
    roi_intensity_native_files = _files(
        'ROI intensity maps, native KSA 400 format (.kdt).'
    )
    roi_intensity_export_files = _files('ROI intensity maps, exported (.txt).')
    roi_intensities = SubSection(
        section_def=ROIIntensityMap,
        repeats=True,
        description='Read-only: read from the exported ROI intensity maps.',
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if archive.m_context is None:
            # Without the upload's files, keep what was read before.
            return
        self.roi_intensities = _technique_exports(
            self,
            archive,
            logger,
            self.roi_intensity_export_files,
            ROIIntensityMap.read,
        )
        self.figures = [f for m in self.roi_intensities for f in m.figures()]


# Columns of an EZ-Curve export, by their name without the unit.
MIC_COLUMNS = {
    'time': 'time',
    'sagittal curvature': 'sagittal_curvature',
    'tangential curvature': 'tangential_curvature',
    'sagittal stress x thickness': 'sagittal_stress_thickness',
    'tangential stress x thickness': 'tangential_stress_thickness',
    'sagittal derivative': 'sagittal_stress_thickness_rate',
    'tangential derivative': 'tangential_stress_thickness_rate',
    'sagittal bow': 'sagittal_bow',
    'tangential bow': 'tangential_bow',
}


def _series(unit=None, description=None):
    return Quantity(type=float, shape=['*'], unit=unit, description=description)


class CurvatureData(ExportedData):
    """
    The curvature data of one exported file of EZ-Curve (.csv): columns
    separated by semicolons, under a header that names each column and its unit.
    """

    m_def = Section(label='Curvature data')
    sagittal_curvature = _series('1/km')
    tangential_curvature = _series('1/km')
    sagittal_stress_thickness = _series('GPa*nm', 'Sagittal stress x thickness.')
    tangential_stress_thickness = _series('GPa*nm', 'Tangential stress x thickness.')
    sagittal_stress_thickness_rate = _series(
        'GPa*nm/s', 'Derivative of the sagittal stress x thickness.'
    )
    tangential_stress_thickness_rate = _series(
        'GPa*nm/s', 'Derivative of the tangential stress x thickness.'
    )
    sagittal_bow = _series(description='Sagittal bow, in the unit of the export.')
    tangential_bow = _series(description='Tangential bow, in the unit of the export.')

    @classmethod
    def read(cls, path: str, lines) -> CurvatureData:
        header, columns = read_columns(lines, ';')
        if header is None or len(header) != len(columns):
            raise ValueError('no header naming each column')
        size = block_size(columns.shape[1])
        columns = block_mean(columns, size)
        data = cls(file=path, averaged_samples=size)
        for name, values in zip(header, columns):
            key = MIC_COLUMNS.get(name.split('(')[0].strip().lower())
            if key is not None:
                setattr(data, key, values)
        if data.time is None:
            raise ValueError('no time column')
        return data

    def figures(self) -> list[PlotlyFigure]:
        time = self.time.to('s').magnitude
        name = _file_name(self.file)
        figures = []
        for title, key, unit in (
            ('Stress x thickness', 'stress_thickness', 'GPa*nm'),
            ('Curvature', 'curvature', '1/km'),
        ):
            series = [
                (side.capitalize(), getattr(self, f'{side}_{key}').to(unit).magnitude)
                for side in ('sagittal', 'tangential')
                if getattr(self, f'{side}_{key}') is not None
            ]
            if series:
                y_title = f'{title} ({unit.replace("*", "·")})'
                figures.append(
                    line_figure(f'MIC {title.lower()}: {name}', time, series, y_title)
                )
        return figures


class MIC(InSituTechnique, PlotSection):
    """
    Magnification inferred curvature, from the EZ-Curve software. The exported
    files (.csv) are read into `curvature_data` and plotted.
    """

    m_def = Section(label='MIC')
    native_files = _files('Native EZ-Curve files (.ezc).')
    export_files = _files('Exported curvature data (.csv).')
    curvature_data = SubSection(
        section_def=CurvatureData,
        repeats=True,
        description='Read-only: read from the exported curvature data.',
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if archive.m_context is None:
            return
        self.curvature_data = _technique_exports(
            self, archive, logger, self.export_files, CurvatureData.read
        )
        self.figures = [f for d in self.curvature_data for f in d.figures()]


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

    def technique_figures(self, prefix: str = '') -> list[PlotlyFigure]:
        """
        Copies of the figures of the techniques (e.g. the RHEED ROI intensities),
        for the entry's overview, which only shows the figures of the entry.
        """
        sub_sections = self.m_def.all_sub_sections
        return [
            PlotlyFigure(label=prefix + figure.label, figure=deepcopy(figure.figure))
            for key in TECHNIQUES
            for technique in self.m_get_sub_sections(sub_sections[key])
            for figure in getattr(technique, 'figures', None) or []
        ]

    @staticmethod
    def _add_methods(archive: EntryArchive, methods: list[str]) -> None:
        if archive.results is None:
            archive.results = Results(eln=ELN())
        if archive.results.eln is None:
            archive.results.eln = ELN()
        known = list(archive.results.eln.methods or [])
        archive.results.eln.methods = known + [m for m in methods if m not in known]


class InSituTechniquesEntry(InSituTechniques, PlotSection, EntryData):
    """Stand-alone in-situ measurement, for samples outside a new deposition run."""

    m_def = Section(label='PLD In-situ Techniques')

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.name:
            # NOMAD would otherwise take the entry name, which may not be set yet.
            self.name = ', '.join(self.techniques_used()) or IN_SITU
        super().normalize(archive, logger)
        # The techniques are normalized before the entry.
        self.figures = self.technique_figures()
