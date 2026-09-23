"""Generate legacy BOY displays and the matching local PV manifest.

Run from softioc: python -m smi_window_tracker.display ../frontend/opi
"""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .contract import (
    APP_FIELDS,
    INPUT_FIELDS,
    INPUT_STEMS,
    PREFIX,
    TREND_SUFFIXES,
    VERSION,
    input_suffix,
)


def display(title, height):
    root = ET.Element("display", typeId="org.csstudio.opibuilder.Display", version="1.0.0")
    for key, value in (
        ("name", title),
        ("width", 1680),
        ("height", height),
        ("show_grid", "false"),
    ):
        ET.SubElement(root, key).text = str(value)
    macros = ET.SubElement(root, "macros")
    ET.SubElement(macros, "include_parent_macros").text = "true"
    ET.SubElement(macros, "P").text = PREFIX
    color = ET.SubElement(root, "background_color")
    ET.SubElement(color, "color", red="245", green="245", blue="245")
    label(root, "title", title, 20, 20, 1620)
    return root


def widget(root, name, kind, x, y, width, text=None, pv=None, numeric=False):
    node = ET.SubElement(
        root, "widget", typeId="org.csstudio.opibuilder.widgets." + kind, version="1.0.0"
    )
    fields = dict(name=name, x=x, y=y, width=width, height=28)
    if text is not None:
        fields["text"] = text
    if pv:
        fields.update(
            pv_name="$(P)" + pv,
            format_type=6 if numeric else 4,
            precision=6,
            precision_from_pv="false",
            show_units="false",
        )
    for key, value in fields.items():
        ET.SubElement(node, key).text = str(value)
    return node


def label(root, name, text, x, y, width):
    return widget(root, name, "Label", x, y, width, text=text)


def readout(root, name, pv, x, y, width, numeric=False):
    return widget(root, name, "TextUpdate", x, y, width, pv=pv, numeric=numeric)


def navigation(root, target, text, x, y):
    node = widget(root, "open_" + target, "ActionButton", x, y, 240, text=text)
    actions = ET.SubElement(node, "actions", hook="false", hook_all="false")
    action = ET.SubElement(actions, "action", type="OPEN_DISPLAY")
    ET.SubElement(action, "path").text = target
    ET.SubElement(action, "mode").text = "0"
    macros = ET.SubElement(action, "macros")
    ET.SubElement(macros, "include_parent_macros").text = "true"


