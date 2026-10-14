"""Facility-style local CA names. Facility approval is still pending."""

PREFIX = "XF:12IDC-ES{KaptonMon:1}"
VERSION = "kapton-monitor-v3"
INPUT_STEMS = {
    "pressure": "Pressure:Downstream",
    "chamber_pressure": "Pressure:Sample",
    "fast_shutter": "Shutter:Fast",
    "photon_shutter": "Shutter:Photon",
    "front_end_shutter": "Shutter:FE",
    "valve": "Valve:Pos",
    "downstream_valve": "Valve:Detector",
    "bragg": "Mono:Bragg",
    "ring_current": "Ring:Current",
    "ring_mode": "Ring:Mode",
    "bpm3_sum_x": "BPM3:SumX",
}
INPUT_FIELDS = {
    "Value": "-I",
    "Text": ":RawText-I",
    "State": ":State-Sts",
    "Connected": ":Conn-Sts",
    "Severity": ":Severity-I",
    "Status": ":Alarm-I",
    "Timestamp": ":SourceTime-I",
    "TimeText": ":SourceTimeText-I",
    "Display": ":Display-I",
    "ReadTime": ":ReadTime-I",
    "ChangeTime": ":ChangeTime-I",
    "ReadAge": ":ReadAgeText-I",
    "ChangeAge": ":ChangeAgeText-I",
}
TREND_SUFFIXES = {
    "Status": "VacWatch:State-Sts",
    "Baseline": "VacWatch:Baseline-I",
    "Change": "VacWatch:Change-I",
    "Rate": "VacWatch:Rate-I",
    "Span": "VacWatch:Span-I",
    "Elapsed": "VacWatch:Elapsed-I",
    "UpstreamChange": "VacWatch:SampleChange-I",
    "DeltaP": "Pressure:Diff-I",
}
APP_FIELDS = {
    "Window": ("Window:ID-I", "", None),
    "InstalledTime": ("Window:InstalledTime-I", float("nan"), "s"),
    "InstalledText": ("Window:InstalledText-I", "Unknown installation date", None),
    "PumpedTimeText": ("Window:PumpedTimeText-I", "0 days 0:00:00", None),
    "BeamTimeText": ("Window:BeamTimeText-I", "0 days 0:00:00", None),
    "HoldRemainingText": ("Procedure:HoldRemainingText-I", "", None),
    "PumpElapsedText": ("Pump:ElapsedText-I", "N/A", None),
    "ChangeReply": ("Window:ChangeReply-I", "No pending change", None),
    "ChangeReceipt": ("Window:ChangeReceipt-I", "No window replacement recorded", None),
    "ChangeRemaining": ("Window:ChangeRemaining-I", 0.0, "s"),
    "Session": ("Session:ID-I", "", None),
    "Storage": ("Storage:State-Sts", "Starting", None),
    "Commit": ("Storage:Seq-I", 0.0, ""),
    "CommitTime": ("Storage:Time-I", 0.0, "s"),
    "CommitAge": ("Storage:Age-I", 0.0, "s"),
    "Queue": ("Storage:Pending-I", 0.0, ""),
    "ProcedurePath": ("Procedure:Path-Sts", "unclassified", None),
    "ProcedureState": ("Procedure:State-Sts", "Acquiring", None),
    "ProcedureAlarm": ("Procedure:Alarm-Sts", "Acquiring", None),
    "ProcedureSeverity": ("Procedure:Severity-I", 3.0, ""),
    "HoldElapsed": ("Procedure:HoldElapsed-I", 0.0, "s"),
    "HoldRemaining": ("Procedure:HoldRemaining-I", 300.0, "s"),
    "OpeningLimit": ("Procedure:PressureLimit-I", 0.009, "mbar"),
    "LastProcedure": ("Procedure:Last-I", "No completed procedure episode", None),
    "PathHistory": ("Pump:PathHistory-I", "No classified pump durations yet", None),
    "Retention": ("Storage:Policy-Sts", "changes-v1", None),
    "HistoryReceived": ("Storage:Received-I", 0.0, ""),
    "HistoryRetained": ("Storage:Retained-I", 0.0, ""),
    "HistorySkipped": ("Storage:Skipped-I", 0.0, ""),
    "HistoryRows": ("Storage:EventRows-I", 0.0, ""),
    "SnapshotRows": ("Storage:SnapshotRows-I", 0.0, ""),
    "DatabaseMiB": ("Storage:Size-I", 0.0, "MiB"),
    "OpenCount": ("Valve:OpenCount-I", 0.0, ""),
    "CloseCount": ("Valve:CloseCount-I", 0.0, ""),
    "ClosedPumpedCount": ("Pump:ClosureCount-I", 0.0, ""),
    "FullPumpCount": ("Pump:Count-I", 0.0, ""),
    "InterruptedCount": ("Pump:InterruptedCount-I", 0.0, ""),
    "PumpState": ("Pump:State-Sts", "Acquiring", None),
    "PumpElapsed": ("Pump:Elapsed-I", float("nan"), "s"),
    "LastPump": ("Pump:LastDuration-I", float("nan"), "s"),
    "EarlyMedian": ("Pump:EarlyMedian-I", float("nan"), "s"),
    "RecentMedian": ("Pump:RecentMedian-I", float("nan"), "s"),
    "EarlyN": ("Pump:EarlyN-I", 0.0, ""),
    "RecentN": ("Pump:RecentN-I", 0.0, ""),
    "PumpHistory": ("Pump:History-I", "No completed cycles", None),
    "Model": ("Model:State-Sts", "Incomplete: attenuation / Kapton data", None),
    "BeamPolicy": ("Beam:Policy-Sts", "Shutter-only observed time", None),
}
METRICS = {
    "beam_path_s": ("Beam:PathTime", "s"),
    "window_beam_s": ("Beam:WindowTime", "s"),
    "closed_pumped_s": ("Pump:ClosedTime", "s"),
    "dp_mbar_s": ("Load:PressureIntegral", "mbar s"),
}
for key, (stem, units) in METRICS.items():
    for field, unit in (("value", units), ("valid_s", "s"), ("unknown_s", "s")):
        suffix = "" if field == "value" else ":ValidTime" if field == "valid_s" else ":UnknownTime"
        APP_FIELDS[f"{key}_{field}"] = (stem + suffix + "-I", 0.0, unit)
for label in ("100", "10", "1", "0p1"):
    APP_FIELDS[f"Milestone{label}"] = (f"Pump:T{label}-I", float("nan"), "s")


def input_suffix(name: str, field: str) -> str:
    return INPUT_STEMS[name] + INPUT_FIELDS[field]


CHANGE_COMMAND = "Window:Change-Cmd"
