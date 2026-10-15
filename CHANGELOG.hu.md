# Változásnapló – Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · **Magyar** · [Français](CHANGELOG.fr.md) · [Español](CHANGELOG.es.md)

> Ez a változásnapló a **1.10.x–1.11.x verziókat** tartalmazza magyarul. A teljes változástörténet:
> [CHANGELOG.md](CHANGELOG.md) (angolul) vagy [CHANGELOG.de.md](CHANGELOG.de.md) (németül).

## 1.12.5
### Licencek
- A telepítő és az AppImage mostantól minden harmadik félre vonatkozó licencmegjegyzést tartalmaz (Python-csomagok, Qt LGPL-3.0, Ghostscript AGPL-3.0 forráshivatkozással, csomagolt rendszerkönyvtárak), megtekinthetők az új Súgó → Licencek menüben.
- README-k: új szakasz a harmadik felek licenceiről, a forráskód kérésre elérhető.
### Dokumentáció
- A CLI-kézikönyv (DE/EN) frissült a `shrink` és a `flatten_softmask` paranccsal.

## 1.12.4
### Fájlméret csökkentése (új)
- Elérhető a „Fájlméret" fülről vagy a Dokumentum → „Fájlméret csökkentése…" menüből, olyan fájloknál is, amelyek nincsenek túl nagyként megjelölve.
- Minden intézkedés külön be- és kikapcsolható:
  - **Veszteségmentes, alapértelmezetten bekapcsolva:** újraírás (a régi mentett verziókat eldobja), nem használt erőforrások eltávolítása, duplikátumok egyesítése (betűtípusok, képek, ICC-profilok), szerkesztési adatok és miniatűrök eltávolítása, képek veszteségmentes újrakomprimálása (a JPEG körüli ZIP-et is eltávolítja, ha kisebb lesz tőle).
  - **Alapértelmezetten kikapcsolva:** 16 → 8 bit, mellékletek eltávolítása, rejtett rétegek tartalmának eltávolítása.
  - **Opcionális lemintázás:** 300/240/150/100 dpi-re küszöbbel és JPEG-minőséggel, a legnagyobb elhelyezésnél mérve. A soft maszkok együtt skálázódnak.
