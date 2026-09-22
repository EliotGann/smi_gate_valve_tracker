# Loading and exposure model

## Mechanical history

Keep the direct observables before attempting a material-lifetime model:

- Observed open/close transitions and closures reaching vacuum.
- Full atmosphere-to-vacuum cycle count and pressure-vs-time curves.
- Closed-and-pumped seconds: `integral closed * pumped_latch dt`. Enter after
  5 s below 0.01 mbar, exit strictly above 0.02; exclude the qualification dwell.
- Differential-pressure loading: `dP = abs(P_atmosphere - P_chamber)` in mbar.
- Loaded seconds: `integral closed * (dP > configured_threshold) dt`.
- Pressure-time exposure: `integral closed * dP dt` in mbar s.

The ambient face is confirmed to be at atmosphere. A barometer is preferable to
a fixed nominal pressure; record which is used. Preserve the sign of the pressure
difference in raw history even if the load proxy uses its absolute value.

Pressure-time is a **loading proxy**, not measured creep strain or a damage law.
Membrane stress depends on aperture, clamping, thickness, deflection and initial
tension; creep also depends on temperature, time and irradiation history. A
later model could use stress/temperature bins and radiation-loading overlap.
Record maximum dP and window temperature if a useful sensor is available.

## Initial exposure model: one nominal upper bound

Let B mean ring available AND front-end open AND photon shutter open AND fast
shutter open. Let W mean the window valve is confirmed closed/inserted.

1. **Beam-path timer:** `integral B dt`, independent of window position.
2. **Window beam timer:** `integral B W dt`, independent of pressure.
3. **BPM-qualified window timer:** `integral B W M dt`, where M is provisional
   `BPM3 SumX > 0.5` in native PV units. This is a diagnostic timer, not a second
   exposure model. Missing/invalid BPM data give unknown M.
4. **Upper-bound photon exposure:** `N_UB = integral B W Phi_UB dt`, where
   `Phi_UB = 1e13 photons/s * T_attenuators(E, foil_states)`.
5. **Upper-bound interaction estimate:**
   `Q_UB = integral B W Phi_UB E_eV * 1.602176634e-19 * f_dep(E,t) dt`, in nominal J,
   once material coefficients and thickness are supplied.

The confirmed path is FE → mono → BPM2 → photon shutter → BPM3 → fast shutter →
attenuators → sample → GV6W → SAXS detector. **BPM3 does not gate or scale Phi_UB**.
Only one exposure model is retained initially; measured-flux calibration is future
work. Use the independent shutter status because BPM3 is upstream of the fast shutter.

Treat the user-supplied 1e13 photons/s reference as energy-independent initially;
attenuator transmission and Kapton interaction still depend on energy. Sample
transmission is set to one, ignoring absorption to avoid underestimating incident
photons from an unmeasured sample. This is a conditional nominal upper-bound
model, not a proven physical bound across all setups, spectra or missing-data
intervals. Ignoring sample absorption does not establish a bound on local dose
if the sample changes the footprint or angular distribution.

Unknown foil positions or unsupported transmission energies invalidate the photon
estimate while timers continue; no silent fallback to zero or unattenuated flux.
If all foils are positively retracted, T=1 needs no energy; weighted interaction
still needs energy. Unknown thickness/coefficients invalidate only interaction.
Do not multiply photon exposure by the Kapton transmission: count photons
**incident on** the window and weight deposition separately.

For scale: a 0.1 s unattenuated exposure contributes **1e12 nominal photons**;
a 0.5 s exposure at attenuator T=0.01 contributes **5e10 nominal photons**.

## Future measured-flux extension

Open shutters and stored current imply beam-path eligibility, not guaranteed
photons at the window. Mis-steering, other blockers and insertion-device state
can suppress actual flux. Label the dumb timers accordingly. A future monitor-based
model could reflect beam losses seen by BPM3, while still requiring shutter gating.

