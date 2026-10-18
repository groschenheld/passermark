# VÃ¡ltozÃ¡snaplÃ³ â Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) Â· [Deutsch](CHANGELOG.de.md) Â· **Magyar** Â· [FranÃ§ais](CHANGELOG.fr.md) Â· [EspaÃ±ol](CHANGELOG.es.md)

> Ez a vÃ¡ltozÃ¡snaplÃ³ a **1.10.0-tÃ³l kezdve** tartalmazza magyarul. A teljes vÃ¡ltozÃ¡stÃ¶rtÃ©net:
> [CHANGELOG.md](CHANGELOG.md) (angolul) vagy [CHANGELOG.de.md](CHANGELOG.de.md) (nÃ©metÃ¼l).

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
### BedobÃ³mappÃ¡k: passermark-cli serve (figyelÅ)
- A `passermark-cli serve` figyeli a mappÃ¡kat, Ã©s minden fÃ¡jlt Ã¡tkÃ¼ld a hozzÃ¡rendelt munkafolyamaton. A hozzÃ¡rendelÃ©s a `watch.json`-ban Ã¡ll (a `--config`-bÃ³l, kÃ¼lÃ¶nben a sajÃ¡tbÃ³l, kÃ¼lÃ¶nben az Ã¶sszes felhasznÃ¡lÃ³Ã©bÃ³l).
- FeldolgozÃ¡s utÃ¡n az eredmÃ©ny az `output/`, az eredeti a `processed/` mappÃ¡ba kerÃ¼l; hibÃ¡nÃ¡l az eredeti a `failed/`-ba kerÃ¼l egy `.log` fÃ¡jllal mellette. Ezek a beÃ¡llÃ­tÃ¡sok mind Ã¡llÃ­thatÃ³k `""`-ra (az eredmÃ©ny nem marad meg / az eredeti tÃ¶rlÅdik). Csak nyomtatÃ³ munkafolyamat alapbÃ³l nem Åriz eredmÃ©nyt.
- MegbÃ­zhatÃ³: egy fÃ¡jl csak akkor kerÃ¼l feldolgozÃ¡sra, ha `settle` mÃ¡sodperce vÃ¡ltozatlan; fÃ©lig bemÃ¡solt fÃ¡jlokat (`.part`, `.tmp`) sosem nyÃºl. Minden fÃ¡jl elÅbb a `.passermark/` mappÃ¡ba kerÃ¼l â kÃ©t figyelÅ ugyanazon a mappÃ¡n sosem dolgozza fel ugyanazt a fÃ¡jlt kÃ©tszer, Ã©s Ã¶sszeomlÃ¡s utÃ¡n a bent ragadt fÃ¡jlok a kÃ¶vetkezÅ indulÃ¡skor visszajÃ¶nnek. Az eredmÃ©nyek sosem kerÃ¼lnek vissza a bemeneti mappÃ¡ba, Ã©s sosem Ã­rÃ³dnak felÃ¼l (`-1`, `-2` â¦).
- OpciÃ³k: `--check`, `--once` (1-es hibakÃ³d, ha egy fÃ¡jl elbukik), `--json`, `--quiet`, `--log`.
- SzolgÃ¡ltatÃ¡skÃ©nt: `linux/passermark-watch.service` sajÃ¡t, jog nÃ©lkÃ¼li felhasznÃ¡lÃ³val (a lÃ©pÃ©sek a fÃ¡jlban); Windowshoz `windows/watch-task.ps1`, amely rendszerindÃ­tÃ¡skor hoz lÃ©tre feladatot.

### Munkafolyamat-mappÃ¡k: ablaeufe â workflows
- A mappa neve mostantÃ³l `workflows`; a rÃ©gi `ablaeufe` mappa az elsÅ hÃ­vÃ¡skor automatikusan Ã¡tnevezÅdik. Ha hiÃ¡nyoznak hozzÃ¡ a jogok, a Passermark egyszerÅ±en a rÃ©gi mappÃ¡t olvassa tovÃ¡bb.
- **KÃ¶zÃ¶s munkafolyamat-mappÃ¡k:** Ãºj a felÃ¼gyeletben, ÃltalÃ¡nos â âTovÃ¡bbi munkafolyamat-mappÃ¡kâ, pl. hÃ¡lÃ³zati megosztÃ¡s. Sorrend: sajÃ¡t â kÃ¶zÃ¶s â mindenki; az elsÅ nÃ©vvel bÃ­rÃ³ munkafolyamat Ã©rvÃ©nyes. Ki tehet oda munkafolyamatot, azt a mappa jogai szabÃ¡lyozzÃ¡k (pl. Ã­rÃ¡si joggal bÃ­rÃ³ csoport) â adminjog ehhez senkinek sem kell. A `workflows --dirs` mutatja, melyik mappÃ¡bÃ³l (user / shared / system) jÃ¶n egy munkafolyamat.

### NyomtatÃ¡si lÃ©pÃ©s
- **`"paper": "auto"`:** a âmÃ©retâ oldalkezelÃ©snÃ©l a nyomtatÃ¡si lÃ©pÃ©s az oldalhoz illÅ papÃ­rt vÃ¡lasztja, brosÃºrÃ¡nÃ¡l kÃ©t oldalt egymÃ¡s mellÃ© (A5 â A4). Ha a nyomtatÃ³on nincs illÅ papÃ­r, a hiba felsorolja a lÃ©tezÅ formÃ¡tumokat; NutzennÃ©l vagy poszternÃ©l vilÃ¡gos hiba jÃ¶n â ott meg kell adni a papÃ­rt. Ãres `paper` a korÃ¡bbi szerint mÅ±kÃ¶dik (a nyomtatÃ³ alappapÃ­rja).

### EgyÃºttal javÃ­tva
- A dokumentumon kÃ­vÃ¼li oldalmegadÃ¡sok (pl. `pages: "1-2"` egyoldalas PDF-nÃ©l) most âa 2. oldal nem lÃ©tezik â¦â hibÃ¡t adnak a âlist index out of rangeâ helyett.

## 1.14.2
### FÃ¡jl â TulajdonsÃ¡gok â¦ (Ctrl+D)
- Ãt lap:
  - **FÃ¡jl:** nÃ©v, mappa (âMappa megnyitÃ¡saâ, âÃtvonal mÃ¡solÃ¡saâ), mÃ©ret, mÃ³dosÃ­tva, Ã¡llapot (mentve / mÃ³dosÃ­tva / csak memÃ³riÃ¡ban / Ã¡tmeneti). EgyesÃ­tett, Ã¡talakÃ­tott vagy kÃ©pekbÅl lÃ©trehozott dokumentumoknÃ¡l âLÃ©trehozva innen:â Ã¡ll a forrÃ¡sfÃ¡jlokkal; eredmÃ©nyeknÃ©l âEredmÃ©nye â¦â.
  - **Dokumentum:** PDF-verziÃ³, cÃ­m, szerzÅ, tÃ©ma, kulcsszavak, lÃ©trehozva ezzel / PDF ezzel kÃ©szÃ¼lt, lÃ©trehozva / mÃ³dosÃ­tva; titkosÃ­tÃ¡s mÃ³dszerrel, engedÃ©lyezett Ã©s tiltott jogokkal; kimeneti profil (Output Intent), rÃ©tegek, Å±rlapmezÅk, kommentek Ã©s pecsÃ©tek, kÃ¶nyvjelzÅk, mellÃ©kletek, JavaScript, gyors webes nÃ©zet.
  - **Oldalak:** tÃ¡blÃ¡zat oldalankÃ©nt formÃ¡tummal, tÃ¡jolÃ¡ssal, forgatÃ¡ssal, vÃ©gformÃ¡tummal Ã©s levÃ¡gÃ¡ssal, fÃ¶lÃ¶tte a formÃ¡tumok Ã¡ttekintÃ©se.
  - **BetÅ±tÃ­pusok:** nÃ©v, tÃ­pus, beÃ¡gyazott, rÃ©szlet, oldalak. A be nem Ã¡gyazott betÅ±tÃ­pusok sÃ¡rgÃ¡val kiemeltek.
  - **EllenÅrzÃ©s:** hibÃ¡k, figyelmeztetÃ©sek Ã©s megjegyzÃ©sek oldalakkal.
