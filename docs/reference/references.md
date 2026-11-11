# Reference

All sections of the PLD and SPS schemas with their fields. **Unit** is the unit shown in
the form; archive files take the SI unit (see
[Explanation › Units](../explanation/explanation.md#units)). Fields marked
**generated** are filled in on save and cannot be edited
(see [Explanation › Generated fields](../explanation/explanation.md#generated-read-only-fields)).

The `m_def` to use in archive files is
`differ_pld4e_schemas.schema_packages.schema_package.<Section>`, e.g.
`differ_pld4e_schemas.schema_packages.schema_package.SAPLDLogbook`.

Every entry type extends a native NOMAD section (core `basesections` or
`nomad-material-processing`, abbreviated *nmp*), so it has the native fields as
well, e.g. `name`, `datetime`, `lab_id` and `description`, and NOMAD's search
finds it (see [Explanation › Search](../explanation/explanation.md#search)).

## Entry types

| Entry type | Section | Native parent | Module |
| --- | --- | --- | --- |
| SA-PLD Logbook | `SAPLDLogbook` | nmp `PulsedLaserDeposition` | `pld_deposition.py` |
| LA-PLD Logbook | `LAPLDLogbook` | nmp `PulsedLaserDeposition` | `pld_deposition.py` |
| SPS Logbook | `SPSLogbook` | nmp `SputterDeposition` | `sps_deposition.py` |
| PLD Target | `PLDTarget` | nmp `PLDTarget` (a `CompositeSystem`) | `target.py` |
| Sputter Target | `SputterTarget` | `CompositeSystem` | `target.py` |
| Sample | `Sample` | `CompositeSystem` | `sample.py` |
| Substrate type | `SubstrateType` | nmp `CrystallineSubstrate` | `sample.py` |
| PLD In-situ Techniques | `InSituTechniquesEntry` | `Measurement` | `in_situ.py` |

## Logbooks

### SA-PLD Logbook / LA-PLD Logbook

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | Optional name of the run. Set to `<system> <yyyy-mm-dd hh:mm>` if empty. |
| `datetime` | date/time | | Start of the run; its date and time make up the sample IDs. Set to the first save if empty. |
| `method` | text | | Native: `Pulsed Laser Deposition`, searchable as the method. |
| `operator_name` | text | | Who carried out the run. |
| `operator_email` | text | | |
| `lab_id` | text | | Optional lab ID. |
| `description` | rich text | | Comments. |
| `pvd_system` | text | | **Generated**: `SA-PLD` or `LA-PLD`, fixed by the logbook type. |
| `base_pressure` | number | mbar | Base pressure of the main chamber. |
| `substrate_carrier` | choice | | SA-PLD: `Omicron carrier`, `1" carrier`. LA-PLD also `4" wafer carrier`, `Sample select carrier`. |
| `particle_reduction_plate` | choice | | LA-PLD only: `in use`, `not in use`. |
| `system_logfiles` | list of files | | Logfiles of the run exported from the TSST software (`.txt`). Optional. |

| Sub-section | Section | Repeats |
| --- | --- | --- |
| `samples` | [SampleInRun](#sampleinrun) | yes |
| `laser_details` | [LaserCalibration](#lasercalibration) | no (added on save) |
| `targets` | [SelectedTarget](#selectedtarget) | yes |
| `load_recipe` | [RecipeLoader](#recipeloader-load-recipe) | no |
| `steps` | SA-PLD: `SAPLDStep` types; LA-PLD: `LAPLDStep` types, see [Process steps](#process-steps) | yes |
| `in_situ_measurements` | [InSituTechniques](#insitutechniques) | yes |

The laser details and targets are only needed when a step uses the laser
(pre-ablation, deposition); the dashboard leaves them out otherwise.

### SampleInRun

A sample made or processed in the run; a native `CompositeSystemReference`.
On save, a new or external sample gets its own [Sample](#sample) entry, linked
in `reference`.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `origin` | choice | | `New sample`, `External sample`, `Existing sample`. |
| `substrate` | reference to Substrate type | | From the substrate database. |
| `substrate_details` | text | | Substrate of an external sample that is not in the database. |
| `substrate_material` | text | | **Generated**: copied from the substrate (or the substrate details). |
| `substrate_size` | text | | **Generated**: copied from the substrate. |
| `substrate_batch_number` | text | | Optional: batch number of the substrate, as given by the supplier. Copied to the Sample entry. |
| `layers` | sub-section, repeats | | [Layer](#layer): the films grown **in this run**. The dashboard fills them in from the deposition steps. |
| `prior_layers` | sub-section, repeats | | [Layer](#layer): films an external sample already had, from the substrate up. They come first in the name and in the Sample entry. |
| `name` | text | | Generated from the substrate and layers if empty: `Substrate_Film-<t>nm_Film-<t>nm`. |
| `comments` | rich text | | |
| `sample_id` | text | | **Generated** for new and external samples: `<system>_<yyyy-mm-dd>_<hh:mm>_S<nn>`; kept once set. Copied from the Sample entry for an existing sample. |
| `sample_uuid` | text | | **Generated** once (UUID4). |
| `reference` | reference to Sample | | The existing sample, or set on save to the created entry. |
| `lab_id` | text | | The sample ID, set once the Sample entry is linked. |

### Layer

A film; a native `ThinFilm`.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target` | reference to a target | | The target the film is grown from. |
| `material` | text | | Taken from the target if empty. Also the `name` of the film. |
| `thickness` | number | nm | Intended thickness. |
| `number_of_pulses` | integer | | The intended thickness as a number of laser pulses, when not given in nm. |
| `elemental_composition` | sub-sections | | **Generated**: the elements of the target, without fractions. |

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
| `target_number` | integer | | Position of the target in the system for this run, 1 to 5 (a warning otherwise). |
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
| `start_time` | date/time | | Start of the step, to find it in the system logs. The dashboard asks for hh:mm and takes the date of the run (the next day after midnight). |
| `end_time` | date/time | | End of the step, entered like `start_time`. |
| `duration` | number | s | Filled in by the dashboard from the start and end time, when both are given. |
| `comment` | rich text | | Comments. |
| `pressure` | number | mbar | Chamber pressure during the step. |
| `atmosphere` | choice | | `Background gas` (default) or `UHV`: no gases, only the pressure. |
| `background_gases` | sub-section, repeats | | [BackgroundGas](#backgroundgas), one per gas. |
| `valve_position` | number | | Gas valve, shared by all gases: 0 (closed) to 1000 (open). |
| `valve_position_fixed` | yes/no | | Valve kept at a fixed position. |

The steps are native vapour deposition steps (nmp `PLDStep`, for the SPS
`PVDStep`). On save their native sub-sections are **generated** from the fields
above, read-only:

| Native field | Filled from |
| --- | --- |
| `environment` | `pressure` and `background_gases` (set flow; read-out flow as value). |
| `sources` | Steps with a target: the target and, for PLD, the laser (`pulses`, `repetition_rate`, `spot_size`); for the SPS the plasma power. |
| `sample_parameters` | The substrate temperature of a step with a target, or the temperature setpoint. |
| `creates_new_thin_film` | Yes for deposition and sputtering steps. |

### Pre-ablation step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target` | reference to PLD Target | | One of the selected targets. Filled in on save if only one target is selected. |
| `target_number` | integer | | **Generated**: from the target details. |
| `substrate_temperature` | number | °C | |
| `target_stage` | sub-section | | [TargetStage](#targetstage) |
| `laser` | sub-section | | [LaserParameters](#laserparameters) |

### Heating step and cool-down step

Shared by all systems (also the SPS).

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `ramp_rate` | number | K/min (= °C/min) | |
| `temperature_setpoint` | number | °C | |
| `heater_output` | number | % | Heating step only: heater output once the setpoint is reached. |

The PLD heating and cool-down steps add `ramp_on` (yes/no) and the
[temperature control](#temperature-control) fields; the SA-PLD ones also
`power_ramp_rate` (%/min), the ramp rate in power mode. The dashboard only
asks for `ramp_on` in heating steps; a cool-down step always has a ramp rate.

### Temperature control

PLD heating, annealing, deposition and cool-down steps record the settings of
the *Temperature control* panel of the system software.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `fix_output` | yes/no | | Fix output switch. Default no. |
| `drift_compensation` | yes/no | | Default no. |
| `heating_mode` | choice | | SA-PLD only: `Laser heating (PID)` (setpoint in °C) or `Laser heating (power)` (setpoint in %). |
| `power_setpoint` | number | % | SA-PLD only: setpoint in power mode. |
| `laser_output_limitation` | number | % | SA-PLD only: set with the knob on the laser output limitation unit. Default 50. |
| `supply_voltage` | number | V | LA-PLD only: set on the main heater power supply. |
| `supply_current` | number | A | LA-PLD only: set on the main heater power supply. |
| `actual_voltage` | number | V | LA-PLD only: read out on the main heater power supply. |
| `actual_current` | number | A | LA-PLD only: read out on the main heater power supply. |

### Annealing step

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `temperature_setpoint` | number | °C | |
| `ramp_rate` | number | K/min (= °C/min) | |
| `power_ramp_rate` | number | %/min | SA-PLD only: the ramp rate in power mode. |
| `heater_output` | number | % | Heater output once the setpoint is reached. |
| `dwell_time` | number | min | Time at the setpoint. |

### Pulsed laser deposition step

All fields of the pre-ablation step, plus:

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `film_thickness_unit` | choice | | `nm` (default) or `pulses`: how the intended thickness is given. |
| `film_thickness` | number | nm | Thickness of the film grown in this step. |
| `film_thickness_pulses` | integer | | The thickness as a number of laser pulses; the sample name shows it as `<n>p`. |
| `samples` | references to Sample | | The samples deposited on: those not shielded by a sample mask (SA-PLD) or the chosen one (LA-PLD). |
| `heater_stage_position` | sub-section | | [HeaterStagePosition](#heaterstageposition) |
| `heater_scan_type` | choice | | `Polar scan` (default), `Cartesian scan`, or `None` (SA-PLD only: no heater scan). The matching sub-section is added on save; none for `None`. |
| `heater_scan_axis` | choice | | `X`. Not asked for without a heater scan. |
| `heater_size` | choice | | `25mm / 1"` (default), `50mm / 2"`, `75mm / 3"`, `100mm / 4"`, `125mm`, `150mm`, `30x30mm`, `75x25mm / 3x1"`. |
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
| `start_y_position` | number | mm |
| `start_z_position` | number | mm |
| `target_select` | number | degree |
| `scan_axis` | choice: `X` | |
| `area` | choice: `None`, `Square filled` (default) | |
| `scan_width_x` | number | mm |
| `scan_width_y` | number | mm |
| `spot_width` | number | mm |
| `spot_height` | number | mm |
| `x_offset` | number | mm |
| `y_offset` | number | mm |
| `scan_speed_x` | number | mm/s |
| `scan_speed_y` | number | mm/s |
| `target_size` | choice: `25mm / 1"` | |

### HeaterStagePosition

| Field | Type | Unit |
| --- | --- | --- |
| `x` | number | mm |
| `y` | number | mm |
| `z` | number | mm |
| `tilt` | number | degree |
| `spin` | number | degree |

### CartesianHeaterScan

| Field | Type | Unit |
| --- | --- | --- |
| `area` | choice: `None` (default), `Square filled` | |
| `width_x` | number | mm |
| `height_z` | number | mm |
| `spot_width` | number | mm |
| `spot_height` | number | mm |
| `x_offset` | number | mm |
| `z_offset` | number | mm |
| `scan_speed_x` | number | mm/s |
| `scan_speed_z` | number | mm/s |

### PolarHeaterScan

| Field | Type | Unit |
| --- | --- | --- |
| `radius_start` | number | mm |
| `radius_stop` | number | mm |
| `pulse_spacing` | number | mm |
| `max_laser_frequency` | number | Hz |
| `number_of_scans` | integer | |

## SPS logbook

### SPS Logbook

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name`, `datetime`, `operator_name`, `operator_email`, `lab_id` | | | As in the PLD logbooks. |
| `method` | text | | Native: `Sputter Deposition`. |
| `description` | rich text | | General comments. |
| `pvd_system` | text | | **Generated**: `SPS`. |
| `samples` | sub-section, repeats | | [SampleInRun](#sampleinrun), as in the PLD logbooks. Sample IDs start with `SPS_`. |
| `substrate_carrier` | choice | | `4" carrier SPS`, `1 cm² sub plate`, `Fixed stage`. |
| `mask_used` | yes/no | | Fixed stage only; a warning is given otherwise. |
| `mask_type` | text | | The mask used on the fixed stage. |
| `base_pressure` | number | mbar | Pressure of the main chamber. |
| `targets` | sub-section, repeats | | [SelectedSputterTarget](#selectedsputtertarget) |
| `steps` | sub-section, repeats | | SPS steps, see below. |

### SelectedSputterTarget

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target_number` | integer | | Position 1, 2 (2" targets) or 3 (4" target). A warning is given if the target's diameter does not fit. |
| `target` | reference to Sputter Target | | |
| `material`, `diameter` | | | **Generated**: copied from the target entry. |

### SPS process steps

| Step | Section |
| --- | --- |
| Pre-sputtering step | `SPSPreSputteringStep` |
| Heating step | `SPSHeatingStep` |
| Sputtering step | `SPSSputteringStep` |
| Cool-down step | `SPSCoolDownStep` |

Every step has the [fields of every step](#fields-of-every-step) (pressure,
gases, valve). The heating and cool-down steps are those of the PLD logbooks.
The pre-sputtering and sputtering steps have:

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `target` | reference to Sputter Target | | One of the selected targets. Filled in on save if only one target is selected. |
| `target_number` | integer | | **Generated**: from the target details. |
| `plasma` | sub-section | | [SputterPlasma](#sputterplasma) |
| `ramp_up_rate` | number | W/min | Pre-sputtering only. Entered in W/5 min in the dashboard. |
| `pre_sputter_time` | number | min | Pre-sputtering only. |
| `heater_stage_position` | sub-section | | Sputtering only: [HeaterStagePosition](#heaterstageposition) (x, y, z, spin). |
| `heater_rotation` | number | rpm | Sputtering only. |
| `shutter` | choice | | Sputtering only: `open`, `closed`. |
| `sputter_time` | number | min | Sputtering only. |
| `ramp_down_rate` | number | W/min | Sputtering only. Entered in W/5 min in the dashboard. |
| `film_thickness` | number | nm | Sputtering only. The film grown on the samples; it makes up the sample names. |
| `samples` | references to Sample | | Sputtering only: the samples deposited on (those not shielded by a sample mask). |

### SputterPlasma

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `plasma_type` | choice | | `DC`, `RF` or `DC+RF`. |
| `voltage` | number | V | U, for DC. |
| `load_capacitance` | number | nF | CL, for RF. |
| `current` | number | mA | I. |
| `dc_bias` | number | V | |
| `power` | number | W | |

## Database entries

### PLD Target

Extends the `Target` section (a native `CompositeSystem`) and nmp `PLDTarget`.
PLD targets are added by maintainers in the NOMAD entry editor, in the target
and substrate database upload (`database_upload_id`); the PLD logbook dashboard
only lets you choose them. A target entry in any other upload gives an error on
save.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | Entry name. Defaults to the material. Do not include the target number. |
| `material` | text | | As named in the lab, e.g. `8YSZ`; used in sample names. |
| `chemical_formula` | text | | Required for search, e.g. `SrTiO3` or `(Y2O3)0.08(ZrO2)0.92` for 8YSZ. Not a lab name: an error on save if it names unknown elements. |
| `lab_id` | text | | Shown as *Target ID*: the ID engraved on the back of the target. |
| `elemental_composition` | sub-sections | | **Generated** from the chemical formula, with atomic and mass fractions. Hidden in the editor. |
| `shape` | choice | | `Circular` (default) or `Rectangular`. |
| `radius` | number | mm | Circular targets. Warning on save if missing. |
| `length` | number | mm | Rectangular targets. Warning on save if missing. |
| `width` | number | mm | Rectangular targets. Warning on save if missing. |
| `diameter` | number | m | **Generated**: twice the radius; empty for a rectangular target. Hidden in the editor. |
| `thickness` | number | m | |
| `density` | number | g/cm³ | |
| `purity` | text | | e.g. `99.999%`. |
| `manufacturer` | text | | |
| `purchase_date` | date/time | | |
| `engraving_picture` | file | | Optional picture of the engraved ID. |
| `in_stock` | yes/no | | Default yes. When no, the dashboard no longer offers it; logbooks that used it keep it. |

### Sputter Target

The sputter target database, separate from the PLD targets. Same fields as the
`Target` section (`name`, `material`, `chemical_formula`, `manufacturer`,
`purchase_date`, `diameter`, `thickness`, `purity`, `in_stock`); enter the
`diameter` (shown in inch), which decides the positions the target fits.

### Substrate type

A kind of substrate in the substrate database. Not specific to PLD. Extends
nmp `CrystallineSubstrate`, so the native crystal and electronic properties can
be added too.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `name` | text | | Entry name. Defaults to the material and size. |
| `material` | text | | e.g. `SrTiO3`; used in sample names. |
| `chemical_formula` | text | | Required for search, e.g. `SrTiO3` or `Si`; as for the PLD Target. |
| `size` | text | | e.g. `10x10 mm` or `1" with flat`. |
| `supplier`, `supplier_id`, `lab_id` | text | | Native. |
| `in_stock` | yes/no | | Default yes. When no, the dashboard no longer offers it; logbooks that used it keep it. |
| `description` | rich text | | |

### Sample

A sample: a substrate with the films grown on it. Not specific to PLD: `system`
records where it was made. Extends NOMAD's `CompositeSystem`: its **generated**
`components` hold the substrate type, and its elements are those of the
substrate and the films.

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `sample_id` | text | | The sample ID; also used as the entry name and, if empty, `lab_id`. |
| `name` | text | | Sample name; generated from substrate and layers if empty. |
| `datetime` | date/time | | Start of the run that made it. |
| `description` | rich text | | Comments. |
| `system` | text | | System it was made in, e.g. `SA-PLD`. |
| `origin` | choice | | `New sample`, `External sample`, `Existing sample`. |
| `substrate` | reference to Substrate type | | As in [SampleInRun](#sampleinrun). |
| `substrate_details` | text | | |
| `substrate_material` | text | | **Generated** from the substrate. |
| `substrate_size` | text | | **Generated** from the substrate. |
| `substrate_batch_number` | text | | Optional: batch number of the substrate. |
| `layers` | sub-section, repeats | | [Layer](#layer): the whole stack, films it came with first. |
| `sample_uuid` | text | | **Generated** once. |

## In-situ techniques

### InSituTechniques

One measurement: used as `in_situ_measurements` in a logbook (one per
measurement), and as the stand-alone entry **PLD In-situ Techniques**
(`InSituTechniquesEntry`).

A native `Measurement`; its `method` is `In-situ diagnostics`, and the
techniques used (e.g. `RHEED`) are added to the entry's searchable methods.

| Field | Type | Notes |
| --- | --- | --- |
| `samples` | sub-section, repeats | The measured sample, as `reference` (to a Sample). One, required in the dashboard. |
| `process_steps` | references to process steps | The steps of the logbook the measurement was taken during, e.g. `#/data/steps/2`. Required in the dashboard. |
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
fields are lists of uploads (several files of one format, e.g. a series of
RHEED images) and optional.

| Technique | Field | Content |
| --- | --- | --- |
| RHEED | `pattern_native_files` | Pattern captures, KSA 400 `.img` |
| | `pattern_export_files` | Pattern captures, exported `.png` |
| | `roi_intensity_native_files` | ROI intensity maps, KSA 400 `.kdt` |
| | `roi_intensity_export_files` | ROI intensity maps, exported `.txt` |
| MIC | `native_files` | EZ-Curve `.ezc` |
| | `export_files` | Exported `.csv` |
| LA-EDS | `sp0_files` | Spectra `.sp0` |
| SE, OES, SHG | `files` | Data files (format to be specified) |

Entries saved before a field took several files have the single file in the
field without the final `s` (e.g. `pattern_export_file`); it is moved into the
list when the entry is processed again.

### LA-EDS

| Field | Type | Unit | Notes |
| --- | --- | --- | --- |
| `energy_offset` | number | eV | E0, energy of channel 0. Default 0 if empty. |
| `energy_per_channel` | number | eV | |
| `number_of_channels` | integer | | Taken from the intensity if empty. |
| `intensity` | list of numbers | counts | **Generated**: intensity per channel (to be read from `.sp0`; archive files only for now). |
| `energy` | list of numbers | eV | **Generated**: `E0 + channel × energy per channel`. |

A plot of intensity versus energy is added on save.
