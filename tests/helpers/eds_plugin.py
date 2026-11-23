"""
Another plugin, for the tests of the export: a spectrum entry like laeds_tools
has, whose values a normalizer would read from its file (the tests give the
processed data directly), and that refers to a sample of this plugin.
"""

import numpy as np
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.plot import PlotSection
from nomad.metainfo import Quantity, Reference, SchemaPackage, SubSection

from differ_pld4e_schemas.sample import Sample

m_package = SchemaPackage()


class SpectrumSettings(ArchiveSection):
    live_time = Quantity(type=np.float64, unit='s')


class Spectrum(PlotSection, EntryData):
    data_file = Quantity(type=str)
    sample = Quantity(type=Reference(Sample.m_def))
    settings = SubSection(section_def=SpectrumSettings)
    energy = Quantity(type=np.float64, shape=['*'], unit='eV')
    counts = Quantity(type=np.int64, shape=['*'])


m_package.__init_metainfo__()
