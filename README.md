# Daggerheart Encounter Builder

A desktop tool for building and printing adversary encounter cards for the [Daggerheart](https://darringtonpress.com/daggerheart/) tabletop RPG.

> **Note:** This tool requires a copy of the Daggerheart Core Rulebook PDF, which is not included. The PDF is available from Darrington Press.

## Features

- Browse and search all adversaries by tier, role, and source
- Build multi-adversary encounters across multiple tabs
- Battle budget calculator with point tracking
- Save and load encounters as JSON files
- Print formatted encounter reference cards (A4, two-column layout)
- Homebrew adversary support

## Getting Started (Standalone Executable)

1. Download the latest release and unzip it anywhere
2. Run `DaggerheartEncounterBuilder.exe`
3. On first launch you will be prompted to import adversary data — select your Daggerheart Core Rulebook PDF
4. The app extracts the stat block data from the PDF (takes about a minute) and stores it in `%USERPROFILE%\.daggerheart\`

To re-import or update the data at any time: **File → Import Source…**

## Running from Source

**Requirements:** Python 3.10+, PySide6, pdfplumber

```powershell
pip install PySide6 pdfplumber
python main.py
```

On first run, import your PDF via **File → Import Source…** — or run `extract.py` directly:

```powershell
# Place your PDF in sources/ then:
python extract.py
```

This writes `adversaries.json` and `environments.json` to `datastore/`.

## Building the Executable

```powershell
pip install pyinstaller
.\build.ps1
```

Output: `dist\DaggerheartEncounterBuilder\DaggerheartEncounterBuilder.exe`

To install, create a shortcut to the exe or right-click it in Explorer → **Pin to taskbar**.

## Adding Sources

`sources.json` lists known PDF versions with their page ranges. If your PDF filename is not recognised on import, the app will prompt you to select from the list or enter custom page ranges.

To add a new entry, edit `sources.json`:

```json
{
  "sources": [
    {
      "filename": "Daggerheart_Core_Rulebook-5-20-2025-1.pdf",
      "label": "Daggerheart Core Rulebook (2025-05-20)",
      "adversary_pages": [211, 240],
      "environment_pages": [244, 252]
    }
  ]
}
```

## License

This project is not affiliated with or endorsed by Darrington Press. Daggerheart is a trademark of Darrington Press LLC.
