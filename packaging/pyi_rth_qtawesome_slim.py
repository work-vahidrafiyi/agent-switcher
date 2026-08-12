"""Limit frozen QtAwesome to the one icon family bundled by the spec file."""

import qtawesome


qtawesome._BUNDLED_FONTS = tuple(
    font for font in qtawesome._BUNDLED_FONTS if font[0] == "fa5s"
)