- Az ablak azonnal megjelenik; a dokumentumadatokat az elemzÅfolyamat olvassa ki, Ã©s rÃ¶viddel utÃ¡na Ã©rkeznek â a program nagy fÃ¡jloknÃ¡l sem fagy be. MÃ³dosÃ­tott dokumentumoknÃ¡l a jelenlegi Ã¡llapot lÃ¡tszik, nem a lemezen lÃ©vÅ fÃ¡jl. Az adatok ugyanazok, mint a `passermark-cli inspect`, amely most szintÃ©n leszÃ¡llÃ­tja a kiegÃ©szÃ­tÅ dokumentumadatokat.

### Parancssor-ÃºtmutatÃ³ (SÃºgÃ³, nÃ©met Ã©s angol)
- Ãj fejezetek a munkafolyamatokrÃ³l (munkafolyamat-mappÃ¡kkal), a nyomtatÃ¡srÃ³l (finisherekkel), az `inspect`-rÅl Ã©s a kÃ¼lsÅ programok felÃ¼letÃ©rÅl; kiegÃ©szÃ­tve a parancsÃ¡ttekintÃ©ssel, Ãºj tippekkel Ã©s a kilÃ¡tÃ¡sok fejezetÃ©vel (figyelÅ, tervezve az 1.15-hÃ¶z).
- Minden pÃ©lda valÃ³ban tesztkÃ©nt fut, a bemutatott munkafolyamat-JSON-okkal egyÃ¼tt; csak a nyomtatÃ¡si pÃ©lda ellenÅrzÃ¶tt, Ã©s nem fut le, ha nincs nyomtatÃ³ beÃ¡llÃ­tva.
- Az ÃºtmutatÃ³ jelenleg nÃ©metÃ¼l Ã©s angolul lÃ©tezik; magyar, spanyol Ã©s francÃ­a tovÃ¡bbra is az angolt mutatja.

## 1.14.1
### Parancssor: nyomtatÃ¡s
- **`print` lÃ©pÃ©s a munkafolyamatban:** nyomtatÃ³, papÃ­r, tÃ¡lca, mÃ©dia, duplex (`none` | `long` | `short`), szÃ­n (`color` | `gray`), pÃ©ldÃ¡nyszÃ¡m, rendezÃ©s Ã©s oldaltartomÃ¡ny â ezen felÃ¼l a nyomtatÃ¡si pÃ¡rbeszÃ©dpanel minden beÃ¡llÃ­tÃ¡sa (Nutzen, brosÃºra, poszter stb.), a nyomtatÃ³ admin szÃ­nprofilja Ã©s a nyers illesztÅprogram-beÃ¡llÃ­tÃ¡sok kÃ¶zvetlenÃ¼l. A `dry_run` nem kÃ¼ld semmit, csak mutatja, mit kÃ¼ldene.
- A nyomtatÃ¡s ugyanazon az Ãºton megy, mint a nyomtatÃ¡si pÃ¡rbeszÃ©dpanelbÅl: automatikus tÃ¡lcavÃ¡lasztÃ¡ssal Ã©s a Windows-gyÃ¡rtÃ³i beÃ¡llÃ­tÃ¡sokkal.
- Az Ã©rtÃ©kek illesztÅÃ©rtÃ©kkÃ©nt, megjelenÅ nÃ©vkÃ©nt vagy az abbÃ³l egyÃ©rtelmÅ±en kiderÃ¼lÅ darabkÃ©nt adhatÃ³k; ha valami nem stimmel, a hibaÃ¼zenet felsorolja az Ã¶sszes lehetsÃ©ges Ã©rtÃ©ket.
- A PDF a nyomtatÃ¡s utÃ¡n vÃ¡ltozatlan marad â utÃ¡na tovÃ¡bb dolgozni, menteni vagy mÃ¡s beÃ¡llÃ­tÃ¡sokkal Ãºjra nyomtatni. `output` nÃ©lkÃ¼l csak nyomtat.
- **Ãj parancsok:** `printers` (nyomtatÃ³k Ã¡llapottal Ã©s alapÃ©rtelmezett nyomtatÃ³val) Ã©s `caps <nyomtatÃ³>` (az illesztÅprogram Ã¶sszes beÃ¡llÃ­tÃ¡sa a vÃ¡lasztÃ¡sokkal, papÃ­rformÃ¡tumok Ã©s mely beÃ¡llÃ­tÃ¡s felelÅs a papÃ­rÃ©rt, tÃ¡lcÃ¡Ã©rt, mÃ©diÃ¡Ã©rt, duplexÃ©rt, szÃ­nÃ©rt, kimeneti tÃ¡lcÃ¡Ã©rt Ã©s a finisherekÃ©rt â tÅ±zÃ©s, lyukasztÃ¡s, hajtÃ¡s, kÃ¶zÃ©ptÅ±zÃ©s, vÃ¡gÃ¡s, eltolÃ¡s).
- BelsÅleg: a nyomtatÃ¡si munkamenet most Qt nÃ©lkÃ¼l Ã©l a `pdfdruck/session.py`-ban, hogy a CLI hasznÃ¡lhassa; a program tovÃ¡bbra is a `gui/common.py`-on keresztÃ¼l kapja.
- Tesztcsomag: a 30-as Ã©s 31-es munkafolyamat prÃ³baÃ¼tÃ©s (`dry_run`), Ã©s rÃ©szt vesz a âminden teszt futtatÃ¡sÃ¡banâ; a kÃ¼lÃ¶n `ablaeufe-echt-drucken/` mappÃ¡ban kÃ©t munkafolyamat van, amelyek tÃ©nylegesen nyomtatnak (automatikusan nem futnak).

