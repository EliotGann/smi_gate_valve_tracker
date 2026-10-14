"""Legacy BOY rendering contract and local facility-name coverage."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from smi_window_tracker.contract import APP_FIELDS, PREFIX, input_suffix
from smi_window_tracker.display import build


def test_generated_displays_and_manifest_match(tmp_path):
    build(tmp_path)
    directory = Path(__file__).parents[1] / "opi"
    for name in (
        "commissioning_overview.opi",
        "window_overview.opi",
        "window_details.opi",
        "change_window.opi",
        "beamline_schematic.opi",
        "pv_manifest.json",
    ):
        assert (tmp_path / name).read_bytes() == (directory / name).read_bytes()
    manifest = json.loads((directory / "pv_manifest.json").read_text())
    assert manifest["prefix"] == PREFIX
    assert len(manifest["suffixes"]) == len(set(manifest["suffixes"]))
    for suffix in manifest["suffixes"]:
        assert suffix.endswith(("-I", "-Sts", "-Cmd"))
    for filename in (
        "commissioning_overview.opi",
        "window_overview.opi",
        "beamline_schematic.opi",
        "window_details.opi",
        "change_window.opi",
    ):
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
                "org.csstudio.opibuilder.widgets.Rectangle",
                "org.csstudio.opibuilder.widgets.polyline",
                "org.csstudio.opibuilder.widgets.polygon",
            }
            x, y, w, h = [int(widget.findtext(key)) for key in ("x", "y", "width", "height")]
            assert 0 <= x < x + w <= int(root.findtext("width"))
            assert 0 <= y < y + h <= int(root.findtext("height"))
            pv = widget.findtext("pv_name")
            if pv:
                assert pv.startswith("$(P)")
                assert pv[4:] in manifest["suffixes"]
            for action in widget.findall("actions/action"):
                if action.get("type") == "OPEN_DISPLAY":
                    assert (directory / action.findtext("path")).is_file()
                else:
                    assert filename == "change_window.opi"
                    assert action.get("type") == "EXECUTE_PYTHONSCRIPT"
                    compile(action.findtext("scriptText"), "<change-action>", "exec")
            for rule in widget.findall("rules/rule"):
                assert rule.get("prop_id") in (
                    "visible",
                    "y",
                    "text",
                    "background_color",
                    "foreground_color",
                    "line_color",
                )
                assert rule.get("out_exp") == "false"
                for pv in rule.findall("pv"):
                    assert pv.text[4:] in manifest["suffixes"]
                    assert pv.get("trig") == "true"
                for expr in rule.findall("exp"):
                    assert "pvSev0 >= 0" in expr.get("bool_exp")
        assert len(names) == len(set(names))


def test_main_and_diagnostics_include_key_readbacks():
    directory = Path(__file__).parents[1] / "opi"
    main = ET.parse(directory / "window_details.opi").getroot()
    pvs = {node.text for node in main.findall(".//pv_name")}
    for name in ("Storage", "Commit", "FullPumpCount", "dp_mbar_s_unknown_s"):
        assert "$(P)" + APP_FIELDS[name][0] in pvs
    diagnostics = ET.parse(directory / "commissioning_overview.opi").getroot()
    pvs = {node.text for node in diagnostics.findall(".//pv_name")}
    for name in ("pressure", "chamber_pressure", "valve"):
        assert "$(P)" + input_suffix(name, "State") in pvs


def test_schematic_direction_and_bowing():
    root = ET.parse(Path(__file__).parents[1] / "opi/beamline_schematic.opi").getroot()
    widgets = {node.findtext("name"): node for node in root.findall("widget")}
    assert int(widgets["sample_chamber"].findtext("x")) > int(
        widgets["intermediate_section"].findtext("x")
    )
    assert min(int(p.get("x")) for p in widgets["kapton_membrane_1"].findall("points/point")) < 780
    assert max(int(p.get("x")) for p in widgets["kapton_membrane_2"].findall("points/point")) > 780
    for i in range(3):
        membrane = widgets[f"kapton_membrane_{i}"]
        assert membrane.findtext("visible") == "false"
        assert "pv1 == 0" in membrane.find("rules/rule/exp").get("bool_exp")
