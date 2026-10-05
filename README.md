# Rigol DHO800/DHO900 skill and Python library

Python control for Rigol DHO800 and DHO900 oscilloscopes over USB or LAN, with model capability profiles, typed settings and results, waveform transfers, and bounded output operations. This repository also contains an agent [skill](SKILL.md) for writing small instrument scripts.

The library follows Rigol's [DHO800/DHO900 Programming Guide](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf), PGA39106-1110 (April 2025, software 00.01.03). The [coverage checklist](COVERAGE.md) tracks all 565 guide command entries for **DHO914S** with simulated tests. The other seven guide-listed models have capability profiles and selected shared operations; full command coverage and live firmware acceptance for them are not claimed.

## Use

Clone the repository, install `requirements.txt` in a Python virtual environment, and add `scripts` to `PYTHONPATH`:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=scripts .venv/bin/python -c 'from dho800900 import connect; print(connect)'
```

`dho800900.connect()` detects the model from `*IDN?`. It returns the VISA resource manager, profiled scope, resource name, and raw identity. `scope.identity.guide_status` reports whether the firmware's first three version components match the guide's software version. See [SKILL.md](SKILL.md) for a read-only script and the instrument-state safeguards.

Run the offline suite from the repository root:

```bash
DHO914S_REQUIRE_FULL_COVERAGE=1 PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

## License

The code and skill are [PolyForm Noncommercial 1.0.0](LICENSE) source-available software. Community research, experimentation, and hobby use are permitted under its terms. Commercial use, including incorporation into a sold product, requires a separate license from the copyright holder. This is not an OSI open-source license.

This project is independent of Rigol Technologies.
