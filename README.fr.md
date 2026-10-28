# Passermark 1.18.6

Visionneuse PDF, outil d'impression et boîte à outils de préparation prépresse pour **Linux et Windows**.
Logiciel libre (GPL-3.0-or-later).

**English :** [README.md](README.md) · [Deutsch](README.de.md) · [Magyar](README.hu.md) · **Français** · [Español](README.es.md)

> **Statut :** un projet privé, développé à côté du travail prépresse quotidien. Les retours sont les
> bienvenus – les réponses et les nouvelles fonctions sont fournies sans garantie. Testé avec les pilotes
> CUPS et Windows (jet d'encre, imprimantes de bureau et de production avec finisseur via un serveur
> d'impression) ; les pilotes plus rares et les options de finisseur peuvent nécessiter des ajustements.
>
> **Banc de test :** pour les tests, un parc de machines virtuelles tourne – neuf imprimantes simulées (Canon, Xerox,
> Epson, Roland, GBC), fonctions de finition incluses et sortie PDF et journal par impression :
> [Virtual-Printer-Machine-Fleet](https://github.com/groschenheld/Virtual-Printer-Machine-Fleet).
> Il a été construit par Claude et a suffi jusqu'ici à mes besoins de test – les suggestions d'amélioration sont bienvenues.

## Captures d'écran

| | |
|---|---|
| ![Contrôle du document avec avertissements et notes](docs/screenshots/preflight_example.jpg) | ![Conversion CMJN avec aperçu des couleurs](docs/screenshots/cmyk_adjustment_example.png) |
| ![Step & repeat (Nutzen)](docs/screenshots/step_and_repeat_example.png) | ![CutContour pour traceurs de découpe](docs/screenshots/cut_contour_example.png) |
| ![Découpe (trim)](docs/screenshots/trim_example.png) | ![Données variables](docs/screenshots/variable_data_example.png) |

## Fonctionnalités

- **Afficher et imprimer** des PDF, des images (y compris HEIC, SVG) et des fichiers Office (via
  LibreOffice). Utilise les pilotes d'imprimante déjà installés (CUPS sous Linux, pilotes Windows) avec
  toutes leurs options.
- **Imposition :** ajuster/mettre à l'échelle, N pages par feuille, poster, pas de répétition (step & repeat) ;
  brochures en piqûre à cheval, cahiers groupés ou feuilles simples empilées (dos carré collé), avec
  décalage (creep), pages blanches, repères de pli, de repérage et d'empilement et aperçu des feuilles.
  Aussi en ligne de commande (`passermark-cli impose`). Le step & repeat permet de monter la feuille terminée une seconde fois sur un format cible librement choisi (étape 2) – désormais aussi à l'impression directe depuis le dialogue d'impression.
- **Plan & Poster :** impression de plans et de posters sur appareils à rouleaux – rouleaux lus depuis l'appareil (IPP, sinon SNMP), « vérifier l'appareil » en lecture seule avec un rapport JSON ; choix du rouleau automatique (le plus étroit qui convient, selon grammage/matière) ou fixe, position centrée ou au bord ; mètres linéaires en direct avec avertissement avant la fin du rouleau, « couper individuellement » fait de chaque exemplaire un travail à part ; outils plans (mise à l'échelle, rotation, bandes de remplissage, marques de coupe, relevage des filets, repères de pli selon DIN 824), outils posters (ourlet, marques d'œillets, CutContour, repères de repérage pour le print & cut avec la Roland), plus large que le rouleau est découpé en bandes ; matières par utilisateur. Aussi en ligne de commande (`passermark-cli plan`/`poster`, `--dry-run` ne calcule que les mètres linéaires), comme étape d'enchaînement et comme sortie hotfolder p. ex. pour VersaWorks.
- **Manipulation de document :** conversion CMYK avec aperçu des couleurs, rognage au format, séparation
  d'objets, **CutContour** pour traceurs de découpe (contour, formes, fond perdu, découpes intérieures ;
  redimensionner et déplacer les formes avec des poignées). Le rognage désormais aussi avec « rogner les
  bords » (mm par côté, sans format cible) et « supprimer l'espace blanc » (détecter le contenu, nouveau
  cadre de page ± marge, le contenu reste 1:1).
