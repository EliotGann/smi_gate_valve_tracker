# Remaining design questions

The question rounds and follow-up decisions are captured in ASSUMPTIONS.md. These questions
are intentionally specific; unknown answers can remain open until commissioning.

## Next high-impact answers

1. What is the **exact GV6W status PV**, and which raw values positively confirm
   closed/open/moving/fault? Does “closed” always place the Kapton in the beam?
2. What is the **front-end shutter status PV** and its enum mapping? Confirm the
   photon-shutter readback suffix and mapping too.
3. Exposures are confirmed as rarely **0.1 s**, generally **>=0.5 s**, triggered
   via EPICS or hardware, with the PV expected to change in both cases. What is
   the typical repetition rate? Verify edge fidelity and physical-position meaning.
4. **SumX selected**, with provisional `>0.5` native-unit beam-present threshold.
   What are the actual units, dark noise and sensible hysteresis? Range and polarity?
5. Both attenuator banks are confirmed adjacent after the fast shutter and before
   the sample. Where are additional slits/blockers, if relevant to later refinement?
6. What thickness/grade of Kapton, number of layers, clear aperture, incidence
   angle, beam dimensions/profile and position stability should be assumed?
7. **No direct photon-energy PV**. Verify `XF:12ID:m65.RBV` degree units, offset
   and Si(111) conversion. Upper range is confirmed **24 keV**; verify 2.1 keV lower limit.

## Counting and pump-down details

8. Should closing into existing vacuum count as a “closure reaching vacuum”?
   Proposed yes, with no full pump-cycle increment.
9. Must GV6W remain closed throughout a full pump cycle? Proposed yes; record
   interrupted attempts separately if it opens or its state becomes unknown.
10. Should atmosphere observed immediately before closure qualify the next cycle,
    or must atmosphere also be seen with the window closed? Foundation uses the latter.
11. **Start qualification agreed:** >700 arms, <=700 latches candidate, <500 within
    120 s confirms. Keep only one candidate. What measured gauge noise/update
    cadence should inform commissioning of these values?
12. **Vacuum qualification agreed:** 5 s below 0.01; latched until >0.02.
    Pumped time starts at confirmation. Verify under-range and gauge-switch behavior.
13. Should a return above 700 mbar abort/restart an attempt? How long before a
    stalled pump-down is tagged incomplete? Foundation restarts at atmosphere.
14. **Milestones 100, 10, 1, 0.1 mbar accepted.** Are proposed baseline sizes
    (first 5, recent 20, minimum 5) appropriate? Maximum expected rate is now
    approximately one cycle/hour; actual baseline collection may take much longer.
15. What timing accuracy is useful for trends? Do you want crossing brackets,
    log-pressure interpolation, or simply first-observed crossing times?
16. **Usually constant setup confirmed.** Keep one normal population per window
    and notes for unusual cycles. Which maintenance events should prompt an explicit
    new reference revision, and who should annotate/exclude exceptional cycles?

## Loading and beam-model details

17. Is ambient pressure measured? Otherwise which nominal value should be used?
    What differential-pressure threshold should define “loaded” time?
18. Is there a temperature PV near the window? Should loaded+irradiated overlap
    time and differential-pressure bins be retained for future creep models?
19. What stored-current threshold and ring modes define availability? Should an
    insertion-device/beam-permit PV also be required?
20. Is counting exposure during energy moves useful? If so, how quickly must
    energy and flux be sampled, and how are harmonic transitions handled?
21. What flux-monitor range/status/acquisition PVs identify saturation, stopped
    acquisition, gain changes and dark-offset updates?
22. **Initial model settled:** one shutter-gated upper-bound estimate using
    1e13 photons/s × attenuator transmission, ignoring sample absorption. BPM3
    calibration is future work. Over which energies/setups is that reference
    a reasonable upper bound, and how should its uncertainty be recorded?
23. Should downstream monitor readings ever be used to infer upstream intensity
    by correcting window transmission? Proposed no until explicitly calibrated.

## Controls, history and operation

24. Does controls prefer caproto or pythonSoftIOC/EPICS Base? Who maintains the
    service, and what CA network/interface/prefix conventions apply?
25. Which host, supervisor (systemd/container/IOC manager) and **local** persistent
    filesystem are available? What backup destination and retention are required?
26. **Up to 1 second accepted**, immediate pump-completion/window-change commits.
    What maximum outage is tolerable, and what shared-host resource budgets apply?
27. **BOY `.opi` confirmed**, scaffolded under `frontend/`; see DISPLAY.md.
    Resolution is adjustable. Which BOY version should we target? What
    launcher conventions and history-export mechanism should be used?
28. Does the site archiver retain these inputs at sufficient resolution to backfill
    outages? Backfill should be a separate provenance-tagged operation.
29. How will a new window be identified: serial/lot, installation date, thickness,
    operator, initial counters, photograph? **New physical windows only** initially;
    retired IDs cannot be reused. Initial offsets/late enrollment remain open.
30. **Arm + 60 s token + typed current ID + explicit confirm accepted** for new
    windows. Which site access rules and operator identity conventions apply to
    lifecycle commands? See WINDOW_LIFECYCLE.md for atomic command requirements.
31. **Slowdown ratios only initially**, with early and recent references; no
    slowdown alarms until commissioning. Should data-quality loss alarm immediately
    or after a dwell? Are load/exposure alarm thresholds wanted later?
32. How long should raw full-rate pressure/flux data be retained versus downsampled
    history? Is every pump curve retained for the full window lifetime?
