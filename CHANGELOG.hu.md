# Változásnapló – Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · **Magyar** · [Français](CHANGELOG.fr.md) · [Español](CHANGELOG.es.md)

> Ez a változásnapló a **1.10.0-tól kezdve** tartalmazza magyarul. A teljes változástörténet:
> [CHANGELOG.md](CHANGELOG.md) (angolul) vagy [CHANGELOG.de.md](CHANGELOG.de.md) (németül).

## 1.16.0

### Munkafolyamatok: feltételek
- **„if” minden lépésen:** egy lépés csak akkor fut le, ha a feltétele teljesül.
- **Elágazások:** a `{"choose": [{"if": …, "steps": […]}, {"else": …}]}` pontosan azt az ágat futtatja, amelynek feltétele igaz.
- **„fail” és „stop”:** a fail elutasítja a fájlt (1-es kilépési kód, `rejected` hibakód), a stop hiba nélkül zárja le a munkafolyamatot. Mindkettő adhat üzenetet, `${pages}`, `${format}` stb. behelyettesítéssel.
- A `check` elgépeléseket is jelez egy feltételben, a pontos hely megadásával.
- Ellenőrizhető: lapszám, formátum, méretek, levágás, fájlméret, fájlnév, a preflight hibái és figyelmeztetései, RGB, direkt színek, hiányzó betűtípusok, átlátszóság, rétegek és `var.NAME`.

### serve: --init és elutasított fájlok
- A `passermark-cli serve --init` (vagy `--init --system`, mindenki számára) létrehoz egy `watch.json` sablont, egy példa munkafolyamatot és a `hotfolder/beispiel` mappát. A már meglévőket sosem írja felül.
- A figyelő az elutasított fájlokat (fail feltétel) a naplóval együtt a `failed/` mappába teszi.
- A linuxos telepítő és a Windows setup a telepítés után egyszer lefuttatja a `serve --init --system` parancsot, ha még nincs semmi.

### Haszonminták (step & repeat): 2. lépés közvetlen nyomtatásnál
- A második kezelés (2. lépés) most közvetlen nyomtatásnál, a nyomtatási párbeszédablakból is lefut – nem csak a `passermark-cli impose` parancsnál. A fél SRA3-ra rakott kilenc névjegy (2×) így is SRA3-ra kerül.

### Preflight: kattintható leletek
- Minden lelet szövegesen megnevezi a helyét („2. oldal – jobb alul, 40 × 20 mm”).
- Egy kattintás odébb ugrik, és piros kerettel jelöli a helyet; a ◀ ▶ gombokkal végigmehetsz a leleteken.

### Nyomtatási napló
- Felhasználónként bekapcsolható a beállításokban, vagy adminként kikényszeríthető (`print_log`: `force`, `dir`, `keep_days`).
- Minden munkához egy JSON íródik a pontos beállításokkal, mellé egy `printlog.csv`. Alapértelmezett mappa: `printlog`.
- A `passermark-cli reprint <log.json>` újranyomtatja a munkát. Ha az eredeti időközben megváltozott, figyelmeztet.

## 1.15.1
### Haszonminták (step & repeat): forgatás
- Ha a rács egyik tájolásban sem fér teljesen az ívre, most az a tájolás nyer, amelyiken a legkisebb a túllógás. Csak ezután számít az „inkább forgatás nélkül”.
- Az álló tájolású adatok most forgatva kerülnek az ívre, pontosan úgy, mint a fekvő tájolásúak.
- Ugyanígy változott a 2. lépésben, és abban az esetben is, amikor egy haszonminta önmagában sem fér az ívre.
- Ha minden fér, marad a forgatás nélküli megoldás. A „Haszonminta forgatása: 0°” ill. „90°” továbbra is kényszeríti a forgatást.