## 1.14.0
### Parancssor: munkafolyamatok
- **TÃ¶bb feladat egymÃ¡s utÃ¡n, verziÃ³zott JSON-fÃ¡jlkÃ©nt** (âmunkafolyamat", formÃ¡tumverziÃ³ 1): a lÃ©pÃ©sek egymÃ¡s utÃ¡n futnak, mindegyik az elÅzÅ lÃ©pÃ©s eredmÃ©nyÃ©n dolgozik. A kimenet csak akkor Ã­rÃ³dik ki, ha minden sikerÃ¼lt.
- **Ãj parancsok:** `run` (munkafolyamat futtatÃ¡sa, tÃ¶bb bemenettel is â a kÃ©pek Ã©s Office-fÃ¡jlok elÅbb Ã¡talakÃ­tva egyesÃ¼lnek a PDF-ekkel), `check` (ellenÅrzÃ©s futtatÃ¡s nÃ©lkÃ¼l, egyszerre az Ã¶sszes hibÃ¡val), `schema` (a munkafolyamatfÃ¡jl vagy egy feladat JSON-sÃ©mÃ¡ja), `inspect` (dokumentuminformÃ¡ciÃ³k: oldalak, formÃ¡tumok, vÃ©gformatum/levÃ¡gÃ¡s, elÅellenÅrzÃ©si leletek â `--check`-kel), `version --json` (verziÃ³, API- Ã©s formÃ¡tumverziÃ³, elÃ©rhetÅ feladatok).
- **VÃ¡ltozÃ³k** a kimeneti Ãºtvonalban: `${â¦}` a `--var`-bÃ³l; beÃ©pÃ­tve `${input}`, `${dir}`, `${stem}`, `${date}` Ã©s `${workflow_dir}`.
- **Az elÃ­rÃ¡s hiba:** az ismeretlen beÃ¡llÃ­tÃ¡sok Ã©s rossz tÃ­pusok jelzÃ©se tÃ¶rtÃ©nik, semmi nem esik vissza nÃ©mÃ¡n egy alapÃ©rtÃ©kre.
- **KÃ¼lsÅ programoknak:** stabil JSON-esemÃ©nyek (`start` â `step` â `progress` â `step_done` â `done`) Ã©s rÃ¶gzÃ­tett hibakÃ³dok (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) lÃ©pÃ©ssel Ã©s feladattal; az API- Ã©s formÃ¡tumverziÃ³ a `version --json` kimenetÃ©ben. A felÃ¼let a [docs/cli-api.md](docs/cli-api.md) fÃ¡jlban van dokumentÃ¡lva (angolul, nÃ©met Ã¶sszefoglalÃ³val) â a kÃ¼lsÅ programok kÃ¶telezÅ szerzÅdÃ©se, minden README-bÅl hivatkozva.

## 1.13.2
### NyomtatÃ¡si pÃ¡rbeszÃ©dpanel: elÅnÃ©zet a hÃ¡ttÃ©rben
- **VÃ¡rakozÃ¡s nÃ©lkÃ¼li elÅnÃ©zet:** a lap felÃ©pÃ­tÃ©se Ã©s rajzolÃ¡sa most a renderfolyamatban tÃ¶rtÃ©nik â az ablak nem vÃ¡r rÃ¡ tÃ¶bbÃ©. Egy nagy fÃ¡jllal az elÅnÃ©zet 0,001 s-ot vesz igÃ©nybe a fÅablakban, korÃ¡bban akÃ¡r 6 s-os blokkolÃ¡sok helyett. Ha valami vÃ¡ltozik, mikÃ¶zben mÃ©g tart a szÃ¡mÃ­tÃ¡s, csak a legutolsÃ³ Ã¡llapot kerÃ¼l vÃ©gigrajzolÃ¡sra.
- A vÃ¡rakozÃ¡s marad: az elÅnÃ©zet Ã­gy is csak 2â5 s mÃºlva kÃ©szÃ¼l el, mert maga az oldal megrajzolÃ¡sa ennyi ideig tart. Az ablak ez alatt is kezelhetÅ marad.
- **TÃ¶bb pÃ©ldÃ¡ny (pl. step & repeat):** az oldal csak egyszer renderelÅdik, nem pÃ©ldÃ¡nyonkÃ©nt â kb. kÃ©tszer gyorsabb. A kÃ©p minimÃ¡lisan eltÃ©r, mert raszterkÃ©p; csak nagyon finom mintÃ¡zatoknÃ¡l lÃ¡tszik enyhe moirÃ©. A nyomtatÃ¡s tovÃ¡bbra is az eredetibÅl tÃ¶rtÃ©nik.
- **TÃ¶bb pÃ©ldÃ¡ny nÃ©lkÃ¼l** az elÅnÃ©zet pixelre azonos a korÃ¡bbival (Ã¶sszehasonlÃ­tva: egyoldalas, 9 az 1-en, brosÃºra, nyomdai Ã­vek Ã©s duplex).
- **VÃ©gformatum/levÃ¡gÃ¡s** most az oldaladatokbÃ³l jÃ¶n, az oldalak betÃ¶ltÃ©se nÃ©lkÃ¼l â az Ã©rtÃ©kek ugyanazok, mint korÃ¡bban.
- **ÃvÃ¡ttekintÃ©s** szintÃ©n a hÃ¡ttÃ©rben szÃ¡molÃ³dik.
- **MÃ©g mindig a fÅablakban:** a âBrosÃºra nyomdai Ã­vekkÃ©ntâ Ã¡tvÃ¡ltÃ¡sa mÃ©g kb. 0,9 s-ot vesz igÃ©nybe; a nyomdai Ã­vek elÅÃ¡llÃ­tÃ¡sa nem kerÃ¼lt ki.
- **OldalnÃ©zet:** a nagy oldal kÃ©pek zoomolÃ¡skor azonnal durvÃ¡n Ã¡tmÃ©retezÅdnek, a tiszta kÃ©p a hÃ¡ttÃ©rben Ã©rkezik utÃ¡na. Az oldal kÃ©p felsÅ korlÃ¡sa vÃ¡ltozatlanul 16 megapixel.

### EgyesÃ­tÃ©s Windowson
- **Egy ablak:** ha egyszerre tÃ¶bb fÃ¡jl Ã©rkezik, mind ugyanabba az ablakba kerÃ¼l. 12 egyidejÅ±leg indÃ­tott hÃ­vÃ¡ssal tesztelve: 1 ablak, 12 fÃ¡jl, nÃ©v szerint rendezve.
- **Ãj gombok:** âMappa hozzÃ¡adÃ¡sa â¦â, fel/le mozgatÃ¡s Ã©s âRendezÃ©s nÃ©v szerintâ. A fÃ¡jlok be is hÃºzhatÃ³k; az ablak mutatja, hÃ¡ny van bent.
- **Sok tervhez:** a legjobb a âKÃ¼ldÃ©s â Passermark â egyesÃ­tÃ©sâ â ez egyszerre adja Ã¡t az Ã¶sszes fÃ¡jlt, Ã©s elsÅ indÃ­tÃ¡skor egyszer hozza lÃ©tre. AlternatÃ­vakÃ©nt a teljes mappa hozzÃ¡adÃ¡sa az ablakban.
- **OldalsÃ¡v:** a kijelÃ¶lt oldalak Ã¡thelyezhetÅk. A sÃ¡rga sÃ¡v mutatja, hovÃ¡ kerÃ¼lnek; a szÃ©lÃ©n az oldalsÃ¡v automatikusan tovÃ¡bbgÃ¶rget.

## 1.13.1
### SebessÃ©gjavÃ­tÃ¡s
- Kisebb sebessÃ©gjavulÃ¡sok az Ãºj nÃ©zetben (renderelÃ©s).

## 1.13.0
### Gyorsabb nÃ©zet (renderelÃ©s-Ã¡tvizsgÃ¡lÃ¡s)
- **RenderelÃ©s kÃ¼lÃ¶n folyamatban:** az oldalokat egy hÃ¡ttÃ©rfolyamat rendereli (`passermark-cli render-server`); a felÃ¼let sosem vÃ¡r rÃ¡. Egyszerre mindig csak egy kÃ©rÃ©s van Ãºtban â gyors lapozÃ¡snÃ¡l nem halmozÃ³dnak az elavult kÃ©rÃ©sek. Ha a folyamat Ã¶sszeomlik, Ãºjraindul; ha egyÃ¡ltalÃ¡n nem indul (vagy a PDF jelszÃ³val vÃ©dett), a nÃ©zet a programon belÃ¼l renderel, mint rÃ©gen.
- **Egy oldal kÃ©p oldalankÃ©nt:** minden oldal egyszer, kb. dupla nÃ©zetmÃ©retben renderelÅdik; az ez alatti zoomszintek Ã©s a miniatÅ±rÃ¶k csak Ã¡tmÃ©retezÃ©ssel kÃ©szÃ¼lnek belÅle. Egy oldal kÃ©pei tehÃ¡t egyszer bontÃ³dnak ki â zoomszintenkÃ©nt Ã©s miniatÅ±renkÃ©nt kÃ¼lÃ¶n helyett.
- **ErÅs zoom csak a lÃ¡thatÃ³ rÃ©szt rendereli,** pixel pontosan elforgatott nÃ©zetben is. 400 %-nÃ¡l az oldal rÃ¶viden Ã©letlen, majd Ã©les (korÃ¡bban felnagyÃ­tott Ã©s Ã©letlen maradt).
- **Ugyanarra a fÃ¡jlba mentÃ©s Windowson is megy:** a fÃ¡jl a memÃ³riÃ¡ba olvasÃ³dik Ã©s lemezre szabadon marad.
- **SzerkesztÅ mÃ³d:** hÃºzÃ¡s kÃ¶zben az objektum fÃ©lig Ã¡tlÃ¡tszÃ³an fut vele; alkalmazÃ¡s utÃ¡n a rÃ©gi kÃ©pek helyÅrzÅkÃ©nt maradnak Ã©s a hÃ¡ttÃ©rben megÃºjulnak, elÅszÃ¶r a szerkesztett oldal. KorÃ¡bban minden elfehÃ©redett, Ã©s az Ã¶sszes miniatÅ±rt a fÅablakban rendereltÃ©k Ãºjra.
- **Az automatikus ellenÅrzÃ©s a vÃ¡ltozatlan fÃ¡jlokat kÃ¶zvetlenÃ¼l olvassa** â megnyitÃ¡skor elmarad az ÃºjmentÃ©s a fÅablakban.
- Hiba beszÅ±kÃ­tÃ©se: `PASSERMARK_RENDER=local` beÃ¡llÃ­tÃ¡ssal minden Ãºgy mÅ±kÃ¶dik, mint elÅtte â Ã­gy gyorsan kiderÃ¼l, hogy az Ãºj renderfolyamat-e az ok.
- Ismert korlÃ¡t: objektum elengedÃ©se szerkesztÅ mÃ³dban nehÃ©z oldalakon mÃ©g kb. 1 s (a biztonsÃ¡gi ellenÅrzÃ©s hasonlÃ­tja Ã¶ssze az oldalt elÅtte Ã©s utÃ¡na). TÃ¶bb oldalon hasznÃ¡lt elem egy mÃ³dosÃ­tÃ¡ssal mindenhol vÃ¡ltozhat, ezÃ©rt szerkesztÃ©s utÃ¡n az Ã¶sszes oldal a hÃ¡ttÃ©rben Ãºjra renderelÅdik, elÅszÃ¶r a szerkesztett.

## 1.12.6
### ElÅellenÅrzÃ©s (preflight) mÃ³dosÃ­tÃ¡sok
- Kis mÃ³dosÃ­tÃ¡sok a âFÃ¡jlmÃ©ret csÃ¶kkentÃ©se" (`shrink`) funkciÃ³n Ã©s az elÅellenÅrzÃ©seken; fordÃ­tÃ¡sok kiegÃ©szÃ­tve; a CLI-kÃ©zikÃ¶nyv (DE/EN) frissÃ­tve.

## 1.12.5
### Licencek
- A telepÃ­tÅ Ã©s az AppImage mostantÃ³l minden harmadik fÃ©lre vonatkozÃ³ licencmegjegyzÃ©st tartalmaz (Python-csomagok, Qt LGPL-3.0, Ghostscript AGPL-3.0 forrÃ¡shivatkozÃ¡ssal, csomagolt rendszerkÃ¶nyvtÃ¡rak), megtekinthetÅk az Ãºj SÃºgÃ³ â Licencek menÃ¼ben.
- README-k: Ãºj szakasz a harmadik felek licenceirÅl, a forrÃ¡skÃ³d kÃ©rÃ©sre elÃ©rhetÅ.
### DokumentÃ¡ciÃ³
- A CLI-kÃ©zikÃ¶nyv (DE/EN) frissÃ¼lt a `shrink` Ã©s a `flatten_softmask` paranccsal.

## 1.12.4
### FÃ¡jlmÃ©ret csÃ¶kkentÃ©se (Ãºj)
- ElÃ©rhetÅ a âFÃ¡jlmÃ©ret" fÃ¼lrÅl vagy a Dokumentum â âFÃ¡jlmÃ©ret csÃ¶kkentÃ©seâ¦" menÃ¼bÅl, olyan fÃ¡jloknÃ¡l is, amelyek nincsenek tÃºl nagykÃ©nt megjelÃ¶lve.
- Minden intÃ©zkedÃ©s kÃ¼lÃ¶n be- Ã©s kikapcsolhatÃ³:
  - **VesztesÃ©gmentes, alapÃ©rtelmezetten bekapcsolva:** ÃºjraÃ­rÃ¡s (a rÃ©gi mentett verziÃ³kat eldobja), nem hasznÃ¡lt erÅforrÃ¡sok eltÃ¡volÃ­tÃ¡sa, duplikÃ¡tumok egyesÃ­tÃ©se (betÅ±tÃ­pusok, kÃ©pek, ICC-profilok), szerkesztÃ©si adatok Ã©s miniatÅ±rÃ¶k eltÃ¡volÃ­tÃ¡sa, kÃ©pek vesztesÃ©gmentes ÃºjrakomprimÃ¡lÃ¡sa (a JPEG kÃ¶rÃ¼li ZIP-et is eltÃ¡volÃ­tja, ha kisebb lesz tÅle).
  - **AlapÃ©rtelmezetten kikapcsolva:** 16 â 8 bit, mellÃ©kletek eltÃ¡volÃ­tÃ¡sa, rejtett rÃ©tegek tartalmÃ¡nak eltÃ¡volÃ­tÃ¡sa.
  - **OpcionÃ¡lis lemintÃ¡zÃ¡s:** 300/240/150/100 dpi-re kÃ¼szÃ¶bbel Ã©s JPEG-minÅsÃ©ggel, a legnagyobb elhelyezÃ©snÃ©l mÃ©rve. A soft maszkok egyÃ¼tt skÃ¡lÃ¡zÃ³dnak.
- Az eredmÃ©ny Ãºj ablakban nyÃ­lik meg, az eredet vÃ¡ltozatlan marad. Ha az eredmÃ©ny nem kisebb, a fÃ¡jl marad, ahogy van.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 â¦]`
- PÃ©lda: egy 34 MB-os fÃ¡jl a 90-szer beÃ¡gyazott, azonos CMYK-profillal 0,5 MB-ra csÃ¶kkent, pixelre azonosan.

## 1.12.3
### ElÅellenÅrzÃ©s (preflight)
- **Ãj fÃ¼l âFÃ¡jlmÃ©ret":** megmutatja, hovÃ¡ mennek a bÃ¡jtok: kÃ©pek, betÅ±tÃ­pusok, szÃ­nprofilok, Illustrator-/Photoshop-szerkesztÃ©si adatok, miniatÅ±rÃ¶k, mellÃ©kletek, oldaltartalom.
  - Felsorolja tovÃ¡bbÃ¡ a rÃ©gi mentett verziÃ³kat, a duplikÃ¡tumokat Ã©s a legnagyobb kÃ©peket effektÃ­v dpi-jÃ¼kkel.
  - Figyelmeztet a nagyon nagy fÃ¡jlokra (A4-es felÃ¼letenkÃ©nt tÃ¶bb mint 20 MB) Ã©s a nagy duplikÃ¡tumokra.

## 1.12.2
### ElÅellenÅrzÃ©s (preflight)
- **ÃtlÃ¡tszÃ³ Ã¡tmenetek (soft mask a mintÃ¡ban):** felismerhetÅk Ã©s javÃ­thatÃ³k. NÃ©hÃ¡ny RIP/plotter fekete felÃ¼ltkÃ©nt nyomtatja Åket, amely letakarja az alatta lÃ©vÅ kÃ©peket. Az Ãºj javÃ­tÃ¡s âÃtlÃ¡tszÃ³ Ã¡tmenetek kÃ©ppÃ© alakÃ­tÃ¡sa (300 dpi)" csak az Ã©rintett Ã¡tmeneteket rendereli, az alatta lÃ©vÅkkel egyÃ¼tt, fedÅ kÃ©pkÃ©nt. A felÃ¼l lÃ©vÅ szÃ¶veg Ã©s vektorok sÃ©rtetlenek maradnak. Ghostscript nem szÃ¼ksÃ©ges.
- **HDR-fotÃ³k (gain map):** a mobilos HDR-fotÃ³, amely mindkÃ©t kÃ©ppel megnyitva volt, most felismerÃ©sre kerÃ¼l az ellenÅrzÃ©sben. JavÃ­tÃ¡s: âHDR-segÃ©dlapok eltÃ¡volÃ­tÃ¡sa â¦", vÃ¡laszthatÃ³ mÃ©rettel Ã©s opcionÃ¡lis gain-map-egyesÃ­tÃ©ssel.
- **Ãj fÃ¼l âKÃ©pek Ã©s szÃ­nek":**
  - SzÃ­ntÃ©r kÃ©p Ã©s oldal szerint (RGB, CMYK, szÃ¼rkeÃ¡rnyalat, direkt szÃ­nek), a pontos ICC-profilnÃ©vvel Ã©s a kimeneti szÃ­ntÃ©rrel (output intent).
  - EffektÃ­v felbontÃ¡s elhelyezÃ©senkÃ©nt, tÃ¶bbszÃ¶r hasznÃ¡lt vagy Å±rlapokon (XObjectek) belÃ¼li kÃ©peknÃ©l is.
  - AjÃ¡nlott legnagyobb mÃ©ret 300 Ã©s 150 dpi-nÃ©l, valamint az oldalankÃ©nti maximÃ¡lis mÃ©retezÃ©s.
  - FigyelmeztetÃ©sek alacsony felbontÃ¡snÃ¡l, informÃ¡ciÃ³k RGB-tartalomrÃ³l Ã©s direkt szÃ­nekrÅl.

## 1.12.1
- **SzerkesztÃ©s: tÃ¶bb objektum Ã©s sor egyszerre.** A âMÃ©retezÃ©s / mozgatÃ¡s â¦â, âObjektum tÃ¶rlÃ©seâ,
  âAlkalmazâ (betÅ±tÃ­pus Ã©s mÃ©ret) Ã©s âSor tÃ¶rlÃ©seâ most az Ã¶sszes kivÃ¡lasztott objektumra vagy
  sorra hat, nem csak egyre. TÃ¶bb sor kijelÃ¶lÃ©sekor a szÃ¶vegmezÅ zÃ¡rolva van â szÃ¶veget csak egy
  sornÃ¡l lehet vÃ¡ltoztatni
- **SzerkesztÃ©s: szÃ­n mÃ³dosÃ­tÃ¡sa.** Ãj âSzÃ­n â¦â gomb szÃ¶vegsorokhoz Ã©s vektorobjektumokhoz,
  vÃ¡laszthatÃ³an CMYK (alapÃ©rtelmezÃ©s, nyomdÃ¡hoz) vagy RGB; vektoroknÃ¡l a kitÃ¶ltÃ©s Ã©s a kÃ¶rvonal
  kÃ¼lÃ¶n-kÃ¼lÃ¶n Ã¡llÃ­thatÃ³. A 0/0/0/100 feketÃ©je tiszta fekete marad. A szÃ­n kÃ¶zvetlenÃ¼l az oldal
  tartalmÃ¡ban kerÃ¼l beÃ¡llÃ­tÃ¡sra â a kijelÃ¶lÃ©sen kÃ­vÃ¼l minden Ã©rintetlen marad, azok az objektumok
  is, amelyek csak Ã¶rÃ¶kÃ¶ltÃ©k a szÃ­nÃ¼ket
- **SzerkesztÃ©s: Ã¡ttekintÃ©s.** A lapok darabszÃ¡mot mutatnak (âSzÃ¶veg (12)â, âObjektumok (40)â); az
  âObjektumokâ lapon vektorokra vagy kÃ©pekre szÅ±rhetÅ a lista, tÃ­pusonkÃ©nti darabszÃ¡mmal. AktÃ­v
  szÅ±rÅnÃ©l az oldalra kattintÃ¡s csak az adott tÃ­pust jelÃ¶li ki
- **HDR telefonfotÃ³k (iPhone, Android) felismerÃ©se.** Az ilyen JPG-k a fotÃ³ mellett szÃ¼rke
  fÃ©nyerÅ-tÃ©rkÃ©pet tartalmaznak a HDR-kijelzÅkhÃ¶z. KorÃ¡bban ebbÅl mÃ¡s mÃ©retÅ± mÃ¡sodik lap lett â
  hibÃ¡s szÃ­nekkel a plotternÃ©l. Most nyitÃ¡skor figyelmeztetÃ©s jelenik meg; a âJavÃ­tÃ¡sâ egy lapot
  ad az vÃ¡ltozatlan fotÃ³val, a mÃ©ret vÃ¡laszthatÃ³ (mint a kiegÃ©szÃ­tÅ kÃ©p, vagy ahogy a fotÃ³ban
  tÃ¡rolva van). A fÃ©nyerÅ-tÃ©rkÃ©pet szÃ¼ksÃ©g szerint be lehet szÃ¡mÃ­tani. RÃ¡kÃ©rdezÃ©s nÃ©lkÃ¼l (parancssor,
  kÃ¶zvetlen nyomtatÃ¡s) automatikus a javÃ­tÃ¡s
- **JavÃ­tva: Ã­v-szÃ¶veg betÅ±mÃ©rete.** A mÃ³dosÃ­tÃ¡s utÃ¡n a lista tovÃ¡bbra is a rÃ©gi mÃ©retet mutatta,
  Ã©s minden tovÃ¡bbi mÃ³dosÃ­tÃ¡s Ãºjra nagyÃ­tott (24 â 36 â 54 pt). Most a tÃ©nyleges mÃ©ret jelenik meg;
  a kevÃ©s betÅ±t tartalmazÃ³ rÃ¶vid Ã­vek is kÃ¶rÃ­v-szÃ¶vegkÃ©nt ismerÅdnek fel. A vÃ¡ltoztatÃ¡s nÃ©lkÃ¼li
  âAlkalmazâ Ã©rintetlenÃ¼l hagyja az oldalt
- **JavÃ­tva: Z-sorrend.** A legfelsÅ objektumon az âegy lÃ©pÃ©s elÅreâ tÃ©vesen âaz oldal szerkezete
  nem ismerhetÅ felâ hibÃ¡t jelzett â most egyszerÅ±en minden marad, ahogy van
- **JavÃ­tva: szÃ¶veg egÃ©rrel hÃºzÃ¡sa** nÃ©hÃ¡ny PDF-nÃ©l (pl. Chrome-bÃ³l) hibaÃ¼zenettel megszakadt
- FordÃ­tÃ¡sok kiegÃ©szÃ­tve a haszon-elrendezÃ©shez a nyomtatÃ¡si pÃ¡rbeszÃ©dablakban (angol, magyar,
  spanyol, francia)

## 1.11.3
- **VDP-pÃ¡rbeszÃ©dablak felfrissÃ­tve.** A vÃ¡ltozÃ³ adatok ugyanÃºgy nÃ©znek ki, mint a nyomtatÃ¡si
  pÃ¡rbeszÃ©dablak: nÃ©gy szÃ¡mozott, Ã¶sszecsukhatÃ³ szakasz (mezÅk, adatok, szÃ¡mozÃ¡s, kimenet),
  felÃ¼l pedig egy Ã¶sszecsukott âÃtmutatÃ³â. A mezÅmagyarÃ¡zatok most tooltipkÃ©nt Ã©lnek, Ã©s csak az
  Ãºj âSÃºgÃ³szÃ¶vegek megjelenÃ­tÃ©seâ kapcsolÃ³val jelennek meg a mezÅ alatt. Az elavult kimeneti
  ÃºtmutatÃ³ most a nyomtatÃ¡si pÃ¡rbeszÃ©dablak sorrendjÃ©re mutat (HaszonmintÃ¡k, âMinden haszonra a
  kÃ¶vetkezÅ oldalâ). A CollapsibleSection widget kÃ¶zÃ¶sen a common.py-ban Ã©l.
- **NyomtatÃ¡si pÃ¡rbeszÃ©dpanel fÃ¼lek nÃ©lkÃ¼l.** A fenti mÃ³dvÃ¡lasztÃ³ (âMit nyomtassunk?") egyetlen,
  folytonos oszlopban vezet vÃ©gig a pÃ¡rbeszÃ©dpanelen: preset, mÃ³d, mÃ³dpanel, skÃ¡lÃ¡zÃ¡s (âHogyan
  az Ã­vre?"), vÃ¡gÃ³jel, papÃ­r/kimenet, finisher, szÃ­nkezelÃ©s. A korÃ¡bbi fÃ¼l-navigÃ¡ciÃ³ megszÅ±nt.
- **A Step & Repeat sajÃ¡t mÃ³d.** A âNutzen" a tÃ¶bbi mÃ³d mellett Ã¡ll az vÃ¡lasztÃ³ban (egyedi Ã­vek,
  tÃ¶bb Ã­ven, fÃ¼zet, poszter) â a tÃ¶bbi mÃ³dhoz hasonlÃ³ magyarÃ¡zÃ³ szÃ¶veggel. A rÃ©gi jelÃ¶lÅnÃ©gyzetet a
  mÃ³d-gomb vÃ¡ltotta ki; a Nutzen-panel ott jelenik meg, ahol a tÃ¶bbi mÃ³dpanel.
- **âHogyan az Ã­vre?"** a skÃ¡lÃ¡zÃ¡s Ã©s a tÃ¡jolÃ¡s most egy csoport: illesztÃ©s/eredeti mÃ©ret/kicsinyÃ­tÃ©s/
  egyÃ©ni, forgatÃ¡s, automatikus forgatÃ¡s, kÃ¶zÃ©pre igazÃ­tÃ¡s, margÃ³k. A skÃ¡lÃ¡zÃ¡svÃ¡lasztÃ¡s minden
  nyomtatÃ¡si mÃ³dban lÃ¡thatÃ³ Ã©s hatÃ¡sos: illesztÃ©s = mÃ³d-alapÃ©rtÃ©k, eredeti mÃ©ret/kicsinyÃ­tÃ©s/egyÃ©ni
  felÃ¼lÃ­rja a mÃ³d skÃ¡lÃ¡zÃ¡sÃ¡t â a mÃ³dmezÅk (kachel-skÃ¡lÃ¡zÃ¡s, Nutzen-mÃ©rtÃ©k, poszter) megmaradnak.
- **TÃ¼krÃ¶zÃ©s Ã©s meghajtÃ³-beÃ¡llÃ­tÃ¡sok Ã¶sszecsukhatÃ³k.** MindkÃ©t szakasz jÃ³l lÃ¡thatÃ³ cÃ­mmel megmarad,
  Ã©s csak szÃ¼ksÃ©g esetÃ©n nyithatÃ³ ki â minden beÃ¡llÃ­tÃ¡s vÃ¡ltozatlanul.
- **FÃ¼zetkÃ¶tÃ©s: âStandard" elÅszÃ¶r.** A klasszikus gerinctÅ±zÃ©s (âminden Ã­v egymÃ¡sba, egyszeri
  behajtÃ¡s") a âStandard" nÃ©ven vezeti a kÃ¶tÃ©smÃ³d-listÃ¡t â az âÃ­v mÅ±venkÃ©nt" szÃ¡mlÃ¡lÃ³ csak a
  âCsoportos Ã­vmÅ±veknÃ©l" jelenik meg, Ã­gy nem sugallhat Ã©rtelmetlen beÃ¡llÃ­tÃ¡st.
- **EgysÃ©ges Ã¶sszecsukhatÃ³ szakaszok.** Az Ãºj oszlop minden blokkja â preset, mÃ³dvÃ¡lasztÃ³
  (âMit nyomtassunk?"), âHogyan az Ã­re?", vÃ¡gÃ³jel, papÃ­r/kimenet, finisher, szÃ­nkezelÃ©s, tÃ¼krÃ¶zÃ©s,
  meghajtÃ³ â azonos mÃ©retÅ±, Ã¶sszecsukhatÃ³ cÃ­msort kap. A mÃ³d-gombok egymÃ¡s alatt Ã¡llnak, Ã­gy minden
  felirat olvashatÃ³ maradt; a mÃ³dpanel a lÃ¡thatÃ³ mÃ³d mÃ©retÃ©re zsugorodik (nincs Ã¼res hely). A Nutzen
  mÃ³dbÃ³l bÃ¡rmikor mÃ¡s mÃ³dra vÃ¡lthatÃ³.
- **FordÃ­tÃ¡sok:** 26 Ãºj/kiegÃ©szÃ­tett Ã¼zenet nyelvenkÃ©nt (EN/DE/ES/FR/HU); az ES/FR/HU/EN
  Ã¼zenetkatalÃ³gusokbÃ³l hiÃ¡nyzÃ³ 1.11.1-sztringek utÃ¡napÃ³tlÃ¡sa. A rÃ©gi presetek teljesen kompatibilisek
  maradnak (size/multiple/sr handling tovÃ¡bbra is betÃ¶lt).

## 1.11.2
- **2. lÃ©pÃ©s: az Ã­v Ãºjra montÃ­rozÃ¡sa.** Az elkÃ©szÃ¼lt 1. lÃ©pÃ©s Ã­v mÃ¡sodszor is egy szabadon vÃ¡lasztott
  cÃ©lformÃ¡tumra kerÃ¼l (eszkÃ¶zformÃ¡tumok vagy sajÃ¡t mÃ©retek mm-ben) â sorrÃ³l sorra, mindig kÃ¶zÃ©pre, a
  tartalom vÃ¡ltozatlanul; az eredmÃ©ny gombbal Ãºj dokumentumkÃ©nt adhatÃ³ ki (Ãºj lap), az elÅnÃ©zet az
  1. lÃ©pÃ©shez hasonlÃ³an mutatja, Ã©s a pÃ¡rbeszÃ©dablak ezutÃ¡n bezÃ¡rul. Az 1. lÃ©pÃ©s elfordÃ­tÃ¡sa Ã©s tÃ¡jolÃ¡sa
  a 2. lÃ©pÃ©sre is Ã©rvÃ©nyes. RÃ¡cs: 0 Ã 0 = automatikus (amennyi csak fÃ©r).
- **MeglÃ©vÅ vÃ¡gÃ³jelÃ¶lÃ©sek hasznÃ¡lata.** VÃ¡gott formÃ¡tumÃº (TrimBox) dokumentumoknÃ¡l a haszonmintablokk
  kÃ¼lsÅ oldalai a dokumentum valÃ³di szÃ©lÃ©t mutatjÃ¡k â a meglÃ©vÅ vÃ¡gÃ³jelÃ¶lÃ©sek lÃ¡thatÃ³ak maradnak; a sajÃ¡t
  jelÃ¶lÃ©sek tovÃ¡bbra is jelÃ¶lÅnÃ©gyzettel kapcsolhatÃ³k be.
- **A rÃ¡cs pontos montÃ­rozÃ¡sa.** Egy definiÃ¡lt rÃ¡cs (pl. 3 Ã 3) az 1. Ã©s a 2. lÃ©pÃ©sben is pontos marad â
  ha nem fÃ©r az Ã­vre, szimmetrikusan a szÃ©lÃ©n levÃ¡gÃ¡sra kerÃ¼l figyelmeztetÃ©ssel, sosem szakad meg.
- **MargÃ³k nÃ©lkÃ¼l tervezett cÃ©lformÃ¡tum:** pl. kÃ©t A4-es Ã­v az 1. lÃ©pÃ©sbÅl tisztÃ¡n fÃ©r egy A3-ra.
- Az 1. lÃ©pÃ©s nyomtatÃ¡si Ãºtvonala Ã©s tÃ¡jolÃ¡sa vÃ¡ltozatlan marad.

## 1.11.1
- **Egyedi formÃ¡tumok: csak Â«MentÃ©s PDF-kÃ©ntÂ».** A sajÃ¡t formÃ¡tumok tÃ¶bbÃ© nem kerÃ¼lnek elkÃ¼ldÃ©sre a nyomtatÃ³knak â
  a Windows-illesztÅk Ã©s spoolerek gyakran nem fogadjÃ¡k el az egyedi mÃ©reteket (Ã¼res lapok, megszakÃ­tÃ¡sok);
  Â«MentÃ©s PDF-kÃ©ntÂ» (â) esetÃ©n tovÃ¡bbra is teljesen hasznÃ¡lhatÃ³k
- **VÃ¡gÃ¡s: kÃ©t Ãºj mÃ³d.** âSzÃ©lek levÃ¡gÃ¡saâ: a lap levÃ¡gÃ¡sa mind a nÃ©gy oldalon mm-ben, cÃ©lformÃ¡tum nÃ©lkÃ¼l;
  âFehÃ©r tÃ©r eltÃ¡volÃ­tÃ¡saâ: felismeri a lÃ¡thatÃ³ tartalmat (JPEG-zajjal egyÃ¼tt), az Ãºj lapmÃ©ret a tartalomkeret
  Â± margÃ³bÃ³l adÃ³dik (negatÃ­v is lehet), a tartalom 1:1 marad (csak eltolva)

## 1.11.0
- **VÃ¡ltozÃ³ adatok â ablakok (oldalcsoportok).** TÃ¶bb oldalas sablonoknÃ¡l minden mezÅ egy ablakhoz tartozik
  (pl. âelÃ¶lapok (nÃ©v), hÃ¡tlapok (QR-kÃ³d)â); az ablakok lÃ©trehozhatÃ³k, Ã¡tnevezhetÅk Ã©s eltÃ¡volÃ­thatÃ³k â
  mezÅik ekkor az elsÅ ablakba kerÃ¼lnek. OldalkivÃ¡lasztÃ¡s ablakonkÃ©nt: minden oldal, pÃ¡ratlan (elÃ¶lapok),
  pÃ¡ros (hÃ¡tlapok) vagy tartomÃ¡nyok (â1,3-5 vagy pÃ¡ratlan 1-50â); sajÃ¡t kivÃ¡lasztÃ¡s nÃ©lkÃ¼l a âminden oldalâ
  alaprÃ©teg Ã©rvÃ©nyes. Rekord-elosztÃ¡s âlaprÃ³l lapraâ (elÅszÃ¶r az Ã¶sszes oldal az 1. rekorddal) vagy
  âoldalrÃ³l oldalraâ (elÅszÃ¶r az 1. oldal az Ã¶sszes rekorddal); kijelzÃ©s â{0} rekord â {1} oldalâ, figyelmeztetÃ©s
  ââ {0} oldal ablak nÃ©lkÃ¼l!â
- **VDP-elÅnÃ©zet:** vÃ¡gott formÃ¡tum zÃ¶ld, vÃ©rzÃ©s piros; Ã¡llÃ­thatÃ³ belsÅ keret (segÃ©dvonal) a kettÅ kÃ¶zÃ¶tt
- **âaktuÃ¡lis / Ã¶sszesenâ oldaljelzÅ** az eszkÃ¶zsÃ¡vban; oldalszÃ¡m beÃ­rÃ¡sa Ã©s Enter â azonnali ugrÃ¡s
- **VonalzÃ³k, mÃ©rÃ©s Ã©s vÃ¡gott-formÃ¡tum-megjelenÃ­tÃ©s Ã¡llandÃ³an a fÅ eszkÃ¶zsÃ¡vban** â minden munkaterÃ¼leten
- **VÃ¡gott formÃ¡tum Ã©s vÃ©rzÃ©s a fÅ nÃ©zetben:** belsÅ hatÃ¡rvonal (vÃ¡gott formÃ¡tum) zÃ¶ld, vÃ©rzÃ©s diszkrÃ©t piros
  pontvonalkÃ©nt teljes piros felÃ¼let helyett
- **MÃ©rÃ©s illesztÃ©ssel:** Control lenyomva a cÃ©lkereszt mÃ¡gnesesen illeszkedik a vÃ¡gÃ³- Ã©s belsÅ vonalakhoz
  (oldalszÃ©l, vÃ¡gott formÃ¡tum, vÃ©rzÃ©s), kÃ©pszÃ©lekhez Ã©s vektorvonalakhoz â szÃ¶vegre soha. Az elÅnÃ©zeti
  cÃ©lkeresett addig tapad az Ã©lhez, amÃ­g az egÃ©r hatÃ¡rozottan el nem hÃºzza; a Shift tovÃ¡bbra is
  vÃ­zszintes/fÃ¼ggÅleges/45Â°-ra zÃ¡rol

## 1.10.7
- **CutContour: alapformÃ¡k szÃ¡mÃ­tÃ¡s nÃ©lkÃ¼l.** Ãj elhelyezÃ©s âA vÃ©gformÃ¡ra (szÃ¡mÃ­tÃ¡s nÃ©lkÃ¼l)â: tÃ©glalap,
  lekerekÃ­tett tÃ©glalap, kÃ¶r â¦ kÃ¶zvetlenÃ¼l a vÃ©gformÃ¡ra kerÃ¼lnek (TrimBox, egyÃ©bkÃ©nt az oldalra) â nincs
  renderelÃ©s, nincs motÃ­vumfelismerÃ©s, nincsenek munkafolyamatok, mÃ¡sodperc tÃ¶rtderekÃ©ben. A tÃ¡volsÃ¡g, a
  mÃ©ret, az eltolÃ¡s Ã©s az egÃ©rrel hÃºzÃ¡s a megszokott mÃ³don mÅ±kÃ¶dik. SzÃ¡mÃ­tÃ¡s csak âKontÃºrâ esetÃ©n vagy ha a
  forma a motÃ­vum kÃ¶rÃ© illetve objektumonkÃ©nt kerÃ¼l. Parancssor: `--set fit=trim`
- **AlapÃ©rtelmezÃ©s a CutContourban:** tÃ©glalap a vÃ©gformÃ¡ra (amÃ­g nincsenek tÃ¡rolt, egyÃ©ni utoljÃ¡ra hasznÃ¡lt
  beÃ¡llÃ­tÃ¡sok)

## 1.10.6
- **Windows javÃ­tÃ¡s: a CutContour 0 %-nÃ¡l elakadt** (az 1.10.5 Ã³ta). A parancssori kimenet UTF-8-ra
  vÃ¡ltÃ¡sÃ¡t visszavontuk; a âLapok felosztÃ¡saâ javÃ­tÃ¡s megmarad (az Ã¡llapotÃ¼zenetek tisztÃ¡n ASCII-ben)
- CutContour: nincs tÃ¶bb hiba, ha az ablak bezÃ¡rÃ¡sakor mÃ©g utolÃ©r egy elÅnÃ©zeti szÃ¡mÃ­tÃ¡s
  (âexpected LP_struct_fpdf_document_t â¦ NoneTypeâ)

## 1.10.5
- **Windows javÃ­tÃ¡s:** a âLapok felosztÃ¡saâ (Ã©s minden olyan feladat, melynek Ã¼zenete olyan karaktert tartalmaz, mint az âââ) a
  `UnicodeEncodeError â¦ cp1252` hibÃ¡val megszakadt. A parancssor most maga Ã¡llÃ­tja Ã¡t a kimenetÃ©t UTF-8-ra, a
  felhasznÃ¡lÃ³i felÃ¼let felÃ© menÅ Ã¡llapotÃ¼zenetek tisztÃ¡n ASCII-ben
- `SECURITY.md`, `CONTRIBUTING.md` Ã©s a GitHub-sablonok hibajelentÃ©sekhez Ã©s javaslatokhoz a csomagban

## 1.10.4
- KÃ©tnyelvÅ± README: `README.md` (angol) Ã©s `README.de.md` (nÃ©met), naprakÃ©szen (lapok felosztÃ¡sa, vÃ¡ltozÃ³
  adatok, adatok rÃ¶gzÃ­tÃ©se, a parancssor Ã¶sszes feladata), a projekt Ã¡llapotÃ¡ra vonatkozÃ³ megjegyzÃ©ssel
- PÃ©ldakonfigurÃ¡ciÃ³ `data/defaults.example.json` semleges nyomtatÃ³nevekkel

## 1.10.3
- **Lapok felosztÃ¡sa jobb egÃ©rgombbal:** lapok kijelÃ¶lÃ©se az oldalsÃ¡vban â jobb egÃ©rgomb â **FelosztÃ¡s** â
  âFelezÃ©s fÃ¼ggÅlegesenâ / âFelezÃ©s vÃ­zszintesenâ â azonnal, csak a kijelÃ¶lt lapokon, Ã¶sszehasonlÃ­tÃ³ lap
  nÃ©lkÃ¼l. A âRÃ¡cs / tovÃ¡bbi beÃ¡llÃ­tÃ¡sok â¦â megnyitja a pÃ¡rbeszÃ©dablakot elÅre beÃ¡llÃ­tott kijelÃ¶lÃ©ssel

## 1.10.2
- **VÃ¡ltozÃ³ adatok â elÅ Ã©s hÃ¡tlap:** Ãºj âLapok rekordonkÃ©ntâ (a 2. alatt): 2 = 1+2. lap â 1. rekord, 3+4 â
  2. rekord â¦ â fÃ¼ggetlenÃ¼l attÃ³l, hogy a sablon 2 oldalas vagy mÃ¡r az Ã¶sszes kÃ¡rtyÃ¡t tartalmazza (pl. 200 lap
  100 nÃ©vjegykÃ¡rtyÃ¡hoz). A âCsak ezeken a lapokonâ mezÅk most ismerik a **pÃ¡ratlan** Ã©s **pÃ¡ros**
  lapokat, tartomÃ¡nyokkal is kombinÃ¡lva (âpÃ¡ratlan 1-50â). 7. pÃ©lda: nÃ©vjegykÃ¡rlya nÃ©vvel elÃ¶l Ã©s QR-nÃ©vjegykÃ¡rtyÃ¡val hÃ¡tul
- **TovÃ¡bbi vÃ¡ltozÃ³k:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. A tartalom melletti **?**
  gomb mindegyiket megjelenÃ­ti pÃ©ldaÃ©rtÃ©kkel, dupla kattintÃ¡ssal beszÃºrhatÃ³. Az azonos nevÅ± CSV-oszlopok
  elsÅbbsÃ©get Ã©lveznek
- Egy oszlopra duplÃ¡n kattintva az vÃ¡ltozatlan {{nr}} **cserÃ©je** tÃ¶rtÃ©nik, nem elÃ©helyezÃ©se
- **Lapok felosztÃ¡sa** (Lapok â Lapok felosztÃ¡sa â¦, SzerkesztÃ©s munkaterÃ¼let): felezÃ©s fÃ¼ggÅlegesen/
  vÃ­zszintesen vagy rÃ¡cs, Ã¶sszes/jelenlegi/kijelÃ¶lt lap vagy tartomÃ¡ny, csak terjedelmek, sorrend
  jobbrÃ³lâbalra; a vÃ¡gÃ¡si vonalak elÅnÃ©zetÃ©vel. **Terjedelmek felosztÃ¡sa** egy kattintÃ¡ssal a hibÃ¡san
  exportÃ¡lt fÃ¼zetekhez. VesztesÃ©gmentes (a tartalom nem kerÃ¼l mÃ¡solÃ¡sra vagy raszterezÃ©sre), a forgatott
  lapok Ãºgy, ahogy lÃ¡tod Åket; vÃ©gformÃ¡n belÃ¼l van a felosztÃ¡s, a levÃ¡gÃ¡s (Anschnitt) kÃ­vÃ¼l marad.
  Parancssor: `split` feladat
- **OldalsÃ¡v:** a miniatÅ±rÃ¶k egyÃ¼tt forognak a âNÃ©zet forgatÃ¡sa balra/jobbraâ funkciÃ³val
- **JavÃ­tva: a kÃ­vÃ¼lrÅl megnyitÃ¡s zÃ¡rt ablakba kerÃ¼lt** (Windows, jobb egÃ©rgomb/dupla kattintÃ¡s, mikÃ¶zben
  egy ablakban egy eszkÃ¶z nyitva van) â most sajÃ¡t ablakba. Ok: a megnyitÃ¡s az Ã¼res kezdÅablakban lÃ¡thatatlan
  Ã¼res fÃ¼let hagyott hÃ¡tra; most maga az Ã¼res ablak hasznÃ¡latos. A zÃ¡rt ablak eredmÃ©nyei is sajÃ¡t ablakban
  nyÃ­lnak meg

## 1.10.1
- **SajÃ¡t CSV mÃ¡s oszlopnevekkel, kÃ¶zvetlenÃ¼l:** VÃ¡ltozÃ³ adatok â CSV megnyitÃ¡sa felismeri, mihez illik a
  tÃ¡blÃ¡zat (âA tÃ¡blÃ¡zat illik: QR â nÃ©vjegykÃ¡rlyaâ), a **IlleszkedÅ mezÅ lÃ©trehozÃ¡sa** lÃ©trehozza a QR-kÃ³dot
  ezzel a tÃ­pussal. Az oszlopok automatikusan hozzÃ¡rendelÃ©sre kerÃ¼lnek â angol, magyar, spanyol, francia
  nevek Ã©s az **Outlook, Google Ã©s Thunderbird** kapcsolatexportjainak fejlÃ©cei is. A CSV vÃ¡ltozatlan marad
- **Oszlopok hozzÃ¡rendelÃ©se â¦** a QR-mezÅben tÃ­pussal: oszlop vÃ¡lasztÃ¡sa adatonkÃ©nt, âÃ¼resen hagyÃ¡sâ vagy
  automatikus; a kÃ©sz tartalom elÅnÃ©zetÃ©vel. A tÃ­pus alatt Ã¡ll, mi honnan jÃ¶n Ã©s mi hiÃ¡nyzik. A hozzÃ¡rendelÃ©s
  a presetben tÃ¡rolÃ³dik (`qr_map`) Ã©s a parancssoron is Ã©rvÃ©nyes
- Adatok rÃ¶gzÃ­tÃ©se: a idegen nevÅ± CSV nem kap tÃ¶bbÃ© dupla oszlopokat; a fejlÃ©c mutatja a hozzÃ¡rendelÃ©st
  (âFirst Name â Vornameâ). A `datencheck` szintÃ©n felismeri az idegen oszlopneveket
- PÃ©ldamappa: `kontakte-outlook.csv` (Ã­gy nÃ©z ki egy Outlook-export); az ÃºtmutatÃ³ kiegÃ©szÃ­tve a âSajÃ¡t CSV
  mÃ¡s oszlopnevekkelâ rÃ©sszel

## 1.10.0
- **Adatok rÃ¶gzÃ­tÃ©se** (VÃ¡ltozÃ³ adatok munkaterÃ¼let, DokumentummanipulÃ¡ciÃ³ menÃ¼ vagy a VÃ¡ltozÃ³ adatok
  pÃ¡rbeszÃ©dablakban a 2. alatt): az adattÃ¡blÃ¡zat kÃ¶zvetlenÃ¼l a Passermarkban hozhatÃ³ lÃ©tre. TÃ­pusonkÃ©nt a
  megfelelÅ oszlopok â **QR-nÃ©vjegykÃ¡rlya (vCard), WLAN-hozzÃ¡fÃ©rÃ©s, e-mail, webcÃ­m, hÃ­vÃ¡s, SMS, idÅpont,
  helyszÃ­n**, szabad QR-szÃ¶veg, **Code 128**, **EAN-13**, szÃ¶veg sajÃ¡t oszlopokkal. Minden sor azonnali
  ellenÅrzÃ©sen megy Ã¡t (kÃ¶telezÅ adatok, EAN-ellenÅrzÅ szÃ¡m, umlautok a Code 128-ban, dÃ¡tum â¦), jobbra a
  kivÃ¡lasztott sor kÃ©sz kÃ³dja. BeszÃºrÃ¡s ExcelbÅl Ctrl+V-vel, sorok duplikÃ¡lÃ¡sa, oszlop kitÃ¶ltÃ©se
  szÃ¡msorral (a sorokat is lÃ©trehozza), sajÃ¡t oszlopok. MentÃ©s CSV-kÃ©nt (UTF-8 BOM-mal, pontosvesszÅvel â az
  Excel helyesen olvassa az umlautokat)
- A **âHasznÃ¡lat vÃ¡ltozÃ³ adatokbanâ** Ã¡tveszi a tÃ¡blÃ¡zatot adatforrÃ¡skÃ©nt Ã©s lÃ©trehozza a megfelelÅ mezÅt
- **QR-mezÅ âQR-kÃ³d tÃ­pusaâ:** a tartalom beÃ­rt mÃ³don vagy a tÃ¡blaoszlopokbÃ³l Ã¶sszeÃ¡llÃ­tva (vCard, WLAN,
  mailto, tel, SMS, idÅpont, geo). A CSV olvashatÃ³ marad; a Passermark a kÃ³dtartalmat a lÃ©trehozÃ¡skor
  Ã©pÃ­ti fel
- **Csendes zÃ³na:** a QR-kÃ³d Ã©s a Code 128 most fehÃ©r szegÃ©llyel rendelkezik a mezÅben (kikapcsolhatÃ³).
  NÃ©lkÃ¼le a mÃ¡s tartalomhoz kÃ¶zeli kÃ³dok rosszul olvashatÃ³k voltak. *MeglÃ©vÅ presetek: a QR-kÃ³d ettÅl kicsit
  kisebb lesz a mezÅben*
- **A 13 szÃ¡mjegyÅ±, hibÃ¡s ellenÅrzÅ szÃ¡mÃº EAN-13 most hiba** (a helyes szÃ¡mmal az Ã¼zenetben) â korÃ¡bban az
  utolsÃ³ szÃ¡mjegy csÃ¶ndben cserÃ©lt
- Parancssor: `datenarten`, `datenvorlage <tÃ­pus> [fÃ¡jl.csv]`, `datencheck <fÃ¡jl.csv> [tÃ­pus]` (1-es
  visszatÃ©rÃ©si kÃ³d problÃ©mÃ¡knÃ¡l); a presetben QR-mezÅnkÃ©nt `qr_type`
- 5. (nÃ©vjegykÃ¡rlya kapcsolatlistÃ¡bÃ³l) Ã©s 6. (WLAN-hozzÃ¡fÃ©rÃ©s) pÃ©lda; a âVÃ¡ltozÃ³ adatokâ ÃºtmutatÃ³ Ãºj
  âAdatok rÃ¶gzÃ­tÃ©seâ fejezettel, a CLI-ÃºtmutatÃ³ kiegÃ©szÃ­tve
- A tesztek most valÃ³ban visszabeolvassÃ¡k a lÃ©trehozott kÃ³dokat: QR Ã©s EAN-13 OpenCV-vel (ha telepÃ­tve), a
  Code 128 sajÃ¡t olvasÃ³val, ellenÅrzÅ Ã¶sszeggel
- JavÃ­tva: a vÃ¡ltozÃ³ adatok az elosztÃ¡s kivÃ¡lasztÃ¡sa nÃ©lkÃ¼l ârekordonkÃ©nt a teljes dokumentum mÃ¡solatÃ¡tâ
  hasznÃ¡ltÃ¡k a âminden lapon a kÃ¶vetkezÅ rekordâ helyett

