# Passermark 1.11.2

Visionneuse PDF, outil d'impression et boîte à outils de préparation prépresse pour **Linux et Windows**.
Logiciel libre (GPL-3.0-or-later).

**English :** [README.md](README.md) · [Deutsch](README.de.md) · [Magyar](README.hu.md) · **Français** · [Español](README.es.md)

> **Statut :** un projet privé, développé à côté du travail prépresse quotidien. Les retours sont les
> bienvenus – les réponses et les nouvelles fonctions sont fournies sans garantie. Testé avec les pilotes
> CUPS et Windows (jet d'encre, imprimantes de bureau et de production avec finisseur via un serveur
> d'impression) ; les pilotes plus rares et les options de finisseur peuvent nécessiter des ajustements.

## Fonctionnalités

- **Afficher et imprimer** des PDF, des images (y compris HEIC, SVG) et des fichiers Office (via
  LibreOffice). Utilise les pilotes d'imprimante déjà installés (CUPS sous Linux, pilotes Windows) avec
  toutes leurs options.
- **Imposition :** ajuster/mettre à l'échelle, N pages par feuille, poster, pas de répétition (step & repeat) ;
  brochures en piqûre à cheval, cahiers groupés ou feuilles simples empilées (dos carré collé), avec
  décalage (creep), pages blanches, repères de pli, de repérage et d'empilement et aperçu des feuilles.
  Aussi en ligne de commande (`passermark-cli impose`). Le step & repeat permet de monter la feuille terminée une seconde fois sur un format cible librement choisi (étape 2).
- **Manipulation de document :** conversion CMYK avec aperçu des couleurs, rognage au format, séparation
  d'objets, **CutContour** pour traceurs de découpe (contour, formes, fond perdu, découpes intérieures ;
  redimensionner et déplacer les formes avec des poignées). Le rognage désormais aussi avec « rogner les
  bords » (mm par côté, sans format cible) et « supprimer l'espace blanc » (détecter le contenu, nouveau
  cadre de page ± marge, le contenu reste 1:1).
- **Diviser les pages :** moitiés ou grille en pages séparées – p. ex. une brochure exportée en doubles
  pages ; sélectionner des pages, clic droit → Diviser. Sans perte (rien n'est tramé), format final et fond
  perdu respectés.
- **Prévol (preflight) :** vérifie polices, calques et transparences à l'ouverture ; corrections : intégrer
  ou remplacer des polices (polices libres métriquement compatibles ou téléchargement depuis fontsource.org),
  texte en courbes, figer/supprimer des calques, aplatir la transparence.
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
- **Espaces de travail** (Affichage et impression, Préparation prépresse, Édition, Données variables,
  Automatisation) avec leur propre barre d'outils.
- **Préréglages** pour CutContour, CMYK/rognage, mise en page d'impression et données variables – partagés
  avec la ligne de commande.
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

Optionnel : LibreOffice (fichiers Office), 7-Zip (import de profils ICC depuis des archives).

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
`split` ; plus `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (tableaux de données). Réglages
imbriqués avec un point (`--set detect.tolerance=40`). Ctrl+C interrompt proprement (pas de fichier à moitié
écrit). Codes de retour : 0 terminé, 1 erreur, 2 mauvaise indication, 130 interrompu. `--json-progress`
affiche progression et résultat en lignes JSON. Les grandes tâches utilisent plusieurs cœurs ; limitation
avec la variable d'environnement `PASSERMARK_WORKERS` (1 = pas de parallélisme).

Où : Linux `install.sh` → `passermark-cli` ; AppImage → `Passermark-*.AppImage --cli …` ;
Windows → `passermark-cli.exe` dans le dossier d'installation (option d'installation : l'ajouter au PATH).
Guides avec des exemples dans le programme : **Aide → Ligne de commande – guide** et
**Aide → Données variables – guide**.

## Journaux d'erreurs

En cas de problème, Passermark écrit un fichier journal à joindre (Aide → Ouvrir les journaux d'erreurs) :
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Après un plantage, le
démarrage suivant pointe vers le journal. Les journaux sans erreur sont supprimés à la fermeture.

## Compilation

Chaque push sur `main` compile sur GitHub l'installateur Windows et l'AppImage Linux (**Actions**) ; les
deux sont vérifiés avec `--selftest`. Un tag `v*` (p. ex. `git tag v1.10.7 && git push origin v1.10.7`) les
joint à une Release GitHub.

En local : `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, nécessite Python 3.12 et
Inno Setup 6) ou `./linux/build-appimage.sh` (Linux, paquets requis dans l'en-tête du script).

Tests : `python3 tests/test_<nom>.py` (pas de framework de test nécessaire).

## Licence

GPL-3.0-or-later, voir `LICENSE`. L'installateur Windows et l'AppImage contiennent
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).
