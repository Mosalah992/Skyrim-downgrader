# Skyrim Special Edition 1.6.1170 Downgrader

A Windows command-line tool that rolls **Skyrim Special Edition** back to version **1.6.1170** using Steam's official `download_depot` console commands.

It downloads the required files from Steam, copies them into the existing Skyrim installation, checks the installed executable version, and locks Steam's automatic updates.

## Before you start

- This tool is for the Steam version of Skyrim Special Edition (Steam App ID `489830`).
- Close Skyrim, the Skyrim launcher, SKSE, and mod managers before installing.
- Keep at least **20 GB of free space** on the drive where Steam is installed.
- The installation overwrites Skyrim files. Back up your game folder or note any local changes you want to keep.
- Do not use Steam's **Play** button after downgrading; start through SKSE or your mod manager instead.

## Quick start: use the ready-made EXE

1. Download [dist/skyrim-downgrade.exe](dist/skyrim-downgrade.exe) from this repository. On GitHub, choose **Download raw file** or download the repository ZIP and extract it.
2. Put `skyrim-downgrade.exe` in an easy-to-find folder, such as `Downloads\\Skyrim Downgrader`.
3. In that folder, right-click empty space and choose **Open in Terminal**.
4. Check that the tool finds Steam and Skyrim:

   ```powershell
   .\skyrim-downgrade.exe status
   ```

5. Start the complete downgrade:

   ```powershell
   .\skyrim-downgrade.exe run
   ```

6. Answer the prompts. The tool downloads the depots, copies the files, and locks updates when finished.

If Windows SmartScreen appears, inspect the repository/source first, then choose **More info** → **Run anyway** only if you trust the downloaded file.

## What the tool downloads

The application uses these exact Steam commands, in disk → core → executable order:

```text
download_depot 489830 489831 8442952117333549665
download_depot 489830 489832 8042843504692938467
download_depot 489830 489833 1914580699073641964
```

Steam may take a while to fetch the files. Leave Steam running and do not close the terminal while a depot is downloading.

## If Steam does not accept an automated command

The tool opens Steam's Console page and normally types the command itself. If Steam does not acknowledge it, the tool copies the exact command to your clipboard and displays it in the terminal.

1. Click Steam's **CONSOLE** tab.
2. Click the command field at the bottom.
3. Paste the displayed command and press Enter.
4. Leave the tool open; it watches Steam's console log and continues automatically after the depot completes.

## Useful commands

Run these from the folder containing `skyrim-downgrade.exe`.

| Command | Purpose |
| --- | --- |
| `.\skyrim-downgrade.exe run` | Download, install, and lock updates. |
| `.\skyrim-downgrade.exe status` | Show detected Steam/game paths, depot state, and `SkyrimSE.exe` version. |
| `.\skyrim-downgrade.exe download` | Only download the required Steam depots. |
| `.\skyrim-downgrade.exe install` | Copy previously downloaded depot files into Skyrim. |
| `.\skyrim-downgrade.exe lock-updates` | Lock Steam auto-updates again. |
| `.\skyrim-downgrade.exe unlock-updates` | Undo the update lock. |
| `.\skyrim-downgrade.exe fix-crash` | Rename `ContentCatalog.txt` if Skyrim crashes immediately after launch. |

Add `-y` to accept all confirmation prompts, for example:

```powershell
.\skyrim-downgrade.exe -y run
```

## Confirming success

Run:

```powershell
.\skyrim-downgrade.exe status
```

The output should show:

```text
SkyrimSE.exe  1.6.1170.0  (target 1.6.1170)
AutoUpdateBehavior  1 (only on launch)
appmanifest read-only  True
```

Also set Steam manually to **Library → Skyrim Special Edition → Properties → Updates → Only update this game when I launch it**. Launch through SKSE or your mod manager to avoid Steam update checks.
