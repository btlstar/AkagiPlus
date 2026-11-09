# Build tools

Run scripts from the repository root.

- `dev.ps1`: starts the source application and frontend; used by `start.bat`.
- `build-release.ps1`: builds the embedded frontend and Windows executable, then creates a portable archive.
- `package-windows.py`: packages a prebuilt executable, plugins, fresh defaults, licenses and pinned runtime using an allowlist.
- `setup-protoc.py`: prepares the pinned Protocol Buffers compiler.
- `fetch-runtime.sh`: fetches portable Python and uv runtimes for source builds.

Runtime versions and hashes are in `packaging/runtime-lock.json`. Python package versions are in `release-requirements.txt`. Store local runtime files under the ignored `runtime` directory.

Protocol extraction and code-generation helpers maintain the supported protocol files; their command-line help describes required inputs. Game assets and generated local inspection output do not belong in published source.
