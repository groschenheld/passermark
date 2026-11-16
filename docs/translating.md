# Translating Passermark

**English** · [Deutsch](#deutsch)

Passermark ships in German (the source language), English, Hungarian, Spanish and French. Anyone can add a
language or improve an existing one – no programming needed, a spreadsheet is enough.

## The quick way

1. Take the table [translations/passermark-texts.csv](translations/passermark-texts.csv) (or export a fresh one
   from the program, see below).
2. Open it in LibreOffice Calc or Excel. It has four columns:

   | Column | Content |
   |---|---|
   | `source_de` | the German text as it is in the program – **do not change** |
   | `english` | the English translation, as a help |
   | `translation` | **your translation** |
   | `note` | hints for this text (placeholders, shortcut letter) |

3. Fill in the column `translation`. You do not have to do everything at once: texts left empty simply stay as
   they are (in English for a new language).
4. Save it as CSV again (UTF-8, semicolon as separator – LibreOffice asks, Excel: "CSV UTF-8").
5. Try it yourself: **File → Settings → Language → Übersetzung einspielen …** (install translation), choose the
   file, enter the language code (`it`, `pl`, `pt_BR` …) and the name of the language in itself (`Italiano`).
   Pick it in the list, press OK and restart Passermark.
6. Send the file in: as an attachment to an issue on
   [GitHub](https://github.com/groschenheld/passermark/issues), with the language code and name.

To improve an existing language, export the table with that language selected (it then contains the current
translation) and change only what you want – installing it puts your corrections over the shipped texts.

## Rules for the texts

- **Placeholders** in braces must stay exactly as they are: `{0}`, `{1}`, `{name}`, `{0:.1f}`. Their order in
  the sentence may change: `Seite {0} von {1}` → `Page {0} of {1}`. Passermark refuses a translation in which a
  placeholder is missing or changed and names the text.
- Doubled braces such as `{{Spalte}}` are shown as they are (a placeholder of variable data); the word inside
  may be translated.
- `&` before a letter marks the shortcut letter in menus (`&Datei` → `&File`); put it before a fitting letter of
  your word. `&&` shows a single `&`.
- Keep line breaks inside a text where they are.
- `…` at the end means "opens a window" – keep it.
- Keep it short: buttons and menus have little room. If a text needs context, look at the program or ask in
  the issue.

## Exporting and checking

In the program: **File → Settings → Language**

- **Übersetzungsvorlage exportieren …** (export template) – all current texts as CSV or JSON. If a language is
  selected in the list, its current translation is filled in.
- **Übersetzung einspielen …** (install translation) – checks the file and installs it for your user only.
- **Entfernen** (remove) – removes an installed translation again.

On the command line:

```sh
passermark-cli lang list                          # languages, shipped and installed
passermark-cli lang export it.csv                 # empty template (also .json)
passermark-cli lang export hu.csv --code hu       # template with the current Hungarian translation
passermark-cli lang check it.csv                  # coverage, missing texts, broken placeholders
passermark-cli lang install it.csv --code it --name Italiano
passermark-cli lang remove it
```

The JSON form is for translation tools:

```json
{"format": "passermark-translation", "language": "it", "name": "Italiano", "program": "1.19.6",
 "messages": {"<German source text>": "<translation>"}, "english": {"<German source text>": "<English>"}}
```

## For the maintainer: taking a translation into the program

```sh
passermark-cli lang import it.csv --code it --name Italiano     # writes pdfdruck/lang/it.py
```

The command checks the file and writes the catalog in the same layout as the existing ones. For a new language
it lists the places that need the code as well: `l10n.LANGS`, the language check in `cfgvalidate.py`, `LANGS` in
`tests/test_l10n.py` and in both `passermark.spec`. Then regenerate the table in this folder:
`passermark-cli lang export docs/translations/passermark-texts.csv` (the tests check that it is current).

Installed translations live next to the user settings in `lang/<code>.json`
(Linux `~/.config/passermark/lang`, Windows `%APPDATA%\Passermark\lang`). For a shipped language they complete
or correct it; texts they lack come from the shipped translation, for a new language from English.

---

## Deutsch

Passermark gibt es auf Deutsch (Ausgangssprache), Englisch, Ungarisch, Spanisch und Französisch. Neue Sprachen
und Verbesserungen kann jeder beitragen – eine Tabellenkalkulation reicht.

1. Tabelle [translations/passermark-texts.csv](translations/passermark-texts.csv) nehmen oder im Programm unter
   **Datei → Einstellungen → Sprache → Übersetzungsvorlage exportieren …** neu erzeugen.
2. In LibreOffice Calc oder Excel öffnen. `source_de` ist der deutsche Text (nicht ändern), `english` die
   englische Fassung als Hilfe, in `translation` kommt die Übersetzung, `note` gibt Hinweise.
3. Leere Zeilen sind erlaubt – diese Texte bleiben wie bisher.
4. Als CSV speichern (UTF-8, Semikolon).
5. Selbst ausprobieren: **Übersetzung einspielen …**, Sprachkürzel (`it`) und Namen der Sprache (`Italiano`)
   eingeben, in der Liste wählen, OK, Passermark neu starten.
6. Datei als Anhang an ein Issue auf GitHub schicken.

Platzhalter wie `{0}` oder `{name}` müssen unverändert bleiben (Reihenfolge im Satz darf sich ändern), `&` vor
einem Buchstaben markiert das Kürzel im Menü, `…` am Ende heißt „öffnet ein Fenster“. Passermark lehnt eine
Datei mit kaputten Platzhaltern ab und nennt die Texte.