`q` starts with a valid, dark-corrected, unsaturated monitor reading. The transfer
function `c(E, setup)` includes monitor energy sensitivity, ranges/gain, and any
transmission between monitor and window. Record the raw value and corrections
separately. Diamond current is not generally proportional to photon count with
an energy-independent coefficient: deposited energy and charge collection vary
with E. Multiplying raw current by E alone is not a calibrated photon-energy
integral. A future extension could preserve a plain current integral alongside
`Phi_measured = q * c(E, setup) * T_attenuators`; this is not an initial output.

Ring current is initially an eligibility input, not a second multiplicative
normalization of measured flux. Multiplying a live intensity reading by ring
current would usually count the ring-current dependence twice. The initial
1e13 reference is likewise not scaled by ring current; ring is an eligibility gate.

## Transmission versus deposited energy

For a homogeneous slab at normal incidence, with density rho in g/cm³, thickness
t in cm and mass attenuation coefficient mu/rho in cm²/g:

```
optical_depth = (mu/rho) * rho * t
T = exp(-optical_depth)
f_removed = 1 - T
```

This gives beam removal, including scattering according to the chosen coefficient
definition. It does **not** generally give local absorbed energy. Prefer a
documented mass energy-absorption coefficient mu_en/rho for dose work. One useful
slab approximation for mean deposited fraction is

```
f_dep ~= ((mu_en/rho) / (mu/rho)) * (1 - exp(-(mu/rho) * rho * t))
```

This accounts for primary-beam attenuation with depth and local energy transfer
under the coefficient model's assumptions. Thin-film electron escape, fluorescence
escape, scattered-photon transport and lack of charged-particle equilibrium can
make true deposition differ. Do not present it as a validated thin-Kapton dose
calculation. If only attenuation data are available, publish a **removed-energy
proxy**, not absorbed dose.

For calibrated photon rate Phi at the window, photon energy E in eV:

```
power_dep_W ~= Phi * E * 1.602176634e-19 * f_dep
mass_kg = rho_g_cm3 * (thickness_um * 1e-4) * (beam_area_mm2 * 1e-2) * 1e-3
dose_rate_Gy_s ~= power_dep_W / mass_kg
```

Substituting Phi_UB yields nominal model-based power/dose estimates rather than
measured values. Keep their upper-bound-model provenance in names/metadata; a
nominal Gy calculation also needs a confirmed footprint and does not establish
a true thin-film local-dose upper bound.

The mass is the **illuminated** mass, not the whole window mass. This formula
assumes a uniform footprint and normal incidence. Gaussian spots require an
explicit average or peak-dose convention. Moving beam footprints require spatial
accumulation to estimate peak damage. Thickness changes both absorption and mass;
in the optically thin regime their leading thickness dependence cancels in dose.

With only relative photon-rate proxy Phi_rel, the same expression gives a
model-dependent relative index, not physical Gy. A convenient display is
“equivalent reference-beam seconds,” normalizing the model rate by its rate at
an explicitly chosen energy, monitor reading, thickness and footprint. Retain the
unnormalized integral and model ID so reference choices can be revised.

## Data sources and calibration work

- Obtain material grade, composition and measured thickness. Polyimide formula
  C22H10N2O5 and density around 1.42 g/cm³ are candidates, not accepted inputs.
- Evaluate CXRO/Henke or xraylib for attenuation; use a suitable documented
  energy-absorption dataset (for example NIST tables) for the deposited-energy
  approximation. Check coefficient definitions, mixture rules, range and units.
- Store a versioned offline table with citations, generation script, checksum,
  interpolation policy, supported energy range and independent reference points.
  No runtime dependency on an external material-data website.
- Future work: calibrate BPM3 SumX, dark offset, gain/range transitions, saturation, energy
  dependence and position dependence. Verify the ordering of foils and slits.
- Compare calculations with independent tabulated transmission and, if possible,
  one photodiode-calibrated flux measurement per representative energy/setup.
- Preserve raw history and epoch IDs for future recalculation; never silently
  relabel old relative values as Gy when a new calibration becomes available.

The foundation implements the slab algebra with explicit caller-supplied
coefficients. It does not ship or fabricate Kapton coefficient data.
