"""BOY local-dialog command transport, no shared proposal staging PVs."""

from xml.etree import ElementTree as ET

from .contract import APP_FIELDS, CHANGE_COMMAND
from .display import display, label, navigation, readout, widget

SCRIPT = """
import json
from java.util import UUID
from java.time import Instant
from org.eclipse.jface.dialogs import InputDialog
from org.eclipse.jface.window import Window
from org.eclipse.swt.widgets import Display
from org.csstudio.opibuilder.scriptUtil import PVUtil, GUIUtil

def ask(title, prompt, default=""):
    dialog = InputDialog(Display.getCurrent().getActiveShell(), title, prompt, default, None)
    if dialog.open() != Window.OK:
        raise ValueError("Cancelled")
    return str(dialog.getValue()).strip()

def text(name):
    pv = display.getWidget(name).getPV()
    if PVUtil.getSeverity(pv) < 0:
        raise ValueError("Disconnected; reopen screen")
    data = PVUtil.getDoubleArray(pv)
    if len(data):
        return ''.join(chr(int(v)) for v in data if int(v) != 0)
    return str(PVUtil.getString(pv))

try:
    current, session = text("current_id"), text("session")
    command = str(display.getWidget("command_target").getPropertyValue("pv_name"))
    operation = "OPERATION"
    if operation == "arm":
        new_id = ask("New physical window", "Unique new window name")
        operator = ask("Operator", "Your name / audit label")
        reason = ask("Removal reason",
                     "failure, suspected_degradation, preventive, experiment_change, unknown",
                     "unknown")
        installed = ask("Installed UTC", "Physical installation time (ISO UTC)", str(Instant.now()))
        notes = ask("Notes", "Optional installation / removal notes")
        prompt = "Arm retirement of " + current + " and installation of " + new_id + "?"
        if not GUIUtil.openConfirmDialog(prompt):
            raise ValueError("Cancelled")
        request_id = str(UUID.randomUUID())
        display.setVar("change_request_id", request_id)
        display.setVar("change_session", session)
        request = dict(op="arm", request_id=request_id, session=session, current_id=current,
                       new_id=new_id, operator=operator, reason=reason,
                       installed_utc=installed, notes=notes)
    else:
        reply = json.loads(text("reply"))
        if (reply.get("status") != "armed" or
                reply.get("request_id") != display.getVar("change_request_id")):
            raise ValueError("No arm owned by this screen; arm again")
        if session != display.getVar("change_session"):
            raise ValueError("IOC restarted; arm again")
        request = dict(op=operation, request_id=reply["request_id"],
                       session=session, token=reply["token"])
        if operation == "confirm":
            request["typed_current_id"] = ask("Confirm physical replacement",
                                             "Type current window ID (" + current + ")")
            prompt = "Retire " + current + " and start " + reply["proposal"]["new_id"]
            if not GUIUtil.openConfirmDialog(prompt + "? Old history is preserved."):
                raise ValueError("Cancelled")
        display.setVar("change_request_id", None)
    PVUtil.writePV(command, json.dumps(request), 5)
except Exception as exc:
    display.getWidget("local_message").setPropertyValue("text", str(exc))
"""


def change_display():
    root = display("KaptonMon | Install a NEW physical window", 780)
    navigation(root, "window_overview.opi", "Return to monitor", 1390, 60)
    label(
        root,
        "instructions",
        "1. Propose and arm.  2. Review server proposal.  "
        "3. Type current ID and confirm within 60 s.",
        20,
        110,
        1600,
    )
    for y, key, name, title in (
        (160, "Window", "current_id", "Current installed window"),
        (200, "Session", "session", "Service session"),
        (240, "InstalledText", "installed", "Installed date"),
        (280, "PumpedTimeText", "pumped", "Closed + pumped time"),
        (320, "BeamTimeText", "beam", "Window shutters-open time"),
        (360, "ChangeRemaining", "remaining", "Arm seconds remaining"),
        (410, "ChangeReply", "reply", "Server proposal / reply"),
        (530, "ChangeReceipt", "receipt", "Durable success receipt"),
    ):
        label(root, name + "_label", title, 20, y, 300)
        node = readout(root, name, APP_FIELDS[key][0], 340, y, 1290, key == "ChangeRemaining")
        if key in ("ChangeReply", "ChangeReceipt"):
            node.find("height").text = "90"
            ET.SubElement(node, "wrap_words").text = "true"
    node = readout(root, "command_target", CHANGE_COMMAND, 20, 750, 100)
    ET.SubElement(node, "visible").text = "false"
    for index, (operation, title) in enumerate(
        (
            ("arm", "1. Propose / Arm..."),
            ("confirm", "2. Retire old / Install new..."),
            ("cancel", "Cancel arm"),
        )
    ):
        node = widget(root, operation, "ActionButton", 20 + 540 * index, 650, 500, text=title)
        actions = ET.SubElement(node, "actions", hook="false", hook_all="false")
        action = ET.SubElement(actions, "action", type="EXECUTE_PYTHONSCRIPT")
        ET.SubElement(action, "embedded").text = "true"
        ET.SubElement(action, "scriptText").text = SCRIPT.replace("OPERATION", operation)
    label(
        root,
        "local_message",
        "No device writes. Success is only the durable server receipt above.",
        20,
        710,
        1600,
    )
    return root
