# Input PV inventory

Reference filenames/line numbers below refer to the supplied files now under
[`docs/examples/bluesky/`](examples/bluesky/README.md) at the repository root.

Names below come from the supplied files. **Observed** means present in code;
**candidate** means composed or inferred and still needs live metadata inspection.
Inspect native data type, enum strings, EGU, precision, timestamp behavior,
alarm fields, scan/update rate, and disconnect behavior during commissioning.

| Input | PV / source | Status and interpretation |
| --- | --- | --- |
| Window chamber pressure | `XF:12IDC-VA:2{Det:300KW-TCG:7}P:Raw-I` | Observed `waxschamber.py:16`; WAXS source and mbar confirmed by user. Validate gauge range/status near 0.01 mbar. |
| Secondary pressure | `XF:12IDC-VA:2{B1:WAXS-TCG:9}P:Raw-I` | Observed `waxschamber.py:17`; MAXS context only, not selected. |
| Existing GV6 prefix | `XF:12IDC-VA:2{Mir:BDM-GV:6}` | Observed `waxschamber.py:30`. |
| New GV6W status | **TBD**; possible `XF:12IDC-VA:2{Mir:BDM-GV:6W}Pos-Sts` | W placement and full name unconfirmed. Do not append W to a guessed field suffix automatically. |
| Photon shutter | `XF:12IDA-PPS:2{PSh}Pos-Sts` | Candidate composed from prefix in `shutter_dev.py:8` and upstream TwoButtonShutter status convention; verify suffix and enum meanings. |
| Front-end shutter | **TBD** | Not present in supplied files. Do not infer from the photon-shutter prefix. |
| Fast shutter | `XF:12IDA-BI:2{EM:BPM1}DAC3` | Observed `shutter_class.py:136–145`: 0=open, 7=closed. Other values unknown. Physically between BPM3 and attenuators, despite the BPM1 PV prefix. Verify feedback and edge capture for 0.1 s exposures. |
| Ring current | `SR:C03-BI{DCCT:1}I:Real-I` | Observed `machine.py:18`; units expected mA, verify. Threshold TBD. |
| Ring mode | `SR-OPS{}Mode-Sts` | Observed `machine.py:21`; allowed modes and enum mapping TBD. |
| Ring energy | `SR{}Energy_SRBend` | Observed; electron energy, **not** monochromatic photon energy. |
| Photon energy | Derived from Bragg readback | User confirms no direct photon-energy PV. `energy.energy` is an ophyd PseudoSingle. |
| Bragg angle | `XF:12ID:m65.RBV` | Candidate motor field composed from `energy.py:110`; degree units and zero offset must be verified. Fallback formula below. |
| BPM3 horizontal sum | `XF:12IDB-BI:2{EM:BPM3}SumX:MeanValue_RBV` | Selected beam-presence input. Provisional `SumX > 0.5` in native units; verify units/noise/polarity. Future calibrated flux source, not a present photon-rate measurement. |
| BPM3 vertical sum | `XF:12IDB-BI:2{EM:BPM3}SumY:MeanValue_RBV` | Same composition; do not add SumX and SumY without verifying whether they duplicate total current. |
| BPM3 channels | `XF:12IDB-BI:2{EM:BPM3}Current[1–4]:MeanValue_RBV` | Four distinct PVs; useful for calibration/position dependence. Not a literal bracketed PV. |
| BPM2 sums | `XF:12IDA-BI:2{EM:BPM2}SumX:MeanValue_RBV`, `...SumY:MeanValue_RBV` | Alternate diagnostics, not automatic substitutes for BPM3. |
| SSA slit current | `XF:12IDB-BI{EM:SSASlit}SumAll:MeanValue_RBV` | Observed `electrometers_dev.py:27–29`; interception/geometry dependence needs study. |
| Photodiode current | `XF:12ID:2{EM:Tetr1}Current2:MeanValue_RBV` | Observed; availability/interception may depend on setup. |
| Foil positions | `XF:12IDC-OP:2{Fltr:B-N}Pos-Sts` | B=1 or 2, N=1…12. Composed from attenuator instances and explicit status suffix. In supplied foil class, “Open” means **inserted**. |

The shutter class explicitly states per-device polarity varies. “Not Open” must
not be treated as positive closed confirmation without checking whether it also
covers motion/faults. Obtain independent end switches if available.

Fast-shutter `.status` is a local ophyd Signal updated by `check_status()`, not a
continuously refreshed EPICS PV. The tracker must subscribe to a real PV or a
better timestamped exposure/edge counter supplied by controls.

User confirms EPICS and hardware triggering are both used, with the PV expected
to change in both cases. Start by validating that readback at 0.1 s and 0.5 s;
alternative timing sources are only needed if the observed fidelity is inadequate.

## Energy derivation

The supplied inverse calculation is

`E_eV = 12398.42 / (2 * 3.1293 * sin(theta_degrees * pi / 180))`.

Use actual Bragg readback, not setpoint, and preserve the derivation version.
Reject invalid angles and energies outside the validated model range. The code
mentions a validated 2.1–16.1 keV operating interval and permits moves as high as
24 keV; the user confirms tracker coverage **through 24 keV**. The lower limit
is still provisionally 2.1 keV. Harmonics and monochromator
motion can invalidate a single-energy approximation.

## Attenuator provenance and ordering

`attenuator_data.py` contains CXRO optical-depth tables for Cu, Sn, Mo, Al over
2–25 keV, plus the 24-foil layout. These are not Kapton data. Its interpolation
clamps out-of-range energies; the tracker should instead mark unsupported models
invalid. Accuracy assertions in that reference file have not been independently
verified here, particularly near edges and saturated optical depths.

`attenuation.transmission` is another local ophyd Signal, not an identified PV.
If needed, reconstruct transmission from physical foil readbacks in the IOC.
Only apply foils located **between the chosen monitor and the window**; applying
attenuation already seen by the monitor would double-correct the estimate.

## Confirmed beam path and first exposure model

**FE → mono → BPM2 → photon shutter → BPM3 → fast shutter → attenuators →
sample → GV6W → SAXS detector.** Slit/other blocker positions and detailed bank
ordering remain to be surveyed. The stated attenuators are upstream of the window
and downstream of BPM3. Both banks are confirmed adjacent, after the fast shutter
and before the sample, so their transmission must be applied to the nominal
unattenuated **1e13 photons/s** reference. Assume sample transmission = 1 for this
upper-bound estimate. BPM3 cannot observe the fast shutter and does not gate or
scale this exposure estimate. Its threshold supports diagnostics and a separate
BPM-qualified window beam timer only.
