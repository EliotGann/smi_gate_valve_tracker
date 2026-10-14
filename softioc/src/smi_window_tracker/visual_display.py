"""Separate BOY schematic, using native shapes and presentation-only rules."""

from xml.etree import ElementTree as ET

from .contract import APP_FIELDS, TREND_SUFFIXES, input_suffix
from .display import display, label, navigation, readout, widget
from .schematic import VISUAL_FIELDS

GRAY = (140, 145, 150)
GREEN = (0, 155, 75)
RED = (210, 45, 45)
BLUE = (190, 222, 245)
AMBER = (249, 220, 145)
WHITE = (245, 245, 245)
INK = (35, 45, 55)


def prop(node, name, value):
    old = node.find(name)
    if old is not None:
        node.remove(old)
    el = ET.SubElement(node, name)
    if isinstance(value, tuple):
        ET.SubElement(
            el, "color", **dict(zip(("red", "green", "blue"), map(str, value), strict=True))
        )
    else:
        el.text = str(value).lower() if isinstance(value, bool) else str(value)


def rule(node, property_name, key, cases):
    """Native BOY RulesProperty serialization; default is widget's unknown style."""
    rules = node.find("rules")
    if rules is None:
        rules = ET.SubElement(node, "rules")
    r = ET.SubElement(rules, "rule", name=property_name, prop_id=property_name, out_exp="false")
    for code, value in cases.items():
        exp = ET.SubElement(r, "exp", bool_exp=f"pvSev0 >= 0 && pv0 == {code}")
        prop(exp, "value", value)
    ET.SubElement(r, "pv", trig="true").text = "$(P)" + VISUAL_FIELDS[key][0]


def box(root, name, x, y, w, h, fill=GRAY):
    node = widget(root, name, "Rectangle", x, y, w)
    for key, value in (
        ("height", h),
        ("background_color", fill),
        ("foreground_color", INK),
        ("line_color", INK),
        ("line_width", 2),
        ("transparent", False),
    ):
        prop(node, key, value)
    return node


def poly(root, name, points, color, *, filled=False):
    xs, ys = zip(*points, strict=True)
    node = widget(
        root, name, "polygon" if filled else "polyline", min(xs), min(ys), max(1, max(xs) - min(xs))
    )
    prop(node, "height", max(1, max(ys) - min(ys)))
    prop(node, "foreground_color", color)
    prop(node, "background_color", color)
    prop(node, "line_color", color)
    prop(node, "line_width", 4)
    prop(node, "transparent", not filled)
    listing = ET.SubElement(node, "points")
    for x, y in points:
        ET.SubElement(listing, "point", x=str(x), y=str(y))
    return node


def state_label(root, name, x, y, width, key, cases):
    node = label(root, name, "UNKNOWN / NO DATA", x, y, width)
    rule(node, "text", key, cases)
    return node


