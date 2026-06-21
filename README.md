# Daggerheart Encounter Builder

A desktop tool for building, printing, and running adversary encounters for the [Daggerheart](https://darringtonpress.com/daggerheart/) tabletop RPG.

> **Note:** This tool requires a copy of the Daggerheart Core Rulebook PDF, which is not included. The PDF is available from Darrington Press.

## Features

- Browse and filter all adversaries by tier, role, and source
- Build multi-adversary encounters across multiple tabs
- Battle budget calculator with point tracking
- Save and load encounters as JSON files
- Print formatted encounter reference cards (A4, two-column layout)
- **Run Encounter mode** — interactive session view with clickable HP and stress trackers per adversary instance, embedded in the main window
- Homebrew adversary support

## Getting Started

Download the latest release from the [Releases](../../releases) page.

**Windows:** unzip and run `DaggerheartEncounterBuilder.exe`

**Mac:** unzip, move `DaggerheartEncounterBuilder.app` to your Applications folder, and open it. On first launch macOS may show an "unidentified developer" warning — right-click the app and choose **Open** to bypass it.

On first launch you will be prompted to import adversary data — select your Daggerheart Core Rulebook PDF. The app extracts all stat block data from the PDF (takes about a minute) and stores it in `~/.daggerheart/`.

To re-import or update the data at any time: **File → Import Source…**

## Running from Source

**Requirements:** Python 3.10+, PySide6, pdfplumber

```bash
pip install -r requirements.txt
python main.py
```

On first run, import your PDF via **File → Import Source…** — or run `extract.py` directly:

```bash
python extract.py
```

This writes `adversaries.json` and `environments.json` to `datastore/`.

## Building Locally

**Requirements:** Python 3.10+, dependencies from `requirements.txt`, PyInstaller

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller daggerheart-encounter-builder.spec --noconfirm
```

**Windows output:** `dist\DaggerheartEncounterBuilder\DaggerheartEncounterBuilder.exe`

**Mac output:** `dist/DaggerheartEncounterBuilder.app`

On Windows you can also use the convenience script:

```powershell
.\build.ps1
```

## Releases

Builds for Windows and Mac are produced automatically by GitHub Actions when a version tag is pushed. To create a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds both platforms in parallel and publishes them as a GitHub Release with auto-generated release notes.

## Adding Sources

`sources.json` lists known PDF versions with their page ranges. If your PDF filename is not recognised on import, the app will prompt you to select from the list or enter custom page ranges manually.

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
