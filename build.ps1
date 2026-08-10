# build.ps1
Write-Host "Building AirPrint Bridge with PyInstaller..."

# Verify PyInstaller is installed
if (-not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyInstaller..."
    pip install pyinstaller
}

# The win32timezone module is critically required for Windows services compiled by PyInstaller.
python -m PyInstaller --onefile `
    --windowed `
    --hidden-import win32timezone `
    --name "AirPrintBridge" `
    .\airprint_bridge.py

Write-Host "Build complete! Executable is in the \dist\ directory."
