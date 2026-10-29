# Sabbat Markdown Editor

[Español](README.ES.md) · English

A Flask + Waitress web application for editing Markdown documents, with a live preview, shared file management, recoverable deletion and previous versions. Access is protected with HTTP Basic authentication using Werkzeug password hashes.

The editor works directly with Markdown source. **It is not a WYSIWYG editor**: formatting buttons insert Markdown syntax, and the preview is read-only. This avoids converting rendered content back into Markdown when saving.

## Features

- Create, open, save, save as and rename `.md` / `.markdown` documents.
- Delete files from the document folder and recover them from the trash.
- Automatically preserve the previous content before overwriting a changed document.
- Restore an archived copy without overwriting an existing file.
- Detect save conflicts between browser tabs using file revisions.
- Import local documents, download the current text, and print the preview or save it as PDF through the browser.
- Formatting toolbar, literal search and replacement, light/dark themes and split/editor/preview views.
- Unsaved-change warnings, word/character/line counts and Ctrl+S / Cmd+S.
- Last-document recovery within the current tab using `sessionStorage`.
- Tables, task lists, strikethrough, footnotes, syntax highlighting, KaTeX formulas and Mermaid diagrams.
- Sanitized basic HTML, CSRF protection, filename validation and rejection of symbolic links.

All authorized users share the same documents, trash and version history. There are no per-user document permissions or real-time collaborative editing.

## Requirements

- Linux, preferably Debian or Ubuntu. File locking uses `fcntl`.
- Python **3.10 or later**, `pip` and `venv`.
- Dependencies from `requirements.txt`.
- A modern browser. JavaScript is required.
- Browser access to jsDelivr for KaTeX, Mermaid, syntax highlighting and their styles/fonts.
- HTTPS for access over an untrusted network, normally through an existing Nginx reverse proxy.

Basic Markdown rendering runs on the server. If CDN assets are unavailable, editing remains available but enhanced rendering may fall back to source text.

## Project layout

```text
markdown/
├── app.py
├── requirements.txt
├── README.md
├── README.ES.md
├── ejemplo.md
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
├── tests/
│   └── test_app.py
├── markdown_files/       # Created automatically: documents
└── instance/             # Created automatically: state and archive
```

Do not expose `instance/` as a static directory or commit it to a repository. Back up both data directories.

## Installation

Examples below use the Linux account **`sabbat`** and installation path **`/home/sabbat/markdown`**. Adjust both if needed. Run application commands as that account, not as root.

### 1. Install system dependencies and copy the application

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip unzip
mkdir -p ~/markdown
cd ~/markdown
```

Copy `app.py`, `requirements.txt`, `templates/` and `static/` into this directory. Also copy the documentation, example and tests if supplied. Keep your existing `markdown_files/` when upgrading.

### 2. Create a virtual environment

```bash
cd ~/markdown
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

### 3. Generate a password hash

No separate `hash_generator.py` is required. The following command prompts for a password without putting it in command-line arguments or shell history:

```bash
python -c 'from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass("Password: ")))' 
```

Copy the complete output, including its `$` characters. Store hashes, not plaintext passwords. Existing compatible Werkzeug hashes can be reused.

### 4. Configure the service environment

```bash
sudo install -d -m 750 /etc/markdown
sudo touch /etc/markdown/markdown.conf
sudo chown root:root /etc/markdown/markdown.conf
sudo chmod 600 /etc/markdown/markdown.conf
sudo nano /etc/markdown/markdown.conf
```

Example content; replace the placeholder with your full hash:

```ini
AUTH_USER_admin=PASTE_THE_COMPLETE_WERKZEUG_HASH_HERE
MARKDOWN_FOLDER=/home/sabbat/markdown/markdown_files
MARKDOWN_STATE=/home/sabbat/markdown/instance
HOST=127.0.0.1
PORT=3555
LOG_FILE=/var/log/markdown/markdown-editor.log
```

Add `AUTH_USER_editor1=...` for another user. The suffix is the login name, including its case. Without any configured users, all accesses are rejected.

This file is read by systemd: use `KEY=VALUE`, without `export`. Password hashes can be pasted unquoted here; `$` is not expanded as it would be by a shell. **Do not load this unquoted file with `source`.** In shell commands, quote hashes with single quotes. Restart the service after changing credentials.

`HOST=127.0.0.1` is suitable for a local reverse proxy or SSH tunnel. Keep the address required by your existing deployment; the application default is `0.0.0.0`.

## Running the application

### Manual test

The environment file above is not automatically read when running Python manually. In a terminal with the virtual environment activated:

```bash
cd ~/markdown
mkdir -p instance
export AUTH_USER_admin='PASTE_THE_COMPLETE_WERKZEUG_HASH_HERE'
export HOST=127.0.0.1
export LOG_FILE="$PWD/instance/markdown-editor.log"
python app.py
```