### Papírformátumok
- A méretek most mindig először a nyomtatótól jönnek, ebben a sorrendben: `*PaperDimension`, különben `<</PageSize[b h]>>` a PPD-ből, különben a névből vagy a megjelenített szövegből (pl. „8K 270 x 390 mm”) – csak ezután a táblázatból.
- Egy formátumtáblázat (papersizes.py) három helyett. Újak benne: SRA4, SRA2, SRA0–1, az RA-sorozat, A7–A10, ISO-B, C0–C10. A korábbi értékek változatlanok maradtak.
- A PPD-ben pont helyett álló vessző is felismerésre kerül: a méretek így is átvehetők, és ez jelezve is van.
- Ha a nyomtatható terület hiányzik, a Passermark azokat a margókat veszi, amiket a nyomtató a többi formátumánál használ. Margó nélküli formátumoknál a teljes ív.
- A nyomtatási párbeszédablak figyelmeztetése megnevezi az okot, és kiírja a kész PPD-sorokat a helyes pt-értékekkel.
- Az IPP- és a Windows-nyomtatók a névre és a táblázatra esnek vissza, ha az illesztőprogram nem mond semmit, vagy 0 × 0-t jelent.
- A `caps --json` most megmutatja, melyik formátum honnan kapja a méreteit, és az esetleges PPD-hibákat.

### Mentés PDF-ként
- A „Mint a dokumentum” esetén nincs többé téves A4-es figyelmeztetés. Az SRA4 és az SRA2 mostantól szintén a listán van.

### Jól olvasható JSON-ok
- A presetek mostantól csak az alapértelkektől eltérőt mentik. Egy füzet-preset például csak ennyi: `{"handling": "booklet", "sheet": "A3"}`.
- A preset-sor menüjében ott a „Minden beállítás mentése” jelölőnégyzet. Az összes párbeszédablakra érvényes.
- A `passermark-cli tidy fájl.json` megrövidíti a meglévő preseteket és munkafolyamatokat. A `--print` csak mutatja; a `--full` újra teljesen kiír egy presetet.
- Két dolgot a tidy tudatosan nem rövidít meg: a `preset`-et tartalmazó munkafolyamat-lépéseket (ott egy alapérték szándékosan felülírhatja a presetet) és a `layout`-ot a nyomtatási lépésben (a hiányzó értékek ott az adminisztrációs beállításból jönnek, nem a program alapértékéből).

## 1.15.0
### Bedobómappák: passermark-cli serve (figyelő)
- A `passermark-cli serve` figyeli a mappákat, és minden fájlt átküld a hozzárendelt munkafolyamaton. A hozzárendelés a `watch.json`-ban áll (a `--config`-ból, különben a sajátból, különben az összes felhasználóéból).
- Feldolgozás után az eredmény az `output/`, az eredeti a `processed/` mappába kerül; hibánál az eredeti a `failed/`-ba kerül egy `.log` fájllal mellette. Ezek a beállítások mind állíthatók `""`-ra (az eredmény nem marad meg / az eredeti törlődik). Csak nyomtató munkafolyamat alapból nem őriz eredményt.
- Megbízható: egy fájl csak akkor kerül feldolgozásra, ha `settle` másodperce változatlan; félig bemásolt fájlokat (`.part`, `.tmp`) sosem nyúl. Minden fájl előbb a `.passermark/` mappába kerül – két figyelő ugyanazon a mappán sosem dolgozza fel ugyanazt a fájlt kétszer, és összeomlás után a bent ragadt fájlok a következő induláskor visszajönnek. Az eredmények sosem kerülnek vissza a bemeneti mappába, és sosem íródnak felül (`-1`, `-2` …).
- Opciók: `--check`, `--once` (1-es hibakód, ha egy fájl elbukik), `--json`, `--quiet`, `--log`.
- Szolgáltatásként: `linux/passermark-watch.service` saját, jog nélküli felhasználóval (a lépések a fájlban); Windowshoz `windows/watch-task.ps1`, amely rendszerindításkor hoz létre feladatot.

### Munkafolyamat-mappák: ablaeufe → workflows
- A mappa neve mostantól `workflows`; a régi `ablaeufe` mappa az első híváskor automatikusan átneveződik. Ha hiányoznak hozzá a jogok, a Passermark egyszerűen a régi mappát olvassa tovább.
- **Közös munkafolyamat-mappák:** új a felügyeletben, Általános → „További munkafolyamat-mappák”, pl. hálózati megosztás. Sorrend: saját → közös → mindenki; az első névvel bíró munkafolyamat érvényes. Ki tehet oda munkafolyamatot, azt a mappa jogai szabályozzák (pl. írási joggal bíró csoport) – adminjog ehhez senkinek sem kell. A `workflows --dirs` mutatja, melyik mappából (user / shared / system) jön egy munkafolyamat.