def watch(root, y):
    label(
        root,
        "watch_title",
        "Closed-window downstream vacuum watch (live, not a leak diagnosis)",
        20,
        y,
        1600,
    )
    for index, (key, title) in enumerate(
        (
            ("Status", "Status"),
            ("Baseline", "Downstream baseline (mbar)"),
            ("Change", "Downstream change (mbar)"),
            ("Rate", "Recent signed rate (mbar/s)"),
            ("Span", "Rate span (s, up to 30)"),
            ("Elapsed", "Observation elapsed (s)"),
            ("UpstreamChange", "Sample pressure change (mbar)"),
            ("DeltaP", "Absolute pressure difference (mbar)"),
        )
    ):
        row = y + 35 + (index // 2) * 34
        x = 20 + (index % 2) * 820
        label(root, "watch_label_" + key, title, x, row, 300)
        readout(root, "watch_" + key, TREND_SUFFIXES[key], x + 310, row, 490, key != "Status")


def diagnostics():
    root = display("KaptonMon - input states and vacuum watch (local CA)", 1190)
    readout(root, "contract", "Version:Contract-I", 20, 60, 450)
    label(root, "hb_label", "Heartbeat", 500, 60, 120)
    readout(root, "heartbeat", "Heartbeat-I", 630, 60, 160, True)
    navigation(root, "window_overview.opi", "Main monitor", 1390, 60)
    columns = [
        (20, 255, "Input"),
        (290, 220, "Raw"),
        (530, 340, "State / relevance"),
        (890, 100, "Connected"),
        (1020, 100, "Severity"),
        (1150, 140, "Last read"),
        (1300, 360, "Last observed value change"),
    ]
    for x, width, title in columns:
        label(root, "header_" + title, title, x, 110, width)
    label(root, "source_header", "IOC source time below (may be unset)", 1150, 137, 510)
    titles = {"pressure": "Pump-down TCG:9 (mbar)", "chamber_pressure": "WAXS sample TCG:7 (mbar)"}
    for index, name in enumerate(INPUT_STEMS):
        y = 175 + index * 60
        label(root, name + "_label", titles.get(name, INPUT_STEMS[name]), 20, y, 255)
        for field, (x, width, _) in zip(
            ("Text", "State", "Connected", "Severity", "ReadAge", "ChangeAge"),
            columns[1:],
            strict=True,
        ):
            readout(
                root,
                name + field,
                input_suffix(name, field),
                x,
                y,
                width,
                field in ("Connected", "Severity"),
            )
        readout(root, name + "TimeText", input_suffix(name, "TimeText"), 1150, y + 27, 510)
    label(
        root,
        "range_note",
        "Last read includes monitors/health reads; last change is observed here, not IOC time. "
        "Startup/reconnect sets a baseline. 'Just now' lasts 5 s.",
        20,
        790,
        1600,
    )
    watch(root, 840)
    label(
        root,
        "watch_note",
        "Positive rate = worsening vacuum. NaN = unavailable. Zero/invalid/gaps reset the watch. "
        "Recorder saves raw events and snapshots.",
        20,
        1045,
        1630,
    )
    return root


def overview():
    root = display("KaptonMon - beamtime recorder / window overview (local CA)", 1190)
    navigation(root, "commissioning_overview.opi", "Input diagnostics", 1390, 60)
    rows = [
        ("Window", "Physical window / beamtime ID"),
        ("Storage", "Storage health"),
        ("Commit", "Durable commit sequence"),
        ("CommitTime", "Last commit UTC (Unix s)"),
        ("Session", "Current session"),
        ("PumpState", "Qualified pump status"),
        ("OpenCount", "Observed valve opens"),
        ("CloseCount", "Observed valve closes"),
        ("ClosedPumpedCount", "Closures reaching vacuum"),
        ("FullPumpCount", "Completed pump cycles"),
        ("InterruptedCount", "Interrupted / expired attempts"),
        ("LastPump", "Last pump duration (s)"),
        ("PumpElapsed", "Current pump elapsed (s)"),
        ("EarlyMedian", "First 5 median (s; see N)"),
        ("EarlyN", "Early sample count (collecting until 5)"),
        ("RecentMedian", "Recent 20 median (s; see N)"),
        ("RecentN", "Recent sample count"),
        ("closed_pumped_s_value", "Closed + qualified vacuum time (s)"),
        ("beam_path_s_value", "Shutters-open time (s; no ring gate)"),
        ("window_beam_s_value", "Closed-window shutters-open time (s)"),
        ("dp_mbar_s_value", "Closed-window pressure integral (mbar s)"),
        ("dp_mbar_s_unknown_s", "Pressure integral unknown time (s)"),
        ("closed_pumped_s_unknown_s", "Vacuum timer unknown time (s)"),
        ("window_beam_s_unknown_s", "Window shutter timer unknown time (s)"),
        ("Milestone100", "Last pump to <100 mbar (s)"),
        ("Milestone10", "Last pump to <10 mbar (s)"),
        ("Milestone1", "Last pump to <1 mbar (s)"),
        ("Milestone0p1", "Last pump to <0.1 mbar (s)"),
    ]
    for index, (key, title) in enumerate(rows):
        x = 20 + (index % 2) * 820
        y = 105 + (index // 2) * 34
        label(root, key + "_label", title, x, y, 350)
        suffix, _, units = APP_FIELDS[key]
        readout(root, key, suffix, x + 360, y, 440, units is not None)
    readout(root, "history", APP_FIELDS["PumpHistory"][0], 20, 600, 1630)
    readout(root, "model", APP_FIELDS["Model"][0], 20, 640, 1630)
    label(
        root,
        "limits",
        "No calibrated photons/J yet; BPM unused. Zero pressure = unknown qualification/load. "
        "Restart restores totals, not hidden transitions.",
        20,
        680,
        1630,
    )
    for index, name in enumerate(("pressure", "chamber_pressure", "valve")):
        x = 20 + index * 540
        label(root, "live_label_" + name, INPUT_STEMS[name], x, 725, 500)
        readout(root, "live_" + name, input_suffix(name, "Text"), x, 755, 200)
        readout(root, "state_" + name, input_suffix(name, "State"), x + 210, 755, 320)
    watch(root, 815)
    label(
        root,
        "durability",
        "Raw PV events, pump attempts, totals and closed-watch snapshots are stored in SQLite; "
        "session boundaries identify downtime.",
        20,
        1020,
        1630,
    )
    label(
        root,
        "restart_note",
        "Close/reopen the display freely. Stop/restart the backend with the same database, "
        "config and window ID to resume.",
        20,
        1060,
        1630,
    )
    return root


def build(directory):
    directory = Path(directory)
    for filename, root in (
        ("commissioning_overview.opi", diagnostics()),
        ("window_overview.opi", overview()),
    ):
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(directory / filename, encoding="UTF-8", xml_declaration=True)
    suffixes = ["Version:Contract-I", "Heartbeat-I", *TREND_SUFFIXES.values()]
    suffixes += [input_suffix(name, field) for name in INPUT_STEMS for field in INPUT_FIELDS]
    suffixes += [value[0] for value in APP_FIELDS.values()]
    (directory / "pv_manifest.json").write_text(
        json.dumps(
            {
                "contract": VERSION,
                "prefix": PREFIX,
                "read_only": True,
                "suffixes": suffixes,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    build(sys.argv[1])