Access `http://127.0.0.1:3555` from the server or through an SSH tunnel. For a remote server, run this on your own computer:

```bash
ssh -L 3555:127.0.0.1:3555 sabbat@YOUR_SERVER
```

Then open `http://127.0.0.1:3555` locally. Stop the manual server before starting systemd on the same port.

### systemd service

If you already have a working service, adapt it instead of creating a second service on port 3555. The example service name is `markdown-editor.service`.

```bash
sudo nano /etc/systemd/system/markdown-editor.service
```

```ini
[Unit]
Description=Sabbat Markdown Editor
After=network.target

[Service]
Type=simple
User=sabbat
Group=www-data
WorkingDirectory=/home/sabbat/markdown
EnvironmentFile=/etc/markdown/markdown.conf
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/sabbat/markdown/venv/bin/python /home/sabbat/markdown/app.py
Restart=on-failure
RestartSec=5
UMask=0077
LogsDirectory=markdown
LogsDirectoryMode=0750
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

The service user needs write access to `markdown_files/` and `instance/`. `LogsDirectory=markdown` supplies a dedicated writable log directory; this also allows the application's rotating handler to create and rename backup logs. Making only a file in `/var/log` writable is insufficient for rotation if the parent directory is not writable.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now markdown-editor.service
sudo systemctl status markdown-editor.service
```

For an existing running service, explicitly restart it after configuration changes:

```bash
sudo systemctl restart markdown-editor.service
```

### Service management

```bash
sudo systemctl status markdown-editor.service
sudo journalctl -u markdown-editor.service -f
sudo systemctl restart markdown-editor.service
sudo systemctl stop markdown-editor.service
```

## Environment variables

| Variable | Application default | Meaning |
| --- | --- | --- |
| `AUTH_USER_name` | None | Werkzeug password hash for `name` |
| `MARKDOWN_FOLDER` | `markdown_files` beside `app.py` | Document directory |
| `MARKDOWN_STATE` | `instance` beside `app.py` | Key, locks and archived versions |
| `HOST` | `0.0.0.0` | Waitress listening address |
| `PORT` | `3555` | Waitress port |
| `LOG_FILE` | `/var/log/markdown-editor.log` | Rotating log file |
| `AUTHORIZED_IPS` | Empty | Optional comma-separated exact client IPs |

The service example intentionally overrides `HOST` and `LOG_FILE`. Use absolute data paths. With no IP list, any authenticated client IP is allowed. If opening the log file fails, the application reports this through stderr/journal. A rotation failure after opening the file needs a permissions fix.

## Editing and recovery

1. Select a document or create a new one.
2. Edit its source; the preview updates after a short delay.
3. Save with the button or Ctrl+S / Cmd+S. Use **Save as** to create another file.
4. Save changes before renaming or deleting a document.
5. Open **Trash / versions** to restore a deleted file or previous content. Choose another name if the destination exists.

The current interface uses Spanish labels, including **Guardar**, **Guardar como** and **Papelera / versiones**.

An archive is created only when overwriting different content or deleting an existing document. It is not a snapshot of every keystroke. Archives have no automatic expiration or permanent-delete button; monitor disk usage.

The tab's recovery draft is not server autosave. After reloading, use **Recuperar borrador** before opening another document. Only the last draft in that tab is retained, and closing the tab can discard it. Browser policy/storage limits may also prevent recovery.

On a save conflict, download your draft, reopen the server version and reconcile the changes. CSRF tokens expire after 12 hours; if prompted, download the draft before reloading.

## Markdown compatibility and limits

- Files: `.md` / `.markdown`, case-insensitive extensions; spaces and Unicode names are supported. No nested folders.
- Maximum document size: **2 MiB**. Larger files can appear in the list but cannot be opened or modified through the editor.
- Encoding: UTF-8 with/without BOM, or UTF-16 with BOM. Other encodings require conversion.
- Saves use UTF-8. The browser may normalize CRLF to LF, and BOMs are removed; byte-for-byte preservation is not guaranteed.
- Math: `$...$` inline and `$$...$$` blocks. `\(...\)` and `\[...\]` are not implemented.
- Diagrams: fenced code blocks with the language `mermaid`.
- Basic HTML is sanitized. Scripts, event handlers, iframes and arbitrary styles are not supported.
- Images require HTTPS URLs. There is no image upload or local attachment serving.
- Same-origin Markdown links open documents by their base filename; nested paths are not resolved.
- No MDX, arbitrary JavaScript components, Obsidian-specific syntax or universal plugin compatibility.
- CDN versions are explicit; a fully offline installation requires vendoring the assets and updating the template/CSP.

Import `ejemplo.md` to check the supported features in your browser. The supplied deployment targets the root of a host; serving under a URL prefix needs additional Flask/proxy configuration.