### Nyomtatási lépés
- **`"paper": "auto"`:** a „méret” oldalkezelésnél a nyomtatási lépés az oldalhoz illő papírt választja, brosúránál két oldalt egymás mellé (A5 → A4). Ha a nyomtatóon nincs illő papír, a hiba felsorolja a létező formátumokat; Nutzennél vagy poszternél világos hiba jön – ott meg kell adni a papírt. Üres `paper` a korábbi szerint működik (a nyomtató alappapírja).

### Egyúttal javítva
- A dokumentumon kívüli oldalmegadások (pl. `pages: "1-2"` egyoldalas PDF-nél) most „a 2. oldal nem létezik …” hibát adnak a „list index out of range” helyett.

## 1.14.2
### Fájl → Tulajdonságok … (Ctrl+D)
- Öt lap:
  - **Fájl:** név, mappa („Mappa megnyitása”, „Útvonal másolása”), méret, módosítva, állapot (mentve / módosítva / csak memóriában / átmeneti). Egyesített, átalakított vagy képekből létrehozott dokumentumoknál „Létrehozva innen:” áll a forrásfájlokkal; eredményeknél „Eredménye …”.
  - **Dokumentum:** PDF-verzió, cím, szerző, téma, kulcsszavak, létrehozva ezzel / PDF ezzel készült, létrehozva / módosítva; titkosítás módszerrel, engedélyezett és tiltott jogokkal; kimeneti profil (Output Intent), rétegek, űrlapmezők, kommentek és pecsétek, könyvjelzők, mellékletek, JavaScript, gyors webes nézet.
  - **Oldalak:** táblázat oldalanként formátummal, tájolással, forgatással, végformátummal és levágással, fölötte a formátumok áttekintése.
  - **Betűtípusok:** név, típus, beágyazott, részlet, oldalak. A be nem ágyazott betűtípusok sárgával kiemeltek.
  - **Ellenőrzés:** hibák, figyelmeztetések és megjegyzések oldalakkal.
- Az ablak azonnal megjelenik; a dokumentumadatokat az elemzőfolyamat olvassa ki, és röviddel utána érkeznek – a program nagy fájloknál sem fagy be. Módosított dokumentumoknál a jelenlegi állapot látszik, nem a lemezen lévő fájl. Az adatok ugyanazok, mint a `passermark-cli inspect`, amely most szintén leszállítja a kiegészítő dokumentumadatokat.

### Parancssor-útmutató (Súgó, német és angol)
- Új fejezetek a munkafolyamatokról (munkafolyamat-mappákkal), a nyomtatásról (finisherekkel), az `inspect`-ről és a külső programok felületéről; kiegészítve a parancsáttekintéssel, új tippekkel és a kilátások fejezetével (figyelő, tervezve az 1.15-höz).
- Minden példa valóban tesztként fut, a bemutatott munkafolyamat-JSON-okkal együtt; csak a nyomtatási példa ellenőrzött, és nem fut le, ha nincs nyomtató beállítva.
- Az útmutató jelenleg németül és angolul létezik; magyar, spanyol és francía továbbra is az angolt mutatja.