- **Diviser les pages :** moitiés ou grille en pages séparées – p. ex. une brochure exportée en doubles
  pages ; sélectionner des pages, clic droit → Diviser. Sans perte (rien n'est tramé), format final et fond
  perdu respectés.
- **Prévol (preflight) :** vérifie à l'ouverture polices, calques, transparences, cases de page (crop/trim/bleed), fond perdu au contenu, protection, PDF/X et output intent, champs de formulaire et pages vides ; corrections : intégrer
  ou remplacer des polices (polices libres métriquement compatibles ou téléchargement depuis fontsource.org),
  texte en courbes, figer/supprimer des calques, aplatir la transparence. Chaque constat nomme sa position (p. ex. « page 2 – en bas à droite, 40 × 20 mm ») ; un clic y saute et l'encadre en rouge, ◀ ▶ fait défiler les constats.
- **Édition :** sélectionner des lignes de texte et des calques à la souris ; modifier texte, police et
  taille ; déplacer, redimensionner, masquer, supprimer ou remplacer des calques ; annuler.
- Règles et mesure : règles en mm au bord de la vue ; cliquer début et fin pour mesurer (Maj s'aligne
  horizontalement/verticalement/45°), résultat dans la barre d'état. Avec Ctrl maintenue, le réticule s'aimante aux lignes de coupe et intérieures (bord de page,
  format final, fond perdu), aux bords d'images et aux lignes vectorielles – jamais au texte ; il colle
  au bord tant que la souris ne s'en éloigne nettement. L'affichage du format final le montre en vert, avec le fond perdu en pointillés.
- **Données variables :** numérotation (départ, pas, chiffres, clés de contrôle, à l'envers, compteur qui
  continue), texte depuis CSV, codes QR, Code 128 et EAN-13 en vecteurs (avec zone de silence) ;
  placeholders `{{…}}` dans le PDF ; date, page, nombre aléatoire et autres variables ; plusieurs pages par
  enregistrement (recto/verso) et champs sur pages impaires/paires ; journal de codes ; step & repeat avec
  son propre enregistrement par copie (feuille par feuille ou couper et empiler) ; **fenêtres (groupes de pages)** pour les gabarits multi-pages – p. ex. recto avec le nom, verso avec un code QR – avec sélection des pages par fenêtre (toutes/impaires/paires ou plages) et répartition des enregistrements feuille par feuille ou page par page. Aussi en ligne de commande
  (`passermark-cli vdp`).
- **Saisie des données :** créer le tableau de données directement dans Passermark – carte de visite QR
  (vCard), accès Wi-Fi, e-mail, adresse web, appel, SMS, rendez-vous, lieu, Code 128, EAN-13 – avec les
  colonnes adaptées, vérification immédiate et collage depuis Excel ; enregistré en CSV et utilisable
  directement dans les données variables. Vos propres fichiers CSV avec d'autres noms de colonnes (p. ex.
  exports de contacts d'Outlook, Google, Thunderbird) sont associés automatiquement. Sept exemples prêts
  (Aide → Obtenir des exemples).
- **Espaces de travail** (Affichage et impression, Plan & Poster, Préparation prépresse, Édition, Données variables,
  Automatisation) avec leur propre barre d'outils.
- **Préréglages** pour CutContour, CMYK/rognage, mise en page d'impression et données variables – partagés
  avec la ligne de commande.
- **Journal d'impression :** par utilisateur dans les réglages, ou imposé par l'admin – un JSON par travail avec les réglages exacts et les pages envoyées par exemplaire (`out_pages`), plus un `printlog.csv` ; `passermark-cli reprint <log.json>` réimprime un travail à tout moment (avec un avertissement si l'original a changé).
- **Automatisation :** enchaînements étape par étape avec conditions (« if » à chaque étape, embranchements « choose »/« else », « fail »/« stop » avec message) ; `passermark-cli serve` surveille des dossiers et envoie chaque fichier dans l'enchaînement assigné – `serve --init` crée un modèle avec un exemple.
- **Dossier d'impression partagé :** un dossier de dépôt pour tous – mis en place via un bouton dans l'administration (« Mettre en place le dossier d'impression partagé … »), via install.sh ou via `passermark-cli shared-folder` ; un seul assistant root crée le groupe et le dossier (root:passermark, 2775, ACL par défaut, les utilisateurs rejoignent le groupe, les liens symboliques sont refusés) ; sous Windows, les trois sous-dossiers `hotfolder`, `ausgabe` et `archiv` reçoivent le droit Modifier pour les utilisateurs – le reste de ProgramData reste réservé aux administrateurs.
- **Softproof :** simuler le résultat d'impression dans la vue (Ctrl+Y) – comme condition d'impression, une matière, un profil de l'administration ou un profil CMYK du système, avec le rendu (intent) et la BPC ; simuler la couleur du papier et l'encre noire d'impression, avertissements pour les couleurs hors gamme imprimable et pour la couverture d'encre au-delà d'une limite en %.
- **Matières :** enregistrer des papiers (grammage, surface, rendu, profil par imprimante) ; blanc de papier mesuré avec ArgyllCMS (spotread), à partir d'un fichier de mesure CGATS ou à la main ; suggestions de profils classées selon le ΔE2000. Les matières définissent le profil et le rendu dans le dialogue d'impression et dans la conversion CMYK ; l'aperçu couleur prend le blanc de papier mesuré.
- **Contrôle couleur :** dans le nouveau menu Couleur (Ctrl+Maj+F) – un panneau latéral comme le prévol : choisir la condition d'impression, Passermark montre ce que contient le document (RVB, couverture d'encre, tons directs, output intent) et des constats en clair, chacun avec un bouton pour corriger ; les constats sont cliquables.
- **Export pour l'imprimeur :** un assistant en quatre étapes – choisir la condition d'impression, convertir selon la recommandation, contrôler, enregistrer ; l'ICC toujours intégré comme output intent, le RVB demande toujours ; paquet facultatif avec PDF, profils et rapport. Aussi en ligne de commande (`passermark-cli press`).
- **Papiers et mesures :** des matières personnelles sans droits d'administration (`~/.config/passermark/materials.json`, enregistrées immédiatement) ; le bouton « Mesurer le papier … » crée le papier et lance la mesure, « Rechercher l'appareil » trouve l'appareil X-Rite via ArgyllCMS ; la liste des matières vide dans le dialogue d'admin explique maintenant les premières étapes.
- **Profils standard :** charger PSO Coated/Uncoated v3, FOGRA39/47, SC-B, GRACoL et SWOP depuis registry.color.org dans son propre dossier ICC avec « Obtenir les profils standard » (pas fournis pour des raisons de licence) ; les suggestions montrent aussi les profils pas encore installés.
- Réparer/optimiser des PDF, PDF/A, protection par mot de passe (aussi lors de « Enregistrer en PDF » dans le
  dialogue d'impression), fusionner des fichiers, sélectionner et copier du texte.
- Langues : français, allemand, anglais, espagnol, hongrois.

## Installation

**Windows :** télécharger `Passermark-<version>-Setup.exe` depuis les [Releases](../../releases) et
l'exécuter. Tout est inclus (Python, Qt, Ghostscript).

**Linux (toute distribution) :** télécharger `Passermark-<version>-x86_64.AppImage` depuis
[Releases](../../releases), puis
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, installation système avec intégration au gestionnaire de fichiers) :**
```sh
sudo ./install.sh        # installe les dépendances via apt, entrée de menu, menu Nautilus
sudo ./uninstall.sh      # supprimer à nouveau (--dry-run pour prévisualiser, --purge supprime aussi /etc/passermark)
```

Optionnel : LibreOffice (fichiers Office), 7-Zip (import de profils ICC depuis des archives), ArgyllCMS (mesurer le blanc de papier des matières – paquet Linux `argyll`).

## Ligne de commande

Toutes les fonctions lourdes tournent aussi sans interface – pour des scripts, des dossiers entiers et
l'automatisation :

```sh
passermark-cli list                                   # tâches disponibles
passermark-cli settings cutcontour > sticker.json     # réglages par défaut = modèle de préréglage
passermark-cli cutcontour entree.pdf sortie.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour entree.pdf sortie.pdf --preset sticker.json --pages 1,3-5
passermark-cli cutcontour entree.pdf sortie.pdf --preset "Sticker rund"   # préréglage enregistré dans le programme
passermark-cli presets                                # préréglages enregistrés dans le programme
```

Tâches : `cutcontour`, `separate`, `manip` (CMYK/rognage), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`, `press` (export pour l'imprimeur), `plan`/`poster` (impression de plans et posters sur rouleau) ; plus `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (tableaux de données). Réglages
imbriqués avec un point (`--set detect.tolerance=40`). Ctrl+C interrompt proprement (pas de fichier à moitié
écrit). Codes de retour : 0 terminé, 1 erreur, 2 mauvaise indication, 130 interrompu. `--json-progress`
affiche progression et résultat en lignes JSON. Les grandes tâches utilisent plusieurs cœurs ; limitation
avec la variable d'environnement `PASSERMARK_WORKERS` (1 = pas de parallélisme).

`passermark-cli serve` surveille les dossiers de dépôt (`--init` crée un modèle avec un exemple) ; `passermark-cli shared-folder` met en place le dossier d'impression partagé (`--user NAME`, `--status`) ; `passermark-cli reprint <log.json>` réimprime un travail depuis le journal d'impression.

Où : Linux `install.sh` → `passermark-cli` ; AppImage → `Passermark-*.AppImage --cli …` ;
Windows → `passermark-cli.exe` dans le dossier d'installation (option d'installation : l'ajouter au PATH).
Guides avec des exemples dans le programme : **Aide → Ligne de commande – guide** et
**Aide → Données variables – guide**.
Interface pour les programmes externes (événements JSON stables, codes d'erreur) : [docs/cli-api.md](docs/cli-api.md).

## Journaux d'erreurs

En cas de problème, Passermark écrit un fichier journal à joindre (Aide → Ouvrir les journaux d'erreurs) :
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Après un plantage, le
démarrage suivant pointe vers le journal. Les journaux sans erreur sont supprimés à la fermeture.

## Compilation

En local : `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, nécessite Python 3.12 et
Inno Setup 6) ou `./linux/build-appimage.sh` (Linux, paquets requis dans l'en-tête du script).

Tests : `python3 tests/test_<nom>.py` (pas de framework de test nécessaire).

## Licence

GPL-3.0-or-later, voir `LICENSE`. L'installateur Windows et l'AppImage contiennent
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).

Licences tierces : l'installateur et l'AppImage contiennent, à côté du programme, un dossier
`licenses` (Aide → Licences …) avec `THIRD_PARTY_NOTICES.txt`, les fichiers de licence de tous les
paquets Python fournis, l'avis LGPL de Qt/PySide6 (remplacement des bibliothèques Qt) et l'avis
Ghostscript avec les liens vers le code source de la version fournie. Sur demande, le code source
correspondant des composants fournis est également mis à disposition – ouvrez une issue sur
[GitHub](https://github.com/groschenheld/passermark/issues).

