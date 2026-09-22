# Supplied SMI Bluesky reference files

These are the original beamline Python examples provided for PV discovery and
physics context, relocated here without changing their contents. They are not
part of the soft IOC package and are not standalone runnable examples: they refer
to the SMI Bluesky environment, instantiate devices and may contain hardware
commands. The soft IOC does not import them.

| Files | Reference use |
| --- | --- |
| `machine.py` | Ring and insertion-device PVs |
| `energy.py` | Bragg/Si(111) energy conversion and motor PVs |
| `waxschamber.py` | Pressure gauges and existing gate-valve prefixes |
| `shutter_class.py`, `shutter_dev.py` | Shutter PVs and state conventions |
| `electrometers_class.py`, `electrometers_dev.py` | BPM/current channels |
| `attenuators_class.py`, `attenuators_dev.py` | Foil readbacks and bank layout |
| `attenuator_data.py` | Supplied CXRO foil optical-depth tables and provenance |

Bare reference filenames and line numbers in [PVS.md](../../PVS.md) refer to files
in this directory. Keeping these inputs separate avoids collecting them as app
tests or treating their hardware-control dependencies as IOC dependencies.
