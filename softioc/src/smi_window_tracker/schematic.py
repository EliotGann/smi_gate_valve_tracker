"""Presentation states for the BOY beamline schematic; no device control."""

from .intervals import gate
from .physics import bragg_energy_ev

VISUAL_FIELDS = {
    "Beam": ("View:Beam-Sts", -1.0),
    "Sample": ("View:Sample-Sts", -1.0),
    "Intermediate": ("View:Intermediate-Sts", -1.0),
    "Kapton": ("View:Kapton-Sts", -1.0),
    "DetectorValve": ("View:DetectorValve-Sts", -1.0),
    "Bow": ("View:Bow-Sts", -1.0),
    "Energy": ("View:Energy-I", float("nan")),
    "BPM": ("View:BPM3-I", float("nan")),
}


def pressure_code(value):
    # 0 = pumped, 1 = vented, 2 = intermediate, 3 = under range, -1 unknown.
    if value is None or value < 0:
        return -1
    if value == 0:
        return 3
    if value < 0.01:
        return 0
    return 1 if value >= 600 else 2


def visual_values(inputs, now):
    def value(name):
        return inputs.value(name, now)

    beam = gate(
        *(
            {0: True, closed: False}.get(value(name))
            for name, closed in (
                ("front_end_shutter", 1),
                ("photon_shutter", 1),
                ("fast_shutter", 7),
            )
        )
    )
    up, down = value("chamber_pressure"), value("pressure")
    kapton, detector = value("valve"), value("downstream_valve")
    bow = -1
    if kapton == 1:
        bow = 0  # Retracted, no membrane drawn across the beam.
    elif kapton == 0 and up is not None and down is not None and up > 0 and down > 0:
        # Direction only, not deflection/stress calibration. 1 mbar display deadband.
        bow = 1 if up - down > 1 else 2 if down - up > 1 else 0
    energy = float("nan")
    angle = value("bragg")
    if angle is not None:
        try:
            energy = bragg_energy_ev(angle, minimum_ev=2100, maximum_ev=24000) / 1000
        except ValueError:
            pass
    bpm = value("bpm3_sum_x")
    return {
        "Beam": -1 if beam is None else int(beam),
        "Sample": pressure_code(up),
        "Intermediate": pressure_code(down),
        "Kapton": kapton if kapton in (0, 1) else -1,
        "DetectorValve": detector if detector in (0, 1) else -1,
        "Bow": bow,
        "Energy": energy,
        "BPM": bpm if bpm is not None else float("nan"),
    }
