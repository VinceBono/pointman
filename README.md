# pointman

Let an AI agent see and operate apps on your Windows PC, with the limits set by you and not by the agent.

An agent connected to pointman reads a window the way a screen reader does (buttons, text boxes, labels) and
can press buttons and fill in text boxes. No screenshots, no mouse takeover. Out of the box it can touch
**nothing**: you name the apps it may read, and you separately switch on the right to act.

| Control | What it does |
|---|---|
| App allowlist | Only apps you list can be read. Other windows show up as `(not allowed)` with their titles hidden. |
| Read-only by default | Clicking and typing stay off until you set `allow_actions = true`. |
| Password boxes | Their contents are never returned, and the agent cannot type into them. |
| Kill switch | Create one file and every request is refused until you delete it. |
| Tamper-evident log | Every request, allowed or refused, is logged. Editing or deleting a line breaks the chain. |

Windows 10 or 11. It is an [MCP](https://modelcontextprotocol.io) server, so it works with Claude Desktop,
Claude Code and other MCP clients.

## Set it up

Needs [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/VinceBono/pointman
cd pointman
uv sync
copy pointman.example.toml pointman.toml   # then edit it
```

`pointman.toml`:

```toml
allowed_apps = ["notepad.exe"]   # executable names; everything else is invisible
allow_actions = false            # true lets the agent click and type in those apps
```

Add it to your MCP client. For Claude Code:

```powershell
claude mcp add pointman -- uv --directory C:\path\to\pointman run pointman serve --config C:\path\to\pointman\pointman.toml
```

## What the agent gets

| Tool | Needs | Returns |
|---|---|---|
| `list_windows` | nothing | Open windows with their app name; titles only for allowed apps |
| `read_window` | app allowed | The window's controls, one per line, each with a ref such as `e3` |
| `click` | app allowed + actions on | Presses the control with that ref |
| `set_text` | app allowed + actions on | Replaces a text box's contents; refuses password boxes |

```
powershell.exe 'Pointman Test Target'
e1 Edit 'Name' value=''
e2 Edit 'Secret' value=(password, hidden)
e3 Button 'Greet'
e4 Text 'waiting'
```

A refused request comes back as text starting with `DENIED:` and the reason, and is logged.

## Stop it, and check what it did

```powershell
New-Item $HOME\.pointman\STOP -Force     # refuse everything from now on
Remove-Item $HOME\.pointman\STOP         # resume
uv run pointman verify-audit --config pointman.toml
```

The log is `~/.pointman/audit.jsonl`: one line per request with the time, tool, app, target control and
outcome. Text the agent types is not logged, only its length.

## Limits

- **An allowed app is fully allowed.** If you allow a browser or a mail client with actions on, the agent can
  do anything you could do in it. There is no per-button rule and no confirmation step yet. Start read-only.
- **The limits bind the agent, not someone at your keyboard.** Anyone who can edit `pointman.toml` or the log
  file can change the rules or rebuild the log. The chain detects edits; it does not prevent them.
- **Text on screen can carry instructions.** A window the agent reads may contain text written to steer it.
  pointman limits what a steered agent can reach; it does not detect the steering.
- **Only apps that expose accessibility information work.** Games, some Electron and custom-drawn apps expose
  little or nothing. Controls that cannot be pressed through the accessibility interface return an error.
- **Typing works in plain text boxes only.** Document areas (Notepad, Word, rich text) can be read, up to the
  first 200 characters, but not typed into yet.
- **Tested on a small test window**, on Windows 11 and in CI, and read-only against Windows 11 Notepad.
  Not yet tried against other real applications or with actions switched on in one.

## Development

```powershell
uv run python -m unittest discover -s tests -v
python scripts/commitguard.py --all
```

The desktop tests open a small test window (`tests/fixture_app.ps1`) and drive it.

## License

MIT. See [LICENSE](LICENSE).
