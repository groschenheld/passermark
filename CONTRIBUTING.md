# Contributing / Mitmachen

**English** · [Deutsch](#deutsch)

Passermark is a private project, developed alongside daily prepress work. Feedback is very welcome – please
understand that answers and new features come without any guarantee.

## Reporting a bug

Open an issue with the **Bug report** form. It asks for what is needed to reproduce the problem:

- Passermark version (title bar) and how it was installed (Windows setup, AppImage, `install.sh`),
- operating system,
- printer and driver (for print problems: CUPS queue/PPD, IPP driverless or Windows driver; print server?),
- steps, expected and actual result,
- the error log, if there is one (**Help → Open error logs**),
- if possible a PDF that shows the problem. Please remove or replace confidential content first.

**Security problems** are not reported in public issues – see [SECURITY.md](SECURITY.md).

## Suggesting a feature

Use the **Feature request** form and describe the job you want to get done (e.g. "a customer sends 100 business
cards as one PDF …") rather than only the button you imagine. That helps to find a solution that fits.

## Pull requests

Please **open an issue first and wait for a reply** before writing code. Unannounced pull requests may be closed
without review – not because they are bad, but because I can only maintain what fits the overall plan.

If we agree on a change:

- one topic per pull request, small is better,
- Python 3.10 compatible, no new dependencies without discussing them,
- tests: add or adapt `tests/test_<name>.py` and run them (`python3 tests/test_<name>.py`),
- user-visible texts go through `tr("…")` (German source text) – translations are added afterwards,
- by submitting a pull request you agree that your contribution is licensed under GPL-3.0-or-later.

## Translations

The program is available in German, English, Hungarian, Spanish and French. Corrections to existing translations
are welcome as an issue (screenshot + better wording).

---

## Deutsch

Passermark ist ein privates Projekt, entwickelt neben der täglichen Arbeit in der Druckvorstufe. Rückmeldungen
sind sehr willkommen – bitte hab Verständnis, dass Antworten und neue Funktionen ohne Garantie kommen.

### Fehler melden

Ein Issue mit dem Formular **Fehler melden / Bug report** öffnen. Es fragt ab, was zum Nachstellen nötig ist:

- Passermark-Version (Titelleiste) und wie installiert (Windows-Setup, AppImage, `install.sh`),
- Betriebssystem,
- Drucker und Treiber (bei Druckproblemen: CUPS-Warteschlange/PPD, IPP ohne Treiber oder Windows-Treiber;
  Druckserver?),
- Schritte, erwartetes und tatsächliches Ergebnis,
- das Fehlerprotokoll, falls vorhanden (**Hilfe → Fehlerprotokolle öffnen**),
- wenn möglich ein PDF, das den Fehler zeigt. Vertrauliche Inhalte bitte vorher entfernen oder ersetzen.

**Sicherheitsprobleme** bitte nicht in öffentlichen Issues melden – siehe [SECURITY.md](SECURITY.md).

### Funktion vorschlagen

Das Formular **Funktion vorschlagen / Feature request** verwenden und die Aufgabe beschreiben, die erledigt werden
soll (z. B. „ein Kunde schickt 100 Visitenkarten als ein PDF …“) – nicht nur den Knopf, den du dir vorstellst.
So findet sich eher eine Lösung, die passt.

### Pull Requests

Bitte **zuerst ein Issue öffnen und auf eine Antwort warten**, bevor du Code schreibst. Unangekündigte Pull
Requests werden eventuell ohne Prüfung geschlossen – nicht weil sie schlecht sind, sondern weil ich nur pflegen
kann, was in den Gesamtplan passt.

Wenn wir uns auf eine Änderung einigen:

- ein Thema je Pull Request, klein ist besser,
- kompatibel mit Python 3.10, keine neuen Abhängigkeiten ohne Absprache,
- Tests: `tests/test_<name>.py` ergänzen oder anpassen und ausführen (`python3 tests/test_<name>.py`),
- sichtbare Texte über `tr("…")` (deutscher Ausgangstext) – Übersetzungen kommen danach dazu,
- mit einem Pull Request stimmst du zu, dass dein Beitrag unter GPL-3.0-or-later steht.

### Übersetzungen

Das Programm gibt es auf Deutsch, Englisch, Ungarisch, Spanisch und Französisch. Verbesserungen bestehender
Übersetzungen gern als Issue (Bildschirmfoto + bessere Formulierung).
