# Passermark 1.10.7

PDF-megjelenítő, nyomtatóeszköz és nyomdai előkészítési szerszámosládája **Linuxra és Windowsra**. Szabad
szoftver (GPL-3.0-or-later).

**English:** [README.md](README.md) · [Deutsch](README.de.md) · **Magyar** · [Français](README.fr.md) · [Español](README.es.md)

> **Állapot:** egy magánprojekt, a napi nyomdai előkészítési munka mellett fejlesztve. Észrevételeket
> szívesen fogadok – a válaszok és az új funkciók garancia nélkül érkeznek. CUPS- és Windows-illesztőprogramokkal
> tesztelve (tintasugaras, irodai és termelési nyomtatók finisherrel, nyomtatószerveren keresztül); a
> ritkább illesztőprogramok és finisher-beállítások módosítást igényelhetnek.

## Funkciók

- **Megjelenítés és nyomtatás**: PDF-ek, képek (HEIC, SVG is) és Office-fájlok (LibreOffice-on keresztül). A
  meglévő nyomtatóillesztőket használja (Linuxon CUPS, Windowson Windows-illesztők) minden beállításukkal.
- **Kiosztás (Ausschießen):** igazítás/skálázás, több lap egy ívre, plakátfelosztás, haszonminták (Nutzen);
  füzetek tűzött kötésként, csoportos ívekként vagy egymásra helyezett ívekként (ragasztott kötés), bundzug
  ( creep) üres lapokkal, hajtási-, passer- és flapjelölésekkel és íváttekintéssel. Parancssorból is
  (`passermark-cli impose`).
- **Dokumentummanipuláció:** CMYK-átalakítás színelőnézettel, formátumra vágás, objektumok szétválasztása,
  **CutContour** vágóplotterekhez (kontúr, formák, túlnyúlás, belső vágások; formák méretezése és mozgatása
  fogantyúkkal).
- **Lapok felosztása:** felezés vagy rács külön lapokként – pl. terjedémesként exportált füzet; lapok
  kijelölése, jobb egérgomb → Felosztás. Veszteségmentes (semmi nem rasztereződik), a végformatum és a
  túlnyúlás figyelembe vételével.
- **Preflight:** megnyitáskor ellenőrzi a betűket, a rétegeket és az átlátszóságot; javítások: betűk beágyazása
  vagy helyettesítése (szabad, metrikailag kompatibilis betűk vagy letöltés a fontsource.org-ról), szöveg
  görbékké alakítása, rétegek rögzítése/eltávolítása, átlátszóság lapítása.
- **Szerkesztés:** szövegsorok és rétegek kiválasztása egérrel; szöveg, betű és méret változtatása; rétegek
  mozgatása, méretezése, elrejtése, eltávolítása vagy cseréje; visszavonás.
- Vonalzók és mérés: mm-vonalzók a nézet szélén; kezdő- és végpont kattintása a méréshez (a Shift
  vízszintes/függőleges/45°-os irányba illeszt), az eredmény az állapotsorban.
- **Változó adatok:** számozás (kezdet, lépés, számjegyek, ellenőrző számok, visszafelé, továbbszámolás),
  CSV-ből származó szöveg, QR-kódok, Code 128 és EAN-13 vektorként (csendes zónával); `{{…}}`
  helyőrzők a PDF-ben; dátum, lap, véletlenszám és további változók; több lap rekordonként (elől/hátul) és
  mezők páratlan/páros lapokon; kódnapló; haszonminták saját rekorddal mintánként (ívről ívre vagy vágás és
  pakolás). Parancssorból is (`passermark-cli vdp`).
- **Adatok rögzítése:** az adattáblázat közvetlenül a Passermarkban hozható létre – QR-névjegykárlya (vCard),
  WLAN-hozzáférés, e-mail, webcím, hívás, SMS, időpont, helyszín, Code 128, EAN-13 – megfelelő oszlopokkal,
  azonnali ellenőrzéssel és Excelből történő beszúrással; CSV-ként mentve és közvetlenül használható a változó
  adatokban. A más oszlopneveket tartalmazó saját CSV-fájlok (pl. Outlook-, Google-, Thunderbird-exportok)
  automatikusan hozzárendelésre kerülnek. Hét kész példa (Súgó → Példák lekérése).
