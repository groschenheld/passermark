# Passermark 1.15.1

PDF-megjelenÃ­tÅ, nyomtatÃ³eszkÃ¶z Ã©s nyomdai elÅkÃ©szÃ­tÃ©si szerszÃ¡moslÃ¡dÃ¡ja **Linuxra Ã©s Windowsra**. Szabad
szoftver (GPL-3.0-or-later).

**English:** [README.md](README.md) Â· [Deutsch](README.de.md) Â· **Magyar** Â· [FranÃ§ais](README.fr.md) Â· [EspaÃ±ol](README.es.md)

> **Ãllapot:** egy magÃ¡nprojekt, a napi nyomdai elÅkÃ©szÃ­tÃ©si munka mellett fejlesztve. ÃszrevÃ©teleket
> szÃ­vesen fogadok â a vÃ¡laszok Ã©s az Ãºj funkciÃ³k garancia nÃ©lkÃ¼l Ã©rkeznek. CUPS- Ã©s Windows-illesztÅprogramokkal
> tesztelve (intasugaras, irodai Ã©s termelÃ©si nyomtatÃ³k finisherrel, nyomtatÃ³szerveren keresztÃ¼l); a
> ritkÃ¡bb illesztÅprogramok Ã©s finisher-beÃ¡llÃ­tÃ¡sok mÃ³dosÃ­tÃ¡st igÃ©nyelhetnek.

## KÃ©pernyÅkÃ©pek

| | |
|---|---|
| ![Dokumentum-ellenÅrzÃ©s figyelmeztetÃ©sekkel Ã©s megjegyzÃ©sekkel](docs/screenshots/preflight_example.jpg) | ![CMYK-Ã¡talakÃ­tÃ¡s szÃ­nelÅnÃ©zettel](docs/screenshots/cmyk_adjustment_example.png) |
| ![Nutzen (step & repeat)](docs/screenshots/step_and_repeat_example.png) | ![CutContour vÃ¡gÃ³plotterekhez](docs/screenshots/cut_contour_example.png) |
| ![KivÃ¡gÃ¡s](docs/screenshots/trim_example.png) | ![VÃ¡ltozÃ³ adatok](docs/screenshots/variable_data_example.png) |

## FunkciÃ³k

- **MegjelenÃ­tÃ©s Ã©s nyomtatÃ¡s**: PDF-ek, kÃ©pek (HEIC, SVG is) Ã©s Office-fÃ¡jlok (LibreOffice-on keresztÃ¼l). A
  meglÃ©vÅ nyomtatÃ³illesztÅket hasznÃ¡lja (Linuxon CUPS, Windowson Windows-illesztÅk) minden beÃ¡llÃ­tÃ¡sukkal.
- **KiosztÃ¡s (AusschieÃen):** igazÃ­tÃ¡s/skÃ¡lÃ¡zÃ¡s, tÃ¶bb lap egy Ã­vre, plakÃ¡tfelosztÃ¡s, haszonmintÃ¡k (Nutzen);
  fÃ¼zetek tÅ±zÃ¶tt kÃ¶tÃ©skÃ©nt, csoportos Ã­vekkÃ©nt vagy egymÃ¡sra helyezett Ã­vekkÃ©nt (ragasztott kÃ¶tÃ©s), bundzug
  ( creep) Ã¼res lapokkal, hajtÃ¡si-, passer- Ã©s flapjelÃ¶lÃ©sekkel Ã©s Ã­vÃ¡ttekintÃ©ssel. ParancssorbÃ³l is
  (`passermark-cli impose`). A haszonmintÃ¡k mÃ¡sodszor is szabadon vÃ¡lasztott cÃ©lformÃ¡tumra helyezhetÅk (2. lÃ©pÃ©s).
- **DokumentummanipulÃ¡ciÃ³:** CMYK-Ã¡talakÃ­tÃ¡s szÃ­nelÅnÃ©zettel, formÃ¡tumra vÃ¡gÃ¡s, objektumok szÃ©tvÃ¡lasztÃ¡sa,
  **CutContour** vÃ¡gÃ³plotterekhez (kontÃºr, formÃ¡k, tÃºlnyÃºlÃ¡s, belsÅ vÃ¡gÃ¡sok; formÃ¡k mÃ©retezÃ©se Ã©s mozgatÃ¡sa
  fogantyÃºkkal). A vÃ¡gÃ¡s most mÃ¡r âszÃ©lek levÃ¡gÃ¡sÃ¡valâ (mm oldalonkÃ©nt, cÃ©lformÃ¡tum nÃ©lkÃ¼l) Ã©s âfehÃ©r tÃ©r
  eltÃ¡volÃ­tÃ¡sÃ¡valâ (tartalom felismerÃ©se, Ãºj lapkeret Â± margÃ³, a tartalom 1:1 marad) is.
