# Passermark 1.18.8

PDF-megjelenítő, nyomtatóeszköz és nyomdai előkészítési szerszámosládája **Linuxra és Windowsra**. Szabad
szoftver (GPL-3.0-or-later).

**English:** [README.md](README.md) · [Deutsch](README.de.md) · **Magyar** · [Français](README.fr.md) · [Español](README.es.md)

> **Állapot:** egy magánprojekt, a napi nyomdai előkészítési munka mellett fejlesztve. Észrevételeket
> szívesen fogadok – a válaszok és az új funkciók garancia nélkül érkeznek. CUPS- és Windows-illesztőprogramokkal
> tesztelve (intasugaras, irodai és termelési nyomtatók finisherrel, nyomtatószerveren keresztül); a
> ritkább illesztőprogramok és finisher-beállítások módosítást igényelhetnek.
>
> **Tesztkörnyezet:** a teszteléshez egy virtuális géppark fut – kilenc szimulált nyomtató (Canon, Xerox, Epson,
> Roland, GBC), befejezőfunkciókkal és nyomtatásonkénti PDF- és naplókimenettel:
> [Virtual-Printer-Machine-Fleet](https://github.com/groschenheld/Virtual-Printer-Machine-Fleet).
> Claude építette, és a tesztjeimhez eddig elegendő volt – a fejlesztési javaslatokat szívesen fogadom.

## Képernyőképek

| | |
|---|---|
| ![Dokumentum-ellenőrzés figyelmeztetésekkel és megjegyzésekkel](docs/screenshots/preflight_example.jpg) | ![CMYK-átalakítás színelőnézettel](docs/screenshots/cmyk_adjustment_example.png) |
| ![Nutzen (step & repeat)](docs/screenshots/step_and_repeat_example.png) | ![CutContour vágóplotterekhez](docs/screenshots/cut_contour_example.png) |
| ![Kivágás](docs/screenshots/trim_example.png) | ![Változó adatok](docs/screenshots/variable_data_example.png) |

## Funkciók

- **Megjelenítés és nyomtatás**: PDF-ek, képek (HEIC, SVG is) és Office-fájlok (LibreOffice-on keresztül). A
  meglévő nyomtatóillesztőket használja (Linuxon CUPS, Windowson Windows-illesztők) minden beállításukkal.
- **Kiosztás (Ausschießen):** igazítás/skálázás, több lap egy ívre, plakátfelosztás, haszonminták (Nutzen);
- **Plan & Poster:** tervnyomtatás és poszternyomtatás tekercses eszközökön – tekercsek kiolvasása az eszközből (IPP, egyébként SNMP), „Eszköz ellenőrzése” csak olvasva JSON-jelentéssel; tekercsválasztás automatikusan (a legkeskenyebb megfelelő, grammage/anyag szerint) vagy rögzítve, elhelyezés középen vagy a szélen; folyóméter élőben figyelmeztetéssel, ha a tekercs elfogy; tev-eszközök (skálázás, forgatás, túltöltősáv, vágójelek, hajszálvonalak kiemelése, hajtási jelek DIN 824 szerint), posztereszközök (szegély, szemkarika-jelek, CutContour, passerjelölések print & cut-hoz a Rolandon), a tekercsnél szélesebb sávokra bontva; anyagok felhasználónként – a betöltött tekercsek médiái automatikusan szerepelnek a listában („(eszköz)” jelöléssel), és pontosan azt a tekercset választják; IPP-n a médiakatalógus is kiolvasásra kerül, így a létrehozott, de be nem töltött médiák „(eszköz, nincs betöltve)” jelöléssel szerepelnek a listában, és médiatípusukkal mennek az illesztőhöz Beállítások tervenként: egyes tervek vagy poszterek kijelölésével az anyag, tekercs, elhelyezés, forgatás, nyomtatási terület, margó, méretezés (százalékban vagy „rövidebb/hosszabb él … mm-re”) és túltöltősáv csak a kijelölésre érvényes – az eltéréseket a lista ✎ jelzéssel mutatja. Küldésnél az „egy munka, példányonként egy ív” az alapértelmezés választható példányonkénti saját munka vagy példányszám; a lista alatt minden nyomtatott ív kicsiben renderelve, mérettel, tekercsel és vágásszámmal. Parancssorból is (`passermark-cli plan`/`poster`, a `--dry-run` csak folyómétert számol, `--copies-mode sheets|jobs|count`, `overrides` oldalszám szerint), munkafolyamat-lépésként és bedobómappa-kimenetként, pl. VersaWorkshoz; a nyomtatási napló eltárolja az eltéréseket, az újranyomtatásnál helyénvalóak maradnak.
  ( creep) üres lapokkal, hajtási-, passer- és flapjelölésekkel és íváttekintéssel. Parancssorból is
  (`passermark-cli impose`). A haszonminták másodszor is szabadon választott célformátumra helyezhetők (2. lépés) – most közvetlen nyomtatásnál, a nyomtatási párbeszédablakból is.
- **Plan & Poster:** tervnyomtatás és poszternyomtatás tekercses eszközökön – tekercsek kiolvasása az eszközből (IPP, egyébként SNMP), „Eszköz ellenőrzése” csak olvasva JSON-jelentéssel; tekercsválasztás automatikusan (a legkeskenyebb megfelelő, grammage/anyag szerint) vagy rögzítve, elhelyezés középen vagy a szélen; folyóméter élőben figyelmeztetéssel, ha a tekercs elfogy, az „Egyenként levágás” minden példányt saját munkává tesz; tev-eszközök (skálázás, forgatás, túltöltősáv, vágójelek, hajszálvonalak kiemelése, hajtási jelek DIN 824 szerint), posztereszközök (szegély, szemkarika-jelek, CutContour, passerjelölések print & cut-hoz a Rolandon), a tekercsnél szélesebb sávokra bontva; anyagok felhasználónként. Parancssorból is (`passermark-cli plan`/`poster`, a `--dry-run` csak folyómétert számol), munkafolyamat-lépésként és bedobómappa-kimenetként, pl. VersaWorkshoz.
- **Dokumentummanipuláció:** CMYK-átalakítás színelőnézettel, formátumra vágás, objektumok szétválasztása,
  **CutContour** vágóplotterekhez (kontúr, formák, túlnyúlás, belső vágások; formák méretezése és mozgatása
  fogantyúkkal). A vágás most már „szélek levágásával” (mm oldalonként, célformátum nélkül) és „fehér tér
  eltávolításával” (tartalom felismerése, új lapkeret ± margó, a tartalom 1:1 marad) is.
- **Lapok felosztása:** felezés vagy rács külön lapokként – pl. terjedémesként exportált füzet; lapok
  kijelölése, jobb egérgomb → Felosztás. Veszteségmentes (semmi nem rasztereződik), a végformatum és a
  túlnyúlás figyelembe vételével.
- **Preflight:** megnyitáskor ellenőrzi a betűket, a rétegeket, az átlátszóságot, az oldalkereteket (Crop-/Trim-/Bleed-Box), a tartalom levágását, a védelmet, a PDF/X-et és az output intentet, az űrlapmezőket és az üres oldalakat; javítások: betűk beágyazása
  vagy helyettesítése (szabad, metrikailag kompatibilis betűk vagy letöltés a fontsource.org-ról), szöveg
  görbékké alakítása, rétegek rögzítése/eltávolítása, átlátszóság lapítása. Minden lelet megnevezi a helyét (pl. „2. oldal – jobb alul, 40 × 20 mm”); egy kattintás odébb ugrik, és piros kerettel jelöli, a ◀ ▶ gombokkal végigmehetsz a leleteken.
- **Szerkesztés:** szövegsorok és rétegek kiválasztása egérrel; szöveg, betű és méret változtatása; rétegek
  mozgatása, méretezése, elrejtése, eltávolítása vagy cseréje; visszavonás.
- Vonalzók és mérés: mm-vonalzók a nézet szélén; kezdő- és végpont kattintása a méréshez (a Shift
  vízszintes/függőleges/45°-os irányba illeszt), az eredmény az állapotsorban. Control lenyomva a célkereszt mágnesesen illeszkedik a vágó- és belső vonalakhoz (oldalszél,
  vágott formátum, vérzés), képszélekhez és vektorvonalakhoz – szövegre soha; addig tapad az élhez,
  amíg az egér határozottan el nem húzza. A vágott-formátum-megjelenítés zölddel mutatja a vágott formátumot, pontvonallal a vértést.
- **Változó adatok:** számozás (kezdet, lépés, számjegyek, ellenőrző számok, visszafelé, továbbszámolás),
  CSV-ből származó szöveg, QR-kódok, Code 128 és EAN-13 vektorként (csendes zónával); `{{…}}`
  helyőrzők a PDF-ben; dátum, lap, véletlenszám és további változók; több lap rekordonként (elől/hátul) és
  mezők páratlan/páros lapokon; kódnapló; haszonminták saját rekorddal mintánként (ívről ívre vagy vágás és
  pakolás); **ablakok (oldalcsoportok)** több oldalas sablonokhoz – pl. elölap a névvel, hátlap QR-kóddal – ablakonkénti oldalkiválasztással (minden/páratlan/páros oldal vagy tartomány) és rekord-elosztással lapról lapra vagy oldalról oldalra. Parancssorból is (`passermark-cli vdp`).
- **Adatok rögzítése:** az adattáblázat közvetlenül a Passermarkban hozható létre – QR-névjegykárlya (vCard),
  WLAN-hozzáférés, e-mail, webcím, hívás, SMS, időpont, helyszín, Code 128, EAN-13 – megfelelő oszlopokkal,
  azonnali ellenőrzéssel és Excelből történő beszúrással; CSV-ként mentve és közvetlenül használható a változó
  adatokban. A más oszlopneveket tartalmazó saját CSV-fájlok (pl. Outlook-, Google-, Thunderbird-exportok)
  automatikusan hozzárendelésre kerülnek. Hét kész példa (Súgó → Példák lekérése).
- **Munkaterületek** (Megjelenítés és nyomtatás, Plan & Poster, Nyomdai előkészítés, Szerkesztés, Változó adatok,
  Automatizálás) saját eszközsorral.
- **Presetek** a CutContourhoz, CMYK/vágáshoz, nyomdai szerkezethez és változó adatokhoz – a parancssorral
  közösen.
- **Nyomtatási napló:** felhasználónként a beállításokban, vagy adminként kikényszerítve – minden munkához egy JSON a pontos beállításokkal és a példányonkénti elküldött oldalakkal (`out_pages`), mellé egy `printlog.csv`; a `passermark-cli reprint <log.json>` bármikor újranyomtatja a munkát (figyelmeztet, ha az eredeti időközben megváltozott).
- **Automatizálás:** lépésenkénti munkafolyamatok feltételekkel („if” minden lépésen, „choose”/„else” elágazások, „fail”/„stop” üzenettel); a `passermark-cli serve` figyeli a mappákat, és minden fájlt átküld a hozzárendelt munkafolyamaton – a `serve --init` sablont hoz létre példával.
- **Közös nyomtatási mappa:** egy bedobómappa mindenki számára – beállítása a Felügyelet → Általános → „Közös nyomtatási mappa beállítása …” gombbal, az install.sh-val vagy a `passermark-cli shared-folder` paranccsal; egyetlen root-segéd hozza létre a csoportot és a mappát (root:passermark, 2775, alapértelmezett ACL, a felhasználók a csoportba kerülnek, a szimbolikus linkeket elutasítja); Windowson a `hotfolder`, `ausgabe` és `archiv` almappák Módosítás jogot kapnak a felhasználóknak – a ProgramData többi része az adminoknak marad fenntartva.
- **Softproof:** a nyomtatási eredmény szimulálása a nézetben (Ctrl+Y) – nyomtatási feltételként anyag, a felügyeletből származó profil vagy rendszerbeli CMYK-profil, intenttel és BPC-vel; papírszín és fekete nyomtatási szín szimulálása, figyelmeztetés a nyomtatható színtartományon kívüli színekre és a határérték feletti festékmennyiségre %-ban.
- **Anyagok:** papírok nyilvántartása (grammage, felület, render intent, profil nyomtatónként); papírfehér mérése ArgyllCMS-szel (spotread), CGATS-mérőfájlból vagy kézzel; profiljavaslatok ΔE2000 szerint. Az anyagok profilt és intentet állítanak be a nyomtatási párbeszédablakban és a CMYK-átalakításban, a szín-előnézet a mért papírfehérjet veszi alapul.
- **Színellenőrzés:** az új Szín menüben (Ctrl+Shift+F) – oldalsáv, mint a preflight: nyomtatási feltétel kiválasztása, a Passermark megmutatja, mi van a dokumentumban (RGB, festékmennyiség, direkt színek, output intent), és a leleteket közérthetően, mindegyikhez javítógomb; a leletek kattinthatók.
- **Kimenet a nyomdának:** négy lépéses varázsló – nyomtatási feltétel kiválasztása, átalakítás a javaslat szerint, ellenőrzés, mentés; az ICC mindig output intentként ágyazódik be, RGB-nél mindig rákérdez; opcionális csomag PDF-fel, profilokkal és jelentéssel. Parancssorban is (`passermark-cli press`).
- **Papírok és mérések:** saját anyagok adminjogok nélkül (`~/.config/passermark/materials.json`, azonnal mentve); a „Papír mérése …” gomb létrehozza a papírt és elindítja a mérést, az „Eszköz keresése” megtalálja az X-Rite eszközt ArgyllCMS-en keresztül; az admin üres anyaglistája most elmagyarázza az első lépéseket.
- **Szabványprofilok:** PSO Coated/Uncoated v3, FOGRA39/47, SC-B, GRACoL és SWOP letöltése a registry.color.org-ról a saját ICC-mappába „Szabványprofilok letöltése” paranccsal (licenc miatt nincsenek a programban); a javaslatok a még nem telepítetteket is mutatják.
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

Opcionális: LibreOffice (Office-fájlok), 7-Zip (ICC-profilok importálása archívumokból), ArgyllCMS (az anyagok papírfehérjének mérése – Linux-csomag `argyll`).

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
`split`, `press` (nyomdai export), `plan`/`poster` (terv- és poszternyomtatás tekercsen); továbbá `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (adattáblázatok). Beágyazott
beállítások ponttal (`--set detect.tolerance=40`). A Ctrl+C tisztán megszakít (nincs félbesúrt fájl).
Visszatérési értékek: 0 kész, 1 hiba, 2 hibás megadás, 130 megszakítva. A `--json-progress` a haladást és az
eredményt JSON-sorokként írja ki. A nagy feladatok több magot használnak; korlátozás a `PASSERMARK_WORKERS`
környezeti változóval (1 = nem párhuzamos).

A `passermark-cli serve` figyeli a bedobómappákat (`--init` sablont hoz létre példával); a `passermark-cli shared-folder` beállítja a közös nyomtatási mappát (`--user NAME`, `--status`); a `passermark-cli reprint <log.json>` a nyomtatási naplóból nyomtat újra.

Hol: Linux `install.sh` → `passermark-cli`; AppImage → `Passermark-*.AppImage --cli …`;
Windows → `passermark-cli.exe` a telepítési mappában (telepítési beállítás: felvétel a keresési útvonalba).
Útmutatók példákkal a programban: **Súgó → Parancssor – útmutató** és **Súgó → Változó adatok – útmutató**.
Felület külső programoknak (stabil JSON-események, hibakódok): [docs/cli-api.md](docs/cli-api.md).

## Hibák naplózása

Hiba esetén a Passermark egy elküldhető naplófájlt ír (Súgó → Hibák naplóinak megnyitása):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Összeomlás után a
következő indítás a naplóra mutat. A hibátlan naplók kilépéskor törlődnek.

## Fordítás (Build)

Helyben: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, Python 3.12 és Inno Setup 6
kell) vagy `./linux/build-appimage.sh` (Linux, a szükséges csomagok a szkript fejében).

Tesztek: `python3 tests/test_<név>.py` (nem kell tesztkeretrendszer).

## Licenc

GPL-3.0-or-later, lásd `LICENSE`. A Windows-telepítő és az AppImage tartalmazza a
[Ghostscript](https://ghostscript.com) programot (AGPL-3.0, Artifex Software).

Harmadik féltől származó licencek: a telepítő és az AppImage a program mellett egy `licenses`
mappát tartalmaz (Súgó → Licencek …) a `THIRD_PARTY_NOTICES.txt` fájllal, az összes mellékelt
Python-csomag licencfájljaival, a Qt/PySide6 LGPL-tájékoztatóval (a Qt-könyvtárak cseréje) és a
Ghostscript-tájékoztatóval, benne a mellékelt verzió forráskódjának hivatkozásaival. Kérésre a
mellékelt összetevők forráskódját is biztosítjuk – kérjük, nyisson egy issue-t a
[GitHubon](https://github.com/groschenheld/passermark/issues).


