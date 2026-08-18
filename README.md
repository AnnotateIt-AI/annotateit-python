# AnnotateIt Python SDK and CLI

`annotateit-ai` is the typed Python SDK and command-line client for the local
AnnotateIt REST API. The project is currently alpha software and targets Python
3.10 or newer.

Three names are intentionally different:

| Purpose | Name |
| --- | --- |
| PyPI distribution | `annotateit-ai` |
| Python package | `annotateit_ai` |
| CLI command | `annotateit` |

The `annotateit` distribution name on PyPI is already owned by another project,
so installs and dependency declarations must use `annotateit-ai`.

## Install

After the first PyPI release, the recommended CLI installation will be:

```console
pipx install annotateit-ai
```

For use as a library:

```console
python -m pip install annotateit-ai
```

To install the current checkout instead:

### Windows PowerShell

```powershell
cd C:\repos\annotateit-python
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
annotateit --help
```

If PowerShell blocks the activation script, either adjust the execution policy
for the current process or call `.\.venv\Scripts\python.exe` directly.

### macOS zsh or bash

```bash
cd /path/to/annotateit-python
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
annotateit --help
```

Python 3.10 or newer is supported. CI exercises the minimum version and the
current stable Python 3.14 on Windows, macOS, and Ubuntu.

## Connect to AnnotateIt

The default endpoint is `http://127.0.0.1:8420/api/v1`. A bare port, host URL,
or complete `/api/v1` URL can be supplied through `ANNOTATEIT_URL` or `--url`.
Authenticated commands also need `ANNOTATEIT_TOKEN` or `--token`.

PowerShell:

```powershell
$env:ANNOTATEIT_URL = "8420"
$env:ANNOTATEIT_TOKEN = "replace-with-your-token"
annotateit doctor
annotateit projects list
```

macOS:

```bash
export ANNOTATEIT_URL="8420"
export ANNOTATEIT_TOKEN="replace-with-your-token"
annotateit doctor
annotateit projects list
```

Command-line values take precedence over environment variables. Avoid putting a
token directly on a shared machine's command line because it can be retained in
shell history or visible to other processes.

## CLI

Commands follow the resource layout of the API:

```console
annotateit status
annotateit product info
annotateit projects list
annotateit datasets list <project-id>
annotateit media list <project-id> <dataset-id>
annotateit annotations get <project-id> <dataset-id> <media-id>
annotateit versions list <project-id> <dataset-id>
annotateit split show <project-id> <dataset-id>
annotateit quality show <project-id> <dataset-id>
annotateit openapi show
```

Use `annotateit --help` or append `--help` to a command for its exact arguments.
The CLI also covers tracks, frame annotations, imports, exports, project
activity, split planning, and quality scans.

Useful global options are:

- `--url` and `--token` override the matching environment variables.
- `--json` emits machine-readable JSON.
- `--no-version-check` skips the API compatibility preflight when connecting to
  an older server.

Lists that expose server cursors are fetched across pages automatically. Use the
command-specific page-size and maximum-item options to cap large results.

Commands that delete or replace data require `--yes`. Downloads and generated
files refuse to replace an existing destination unless `--force` is present.
JSON request bodies accept `--from path.json`; use `--from -` to read UTF-8 JSON
from standard input. Downloads are written through a temporary file and moved
into place only after a successful response.

Examples:

```console
annotateit projects create --name "Road signs" --task-type Detection
annotateit media upload <project-id> <dataset-id> ./frame.jpg
annotateit export <project-id> <dataset-id> --format coco --out dataset-coco.zip
annotateit annotations replace <project-id> <dataset-id> <media-id> --from annotations.json --yes
annotateit openapi show --out annotateit-openapi.json
```

## Python SDK

The client can use the same environment variables as the CLI:

```python
from annotateit_ai import Client

with Client() as client:
    response = client.call("listProjects")
    print(response)
```

Typed resource helpers are also available on `client.projects`,
`client.datasets`, `client.media`, `client.annotations`, `client.tracks`,
`client.versions`, `client.splits`, `client.quality`, and `client.system`.

For explicit configuration:

```python
from annotateit_ai import Client

with Client("http://127.0.0.1:8420", "replace-with-your-token") as client:
    project = client.projects.get("project-id")
```

## Development and CI

Install the development tools with `python -m pip install -e ".[dev]"`.
The local preflight creates isolated temporary environments, runs the same
quality gates as CI, builds both distributions, checks their metadata, installs
the wheel, and smoke-tests the console entry point.

PowerShell:

```powershell
.\scripts\preflight.ps1
```

macOS or Linux:

```bash
bash scripts/preflight.sh
```

Pass a Python executable to select a version:

```powershell
.\scripts\preflight.ps1 -Python C:\Python310\python.exe
```

```bash
bash scripts/preflight.sh python3.10
```

GitHub Actions runs the same lint, formatting, strict type checking, tests,
package build, `twine check`, and wheel smoke test for Python 3.10 and 3.14 on
`windows-latest`, `macos-15`, and `ubuntu-latest`.

## License

License metadata is intentionally omitted until the repository owner selects a
license. Do not assume an open-source license from the package's public source.
