# Ubuntu fonts

These are the unmodified Ubuntu Sans and Ubuntu Sans Mono 1.006 variable fonts
from Ubuntu's `fonts-ubuntu` package `0.869+git20240321-0ubuntu1`.
Copyright 2011, 2022, 2023 Canonical Ltd. The Ubuntu Font Licence 1.0 is included
in `LICENCE.txt`; SHA-256 checksums are recorded in `SHA256SUMS`.

`make install` includes these assets in `/usr/local/share/simplewm/fonts`.
SimpleWM's existing style helper selects these exact files in the user's font
configuration while retaining other installed font families.

The session uses 104 DPI (`GDK_DPI_SCALE=104/96`), slight hinting and RGB
antialiasing. The default terminal font is Ubuntu Sans Mono 12, retaining the
text size of Ubuntu Sans Mono 13 at 96 DPI. These defaults arrive through an
ordinary `simpleupdate`; log out and back in to use the session DPI.
