# Stand-ins for pywin32 (Linux only)

pywin32 installs only on Windows, so on Linux the offline tests could not even be collected
(issue #102). These modules stand in for it **only when it is not installed**:
`tests/conftest.py` and `tools/check_structure.py` put this folder on the import path only if
`pythoncom` cannot be found. On Windows, and in Windows CI, they are never used.

They do just enough for the code to import and for faked COM objects to work: `com_error`, the
`VT_*` numbers, a `VARIANT` that keeps its type and value, `pywintypes.error`. They talk to
nothing. A test that really needs Windows (named pipes, the COM message filter on a real thread,
Windows paths) is marked to skip off Windows, with the reason.