- Az eredmény új ablakban nyílik meg, az eredet változatlan marad. Ha az eredmény nem kisebb, a fájl marad, ahogy van.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 …]`
- Példa: egy 34 MB-os fájl a 90-szer beágyazott, azonos CMYK-profillal 0,5 MB-ra csökkent, pixelre azonosan.

## 1.12.3
### Előellenőrzés (preflight)
- **Új fül „Fájlméret":** megmutatja, hová mennek a bájtok: képek, betűtípusok, színprofilok, Illustrator-/Photoshop-szerkesztési adatok, miniatűrök, mellékletek, oldaltartalom.
  - Felsorolja továbbá a régi mentett verziókat, a duplikátumokat és a legnagyobb képeket effektív dpi-jükkel.
  - Figyelmeztet a nagyon nagy fájlokra (A4-es felületenként több mint 20 MB) és a nagy duplikátumokra.

## 1.12.2
### Előellenőrzés (preflight)
- **Átlátszó átmenetek (soft mask a mintában):** felismerhetők és javíthatók. Néhány RIP/plotter fekete felültként nyomtatja őket, amely letakarja az alatta lévő képeket. Az új javítás „Átlátszó átmenetek képpé alakítása (300 dpi)" csak az érintett átmeneteket rendereli, az alatta lévőkkel együtt, fedő képként. A felül lévő szöveg és vektorok sértetlenek maradnak. Ghostscript nem szükséges.
- **HDR-fotók (gain map):** a mobilos HDR-fotó, amely mindkét képpel megnyitva volt, most felismerésre kerül az ellenőrzésben. Javítás: „HDR-segédlapok eltávolítása …", választható mérettel és opcionális gain-map-egyesítéssel.
- **Új fül „Képek és színek":**
  - Színtér kép és oldal szerint (RGB, CMYK, szürkeárnyalat, direkt színek), a pontos ICC-profilnévvel és a kimeneti színtérrel (output intent).
  - Effektív felbontás elhelyezésenként, többször használt vagy űrlapokon (XObjectek) belüli képeknél is.
  - Ajánlott legnagyobb méret 300 és 150 dpi-nél, valamint az oldalankénti maximális méretezés.
  - Figyelmeztetések alacsony felbontásnál, információk RGB-tartalomról és direkt színekről.

## 1.12.1
- **Szerkesztés: több objektum és sor egyszerre.** A „Méretezés / mozgatás …”, „Objektum törlése”,
  „Alkalmaz” (betűtípus és méret) és „Sor törlése” most az összes kiválasztott objektumra vagy
  sorra hat, nem csak egyre. Több sor kijelölésekor a szövegmező zárolva van – szöveget csak egy
  sornál lehet változtatni
- **Szerkesztés: szín módosítása.** Új „Szín …” gomb szövegsorokhoz és vektorobjektumokhoz,
  választhatóan CMYK (alapértelmezés, nyomdához) vagy RGB; vektoroknál a kitöltés és a körvonal
  külön-külön állítható. A 0/0/0/100 feketéje tiszta fekete marad. A szín közvetlenül az oldal
  tartalmában kerül beállításra – a kijelölésen kívül minden érintetlen marad, azok az objektumok
  is, amelyek csak örökölték a színüket
- **Szerkesztés: áttekintés.** A lapok darabszámot mutatnak („Szöveg (12)”, „Objektumok (40)”); az
  „Objektumok” lapon vektorokra vagy képekre szűrhető a lista, típusonkénti darabszámmal. Aktív
  szűrőnél az oldalra kattintás csak az adott típust jelöli ki
- **HDR telefonfotók (iPhone, Android) felismerése.** Az ilyen JPG-k a fotó mellett szürke
  fényerő-térképet tartalmaznak a HDR-kijelzőkhöz. Korábban ebből más méretű második lap lett –
  hibás színekkel a plotternél. Most nyitáskor figyelmeztetés jelenik meg; a „Javítás” egy lapot
  ad az változatlan fotóval, a méret választható (mint a kiegészítő kép, vagy ahogy a fotóban
  tárolva van). A fényerő-térképet szükség szerint be lehet számítani. Rákérdezés nélkül (parancssor,
  közvetlen nyomtatás) automatikus a javítás
- **Javítva: ív-szöveg betűmérete.** A módosítás után a lista továbbra is a régi méretet mutatta,
  és minden további módosítás újra nagyított (24 → 36 → 54 pt). Most a tényleges méret jelenik meg;
  a kevés betűt tartalmazó rövid ívek is körív-szövegként ismerődnek fel. A változtatás nélküli
  „Alkalmaz” érintetlenül hagyja az oldalt
- **Javítva: Z-sorrend.** A legfelső objektumon az „egy lépés előre” tévesen „az oldal szerkezete
  nem ismerhető fel” hibát jelzett – most egyszerűen minden marad, ahogy van
- **Javítva: szöveg egérrel húzása** néhány PDF-nél (pl. Chrome-ból) hibaüzenettel megszakadt
- Fordítások kiegészítve a haszon-elrendezéshez a nyomtatási párbeszédablakban (angol, magyar,
  spanyol, francia)

## 1.11.3
- **VDP-párbeszédablak felfrissítve.** A változó adatok ugyanúgy néznek ki, mint a nyomtatási
  párbeszédablak: négy számozott, összecsukható szakasz (mezők, adatok, számozás, kimenet),
  felül pedig egy összecsukott „Útmutató”. A mezőmagyarázatok most tooltipként élnek, és csak az
  új „Súgószövegek megjelenítése” kapcsolóval jelennek meg a mező alatt. Az elavult kimeneti
  útmutató most a nyomtatási párbeszédablak sorrendjére mutat (Haszonminták, „Minden haszonra a
  következő oldal”). A CollapsibleSection widget közösen a common.py-ban él.
- **Nyomtatási párbeszédpanel fülek nélkül.** A fenti módválasztó („Mit nyomtassunk?") egyetlen,
  folytonos oszlopban vezet végig a párbeszédpanelen: preset, mód, módpanel, skálázás („Hogyan
  az ívre?"), vágójel, papír/kimenet, finisher, színkezelés. A korábbi fül-navigáció megszűnt.
- **A Step & Repeat saját mód.** A „Nutzen" a többi mód mellett áll az választóban (egyedi ívek,
  több íven, füzet, poszter) – a többi módhoz hasonló magyarázó szöveggel. A régi jelölőnégyzetet a
  mód-gomb váltotta ki; a Nutzen-panel ott jelenik meg, ahol a többi módpanel.
- **„Hogyan az ívre?"** a skálázás és a tájolás most egy csoport: illesztés/eredeti méret/kicsinyítés/
  egyéni, forgatás, automatikus forgatás, középre igazítás, margók. A skálázásválasztás minden
  nyomtatási módban látható és hatásos: illesztés = mód-alapérték, eredeti méret/kicsinyítés/egyéni
  felülírja a mód skálázását – a módmezők (kachel-skálázás, Nutzen-mérték, poszter) megmaradnak.
- **Tükrözés és meghajtó-beállítások összecsukhatók.** Mindkét szakasz jól látható címmel megmarad,
  és csak szükség esetén nyitható ki – minden beállítás változatlanul.
- **Füzetkötés: „Standard" először.** A klasszikus gerinctűzés („minden ív egymásba, egyszeri
  behajtás") a „Standard" néven vezeti a kötésmód-listát – az „ív művenként" számláló csak a
  „Csoportos ívműveknél" jelenik meg, így nem sugallhat értelmetlen beállítást.
- **Egységes összecsukható szakaszok.** Az új oszlop minden blokkja – preset, módválasztó
  („Mit nyomtassunk?"), „Hogyan az íre?", vágójel, papír/kimenet, finisher, színkezelés, tükrözés,
  meghajtó – azonos méretű, összecsukható címsort kap. A mód-gombok egymás alatt állnak, így minden
  felirat olvasható maradt; a módpanel a látható mód méretére zsugorodik (nincs üres hely). A Nutzen
  módból bármikor más módra váltható.
- **Fordítások:** 26 új/kiegészített üzenet nyelvenként (EN/DE/ES/FR/HU); az ES/FR/HU/EN
  üzenetkatalógusokból hiányzó 1.11.1-sztringek utánapótlása. A régi presetek teljesen kompatibilisek
  maradnak (size/multiple/sr handling továbbra is betölt).

## 1.11.2
- **2. lépés: az ív újra montírozása.** Az elkészült 1. lépés ív másodszor is egy szabadon választott
  célformátumra kerül (eszközformátumok vagy saját méretek mm-ben) – sorról sorra, mindig középre, a
  tartalom változatlanul; az eredmény gombbal új dokumentumként adható ki (új lap), az előnézet az
  1. lépéshez hasonlóan mutatja, és a párbeszédablak ezután bezárul. Az 1. lépés elfordítása és tájolása
  a 2. lépésre is érvényes. Rács: 0 × 0 = automatikus (amennyi csak fér).
- **Meglévő vágójelölések használata.** Vágott formátumú (TrimBox) dokumentumoknál a haszonmintablokk
  külső oldalai a dokumentum valódi szélét mutatják – a meglévő vágójelölések láthatóak maradnak; a saját
  jelölések továbbra is jelölőnégyzettel kapcsolhatók be.
- **A rács pontos montírozása.** Egy definiált rács (pl. 3 × 3) az 1. és a 2. lépésben is pontos marad –
  ha nem fér az ívre, szimmetrikusan a szélén levágásra kerül figyelmeztetéssel, sosem szakad meg.
- **Margók nélkül tervezett célformátum:** pl. két A4-es ív az 1. lépésből tisztán fér egy A3-ra.
- Az 1. lépés nyomtatási útvonala és tájolása változatlan marad.

## 1.11.1
- **Egyedi formátumok: csak «Mentés PDF-ként».** A saját formátumok többé nem kerülnek elküldésre a nyomtatóknak –
  a Windows-illesztők és spoolerek gyakran nem fogadják el az egyedi méreteket (üres lapok, megszakítások);
  «Mentés PDF-ként» (★) esetén továbbra is teljesen használhatók
- **Vágás: két új mód.** „Szélek levágása”: a lap levágása mind a négy oldalon mm-ben, célformátum nélkül;
  „Fehér tér eltávolítása”: felismeri a látható tartalmat (JPEG-zajjal együtt), az új lapméret a tartalomkeret
  ± margóból adódik (negatív is lehet), a tartalom 1:1 marad (csak eltolva)

## 1.11.0
- **Változó adatok – ablakok (oldalcsoportok).** Több oldalas sablonoknál minden mező egy ablakhoz tartozik
  (pl. „elölapok (név), hátlapok (QR-kód)”); az ablakok létrehozhatók, átnevezhetők és eltávolíthatók –
  mezőik ekkor az első ablakba kerülnek. Oldalkiválasztás ablakonként: minden oldal, páratlan (elölapok),
  páros (hátlapok) vagy tartományok („1,3-5 vagy páratlan 1-50”); saját kiválasztás nélkül a „minden oldal”
  alapréteg érvényes. Rekord-elosztás „lapról lapra” (először az összes oldal az 1. rekorddal) vagy
  „oldalról oldalra” (először az 1. oldal az összes rekorddal); kijelzés „{0} rekord → {1} oldal”, figyelmeztetés
  „– {0} oldal ablak nélkül!”
- **VDP-előnézet:** vágott formátum zöld, vérzés piros; állítható belső keret (segédvonal) a kettő között
- **„aktuális / összesen” oldaljelző** az eszközsávban; oldalszám beírása és Enter – azonnali ugrás
- **Vonalzók, mérés és vágott-formátum-megjelenítés állandóan a fő eszközsávban** – minden munkaterületen
- **Vágott formátum és vérzés a fő nézetben:** belső határvonal (vágott formátum) zöld, vérzés diszkrét piros
  pontvonalként teljes piros felület helyett
- **Mérés illesztéssel:** Control lenyomva a célkereszt mágnesesen illeszkedik a vágó- és belső vonalakhoz
  (oldalszél, vágott formátum, vérzés), képszélekhez és vektorvonalakhoz – szövegre soha. Az előnézeti
  célkeresett addig tapad az élhez, amíg az egér határozottan el nem húzza; a Shift továbbra is
  vízszintes/függőleges/45°-ra zárol

## 1.10.7
- **CutContour: alapformák számítás nélkül.** Új elhelyezés „A végformára (számítás nélkül)”: téglalap,
  lekerekített téglalap, kör … közvetlenül a végformára kerülnek (TrimBox, egyébként az oldalra) – nincs
  renderelés, nincs motívumfelismerés, nincsenek munkafolyamatok, másodperc törtderekében. A távolság, a
  méret, az eltolás és az egérrel húzás a megszokott módon működik. Számítás csak „Kontúr” esetén vagy ha a
  forma a motívum köré illetve objektumonként kerül. Parancssor: `--set fit=trim`
- **Alapértelmezés a CutContourban:** téglalap a végformára (amíg nincsenek tárolt, egyéni utoljára használt
  beállítások)

## 1.10.6
- **Windows javítás: a CutContour 0 %-nál elakadt** (az 1.10.5 óta). A parancssori kimenet UTF-8-ra
  váltását visszavontuk; a „Lapok felosztása” javítás megmarad (az állapotüzenetek tisztán ASCII-ben)
- CutContour: nincs több hiba, ha az ablak bezárásakor még utolér egy előnézeti számítás
  („expected LP_struct_fpdf_document_t … NoneType”)

## 1.10.5
- **Windows javítás:** a „Lapok felosztása” (és minden olyan feladat, melynek üzenete olyan karaktert tartalmaz, mint az „→”) a
  `UnicodeEncodeError … cp1252` hibával megszakadt. A parancssor most maga állítja át a kimenetét UTF-8-ra, a
  felhasználói felület felé menő állapotüzenetek tisztán ASCII-ben
- `SECURITY.md`, `CONTRIBUTING.md` és a GitHub-sablonok hibajelentésekhez és javaslatokhoz a csomagban

## 1.10.4
- Kétnyelvű README: `README.md` (angol) és `README.de.md` (német), naprakészen (lapok felosztása, változó
  adatok, adatok rögzítése, a parancssor összes feladata), a projekt állapotára vonatkozó megjegyzéssel
- Példakonfiguráció `data/defaults.example.json` semleges nyomtatónevekkel

## 1.10.3
- **Lapok felosztása jobb egérgombbal:** lapok kijelölése az oldalsávban → jobb egérgomb → **Felosztás** →
  „Felezés függőlegesen” / „Felezés vízszintesen” – azonnal, csak a kijelölt lapokon, összehasonlító lap
  nélkül. A „Rács / további beállítások …” megnyitja a párbeszédablakot előre beállított kijelöléssel

## 1.10.2
- **Változó adatok – elő és hátlap:** új „Lapok rekordonként” (a 2. alatt): 2 = 1+2. lap → 1. rekord, 3+4 →
  2. rekord … – függetlenül attól, hogy a sablon 2 oldalas vagy már az összes kártyát tartalmazza (pl. 200 lap
  100 névjegykártyához). A „Csak ezeken a lapokon” mezők most ismerik a **páratlan** és **páros**
  lapokat, tartományokkal is kombinálva („páratlan 1-50”). 7. példa: névjegykárlya névvel elöl és QR-névjegykártyával hátul
- **További változók:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. A tartalom melletti **?**
  gomb mindegyiket megjeleníti példaértékkel, dupla kattintással beszúrható. Az azonos nevű CSV-oszlopok
  elsőbbséget élveznek
- Egy oszlopra duplán kattintva az változatlan {{nr}} **cseréje** történik, nem eléhelyezése
- **Lapok felosztása** (Lapok → Lapok felosztása …, Szerkesztés munkaterület): felezés függőlegesen/
  vízszintesen vagy rács, összes/jelenlegi/kijelölt lap vagy tartomány, csak terjedelmek, sorrend
  jobbról→balra; a vágási vonalak előnézetével. **Terjedelmek felosztása** egy kattintással a hibásan
  exportált füzetekhez. Veszteségmentes (a tartalom nem kerül másolásra vagy raszterezésre), a forgatott
  lapok úgy, ahogy látod őket; végformán belül van a felosztás, a levágás (Anschnitt) kívül marad.
  Parancssor: `split` feladat
- **Oldalsáv:** a miniatűrök együtt forognak a „Nézet forgatása balra/jobbra” funkcióval
- **Javítva: a kívülről megnyitás zárt ablakba került** (Windows, jobb egérgomb/dupla kattintás, miközben
  egy ablakban egy eszköz nyitva van) – most saját ablakba. Ok: a megnyitás az üres kezdőablakban láthatatlan
  üres fület hagyott hátra; most maga az üres ablak használatos. A zárt ablak eredményei is saját ablakban
  nyílnak meg

## 1.10.1
- **Saját CSV más oszlopnevekkel, közvetlenül:** Változó adatok → CSV megnyitása felismeri, mihez illik a
  táblázat („A táblázat illik: QR – névjegykárlya”), a **Illeszkedő mező létrehozása** létrehozza a QR-kódot
  ezzel a típussal. Az oszlopok automatikusan hozzárendelésre kerülnek – angol, magyar, spanyol, francia
  nevek és az **Outlook, Google és Thunderbird** kapcsolatexportjainak fejlécei is. A CSV változatlan marad
- **Oszlopok hozzárendelése …** a QR-mezőben típussal: oszlop választása adatonként, „üresen hagyás” vagy
  automatikus; a kész tartalom előnézetével. A típus alatt áll, mi honnan jön és mi hiányzik. A hozzárendelés
  a presetben tárolódik (`qr_map`) és a parancssoron is érvényes
- Adatok rögzítése: a idegen nevű CSV nem kap többé dupla oszlopokat; a fejléc mutatja a hozzárendelést
  („First Name → Vorname”). A `datencheck` szintén felismeri az idegen oszlopneveket
- Példamappa: `kontakte-outlook.csv` (így néz ki egy Outlook-export); az útmutató kiegészítve a „Saját CSV
  más oszlopnevekkel” résszel

## 1.10.0
- **Adatok rögzítése** (Változó adatok munkaterület, Dokumentummanipuláció menü vagy a Változó adatok
  párbeszédablakban a 2. alatt): az adattáblázat közvetlenül a Passermarkban hozható létre. Típusonként a
  megfelelő oszlopok – **QR-névjegykárlya (vCard), WLAN-hozzáférés, e-mail, webcím, hívás, SMS, időpont,
  helyszín**, szabad QR-szöveg, **Code 128**, **EAN-13**, szöveg saját oszlopokkal. Minden sor azonnali
  ellenőrzésen megy át (kötelező adatok, EAN-ellenőrző szám, umlautok a Code 128-ban, dátum …), jobbra a
  kiválasztott sor kész kódja. Beszúrás Excelből Ctrl+V-vel, sorok duplikálása, oszlop kitöltése
  számsorral (a sorokat is létrehozza), saját oszlopok. Mentés CSV-ként (UTF-8 BOM-mal, pontosvesszővel – az
  Excel helyesen olvassa az umlautokat)
- A **„Használat változó adatokban”** átveszi a táblázatot adatforrásként és létrehozza a megfelelő mezőt
- **QR-mező „QR-kód típusa”:** a tartalom beírt módon vagy a táblaoszlopokból összeállítva (vCard, WLAN,
  mailto, tel, SMS, időpont, geo). A CSV olvasható marad; a Passermark a kódtartalmat a létrehozáskor
  építi fel
- **Csendes zóna:** a QR-kód és a Code 128 most fehér szegéllyel rendelkezik a mezőben (kikapcsolható).
  Nélküle a más tartalomhoz közeli kódok rosszul olvashatók voltak. *Meglévő presetek: a QR-kód ettől kicsit
  kisebb lesz a mezőben*
- **A 13 számjegyű, hibás ellenőrző számú EAN-13 most hiba** (a helyes számmal az üzenetben) – korábban az
  utolsó számjegy csöndben cserélt
- Parancssor: `datenarten`, `datenvorlage <típus> [fájl.csv]`, `datencheck <fájl.csv> [típus]` (1-es
  visszatérési kód problémáknál); a presetben QR-mezőnként `qr_type`
- 5. (névjegykárlya kapcsolatlistából) és 6. (WLAN-hozzáférés) példa; a „Változó adatok” útmutató új
  „Adatok rögzítése” fejezettel, a CLI-útmutató kiegészítve
- A tesztek most valóban visszabeolvassák a létrehozott kódokat: QR és EAN-13 OpenCV-vel (ha telepítve), a
  Code 128 saját olvasóval, ellenőrző összeggel
- Javítva: a változó adatok az elosztás kiválasztása nélkül „rekordonként a teljes dokumentum másolatát”
  használták a „minden lapon a következő rekord” helyett
