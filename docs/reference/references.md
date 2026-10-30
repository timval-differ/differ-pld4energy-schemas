# Reference

All sections of the PLD schemas with their fields. **Unit** is the unit shown in
the form; archive files take the SI unit (see
[Explanation › Units](../explanation/explanation.md#units)). Fields marked
**generated** are filled in on save and cannot be edited
(see [Explanation › Generated fields](../explanation/explanation.md#generated-read-only-fields)).

The `m_def` to use in archive files is
`differ_pld4e_schemas.schema_packages.schema_package.<Section>`, e.g.
`differ_pld4e_schemas.schema_packages.schema_package.SAPLDLogbook`.

## Entry types

| Entry type | Section | Module |
| --- | --- | --- |
| SA-PLD Logbook | `SAPLDLogbook` | `pld_deposition.py` |
| LA-PLD Logbook | `LAPLDLogbook` | `pld_deposition.py` |
| PLD Target | `PLDTarget` | `target.py` |
| Sample | `Sample` | `sample.py` |
| PLD In-situ Techniques | `InSituTechniquesEntry` | `in_situ.py` |

## Logbooks

### SA-PLD Logbook / LA-PLD Logbook

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | Optional name of the run. |
| `datetime` | date/time | | Start of the run; its date and time make up the sample IDs. Set to the first save if empty. |
| `operator_name` | text | | Who carried out the run. |
| `operator_email` | text | | |
| `lab_id` | text | | Optional lab ID. |
| `description` | rich text | | Comments. |
| `pvd_system` | text | | **Generated**: `SA-PLD` or `LA-PLD`, fixed by the logbook type. |
| `base_pressure` | number | mbar | Base pressure of the main chamber. |
| `substrate_carrier` | choice | | SA-PLD: `Omicron carrier`, `1" carrier`. LA-PLD also `4" wafer carrier`, `Sample select carrier`. |
| `particle_reduction_plate` | choice | | LA-PLD only: `in use`, `not in use`. |

| Sub-section | Section | Repeats |
| --- | --- | --- |
| `samples` | [SampleInRun](#sampleinrun) | yes |
| `laser_details` | [LaserCalibration](#lasercalibration) | no (added on save) |
| `targets` | [SelectedTarget](#selectedtarget) | yes |
| `load_recipe` | [RecipeLoader](#recipeloader-load-recipe) | no |
| `steps` | SA-PLD: `SAPLDStep` types; LA-PLD: `LAPLDStep` types, see [Process steps](#process-steps) | yes |
| `in_situ_techniques` | [InSituTechniques](#insitutechniques) | no |

The laser details and targets are only needed when a step uses the laser
(pre-ablation, deposition); the dashboard leaves them out otherwise.

### SampleInRun

A sample made or processed in the run. On save, a new or external sample gets
its own [Sample](#sample) entry, linked in `sample`.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `origin` | choice | | `New sample`, `External sample`, `Existing sample`. |
| `substrate` | choice | | `SrTiO3 10x10 mm`, `Si 1" with flat`, `Si 1" without flat`, `glass`, `FTO`, `Other`. |
| `substrate_details` | text | | Substrate of an external sample that is not in the list. |
| `layers` | sub-section, repeats | | [Layer](#layer): the films grown **in this run**. |
| `name` | text | | Generated from the substrate and layers if empty: `Substrate_Film-<t>nm_Film-<t>nm`. |
| `comments` | rich text | | |
| `sample_id` | text | | **Generated** for new and external samples: `<system>_<yyyy-mm-dd>_<hh:mm>_S<nn>`; kept once set. Copied from the Sample entry for an existing sample. |
| `sample_uuid` | text | | **Generated** once (UUID4). |
| `sample` | reference to Sample | | The existing sample, or set on save to the created entry. |

### Layer

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `material` | text | | Film material, as named in the target database. |
| `thickness` | number | nm | Intended thickness. |
| `target` | reference to a target | | Optional. |

### LaserCalibration

Laser details. Calibrate with the attenuator 100 % open, 1 Hz, HV NGR mode with
HV = 22 kV, 500 mJ, mask 5x18 mm.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `energy_before_chamber` | number | mJ | |
| `energy_after_chamber` | number | mJ | |
| `transmission_window_2` | number | % | Default 92. |
| `transmission_window_1` | number | % | Calculated as `E_after / (E_before × T2)` on save, unless the manual flag is set and a value is entered. |
| `transmission_window_1_manual` | yes/no | | Keep a manually entered `transmission_window_1`. Default no. |
| `comments` | rich text | | |

### SelectedTarget

One target loaded in the system for this run.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target_number` | integer | | Target number in the system for this run. |
| `target` | reference to PLD Target | | Must be unique within the logbook (error otherwise). |
| `material` | text | | **Generated**: copied from the target. |
| `manufacturer` | text | | **Generated**: copied from the target. |
| `purchase_date` | date/time | | **Generated**: copied from the target. |

### RecipeLoader (Load recipe)

See [Reproduce a run with a recipe](../how_to/reuse_a_recipe.md).

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `recipe` | reference to a logbook | | Earlier logbook of the same system. |
| `sample` | reference to Sample | | Sample for the copied deposition steps. Default: all samples of this logbook. |
| `apply_recipe` | yes/no | | Tick and save to copy. Unticked after the copy. |
| `applied_recipe` | text | | **Generated**: name of the last applied recipe. |

## Process steps

| Step | SA-PLD section | LA-PLD section |
| --- | --- | --- |
| Pre-ablation step | `SAPLDPreAblationStep` | `LAPLDPreAblationStep` |
| Heating step | `SAPLDHeatingStep` | `LAPLDHeatingStep` |
| Annealing step | `SAPLDAnnealingStep` | `LAPLDAnnealingStep` |
| Pulsed laser deposition step | `SAPLDDepositionStep` | `LAPLDDepositionStep` |
| Cool-down step | `SAPLDCoolDownStep` | `LAPLDCoolDownStep` |

### Fields of every step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | |
| `start_time` | date/time | | |
| `duration` | number | s | |
| `description` | rich text | | Comments. |
| `pressure` | number | mbar | Chamber pressure during the step. |
| `atmosphere` | choice | | `Background gas` (default) or `UHV`: no gases, only the pressure. |
| `background_gases` | sub-section, repeats | | [BackgroundGas](#backgroundgas), one per gas. |
| `valve_position` | number | % | Gas valve, shared by all gases. |
| `valve_position_fixed` | yes/no | | Valve kept at a fixed position. |

### Pre-ablation step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target` | reference to PLD Target | | One of the selected targets. Filled in on save if only one target is selected. |
| `target_number` | integer | | **Generated**: from the target details. |
| `substrate_temperature` | number | °C | |
| `target_stage` | sub-section | | [TargetStage](#targetstage) |
| `laser` | sub-section | | [LaserParameters](#laserparameters) |

### Heating step and cool-down step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `ramp_rate` | number | K/min (= °C/min) | |
| `temperature_setpoint` | number | °C | |
| `heater_output` | number | % | Heating step only: heater output once the setpoint is reached. |

### Annealing step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `temperature_setpoint` | number | °C | |
| `heater_output` | number | % | Heater output once the setpoint is reached. |
| `dwell_time` | number | min | Time at the setpoint. |

### Pulsed laser deposition step

All fields of the pre-ablation step, plus:

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `samples` | references to Sample | | The samples deposited on: all samples of the run (SA-PLD) or the chosen one (LA-PLD). |
| `heater_stage_position` | sub-section | | [HeaterStagePosition](#heaterstageposition) |

SA-PLD (`SAPLDDepositionStep`) adds:

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `substrate_stage_scan` | yes/no | | Default no. When yes, `substrate_scan` is added on save. |
| `substrate_scan` | sub-section | | [SubstrateStageScan](#substratestagescan) |

LA-PLD (`LAPLDDepositionStep`) adds:

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `heater_scan_type` | choice | | `Polar scan` (default), `Cartesian scan`. The matching sub-section is added on save. |
| `polar_scan` | sub-section | | [PolarHeaterScan](#polarheaterscan) |
| `cartesian_scan` | sub-section | | [CartesianHeaterScan](#cartesianheaterscan) |

### BackgroundGas

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `gas` | choice | | `Ar`, `O2`, `N2`. |
| `flow_setpoint` | number | sccm | Set flow. |
| `flow_readout` | number | sccm | Read-out (measured) flow. |

The valve position is recorded on the step, see
[Fields of every step](#fields-of-every-step).

### LaserParameters

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `laser_mode` | choice | | `HV NGR`, `HV PGR`, `EGY PGR`, `EGY NGR`. |
| `laser_voltage` | number | kV | |
| `magnification` | choice | | `5X`, `10X`. |
| `mask_size` | choice | | `3x12`, `4x12`, `3x15`, `4x15`, `5x18`, `4x2 (5 slits)`. |
| `spot_size` | number | mm² | |
| `laser_fluence` | number | J/cm² | |
| `laser_energy` | number | mJ | |
| `attenuator_position` | number | % | |
| `laser_frequency` | number | Hz | |
| `number_of_laser_pulses` | integer | | |

### TargetStage

| Field | Type | Unit |
| --- | --- | --- |
| `start_x_position` | number | mm |
| `x_offset` | number | mm |
| `start_y_position` | number | mm |
| `y_offset` | number | mm |
| `start_z_position` | number | mm |
| `scan_width_x` | number | mm |
| `scan_width_y` | number | mm |
| `scan_speed_x` | number | mm/s |
| `scan_speed_y` | number | mm/s |

### HeaterStagePosition

| Field | Type | Unit |
| --- | --- | --- |
| `x` | number | mm |
| `y` | number | mm |
| `z` | number | mm |
| `tilt` | number | degree |
| `spin` | number | degree |

### SubstrateStageScan

SA-PLD substrate stage scan.

| Field | Type | Unit |
| --- | --- | --- |
| `scan_width_x` | number | mm |
| `scan_width_y` | number | mm |
| `scan_speed_x` | number | mm/s |
| `scan_speed_y` | number | mm/s |

### CartesianHeaterScan

LA-PLD cartesian heater scan.

| Field | Type | Unit |
| --- | --- | --- |
| `x_offset` | number | mm |
| `y_offset` | number | mm |
| `scan_rate` | number | mm/s |
| `rotation_rate` | number | rpm |

### PolarHeaterScan

| Field | Type | Unit |
| --- | --- | --- |
| `radius_start` | number | mm |
| `radius_stop` | number | mm |
| `pulse_spacing` | number | mm |
| `max_laser_frequency` | number | Hz |
| `number_of_scans` | integer | |

## Database entries

### PLD Target

Extends the sputter `Target` section.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | Entry name. Defaults to the material. Do not include the target number. |
| `material` | text | | |
| `manufacturer` | text | | |
| `purchase_date` | date/time | | |
| `diameter` | number | m | |
| `thickness` | number | m | |
| `purity` | text | | e.g. `99.999%`. |

### Sample

A sample: a substrate with the films grown on it. Not specific to PLD: `system`
records where it was made. Extends NOMAD's `CompositeSystem`.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `sample_id` | text | | The sample ID; also used as the entry name and, if empty, `lab_id`. |
| `name` | text | | Sample name; generated from substrate and layers if empty. |
| `datetime` | date/time | | Start of the run that made it. |
| `description` | rich text | | Comments. |
| `system` | text | | System it was made in, e.g. `SA-PLD`. |
| `origin` | choice | | `New sample`, `External sample`, `Existing sample`. |
| `substrate` | choice | | As in [SampleInRun](#sampleinrun). |
| `substrate_details` | text | | |
| `substrate_material` | text | | **Generated** from the substrate. |
| `substrate_size` | text | | **Generated** from the substrate. |
| `layers` | sub-section, repeats | | [Layer](#layer) |
| `sample_uuid` | text | | **Generated** once. |

## In-situ techniques

### InSituTechniques

Used as `in_situ_techniques` in a logbook, and as the stand-alone entry
**PLD In-situ Techniques** (`InSituTechniquesEntry`).

| Field | Type | Notes |
| --- | --- | --- |
| `sample` | reference to Sample | Optional. |
| `process` | reference to a logbook | Optional. |

| Sub-section | Section | Repeats |
| --- | --- | --- |
| `rheed` | RHEED | yes |
| `mic` | MIC | yes |
| `se` | SE | yes |
| `la_eds` | LA-EDS | yes |
| `oes` | OES | yes |
| `shg` | SHG | yes |

Every technique has a `comments` field and a **generated** `data_status`:
`awaiting data` until one of its files is added, then `complete`. All file
fields are uploads and optional.

| Technique | Field | Content |
| --- | --- | --- |
| RHEED | `pattern_native_file` | Pattern capture, KSA 400 `.img` |
| | `pattern_export_file` | Pattern capture, exported `.png` |
| | `roi_intensity_native_file` | ROI intensity map, KSA 400 `.kdt` |
| | `roi_intensity_export_file` | ROI intensity map, exported `.txt` |
| MIC | `native_file` | EZ-Curve `.ezc` |
| | `export_file` | Exported `.csv` |
| LA-EDS | `sp0_file` | Spectrum `.sp0` |
| SE, OES, SHG | `file` | Data file (format to be specified) |

### LA-EDS

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `energy_offset` | number | eV | E0, energy of channel 0. Default 0 if empty. |
| `energy_per_channel` | number | eV | |
| `number_of_channels` | integer | | Taken from the intensity if empty. |
| `intensity` | list of numbers | counts | **Generated**: intensity per channel (to be read from `.sp0`; archive files only for now). |
| `energy` | list of numbers | eV | **Generated**: `E0 + channel × energy per channel`. |

A plot of intensity versus energy is added on save.