## 1.14.1
### Parancssor: nyomtatás
- **`print` lépés a munkafolyamatban:** nyomtató, papír, tálca, média, duplex (`none` | `long` | `short`), szín (`color` | `gray`), példányszám, rendezés és oldaltartomány – ezen felül a nyomtatási párbeszédpanel minden beállítása (Nutzen, brosúra, poszter stb.), a nyomtató admin színprofilja és a nyers illesztőprogram-beállítások közvetlenül. A `dry_run` nem küld semmit, csak mutatja, mit küldene.
- A nyomtatás ugyanazon az úton megy, mint a nyomtatási párbeszédpanelből: automatikus tálcaválasztással és a Windows-gyártói beállításokkal.
- Az értékek illesztőértékként, megjelenő névként vagy az abból egyértelműen kiderülő darabként adhatók; ha valami nem stimmel, a hibaüzenet felsorolja az összes lehetséges értéket.
- A PDF a nyomtatás után változatlan marad – utána tovább dolgozni, menteni vagy más beállításokkal újra nyomtatni. `output` nélkül csak nyomtat.
- **Új parancsok:** `printers` (nyomtatók állapottal és alapértelmezett nyomtatóval) és `caps <nyomtató>` (az illesztőprogram összes beállítása a választásokkal, papírformátumok és mely beállítás felelős a papírért, tálcáért, médiáért, duplexért, színért, kimeneti tálcáért és a finisherekért – tűzés, lyukasztás, hajtás, középtűzés, vágás, eltolás).
- Belsőleg: a nyomtatási munkamenet most Qt nélkül él a `pdfdruck/session.py`-ban, hogy a CLI használhassa; a program továbbra is a `gui/common.py`-on keresztül kapja.
- Tesztcsomag: a 30-as és 31-es munkafolyamat próbaütés (`dry_run`), és részt vesz a „minden teszt futtatásában”; a külön `ablaeufe-echt-drucken/` mappában két munkafolyamat van, amelyek ténylegesen nyomtatnak (automatikusan nem futnak).