- **Munkaterületek** (Megjelenítés és nyomtatás, Nyomdai előkészítés, Szerkesztés, Változó adatok,
  Automatizálás) saját eszközsorral.
- **Presetek** a CutContourhoz, CMYK/vágáshoz, nyomdai szerkezethez és változó adatokhoz – a parancssorral
  közösen.
- PDF-ek javítása/optimalizálása, PDF/A, jelszavas védelem (a nyomtatási párbeszédablak „Mentés PDF-ként”
  funkciójánál is), fájlok egyesítése, szöveg kijelölése és másolása.
- Nyelvek: magyar, német, angol, spanyol, francia.

## Telepítés

**Windows:** töltsd le a `Passermark-<verzió>-Setup.exe` fájlt a [Release-ek](../../releases) alól, és
futtasd. Minden benne van (Python, Qt, Ghostscript).

**Linux (bármely disztribúció):** töltsd le a `Passermark-<verzió>-x86_64.AppImage` fájlt a
[Release-ek](../../releases) alól, majd
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, rendszerTelepítés fájlkezelő-integrációval):**
```sh
sudo ./install.sh        # telepíti a függőségeket apt-tal, startmenü-bejegyzés, Nautilus-menü
sudo ./uninstall.sh      # ismételt eltávolítás (--dry-run előnézet, --purge a /etc/passermark mappát is eltávolítja)
```

Opcionális: LibreOffice (Office-fájlok), 7-Zip (ICC-profilok importálása archívumokból).

## Parancssor

Minden nehéz feladat felület nélkül is fut – szkriptekhez, teljes mappákhoz és automatizáláshoz:

```sh
passermark-cli list                                   # elérhető feladatok
passermark-cli settings cutcontour > sticker.json     # alapértelmezések = preset-sablon
passermark-cli cutcontour in.pdf aus.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour in.pdf aus.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour in.pdf aus.pdf --preset "Sticker rund"   # a programban mentett preset
passermark-cli presets                                # a programban mentett presetek
```

Feladatok: `cutcontour`, `separate`, `manip` (CMYK/vágás), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`; továbbá `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (adattáblázatok). Beágyazott
beállítások ponttal (`--set detect.tolerance=40`). A Ctrl+C tisztán megszakít (nincs félbeszúrt fájl).
Visszatérési értékek: 0 kész, 1 hiba, 2 hibás megadás, 130 megszakítva. A `--json-progress` a haladást és az
eredményt JSON-sorokként írja ki. A nagy feladatok több magot használnak; korlátozás a `PASSERMARK_WORKERS`
környezeti változóval (1 = nem párhuzamos).

Hol: Linux `install.sh` → `passermark-cli`; AppImage → `Passermark-*.AppImage --cli …`;
Windows → `passermark-cli.exe` a telepítési mappában (telepítési beállítás: felvétel a keresési útvonalba).
Útmutatók példákkal a programban: **Súgó → Parancssor – útmutató** és **Súgó → Változó adatok – útmutató**.

## Hibák naplózása

Hiba esetén a Passermark egy elküldhető naplófájlt ír (Súgó → Hibák naplóinak megnyitása):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Összeomlás után a
következő indítás a naplóra mutat. A hibátlan naplók kilépéskor törlődnek.

## Fordítás (Build)

Minden `main` ágra történt push GitHubon felépíti a Windows-telepítőt és a Linux-AppImage-ot
(**Actions**); mindkettőt `--selftest`-tel ellenőrzi. Egy `v*` címke (pl. `git tag v1.10.7 && git push origin
v1.10.7`) GitHub-Release-hez csatolja őket.

Helyben: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, Python 3.12 és Inno Setup 6
kell) vagy `./linux/build-appimage.sh` (Linux, a szükséges csomagok a szkript fejében).

Tesztek: `python3 tests/test_<név>.py` (nem kell tesztkeretrendszer).

## Licenc

GPL-3.0-or-later, lásd `LICENSE`. A Windows-telepítő és az AppImage tartalmazza a
[Ghostscript](https://ghostscript.com) programot (AGPL-3.0, Artifex Software).
