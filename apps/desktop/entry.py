"""PyInstaller entry point for the Windows EXE.

Kept trivial on purpose: all behaviour lives in
``services.desktop.boot`` so it stays unit-testable outside the bundle.
"""

from services.desktop.boot import main

if __name__ == "__main__":
    main()