- **Lapok felosztÃ¡sa:** felezÃ©s vagy rÃ¡cs kÃ¼lÃ¶n lapokkÃ©nt â pl. terjedÃ©meskÃ©nt exportÃ¡lt fÃ¼zet; lapok
  kijelÃ¶lÃ©se, jobb egÃ©rgomb â FelosztÃ¡s. VesztesÃ©gmentes (semmi nem raszterezÅdik), a vÃ©gformatum Ã©s a
  tÃºlnyÃºlÃ¡s figyelembe vÃ©telÃ©vel.
- **Preflight:** megnyitÃ¡skor ellenÅrzi a betÅ±ket, a rÃ©tegeket Ã©s az Ã¡tlÃ¡tszÃ³sÃ¡got; javÃ­tÃ¡sok: betÅ±k beÃ¡gyazÃ¡sa
  vagy helyettesÃ­tÃ©se (szabad, metrikailag kompatibilis betÅ±k vagy letÃ¶ltÃ©s a fontsource.org-rÃ³l), szÃ¶veg
  gÃ¶rbÃ©kkÃ© alakÃ­tÃ¡sa, rÃ©tegek rÃ¶gzÃ­tÃ©se/eltÃ¡volÃ­tÃ¡sa, Ã¡tlÃ¡tszÃ³sÃ¡g lapÃ­tÃ¡sa.
- **SzerkesztÃ©s:** szÃ¶vegsorok Ã©s rÃ©tegek kivÃ¡lasztÃ¡sa egÃ©rrel; szÃ¶veg, betÅ± Ã©s mÃ©ret vÃ¡ltoztatÃ¡sa; rÃ©tegek
  mozgatÃ¡sa, mÃ©retezÃ©se, elrejtÃ©se, eltÃ¡volÃ­tÃ¡sa vagy cserÃ©je; visszavonÃ¡s.
- VonalzÃ³k Ã©s mÃ©rÃ©s: mm-vonalzÃ³k a nÃ©zet szÃ©lÃ©n; kezdÅ- Ã©s vÃ©gpont kattintÃ¡sa a mÃ©rÃ©shez (a Shift
  vÃ­zszintes/fÃ¼ggÅleges/45Â°-os irÃ¡nyba illeszt), az eredmÃ©ny az Ã¡llapotsorban. Control lenyomva a cÃ©lkereszt mÃ¡gnesesen illeszkedik a vÃ¡gÃ³- Ã©s belsÅ vonalakhoz (oldalszÃ©l,
  vÃ¡gott formÃ¡tum, vÃ©rzÃ©s), kÃ©pszÃ©lekhez Ã©s vektorvonalakhoz â szÃ¶vegre soha; addig tapad az Ã©lhez,
  amÃ­g az egÃ©r hatÃ¡rozottan el nem hÃºzza. A vÃ¡gott-formÃ¡tum-megjelenÃ­tÃ©s zÃ¶lddel mutatja a vÃ¡gott formÃ¡tumot, pontvonallal a vÃ©rtÃ©st.
- **VÃ¡ltozÃ³ adatok:** szÃ¡mozÃ¡s (kezdet, lÃ©pÃ©s, szÃ¡mjegyek, ellenÅrzÅ szÃ¡mok, visszafelÃ©, tovÃ¡bbszÃ¡molÃ¡s),
  CSV-bÅl szÃ¡rmazÃ³ szÃ¶veg, QR-kÃ³dok, Code 128 Ã©s EAN-13 vektorkÃ©nt (csendes zÃ³nÃ¡val); `{{â¦}}`
  helyÅrzÅk a PDF-ben; dÃ¡tum, lap, vÃ©letlenszÃ¡m Ã©s tovÃ¡bbi vÃ¡ltozÃ³k; tÃ¶bb lap rekordonkÃ©nt (elÅl/hÃ¡tul) Ã©s
  mezÅk pÃ¡ratlan/pÃ¡ros lapokon; kÃ³dnaplÃ³; haszonmintÃ¡k sajÃ¡t rekorddal mintÃ¡nkÃ©nt (Ã­vrÅl Ã­vre vagy vÃ¡gÃ¡s Ã©s
  pakolÃ¡s); **ablakok (oldalcsoportok)** tÃ¶bb oldalas sablonokhoz â pl. elÃ¶lap a nÃ©vvel, hÃ¡tlap QR-kÃ³ddal â ablakonkÃ©nti oldalkivÃ¡lasztÃ¡ssal (minden/pÃ¡ratlan/pÃ¡ros oldal vagy tartomÃ¡ny) Ã©s rekord-elosztÃ¡ssal laprÃ³l lapra vagy oldalrÃ³l oldalra. ParancssorbÃ³l is (`passermark-cli vdp`).
