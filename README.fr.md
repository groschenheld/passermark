# Passermark 1.15.1

Visionneuse PDF, outil d'impression et boÃ®te Ã  outils de prÃ©paration prÃ©presse pour **Linux et Windows**.
Logiciel libre (GPL-3.0-or-later).

**English :** [README.md](README.md) Â· [Deutsch](README.de.md) Â· [Magyar](README.hu.md) Â· **FranÃ§ais** Â· [EspaÃ±ol](README.es.md)

> **Statut :** un projet privÃ©, dÃ©veloppÃ© Ã  cÃ´tÃ© du travail prÃ©presse quotidien. Les retours sont les
> bienvenus â les rÃ©ponses et les nouvelles fonctions sont fournies sans garantie. TestÃ© avec les pilotes
> CUPS et Windows (jet d'encre, imprimantes de bureau et de production avec finisseur via un serveur
> d'impression) ; les pilotes plus rares et les options de finisseur peuvent nÃ©cessiter des ajustements.

## Captures d'Ã©cran

| | |
|---|---|
| ![ContrÃ´le du document avec avertissements et notes](docs/screenshots/preflight_example.jpg) | ![Conversion CMJN avec aperÃ§u des couleurs](docs/screenshots/cmyk_adjustment_example.png) |
| ![Step & repeat (Nutzen)](docs/screenshots/step_and_repeat_example.png) | ![CutContour pour traceurs de dÃ©coupe](docs/screenshots/cut_contour_example.png) |
| ![DÃ©coupe (trim)](docs/screenshots/trim_example.png) | ![DonnÃ©es variables](docs/screenshots/variable_data_example.png) |

## FonctionnalitÃ©s

- **Afficher et imprimer** des PDF, des images (y compris HEIC, SVG) et des fichiers Office (via
  LibreOffice). Utilise les pilotes d'imprimante dÃ©jÃ  installÃ©s (CUPS sous Linux, pilotes Windows) avec
  toutes leurs options.
- **Imposition :** ajuster/mettre Ã  l'Ã©chelle, N pages par feuille, poster, pas de rÃ©pÃ©tition (step & repeat) ;
  brochures en piqÃ»re Ã  cheval, cahiers groupÃ©s ou feuilles simples empilÃ©es (dos carrÃ© collÃ©), avec
  dÃ©calage (creep), pages blanches, repÃ¨res de pli, de repÃ©rage et d'empilement et aperÃ§u des feuilles.
  Aussi en ligne de commande (`passermark-cli impose`). Le step & repeat permet de monter la feuille terminÃ©e une seconde fois sur un format cible librement choisi (Ã©tape 2).
- **Manipulation de document :** conversion CMYK avec aperÃ§u des couleurs, rognage au format, sÃ©paration
  d'objets, **CutContour** pour traceurs de dÃ©coupe (contour, formes, fond perdu, dÃ©coupes intÃ©rieures ;
  redimensionner et dÃ©placer les formes avec des poignÃ©es). Le rognage dÃ©sormais aussi avec Â« rogner les
  bords Â» (mm par cÃ´tÃ©, sans format cible) et Â« supprimer l'espace blanc Â» (dÃ©tecter le contenu, nouveau
  cadre de page Â± marge, le contenu reste 1:1).