## Logging and optional Fail2Ban

The application logs authentication failures, including requests without credentials. The initial HTTP Basic challenge may therefore produce a failure entry even for a legitimate visitor. Choose thresholds accordingly.

The log handler rotates at approximately 1 MB and retains three backup files. With the service configuration above, the path is `/var/log/markdown/markdown-editor.log`.

### Reverse-proxy limitation

**The application records `request.remote_addr`; it does not automatically trust `X-Forwarded-For`.** Behind local Nginx, this is normally `127.0.0.1`, not the visitor's IP. Do not enable the direct-access jail below against such logs. Blocking the proxy would not identify the attacker and could disrupt access.

For Nginx deployments, use a separately reviewed proxy-log/authentication configuration or explicitly configure trusted-proxy handling after restricting backend access. An arbitrary `X-Forwarded-For` header is not proof of the client's identity. `AUTHORIZED_IPS` has the same proxy limitation.

### Direct-access jail example

Use this example only where logs contain the real client address and the protected network path actually uses port 3555. It is not the appropriate jail for requests arriving through HTTPS on port 443.

```bash
sudo apt install fail2ban
sudo nano /etc/fail2ban/filter.d/markdown-editor.conf
```

```ini
[Definition]
failregex = ^\s*- app - WARNING - Failed login attempt for user '\(redacted\)' from IP '<HOST>'\s*$
ignoreregex =
```

This filter matches the application's `app` logger after Fail2Ban removes the timestamp. Validate it against your actual log format:

```bash
sudo fail2ban-regex /var/log/markdown/markdown-editor.log /etc/fail2ban/filter.d/markdown-editor.conf
```

Then create `/etc/fail2ban/jail.d/markdown-editor.local`:

```ini
[markdown-editor]
enabled  = true
backend  = polling
port     = 3555
filter   = markdown-editor
logpath  = /var/log/markdown/markdown-editor.log
usedns   = no
maxretry = 10
findtime = 600
bantime  = 600
```

This example bans for 10 minutes after 10 matching failures within 10 minutes. Review the threshold and firewall action for your environment.

```bash
sudo fail2ban-client -t
sudo systemctl restart fail2ban
sudo fail2ban-client status markdown-editor
```

## Updating and backups

For documentation-only updates, replace `README.md` and `README.ES.md`; **no service restart is required**.

For application updates, stop the real service first and back up the installation:

```bash
sudo systemctl stop markdown-editor.service
cd ~
tar --exclude='markdown/venv' --exclude='markdown/.venv' \
    --exclude='markdown/__pycache__' \
    -czf "markdown-backup-$(date +%Y%m%d-%H%M%S).tar.gz" markdown
```

If using custom data paths, back those up separately. Also back up `/etc/markdown/markdown.conf` and your systemd unit with appropriate access restrictions.

Replace application files, preserve `markdown_files/` and `instance/`, install the updated requirements, then restart:

```bash
cd ~/markdown
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
sudo systemctl restart markdown-editor.service
```

Reload the browser with Ctrl+F5. Restore a backup if the update fails.

Archived content is stored in `instance/archive/<id>/content`, with its original filename and timestamp in `meta.json`. This enables manual recovery, but local archives do not replace external backups. File locks coordinate this application's processes sharing the same state directory; they do not coordinate unrelated external editors. Use a local filesystem.

## Tests and troubleshooting

From the project directory with its virtual environment active:

```bash
python -m pip install pytest
python -m pytest -q
```

The supplied backend suite covers authentication, CSRF, concurrent creation, save/rename conflicts, trash/version restoration, invalid paths, symbolic links, encodings, size limits and sanitized rendering.

| Symptom | Check |
| --- | --- |
| Login rejected | Full hash, exact username, loaded `AUTH_USER_*` variables, service restart |
| Files missing | `MARKDOWN_FOLDER`, actual data location and service-user permissions |
| HTTP 409 | Server content changed or destination already exists; recover/rename your draft |
| HTTP 403 while saving | Expired CSRF token or IP restriction; download draft before reloading |
| HTTP 413 | Document exceeds 2 MiB or request exceeds the proxy limit |
| Formula/diagram remains text | Syntax, CDN access and browser console |
| Log rotation error | Write permissions on the log directory, not only the file |
| Port already in use | Another manual process or service is listening on 3555 |

## Technical references

- [systemd service environment](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [Fail2Ban filter guidelines](https://github.com/fail2ban/fail2ban/blob/master/FILTERS)
- [Fail2Ban regex testing](https://github.com/fail2ban/fail2ban/blob/master/man/fail2ban-regex.1)
- [markdown-it-py security](https://markdown-it-py.readthedocs.io/en/latest/security.html)
- [Mermaid configuration](https://mermaid.js.org/config/usage)
- [KaTeX options](https://katex.org/docs/options)