- **Adatok rÃ¶gzÃ­tÃ©se:** az adattÃ¡blÃ¡zat kÃ¶zvetlenÃ¼l a Passermarkban hozhatÃ³ lÃ©tre â QR-nÃ©vjegykÃ¡rlya (vCard),
  WLAN-hozzÃ¡fÃ©rÃ©s, e-mail, webcÃ­m, hÃ­vÃ¡s, SMS, idÅpont, helyszÃ­n, Code 128, EAN-13 â megfelelÅ oszlopokkal,
  azonnali ellenÅrzÃ©ssel Ã©s ExcelbÅl tÃ¶rtÃ©nÅ beszÃºrÃ¡ssal; CSV-kÃ©nt mentve Ã©s kÃ¶zvetlenÃ¼l hasznÃ¡lhatÃ³ a vÃ¡ltozÃ³
  adatokban. A mÃ¡s oszlopneveket tartalmazÃ³ sajÃ¡t CSV-fÃ¡jlok (pl. Outlook-, Google-, Thunderbird-exportok)
  automatikusan hozzÃ¡rendelÃ©sre kerÃ¼lnek. HÃ©t kÃ©sz pÃ©lda (SÃºgÃ³ â PÃ©ldÃ¡k lekÃ©rÃ©se).
- **MunkaterÃ¼letek** (MegjelenÃ­tÃ©s Ã©s nyomtatÃ¡s, Nyomdai elÅkÃ©szÃ­tÃ©s, SzerkesztÃ©s, VÃ¡ltozÃ³ adatok,
  AutomatizÃ¡lÃ¡s) sajÃ¡t eszkÃ¶zsorral.
- **Presetek** a CutContourhoz, CMYK/vÃ¡gÃ¡shoz, nyomdai szerkezethez Ã©s vÃ¡ltozÃ³ adatokhoz â a parancssorral
  kÃ¶zÃ¶sen.
- PDF-ek javÃ­tÃ¡sa/optimalizÃ¡lÃ¡sa, PDF/A, jelszavas vÃ©delem (a nyomtatÃ¡si pÃ¡rbeszÃ©dablak âMentÃ©s PDF-kÃ©ntâ
  funkciÃ³jÃ¡nÃ¡l is), fÃ¡jlok egyesÃ­tÃ©se, szÃ¶veg kijelÃ¶lÃ©se Ã©s mÃ¡solÃ¡sa.
- Nyelvek: magyar, nÃ©met, angol, spanyol, francia.

## TelepÃ­tÃ©s

**Windows:** tÃ¶ltsd le a `Passermark-<verziÃ³>-Setup.exe` fÃ¡jlt a [Release-ek](../../releases) alÃ³l, Ã©s
futtasd. Minden benne van (Python, Qt, Ghostscript).

**Linux (bÃ¡rmely disztribÃºciÃ³):** tÃ¶ltsd le a `Passermark-<verziÃ³>-x86_64.AppImage` fÃ¡jlt a
[Release-ek](../../releases) alÃ³l, majd
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, rendszerTelepÃ­tÃ©s fÃ¡jlkezelÅ-integrÃ¡ciÃ³val):**
```sh
sudo ./install.sh        # telepÃ­ti a fÃ¼ggÅsÃ©geket apt-tal, startmenÃ¼-bejegyzÃ©s, Nautilus-menÃ¼
sudo ./uninstall.sh      # ismÃ©telt eltÃ¡volÃ­tÃ¡s (--dry-run elÅnÃ©zet, --purge a /etc/passermark mappÃ¡t is eltÃ¡volÃ­tja)
```

OpcionÃ¡lis: LibreOffice (Office-fÃ¡jlok), 7-Zip (ICC-profilok importÃ¡lÃ¡sa archÃ­vumokbÃ³l).

## Parancssor

Minden nehÃ©z feladat felÃ¼let nÃ©lkÃ¼l is fut â szkriptekhez, teljes mappÃ¡khoz Ã©s automatizÃ¡lÃ¡shoz:

```sh
passermark-cli list                                   # elÃ©rhetÅ feladatok
passermark-cli settings cutcontour > sticker.json     # alapÃ©rtelmezÃ©sek = preset-sablon
passermark-cli cutcontour in.pdf aus.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour in.pdf aus.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour in.pdf aus.pdf --preset "Sticker rund"   # a programban mentett preset
passermark-cli presets                                # a programban mentett presetek
```

Feladatok: `cutcontour`, `separate`, `manip` (CMYK/vÃ¡gÃ¡s), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`; tovÃ¡bbÃ¡ `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (adattÃ¡blÃ¡zatok). BeÃ¡gyazott
beÃ¡llÃ­tÃ¡sok ponttal (`--set detect.tolerance=40`). A Ctrl+C tisztÃ¡n megszakÃ­t (nincs fÃ©lbesÃºrt fÃ¡jl).
VisszatÃ©rÃ©si Ã©rtÃ©kek: 0 kÃ©sz, 1 hiba, 2 hibÃ¡s megadÃ¡s, 130 megszakÃ­tva. A `--json-progress` a haladÃ¡st Ã©s az
eredmÃ©nyt JSON-sorokkÃ©nt Ã­rja ki. A nagy feladatok tÃ¶bb magot hasznÃ¡lnak; korlÃ¡tozÃ¡s a `PASSERMARK_WORKERS`
kÃ¶rnyezeti vÃ¡ltozÃ³val (1 = nem pÃ¡rhuzamos).

Hol: Linux `install.sh` â `passermark-cli`; AppImage â `Passermark-*.AppImage --cli â¦`;
Windows â `passermark-cli.exe` a telepÃ­tÃ©si mappÃ¡ban (telepÃ­tÃ©si beÃ¡llÃ­tÃ¡s: felvÃ©tel a keresÃ©si Ãºtvonalba).
ÃtmutatÃ³k pÃ©ldÃ¡kkal a programban: **SÃºgÃ³ â Parancssor â ÃºtmutatÃ³** Ã©s **SÃºgÃ³ â VÃ¡ltozÃ³ adatok â ÃºtmutatÃ³**.
FelÃ¼let kÃ¼lsÅ programoknak (stabil JSON-esemÃ©nyek, hibakÃ³dok): [docs/cli-api.md](docs/cli-api.md).

## HibÃ¡k naplÃ³zÃ¡sa

Hiba esetÃ©n a Passermark egy elkÃ¼ldhetÅ naplÃ³fÃ¡jlt Ã­r (SÃºgÃ³ â HibÃ¡k naplÃ³inak megnyitÃ¡sa):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. ÃsszeomlÃ¡s utÃ¡n a
kÃ¶vetkezÅ indÃ­tÃ¡s a naplÃ³ra mutat. A hibÃ¡tlan naplÃ³k kilÃ©pÃ©skor tÃ¶rlÅdnek.

## FordÃ­tÃ¡s (Build)

Helyben: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, Python 3.12 Ã©s Inno Setup 6
kell) vagy `./linux/build-appimage.sh` (Linux, a szÃ¼ksÃ©ges csomagok a szkript fejÃ©ben).

Tesztek: `python3 tests/test_<nÃ©v>.py` (nem kell tesztkeretrendszer).

## Licenc

GPL-3.0-or-later, lÃ¡sd `LICENSE`. A Windows-telepÃ­tÅ Ã©s az AppImage tartalmazza a
[Ghostscript](https://ghostscript.com) programot (AGPL-3.0, Artifex Software).

Harmadik fÃ©ltÅl szÃ¡rmazÃ³ licencek: a telepÃ­tÅ Ã©s az AppImage a program mellett egy `licenses`
mappÃ¡t tartalmaz (SÃºgÃ³ â Licencek â¦) a `THIRD_PARTY_NOTICES.txt` fÃ¡jllal, az Ã¶sszes mellÃ©kelt
Python-csomag licencfÃ¡jljaival, a Qt/PySide6 LGPL-tÃ¡jÃ©koztatÃ³val (a Qt-kÃ¶nyvtÃ¡rak cserÃ©je) Ã©s a
Ghostscript-tÃ¡jÃ©koztatÃ³val, benne a mellÃ©kelt verziÃ³ forrÃ¡skÃ³djÃ¡nak hivatkozÃ¡saival. KÃ©rÃ©sre a
mellÃ©kelt Ã¶sszetevÅk forrÃ¡skÃ³djÃ¡t is biztosÃ­tjuk â kÃ©rjÃ¼k, nyisson egy issue-t a
[GitHubon](https://github.com/groschenheld/passermark/issues).