def schematic_display():
    root = display("SMI KaptonMon | Installed window monitor | beam travels RIGHT to LEFT", 1100)
    navigation(root, "window_details.opi", "Detailed statistics", 1120, 65)
    navigation(root, "commissioning_overview.opi", "Input diagnostics", 1390, 65)
    readout(root, "heartbeat", "Heartbeat-I", 20, 65, 120, True)
    label(root, "heartbeat_label", "IOC heartbeat (must advance)", 150, 65, 400)

    # Physical order, from right to left: incoming beam, sample, window,
    # intermediate section, detector isolation gate, detector.
    box(root, "sample_chamber", 840, 230, 440, 360)
    sample = root.findall("widget")[-1]
    rule(sample, "background_color", "Sample", {0: BLUE, 1: WHITE, 2: AMBER, 3: (210, 205, 240)})
    intermediate = box(root, "intermediate_section", 350, 290, 370, 240)
    rule(
        intermediate,
        "background_color",
        "Intermediate",
        {0: BLUE, 1: WHITE, 2: AMBER, 3: (210, 205, 240)},
    )
    box(root, "detector_body", 35, 325, 180, 170, (220, 225, 230))
    label(root, "detector_title", "Pilatus 2M", 55, 350, 150)
    label(root, "detector_subtitle", "Detector vacuum", 45, 455, 165)
    label(root, "sample_title", "WAXS / SAMPLE CHAMBER", 865, 250, 400)
    label(root, "intermediate_title", "INTERMEDIATE / TCG:9", 370, 310, 340)
    state_label(
        root,
        "sample_state",
        865,
        295,
        400,
        "Sample",
        {
            0: "PUMPED (<0.01 mbar, raw)",
            1: "VENTED RANGE (>=600 mbar)",
            2: "BETWEEN TARGETS",
            3: "UNDER RANGE (reported zero)",
        },
    )
    state_label(
        root,
        "intermediate_state",
        370,
        345,
        340,
        "Intermediate",
        {
            0: "PUMPED (<0.01 mbar, raw)",
            1: "VENTED RANGE (>=600 mbar)",
            2: "BETWEEN TARGETS",
            3: "UNDER RANGE (reported zero)",
        },
    )
    readout(root, "sample_pressure", input_suffix("chamber_pressure", "Display"), 865, 510, 240)
    label(root, "sample_units", "mbar (TCG:7)", 1110, 510, 160)
    readout(root, "downstream_pressure", input_suffix("pressure", "Display"), 370, 455, 210)
    label(root, "downstream_units", "mbar", 590, 455, 100)

    # Static neutral beam axis; incoming arrow encodes shutter eligibility only.
    poly(root, "beam_axis", [(160, 410), (1280, 410)], (190, 190, 190))
    arrow = poly(
        root,
        "incoming_beam",
        [(1625, 396), (1370, 396), (1370, 377), (1300, 410), (1370, 443), (1370, 424), (1625, 424)],
        GRAY,
        filled=True,
    )
    for color_prop in ("foreground_color", "background_color", "line_color"):
        rule(arrow, color_prop, "Beam", {0: RED, 1: GREEN})
    state_label(
        root,
        "beam_state",
        1300,
        325,
        360,
        "Beam",
        {
            0: "OFF: shutter closed",
            1: "ON: all shutters open",
        },
    )
    label(root, "beam_note", "Shutter eligibility, not measured flux", 1300, 355, 370)
    label(root, "energy_label", "Photon energy (keV)", 1310, 485, 340)
    readout(root, "energy", VISUAL_FIELDS["Energy"][0], 1310, 515, 330, True)
    label(root, "bpm_label", "BPM3 SumX (raw intensity)", 1310, 555, 340)
    readout(root, "bpm_intensity", VISUAL_FIELDS["BPM"][0], 1310, 585, 330, True)
    label(root, "bpm_note", "Uncalibrated; does not gate beam", 1300, 615, 370)

    # Gate blades move out of the beam for OPEN. Unknown stays gray at the center.
    for key, x, title in (
        ("Kapton", 780, "GV6W / KAPTON"),
        ("DetectorValve", 280, "GV7 / DETECTOR"),
    ):
        box(root, key + "_housing", x - 23, 190, 46, 375, (225, 225, 225))
        label(root, key + "_label", title, x - 100, 150, 250)
        unknown = box(root, key + "_unknown", x - 12, 355, 24, 110)
        rule(unknown, "visible", key, {0: False, 1: False})
        blade = box(root, key + "_blade", x - 7, 230, 14, 110, (90, 115, 135))
        prop(blade, "visible", False)
        rule(blade, "visible", key, {1: True, 0: key == "DetectorValve"})
        rule(blade, "y", key, {1: 230, 0: 355})
        state_label(
            root,
            key + "_position",
            x - 90,
            600,
            270,
            key,
            {
                0: "IN PLACE / CLOSED" if key == "Kapton" else "CLOSED / IN",
                1: "RETRACTED / OPEN" if key == "Kapton" else "OPEN / OUT",
            },
        )

    # Fixed exaggerated curves indicate pressure direction, never physical deflection.
    for code, points in (
        (0, [(780, 350), (780, 470)]),
        (1, [(780, 350), (755, 365), (735, 390), (730, 410), (735, 430), (755, 455), (780, 470)]),
        (2, [(780, 350), (805, 365), (825, 390), (830, 410), (825, 430), (805, 455), (780, 470)]),
    ):
        membrane = poly(root, f"kapton_membrane_{code}", points, (210, 135, 20))
        prop(membrane, "visible", False)
        # Two inputs: pressure shape and valve position, no server-side physics duplicated.
        rule(membrane, "visible", "Bow", {code: True})
        r = membrane.find("rules/rule")
        r.find("exp").set("bool_exp", f"pvSev0 >= 0 && pvSev1 >= 0 && pv0 == {code} && pv1 == 0")
        ET.SubElement(r, "pv", trig="true").text = "$(P)" + VISUAL_FIELDS["Kapton"][0]
    state_label(
        root,
        "bow_state",
        570,
        650,
        670,
        "Bow",
        {
            0: "No bow shown (balanced or retracted)",
            1: "Pressure pushes LEFT toward intermediate section",
            2: "Pressure pushes RIGHT toward sample chamber",
        },
    )
    label(
        root,
        "bow_note",
        "Bow is qualitative, exaggerated; 1 mbar display deadband. Not a strain measurement.",
        390,
        685,
        1050,
    )
    box(root, "window_summary_box", 350, 735, 580, 295, WHITE)
    box(root, "state_box", 950, 735, 710, 295, WHITE)
    label(root, "window_summary_title", "INSTALLED KAPTON WINDOW", 370, 742, 540)
    for index, (key, title) in enumerate(
        (
            ("Window", "Window"),
            ("InstalledText", "Installed"),
            ("PumpedTimeText", "Closed + pumped"),
            ("BeamTimeText", "In beam (shutters)"),
            ("FullPumpCount", "Pump cycles"),
        )
    ):
        y = 780 + 34 * index
        label(root, key + "_label", title, 370, y, 180)
        readout(root, key, APP_FIELDS[key][0], 555, y, 360, key == "FullPumpCount")
    navigation(root, "change_window.opi", "Change installed window...", 550, 975)
    label(root, "state_title", "TRACKER STATE / PROCEDURE", 970, 742, 670)
    for index, (key, title) in enumerate(
        (
            ("PumpState", "Pump"),
            ("ProcedurePath", "Path"),
            ("ProcedureState", "Procedure"),
            ("HoldRemainingText", "Hold remaining"),
            ("ProcedureAlarm", "Alarm"),
        )
    ):
        y = 780 + 34 * index
        label(root, key + "_label", title, 970, y, 150)
        readout(root, key, APP_FIELDS[key][0], 1125, y, 520)
    label(root, "rate_label", "Rise (mbar/s)", 970, 975, 220)
    readout(root, "rate", TREND_SUFFIXES["Rate"], 1200, 975, 440, True)
    label(
        root,
        "legend",
        "Gray = unknown. Blue = pumped. White = vented. "
        "Amber = between targets. Purple = under range.",
        30,
        1050,
        1620,
    )
    return root
