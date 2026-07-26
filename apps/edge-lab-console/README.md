# Tomato edge lab console

This is a local, read-only PC diagnostic tool for the simulated research lab.
It opens no listener, starts no experiment, accesses no hardware and makes no
network request.

Run it from the repository root with the local environment:

```text
.venv/bin/python apps/edge-lab-console/run.py validate-config
.venv/bin/python apps/edge-lab-console/run.py capabilities
.venv/bin/python apps/edge-lab-console/run.py dashboard
.venv/bin/python apps/edge-lab-console/run.py proposal --prompt spectra
```

The Spectra proposal selects the current version 2 schema: optical fixture,
Manchester symbols, Hamming(8,4), 120 synthetic payload bits and bounded
deterministic noise. The command proposes those reviewed parameters only; it
does not start an experiment.

Every output is JSON and explicitly labeled `simulation`.
