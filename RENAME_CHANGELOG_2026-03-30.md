# Rename + Rewire Changelog (2026-03-30)

## Suggested Commit Title
rebrand apps by removing NTX names and rewire paths/runtime

## Suggested Commit Body
- rename Tool Library project folder to Tools and jaws Library
- rename style/spec/settings files to non-NTX names
- update Setup Manager cross-project discovery paths and EXE candidates
- rename runtime/server/env identifiers to non-NTX names
- add one-release compatibility for legacy marker/runtime/env values
- refresh i18n labels, splash text, docs, and build script outputs

## What Changed

### 1) Filesystem renames
- NTX Tool Library -> Tools and jaws Library
- Tools and jaws Library/ntx_tool_library.spec -> Tools and jaws Library/library.spec
- Setup Manager/ntx_tool_library.spec -> Setup Manager/setup_manager.spec
- Tools and jaws Library/ntx_tool_library_settings.json -> Tools and jaws Library/library_settings.json
- Setup Manager/ntx_tool_library_settings.json -> Setup Manager/library_settings.json
- Tools and jaws Library/styles/ntx_tool_library_style.qss -> Tools and jaws Library/styles/library_style.qss
- Setup Manager/styles/ntx_setup_manager_style.qss -> Setup Manager/styles/setup_manager_style.qss

### 2) Runtime/path rewiring
- Tool Library title/style/settings/runtime/server constants updated in Tools and jaws Library/config.py
- Setup Manager sibling project/install paths and EXE candidates updated in Setup Manager/config.py
- Shared runtime location now uses Shared Runtime (with migration fallback from NTX Shared Runtime)

### 3) Launch/build script updates
- build.bat now uses Setup Manager/setup_manager.spec
- run.bat and Setup Manager/run.cmd now use .library_ready marker
- compatibility migration from .ntx_ready -> .library_ready added

### 4) One-release compatibility shims
- config runtime preference migration from legacy NTX Shared Runtime to Shared Runtime
- Setup Manager relaunch env var supports both:
  - SETUP_MANAGER_VENV_RELAUNCHED
  - NTX_SETUP_MANAGER_VENV_RELAUNCHED
- .gitignore includes both .library_ready and .ntx_ready markers for transition

### 5) UI/i18n/docs refresh
- loading text and window title switched to Tools and jaws Library
- setup card temp folder renamed to setup_cards
- docs and metadata updated to reflect new names and paths

## Validation Performed
- py_compile passed for key entry/config files
- cross-launch wiring constants validated by importing both config modules
- launcher scripts invoked successfully with no shell/runtime errors
- diagnostics check returned no errors for edited files

## Notes
- Legacy NTX references remain only in intentional compatibility fallback lines.
- Existing unrelated workspace changes were not modified or reverted.