- **Diviser les pages :** moitiÃ©s ou grille en pages sÃ©parÃ©es â p. ex. une brochure exportÃ©e en doubles
  pages ; sÃ©lectionner des pages, clic droit â Diviser. Sans perte (rien n'est tramÃ©), format final et fond
  perdu respectÃ©s.
- **PrÃ©vol (preflight) :** vÃ©rifie polices, calques et transparences Ã  l'ouverture ; corrections : intÃ©grer
  ou remplacer des polices (polices libres mÃ©triquement compatibles ou tÃ©lÃ©chargement depuis fontsource.org),
  texte en courbes, figer/supprimer des calques, aplatir la transparence.
- **Ãdition :** sÃ©lectionner des lignes de texte et des calques Ã  la souris ; modifier texte, police et
  taille ; dÃ©placer, redimensionner, masquer, supprimer ou remplacer des calques ; annuler.
- RÃ¨gles et mesure : rÃ¨gles en mm au bord de la vue ; cliquer dÃ©but et fin pour mesurer (Maj s'aligne
  horizontalement/verticalement/45Â°), rÃ©sultat dans la barre d'Ã©tat. Avec Ctrl maintenue, le rÃ©ticule s'aimante aux lignes de coupe et intÃ©rieures (bord de page,
  format final, fond perdu), aux bords d'images et aux lignes vectorielles â jamais au texte ; il colle
  au bord tant que la souris ne s'en Ã©loigne nettement. L'affichage du format final le montre en vert, avec le fond perdu en pointillÃ©s.
- **DonnÃ©es variables :** numÃ©rotation (dÃ©part, pas, chiffres, clÃ©s de contrÃ´le, Ã  l'envers, compteur qui
  continue), texte depuis CSV, codes QR, Code 128 et EAN-13 en vecteurs (avec zone de silence) ;
  placeholders `{{â¦}}` dans le PDF ; date, page, nombre alÃ©atoire et autres variables ; plusieurs pages par
  enregistrement (recto/verso) et champs sur pages impaires/paires ; journal de codes ; step & repeat avec
  son propre enregistrement par copie (feuille par feuille ou couper et empiler) ; **fenÃªtres (groupes de pages)** pour les gabarits multi-pages â p. ex. recto avec le nom, verso avec un code QR â avec sÃ©lection des pages par fenÃªtre (toutes/impaires/paires ou plages) et rÃ©partition des enregistrements feuille par feuille ou page par page. Aussi en ligne de commande
  (`passermark-cli vdp`).
- **Saisie des donnÃ©es :** crÃ©er le tableau de donnÃ©es directement dans Passermark â carte de visite QR
  (vCard), accÃ¨s Wi-Fi, e-mail, adresse web, appel, SMS, rendez-vous, lieu, Code 128, EAN-13 â avec les
  colonnes adaptÃ©es, vÃ©rification immÃ©diate et collage depuis Excel ; enregistrÃ© en CSV et utilisable
  directement dans les donnÃ©es variables. Vos propres fichiers CSV avec d'autres noms de colonnes (p. ex.
  exports de contacts d'Outlook, Google, Thunderbird) sont associÃ©s automatiquement. Sept exemples prÃªts
  (Aide â Obtenir des exemples).
- **Espaces de travail** (Affichage et impression, PrÃ©paration prÃ©presse, Ãdition, DonnÃ©es variables,
  Automatisation) avec leur propre barre d'outils.
- **PrÃ©rÃ©glages** pour CutContour, CMYK/rognage, mise en page d'impression et donnÃ©es variables â partagÃ©s
  avec la ligne de commande.
- RÃ©parer/optimiser des PDF, PDF/A, protection par mot de passe (aussi lors de Â« Enregistrer en PDF Â» dans le
  dialogue d'impression), fusionner des fichiers, sÃ©lectionner et copier du texte.
- Langues : franÃ§ais, allemand, anglais, espagnol, hongrois.

## Installation

**Windows :** tÃ©lÃ©charger `Passermark-<version>-Setup.exe` depuis les [Releases](../../releases) et
l'exÃ©cuter. Tout est inclus (Python, Qt, Ghostscript).

**Linux (toute distribution) :** tÃ©lÃ©charger `Passermark-<version>-x86_64.AppImage` depuis
[Releases](../../releases), puis
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, installation systÃ¨me avec intÃ©gration au gestionnaire de fichiers) :**
```sh
sudo ./install.sh        # installe les dÃ©pendances via apt, entrÃ©e de menu, menu Nautilus
sudo ./uninstall.sh      # supprimer Ã  nouveau (--dry-run pour prÃ©visualiser, --purge supprime aussi /etc/passermark)
```

Optionnel : LibreOffice (fichiers Office), 7-Zip (import de profils ICC depuis des archives).

## Ligne de commande

Toutes les fonctions lourdes tournent aussi sans interface â pour des scripts, des dossiers entiers et
l'automatisation :

```sh
passermark-cli list                                   # tÃ¢ches disponibles
passermark-cli settings cutcontour > sticker.json     # rÃ©glages par dÃ©faut = modÃ¨le de prÃ©rÃ©glage
passermark-cli cutcontour entree.pdf sortie.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour entree.pdf sortie.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour entree.pdf sortie.pdf --preset "Sticker rund"   # prÃ©rÃ©glage enregistrÃ© dans le programme
passermark-cli presets                                # prÃ©rÃ©glages enregistrÃ©s dans le programme
```

TÃ¢ches : `cutcontour`, `separate`, `manip` (CMYK/rognage), `repair`, `preflight_fix`, `impose`, `vdp`,
`split` ; plus `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (tableaux de donnÃ©es). RÃ©glages
imbriquÃ©s avec un point (`--set detect.tolerance=40`). Ctrl+C interrompt proprement (pas de fichier Ã  moitiÃ©
Ã©crit). Codes de retour : 0 terminÃ©, 1 erreur, 2 mauvaise indication, 130 interrompu. `--json-progress`
affiche progression et rÃ©sultat en lignes JSON. Les grandes tÃ¢ches utilisent plusieurs cÅurs ; limitation
avec la variable d'environnement `PASSERMARK_WORKERS` (1 = pas de parallÃ©lisme).

OÃ¹ : Linux `install.sh` â `passermark-cli` ; AppImage â `Passermark-*.AppImage --cli â¦` ;
Windows â `passermark-cli.exe` dans le dossier d'installation (option d'installation : l'ajouter au PATH).
Guides avec des exemples dans le programme : **Aide â Ligne de commande â guide** et
**Aide â DonnÃ©es variables â guide**.
Interface pour les programmes externes (Ã©vÃ©nements JSON stables, codes d'erreur) : [docs/cli-api.md](docs/cli-api.md).

## Journaux d'erreurs

En cas de problÃ¨me, Passermark Ã©crit un fichier journal Ã  joindre (Aide â Ouvrir les journaux d'erreurs) :
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. AprÃ¨s un plantage, le
dÃ©marrage suivant pointe vers le journal. Les journaux sans erreur sont supprimÃ©s Ã  la fermeture.

## Compilation

En local : `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, nÃ©cessite Python 3.12 et
Inno Setup 6) ou `./linux/build-appimage.sh` (Linux, paquets requis dans l'en-tÃªte du script).

Tests : `python3 tests/test_<nom>.py` (pas de framework de test nÃ©cessaire).

## Licence

GPL-3.0-or-later, voir `LICENSE`. L'installateur Windows et l'AppImage contiennent
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).

Licences tierces : l'installateur et l'AppImage contiennent, Ã  cÃ´tÃ© du programme, un dossier
`licenses` (Aide â Licences â¦) avec `THIRD_PARTY_NOTICES.txt`, les fichiers de licence de tous les
paquets Python fournis, l'avis LGPL de Qt/PySide6 (remplacement des bibliothÃ¨ques Qt) et l'avis
Ghostscript avec les liens vers le code source de la version fournie. Sur demande, le code source
correspondant des composants fournis est Ã©galement mis Ã  disposition â ouvrez une issue sur
[GitHub](https://github.com/groschenheld/passermark/issues).

