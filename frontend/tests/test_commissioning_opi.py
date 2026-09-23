"""Legacy BOY rendering contract and local facility-name coverage."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from smi_window_tracker.contract import APP_FIELDS, PREFIX, input_suffix
from smi_window_tracker.display import build


def test_generated_displays_and_manifest_match(tmp_path):
    build(tmp_path)
    directory = Path(__file__).parents[1] / "opi"
    for name in ("commissioning_overview.opi", "window_overview.opi", "pv_manifest.json"):
        assert (tmp_path / name).read_bytes() == (directory / name).read_bytes()
    manifest = json.loads((directory / "pv_manifest.json").read_text())
    assert manifest["prefix"] == PREFIX
    assert len(manifest["suffixes"]) == len(set(manifest["suffixes"]))
    for suffix in manifest["suffixes"]:
        assert suffix.endswith(("-I", "-Sts"))
    for filename in ("commissioning_overview.opi", "window_overview.opi"):
        root = ET.parse(directory / filename).getroot()
        assert root.get("typeId") == "org.csstudio.opibuilder.Display"
        assert root.findtext("macros/P") == PREFIX
        names = []
        for widget in root.findall("widget"):
            names.append(widget.findtext("name"))
            assert widget.get("typeId") in {
                "org.csstudio.opibuilder.widgets.Label",
                "org.csstudio.opibuilder.widgets.TextUpdate",
                "org.csstudio.opibuilder.widgets.ActionButton",
            }
            x, y, w, h = [int(widget.findtext(key)) for key in ("x", "y", "width", "height")]
            assert 0 <= x < x + w <= int(root.findtext("width"))
            assert 0 <= y < y + h <= int(root.findtext("height"))
            pv = widget.findtext("pv_name")
            if pv:
                assert pv.startswith("$(P)")
                assert pv[4:] in manifest["suffixes"]
            for action in widget.findall("actions/action"):
                assert action.get("type") == "OPEN_DISPLAY"
                assert (directory / action.findtext("path")).is_file()
        assert len(names) == len(set(names))


def test_main_and_diagnostics_include_key_readbacks():
    directory = Path(__file__).parents[1] / "opi"
    main = ET.parse(directory / "window_overview.opi").getroot()
    pvs = {node.text for node in main.findall(".//pv_name")}
    for name in ("Storage", "Commit", "FullPumpCount", "dp_mbar_s_unknown_s"):
        assert "$(P)" + APP_FIELDS[name][0] in pvs
    diagnostics = ET.parse(directory / "commissioning_overview.opi").getroot()
    pvs = {node.text for node in diagnostics.findall(".//pv_name")}
    for name in ("pressure", "chamber_pressure", "valve"):
        assert "$(P)" + input_suffix(name, "State") in pvs
