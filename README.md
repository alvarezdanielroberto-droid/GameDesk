# GameDesk

A game launcher for the **Windows 11** desktop. It shows 9:16 game covers on top of your wallpaper; hover over one and it expands with a quick animation, click it and the game starts.

<!-- Add a screenshot or GIF of the animation here:
![GameDesk](docs/demo.gif)
-->

## Features

- **Collapsed / expanded:** each cover is shown at half size and grows with a short animation when you hover over it.
- **Two images per game:** the collapsed one defaults to the `.exe` icon (or an image of your own); the expanded one is a custom large image.
- **Click to play:** launches `.exe`, `.lnk`, `.url` or `.bat` files (for example, Steam shortcuts).
- **Move by hand:** hold the click on a cover and drag it.
- **Arrange:** top center, screen center or bottom center, in aligned rows.
- **Adjustable sizes:** expanded size (220, 340 or 510 px wide) and collapsed ratio (40, 50 or 60 %).
- **Start with Windows** (optional) from the menu.
- Empty areas are transparent: clicks pass through to the desktop, so your desktop icons keep working.

## Installation

### Option 1: executable (no Python needed)

1. Go to the **Releases** section of this repository.
2. Download `GameDesk.exe` and run it.

> The executable is not code-signed, so Windows SmartScreen may show a warning. Click "More info" > "Run anyway", or build it yourself (option 3).

### Option 2: run from source

Requires [Python 3.9+](https://www.python.org/downloads/) with tcl/tk (enabled by default in the official installer).

```
pip install -r requirements.txt
python gamedesk.py
```

### Option 3: build your own `.exe`

With Python installed, double-click `build_exe.bat`. It installs the dependencies and creates `GameDesk.exe` in the same folder.

## Usage

| Action | How |
|---|---|
| Add a game | Click the **+** button (you pick the executable, the name and the large image) |
| Launch a game | Click its cover |
| Move a cover | Hold the click and drag |
| Change images, executable or name; remove a game | Right-click the cover |
| Arrange, change sizes, start with Windows, quit | Right-click (menu) |

Tips:

- Use high-resolution images for the large cover; they are automatically cropped to 9:16.
- The collapsed icon is extracted from the `.exe`. Shortcuts (`.lnk`, `.url`) have no icon to extract: pick a small image from the menu instead.
- Moving a cover by hand switches the layout to free mode. Choose an **Arrange** option again whenever you want to realign everything.

## Data and uninstalling

Settings and images are stored in `%APPDATA%\GameDesk`. To uninstall:

1. Turn off **Start with Windows** in the menu and choose **Quit GameDesk**.
2. Delete `GameDesk.exe` and the `%APPDATA%\GameDesk` folder.

## Known limitations

- The covers are a transparent window kept behind all other windows, not real desktop icons, so **Win + D** (show desktop) may hide them.
- Only the primary monitor is used.
- If a game requires administrator rights, Windows will show its usual prompt when launching it.
- The interface is in English only for now.

## Contributing

Issues and pull requests are welcome. Ideas for later: snapping covers to a grid, showing the game name, multi-monitor support, a Spanish translation.

## License

[MIT](LICENSE). Images and game names belong to their respective owners; this repository does not include any game covers.
