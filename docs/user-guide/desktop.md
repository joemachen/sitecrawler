# Desktop app

The desktop app is the [web UI](serve.md) in its own window instead of a
browser tab. Everything works the same: crawl from the bar, browse the
tabs, open the detail pane, export CSV.

## The standalone exe (Windows)

`sitecrawler.exe` is one file with nothing to install: no Python, no uv.
Put it in a folder of its own and double-click it.

- **Crawls** you start are saved to a `crawls` folder next to the exe, one
  `.db` file per crawl, until you choose another folder (below).
- **To open a saved crawl**, drag its `.db` file onto `sitecrawler.exe`,
  or right-click the file, choose *Open with*, and pick the exe. It opens
  read-only, with the file name in the title bar.
- **Closing the window** quits the app and stops any crawl still running.
  A stopped crawl can be continued later from the command line (see
  [Crawling from the UI](serve.md#crawling-from-the-ui)).
- **Problems** (a file that is not a crawl, say) appear in a message box.
  Anything else the app prints goes to `sitecrawler.log` next to the exe.

The exe needs Microsoft Edge WebView2, which comes with Windows 11 and
current Windows 10. It takes a few seconds to start because it unpacks
itself on every launch. It is not code-signed, so on a machine that has
never seen it, Windows SmartScreen may warn: choose *More info*, then
*Run anyway*.

*Render JavaScript* is not available in the exe, because rendering needs
Playwright and a Chromium download. Use the command line for rendered
crawls (see [JavaScript rendering](render.md)), then open the `.db` in the
exe.

## Choosing where crawls are saved

Open **Settings**. The top line, **Save crawls to**, shows the folder new
crawls go to. Click **Browse…** to pick another one with the Windows folder
picker, or type a path and press Enter. The folder is created if it does
not exist yet.

The choice is remembered: the next time you open the app, crawls go to the
same folder. It is kept in `%APPDATA%\sitecrawler\settings.json`, outside
the exe's folder, so it survives moving, copying or rebuilding the exe.

Changing the folder only affects crawls you start afterwards. A crawl that
is running keeps writing to its file, and earlier crawls stay where they
are (open them by dragging the `.db` onto the exe, as above).

## Building the exe

From a checkout:

```bash
uv sync
uv run pyinstaller --noconfirm packaging/sitecrawler.spec
```

The exe is written to `dist/sitecrawler.exe`. The build takes about a
minute.

## From a checkout

```bash
uv run sitecrawler desktop
uv run sitecrawler desktop crawls/example.com-20261023-120000.db
```

| Option | Meaning |
| --- | --- |
| `desktop crawl.db` | Open a stored crawl read-only instead of starting empty |
| `--crawls-dir DIR` | Where crawls started from the window are written. Default: the folder last chosen in Settings, else `./crawls` |

The window needs pywebview. `uv sync` installs it with the dev tools; on
its own it is the `desktop` extra (`uv sync --extra desktop`).
