from differ_pld4e_schemas import (
    base_sections,
    environment,
    gas,
    in_situ,
    laser,
    m_package,
    pld_deposition,
    pld_substrate,
    sample_parameters,
    source,
    sputter_deposition,
    stages,
    substrate,
    target,
    thin_film,
)

__all__ = [
    'base_sections',
    'environment',
    'gas',
    'in_situ',
    'laser',
    'm_package',
    'pld_deposition',
    'pld_substrate',
    'sample_parameters',
    'source',
    'sputter_deposition',
    'stages',
    'substrate',
    'target',
    'thin_film',
]

# All modules share m_package, and NOMAD renames the package to the module of the
# last section defined. GUI entries store m_def as '<package name>.<section>' and
# resolve it by importing that module, so name the package after this module and
# expose every section here.
m_package.name = __name__
globals().update(
    {section.name: section.section_cls for section in m_package.section_definitions}
)

m_package.__init_metainfo__()
