# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
"""Druck-Sitzung (Drucker, Optionen, Farbprofil, Layout) – ohne Qt, für Programm und Kommandozeile."""
from __future__ import annotations

from . import printers
from .layout import LayoutSettings


class Session:
    """User changes of this program session. NEVER saved.

        On the next start, the admin defaults from /etc are loaded again –
        that is the "reset on exit", crash-safe without cleanup.
        """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.printer: str | None = cfg.get("default_printer") or None
        self.layout = LayoutSettings.from_dict(cfg.get("layout"))
        self.values: dict[str, dict[str, str]] = {}       # drucker -> Optionen
        self.color: dict[str, tuple[str, str]] = {}       # drucker -> (profil-id, intent)
        self.material: dict[str, str] = {}                 # drucker -> Material-ID (Druckdialog)
        self.caps: dict[str, printers.PrinterCaps] = {}
        from .cmyk import ManipSettings
        self.manip = ManipSettings()          # Dokument-Manipulation (nur diese Sitzung)
        self.copies = 1
        self.collate = True
        self.subset = "all"
        self.reverse = False

    def caps_for(self, name: str, reload: bool = False) -> printers.PrinterCaps:
        if reload or name not in self.caps:
            self.caps[name] = printers.pdf_caps() if name == printers.PDF_TARGET else printers.load_caps(name)
            try:
                printers.apply_custom_sizes(self.caps[name])      # Sonderformate des Benutzers
            except Exception:
                pass
        return self.caps[name]

    def refresh_custom_sizes(self):
        sizes = printers.load_custom_sizes()
        for c in self.caps.values():
            printers.apply_custom_sizes(c, sizes)

    def values_for(self, name: str) -> dict[str, str]:
        if name not in self.values:
            caps = self.caps_for(name)
            vals = caps.defaults()
            admin = self.cfg.get("printers", {}).get(name, {}).get("options", {})
            for k, v in admin.items():
                opt = caps.options.get(k)
                if opt and not opt.installable and any(c.value == v for c in opt.choices):
                    vals[k] = v
            pc = self.cfg.get("printers", {}).get(name, {})
            if caps.backend == "win" and pc.get("devmode"):
                vals["__devmode__"] = pc["devmode"]          # Herstellereinstellungen (Finisher …)
            self.values[name] = vals
        return self.values[name]

    def color_for(self, name: str) -> tuple[str, str]:
        if name not in self.color:
            pc = self.cfg.get("printers", {}).get(name, {})
            self.color[name] = (pc.get("color_profile", ""), pc.get("intent", "relative"))
        return self.color[name]
