# Input PV inventory

Reference filenames/line numbers below refer to the supplied files now under
[`docs/examples/bluesky/`](examples/bluesky/README.md) at the repository root.

Names below come from the supplied files or operator commissioning updates.
**Observed** means present in code;
**candidate** means composed or inferred and still needs live metadata inspection.
Inspect native data type, enum strings, EGU, precision, timestamp behavior,
alarm fields, scan/update rate, and disconnect behavior during commissioning.

| Input | PV / source | Status and interpretation |
| --- | --- | --- |
| WAXS sample chamber pressure | `XF:12IDC-VA:2{Det:300KW-TCG:7}P:Raw-I` | Operator confirms mbar and correct reading. This is the sample chamber, opposite the pump-down side. Observer key `chamber_pressure`. |
| Primary pump-down pressure (formerly MAXS) | `XF:12IDC-VA:2{B1:WAXS-TCG:9}P-I` | Operator confirms this is the frequently pumped side, in mbar. Use for pump-cycle qualification. Observer key `pressure`. |
| Alternate pressure representations | TCG:7 `P-I`; TCG:9 `P:Raw-I` | Same gauge prefixes as above; not extra physical faces. TCG:9 raw field occurs in `waxschamber.py:17`. Not automatic fallbacks; inspect native data/alarms if a display says Lo. |
| Existing GV6 prefix | `XF:12IDC-VA:2{Mir:BDM-GV:6}` | Observed `waxschamber.py:30`. |
| New GV6W status | `XF:12IDC-VA:2{BT:WAXS-GV:6W}Pos-Sts` | Operator convention: **1=open, 0=not open, treated as closed** for tracking. Other values unknown. |
| Photon shutter | `XF:12IDA-PPS:2{PSh}Pos-Sts` | Operator convention: **1=closed, 0=not closed, treated as open** for tracking. Other values unknown. |
| Front-end shutter | `XF:12ID-PPS{Sh:FE}Sts:Cls-Sts` | Operator convention: **1=closed, 0=not closed, treated as open** for tracking. Other values unknown. |
| Fast shutter | `XF:12IDA-BI:2{EM:BPM1}DAC3` | Operator confirms **7=closed, 0=open**. Other values unknown. Physically between BPM3 and attenuators, despite the BPM1 PV prefix. Operator reports timing adequate, less than approximately 0.1 s. |
| Ring current | `SR:C03-BI{DCCT:1}I:Real-I` | Observed `machine.py:18`; units expected mA, verify. Threshold TBD. |
| Ring mode | `SR-OPS{}Mode-Sts` | Observed `machine.py:21`; allowed modes and enum mapping TBD. |
| Ring energy | `SR{}Energy_SRBend` | Observed; electron energy, **not** monochromatic photon energy. |
| Photon energy | Derived from Bragg readback | User confirms no direct photon-energy PV. `energy.energy` is an ophyd PseudoSingle. |
| Bragg angle | `XF:12ID:m65.RBV` | Operator confirms correct readback during commissioning. Energy formula below. |
| BPM3 horizontal sum | `XF:12IDB-BI:2{EM:BPM3}SumX:MeanValue_RBV` | **Raw diagnostic only; beam inference disabled.** Operator reports 0.6 with no beam, invalidating provisional >0.5 threshold. No BPM-qualified timer or exposure gating/scaling for now. |
| BPM3 vertical sum | `XF:12IDB-BI:2{EM:BPM3}SumY:MeanValue_RBV` | Same composition; do not add SumX and SumY without verifying whether they duplicate total current. |
| BPM3 channels | `XF:12IDB-BI:2{EM:BPM3}Current[1–4]:MeanValue_RBV` | Four distinct PVs; useful for calibration/position dependence. Not a literal bracketed PV. |
| BPM2 sums | `XF:12IDA-BI:2{EM:BPM2}SumX:MeanValue_RBV`, `...SumY:MeanValue_RBV` | Alternate diagnostics, not automatic substitutes for BPM3. |
| SSA slit current | `XF:12IDB-BI{EM:SSASlit}SumAll:MeanValue_RBV` | Observed `electrometers_dev.py:27–29`; interception/geometry dependence needs study. |
| Photodiode current | `XF:12ID:2{EM:Tetr1}Current2:MeanValue_RBV` | Observed; availability/interception may depend on setup. |
| Foil positions | `XF:12IDC-OP:2{Fltr:B-N}Pos-Sts` | B=1 or 2, N=1…12. Composed from attenuator instances and explicit status suffix. In supplied foil class, “Open” means **inserted**. |

Per-device polarity varies. For this monitoring application the operator accepts
the binary conventions above, including not-open as closed for GV6W and not-closed
as open for shutters. These are monitoring assumptions, not independent endpoint
confirmation. Additional opposite-status PVs are not required for this scope.
Disconnected, invalid-alarm and unsupported values remain unknown.

Fast-shutter `.status` is a local ophyd Signal updated by `check_status()`, not a
continuously refreshed EPICS PV. The tracker must subscribe to a real PV or a
better timestamped exposure/edge counter supplied by controls.

User confirms EPICS and hardware triggering are both used and reports timing
adequate (less than approximately 0.1 s). This is operator acceptance for current
commissioning, not a quantified guarantee that every 0.1 s exposure is captured.

## Pressure loading and commissioning observations

The corrected geometry uses **TCG:9 for pump-down** and **TCG:7 for the WAXS
sample chamber**, both in mbar. Window loading uses
`abs(P_TCG9 - P_TCG7)` while GV6W is closed. This supersedes the fixed-atmosphere
opposite-face assumption. Observer v2 adds state interpretations and a live
pressure difference/rise watch (CLOSED_WINDOW_WATCH.md); lifetime integration
and durable recording remain future work.

Operator checked `P-I`: it remains numeric and reports **0E0 below the gauge
threshold**, so no `Lo` text handling is needed for this source. Mirror that zero
as received with source alarms; interpret it as under-range, not exact physical
zero. The gauge's lower reporting threshold is still unspecified. For the future
reducer, establish that bound relative to 0.01 mbar before accepting under-range
as vacuum qualification; retain its loading uncertainty rather than inventing an
exact pressure. Generic text sources, if configured later, remain text/NaN.

**Commissioning contract correction:** the `Input:pressure:*` output now means
TCG:9 pump-down pressure; `Input:chamber_pressure:*` means TCG:7 sample pressure.
Restart the observer and reload the matching OPI together. Earlier screenshots
and samples used the old roles and must not be treated as TCG:9 pump histories.

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
scale this exposure estimate. Its raw diagnostic remains visible, but beam-presence
inference and the BPM-qualified timer are disabled pending future calibration.