## 1.14.0
### Parancssor: munkafolyamatok
- **Több feladat egymás után, verziózott JSON-fájlként** („munkafolyamat", formátumverzió 1): a lépések egymás után futnak, mindegyik az előző lépés eredményén dolgozik. A kimenet csak akkor íródik ki, ha minden sikerült.
- **Új parancsok:** `run` (munkafolyamat futtatása, több bemenettel is – a képek és Office-fájlok előbb átalakítva egyesülnek a PDF-ekkel), `check` (ellenőrzés futtatás nélkül, egyszerre az összes hibával), `schema` (a munkafolyamatfájl vagy egy feladat JSON-sémája), `inspect` (dokumentuminformációk: oldalak, formátumok, végformatum/levágás, előellenőrzési leletek – `--check`-kel), `version --json` (verzió, API- és formátumverzió, elérhető feladatok).
- **Változók** a kimeneti útvonalban: `${…}` a `--var`-ból; beépítve `${input}`, `${dir}`, `${stem}`, `${date}` és `${workflow_dir}`.
- **Az elírás hiba:** az ismeretlen beállítások és rossz típusok jelzése történik, semmi nem esik vissza némán egy alapértékre.
- **Külső programoknak:** stabil JSON-események (`start` → `step` → `progress` → `step_done` → `done`) és rögzített hibakódok (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) lépéssel és feladattal; az API- és formátumverzió a `version --json` kimenetében. A felület a [docs/cli-api.md](docs/cli-api.md) fájlban van dokumentálva (angolul, német összefoglalóval) – a külső programok kötelező szerződése, minden README-ből hivatkozva.

## 1.13.2
### Nyomtatási párbeszédpanel: előnézet a háttérben
- **Várakozás nélküli előnézet:** a lap felépítése és rajzolása most a renderfolyamatban történik – az ablak nem vár rá többé. Egy nagy fájllal az előnézet 0,001 s-ot vesz igénybe a főablakban, korábban akár 6 s-os blokkolások helyett. Ha valami változik, miközben még tart a számítás, csak a legutolsó állapot kerül végigrajzolásra.
- A várakozás marad: az előnézet így is csak 2–5 s múlva készül el, mert maga az oldal megrajzolása ennyi ideig tart. Az ablak ez alatt is kezelhető marad.
- **Több példány (pl. step & repeat):** az oldal csak egyszer renderelődik, nem példányonként – kb. kétszer gyorsabb. A kép minimálisan eltér, mert raszterkép; csak nagyon finom mintázatoknál látszik enyhe moiré. A nyomtatás továbbra is az eredetiből történik.
- **Több példány nélkül** az előnézet pixelre azonos a korábbival (összehasonlítva: egyoldalas, 9 az 1-en, brosúra, nyomdai ívek és duplex).
- **Végformatum/levágás** most az oldaladatokból jön, az oldalak betöltése nélkül – az értékek ugyanazok, mint korábban.
- **Íváttekintés** szintén a háttérben számolódik.
- **Még mindig a főablakban:** a „Brosúra nyomdai ívekként” átváltása még kb. 0,9 s-ot vesz igénybe; a nyomdai ívek előállítása nem került ki.
- **Oldalnézet:** a nagy oldal képek zoomoláskor azonnal durván átméreteződnek, a tiszta kép a háttérben érkezik utána. Az oldal kép felső korlása változatlanul 16 megapixel.

### Egyesítés Windowson
- **Egy ablak:** ha egyszerre több fájl érkezik, mind ugyanabba az ablakba kerül. 12 egyidejűleg indított hívással tesztelve: 1 ablak, 12 fájl, név szerint rendezve.
- **Új gombok:** „Mappa hozzáadása …”, fel/le mozgatás és „Rendezés név szerint”. A fájlok be is húzhatók; az ablak mutatja, hány van bent.
- **Sok tervhez:** a legjobb a „Küldés → Passermark – egyesítés” – ez egyszerre adja át az összes fájlt, és első indításkor egyszer hozza létre. Alternatívaként a teljes mappa hozzáadása az ablakban.
- **Oldalsáv:** a kijelölt oldalak áthelyezhetők. A sárga sáv mutatja, hová kerülnek; a szélén az oldalsáv automatikusan továbbgörget.

## 1.13.1
### Sebességjavítás
- Kisebb sebességjavulások az új nézetben (renderelés).

## 1.13.0
### Gyorsabb nézet (renderelés-átvizsgálás)
- **Renderelés külön folyamatban:** az oldalokat egy háttérfolyamat rendereli (`passermark-cli render-server`); a felület sosem vár rá. Egyszerre mindig csak egy kérés van útban – gyors lapozásnál nem halmozódnak az elavult kérések. Ha a folyamat összeomlik, újraindul; ha egyáltalán nem indul (vagy a PDF jelszóval védett), a nézet a programon belül renderel, mint régen.
- **Egy oldal kép oldalanként:** minden oldal egyszer, kb. dupla nézetméretben renderelődik; az ez alatti zoomszintek és a miniatűrök csak átméretezéssel készülnek belőle. Egy oldal képei tehát egyszer bontódnak ki – zoomszintenként és miniatűrenként külön helyett.
- **Erős zoom csak a látható részt rendereli,** pixel pontosan elforgatott nézetben is. 400 %-nál az oldal röviden életlen, majd éles (korábban felnagyított és életlen maradt).
- **Ugyanarra a fájlba mentés Windowson is megy:** a fájl a memóriába olvasódik és lemezre szabadon marad.
- **Szerkesztő mód:** húzás közben az objektum félig átlátszóan fut vele; alkalmazás után a régi képek helyőrzőként maradnak és a háttérben megújulnak, először a szerkesztett oldal. Korábban minden elfehéredett, és az összes miniatűrt a főablakban renderelték újra.
- **Az automatikus ellenőrzés a változatlan fájlokat közvetlenül olvassa** – megnyitáskor elmarad az újmentés a főablakban.
- Hiba beszűkítése: `PASSERMARK_RENDER=local` beállítással minden úgy működik, mint előtte – így gyorsan kiderül, hogy az új renderfolyamat-e az ok.
- Ismert korlát: objektum elengedése szerkesztő módban nehéz oldalakon még kb. 1 s (a biztonsági ellenőrzés hasonlítja össze az oldalt előtte és utána). Több oldalon használt elem egy módosítással mindenhol változhat, ezért szerkesztés után az összes oldal a háttérben újra renderelődik, először a szerkesztett.

## 1.12.6
### Előellenőrzés (preflight) módosítások
- Kis módosítások a „Fájlméret csökkentése" (`shrink`) funkción és az előellenőrzéseken; fordítások kiegészítve; a CLI-kézikönyv (DE/EN) frissítve.

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

