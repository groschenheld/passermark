# Journal des modifications â Passermark

**English :** [CHANGELOG.md](CHANGELOG.md) Â· [Deutsch](CHANGELOG.de.md) Â· [Magyar](CHANGELOG.hu.md) Â· **FranÃ§ais** Â· [EspaÃ±ol](CHANGELOG.es.md)

> Ce journal contient les versions depuis **1.10.0** en franÃ§ais. L'historique complet :
> [CHANGELOG.md](CHANGELOG.md) (anglais) ou [CHANGELOG.de.md](CHANGELOG.de.md) (allemand).

## 1.15.1
### Poses (step & repeat) : rotation
- Si la grille ne tient pas entièrement sur la feuille dans aucune orientation, l'orientation avec le plus petit débord l'emporte désormais. Ce n'est qu'ensuite que « de préférence sans rotation » compte.
- Les données en portrait sont désormais pivotées et placées exactement comme les données en paysage.
- Modifié de la même façon à l'étape 2 et pour le cas où une pose ne tient même pas seule sur la feuille.
- Si tout tient, cela reste « sans rotation ». « Pivoter les poses : 0° » ou « 90° » force toujours la rotation.

### Formats de papier
- Les dimensions viennent désormais toujours d'abord de l'imprimante, dans cet ordre : `*PaperDimension`, sinon `<</PageSize[b h]>>` de la PPD, sinon du nom ou du texte affiché (p. ex. « 8K 270 x 390 mm ») – et seulement ensuite de la table.
- Une seule table de formats (papersizes.py) au lieu de trois. Nouveaux : SRA4, SRA2, SRA0–1, la série RA, A7–A10, ISO-B, C0–C10. Les valeurs existantes sont restées identiques.
- Une virgule à la place d'un point dans la PPD est reconnue : les dimensions sont quand même reprises, et c'est signalé.
- Quand la zone imprimable manque, Passermark prend les marges que l'imprimante a sur ses autres formats. Pour les formats sans marge, c'est la feuille entière.
- L'avertissement dans le dialogue d'impression nomme la cause et donne les lignes PPD prêtes avec les valeurs pt correctes.
- Les imprimantes IPP et Windows retombent sur le nom et la table quand le pilote ne dit rien ou signale 0 × 0.
- `caps --json` montre désormais d'où chaque format tire ses dimensions, et les éventuelles erreurs de PPD.

### Enregistrer en PDF
- Avec « Comme le document », plus de faux avertissement A4. SRA4 et SRA2 figurent désormais aussi dans la liste.

### JSON lisibles
- Les préréglages n'enregistrent plus que ce qui s'écarte de la valeur par défaut. Un préréglage de brochure devient p. ex. seulement `{"handling": "booklet", "sheet": "A3"}`.
- Dans le menu de la ligne de préréglage se trouve la case « Enregistrer tous les réglages ». Elle vaut pour tous les dialogues.
- `passermark-cli tidy fichier.json` raccourcit les préréglages et enchaînements existants. Avec `--print` il ne fait que montrer ; avec `--full` il réécrit un préréglage complètement.
- Deux choses que tidy ne raccourcit pas volontairement : les étapes d'enchaînement avec `preset` (une valeur par défaut peut y remplacer le préréglage exprès) et `layout` dans l'étape d'impression (les valeurs manquantes y viennent du réglage d'administration, pas de la valeur par défaut du programme).

## 1.15.0
### Dossiers de dÃ©pÃ´t : passermark-cli serve (surveillance)
- `passermark-cli serve` surveille des dossiers et envoie chaque fichier dans l'enchaÃ®nement assignÃ©. L'assignation est dans `watch.json` (prise depuis `--config`, sinon la vÃ´tre, sinon celle pour tous).
- AprÃ¨s traitement, le rÃ©sultat va dans `output/`, l'original dans `processed/` ; en cas d'erreur l'original va dans `failed/` avec un `.log` Ã  cÃ´tÃ©. Chacun de ces rÃ©glages peut aussi valoir `""` (ne pas garder le rÃ©sultat / supprimer l'original). Un enchaÃ®nement qui ne fait qu'imprimer ne garde aucun rÃ©sultat par dÃ©faut.
- Fiable : un fichier n'est pris qu'aprÃ¨s Ãªtre restÃ© `settle` secondes sans modification ; les fichiers Ã  moitiÃ© copiÃ©s (`.part`, `.tmp`) ne sont jamais touchÃ©s. Chaque fichier est d'abord dÃ©placÃ© dans `.passermark/` â deux surveillances sur le mÃªme dossier ne traitent jamais deux fois le mÃªme fichier, et aprÃ¨s un blocage les fichiers restÃ©s en plan reviennent au dÃ©marrage suivant. Les rÃ©sultats ne retombent jamais dans le dossier d'entrÃ©e et ne sont jamais Ã©crasÃ©s (`-1`, `-2` â¦).
- Options : `--check`, `--once` (code 1 si un fichier Ã©choue), `--json`, `--quiet`, `--log`.
- En service : `linux/passermark-watch.service` avec un utilisateur propre sans droits (les Ã©tapes sont dans le fichier) ; pour Windows `windows/watch-task.ps1`, qui crÃ©e une tÃ¢che au dÃ©marrage du systÃ¨me.

### Dossiers d'enchaÃ®nements : ablaeufe â workflows
- Le dossier s'appelle dÃ©sormais `workflows` ; un ancien dossier `ablaeufe` est renommÃ© automatiquement au premier appel. Si les droits manquent, Passermark continue simplement de lire l'ancien dossier.
- **Dossiers d'enchaÃ®nements partagÃ©s :** nouveau dans l'administration sous GÃ©nÃ©ral â Â« Autres dossiers d'enchaÃ®nements Â», p. ex. un partage rÃ©seau. Ordre : propre â partagÃ© â pour tous ; le premier enchaÃ®nement portant le nom l'emporte. Qui peut y dÃ©poser des enchaÃ®nements relÃ¨ve des droits du dossier (p. ex. un groupe avec droit d'Ã©criture) â personne n'a besoin de droits admin pour cela. `workflows --dirs` montre de quel dossier (user / shared / system) vient un enchaÃ®nement.

### Ãtape d'impression
- **`"paper": "auto"` :** avec la gestion de pages Â« taille Â», l'Ã©tape d'impression choisit le papier adaptÃ© Ã  la page, pour les brochures deux pages cÃ´te Ã  cÃ´te (A5 â A4). Si l'imprimante n'a pas de papier adaptÃ©, une erreur liste les formats disponibles ; avec step & repeat ou poster, une erreur claire â le papier doit y Ãªtre indiquÃ©. Un `paper` vide fonctionne comme avant (papier par dÃ©faut de l'imprimante).

### CorrigÃ© par la mÃªme occasion
- Les plages de pages hors document (p. ex. `pages: "1-2"` sur un PDF d'une page) donnent dÃ©sormais Â« la page 2 n'existe pas â¦ Â» au lieu de Â« list index out of range Â».

## 1.14.2
### Fichier â PropriÃ©tÃ©s â¦ (Ctrl+D)
- Cinq onglets :
  - **Fichier :** nom, dossier (Â« Ouvrir le dossier Â», Â« Copier le chemin Â»), taille, modifiÃ© le, Ã©tat (enregistrÃ© / modifiÃ© / en mÃ©moire uniquement / temporaire). Pour les documents fusionnÃ©s, convertis ou crÃ©Ã©s Ã  partir d'images, Â« CrÃ©Ã© Ã  partir de : Â» avec les fichiers sources ; pour les rÃ©sultats, Â« RÃ©sultat de â¦ Â».
  - **Document :** version PDF, titre, auteur, sujet, mots-clÃ©s, crÃ©Ã© avec / PDF produit avec, crÃ©Ã© le / modifiÃ© le ; chiffrement avec mÃ©thode, autorisations accordÃ©es et refusÃ©es ; profil de sortie (Output Intent), calques, champs de formulaire, commentaires et tampons, signets, piÃ¨ces jointes, JavaScript, affichage web rapide.
  - **Pages :** tableau par page avec format, orientation, rotation, format final et fond perdu, et au-dessus un aperÃ§u des formats.
  - **Polices :** nom, type, incorporÃ©e, sous-ensemble, pages. Les polices non incorporÃ©es sont surlignÃ©es en jaune.
  - **ContrÃ´le :** erreurs, avertissements et notes avec les pages.
- La fenÃªtre s'ouvre immÃ©diatement ; les donnÃ©es du document sont lues dans le processus d'analyse et arrivent juste aprÃ¨s â le programme ne se fige pas, mÃªme avec de gros fichiers. Pour les documents modifiÃ©s, l'Ã©tat actuel est affichÃ©, pas le fichier sur le disque. Les donnÃ©es sont les mÃªmes que dans `passermark-cli inspect`, qui livre dÃ©sormais aussi les donnÃ©es supplÃ©mentaires du document.

### Guide de la ligne de commande (Aide, allemand et anglais)
- Nouvelles sections sur les enchaÃ®nements (avec dossiers d'enchaÃ®nements), l'impression (avec finisseurs), `inspect` et l'interface pour les autres programmes ; ajoutÃ©s aussi : l'aperÃ§u des commandes, de nouveaux conseils et le chapitre perspectives (surveillance, prÃ©vu pour 1.15).
- Tous les exemples tournent rÃ©ellement comme tests, y compris les JSON d'enchaÃ®nement montrÃ©s ; seul l'exemple d'impression est vÃ©rifiÃ© et non exÃ©cutÃ© quand aucune imprimante n'est configurÃ©e.
- Le guide existe pour l'instant en allemand et en anglais ; hongrois, espagnol et franÃ§ais affichent l'anglaise comme avant.

## 1.14.1
### Ligne de commande : impression
- **Ãtape `print` dans les enchaÃ®nements :** imprimante, papier, bac, support, recto verso (`none` | `long` | `short`), couleur (`color` | `gray`), copies, tri et plage de pages â plus toutes les options de la boÃ®te d'impression (step & repeat, brochure, poster etc.), le profil colorimÃ©trique de l'imprimante issu des rÃ©glages admin et les options brutes du pilote directement. `dry_run` n'envoie rien et montre seulement ce qui serait envoyÃ©.
- L'impression passe par le mÃªme chemin que la boÃ®te d'impression : avec sÃ©lection automatique du bac et les rÃ©glages constructeur sous Windows.
- Les valeurs sont acceptÃ©es comme valeur du pilote, comme nom affichÃ© ou comme fragment non ambigu ; si quelque chose ne correspond pas, le message d'erreur Ã©numÃ¨re toutes les valeurs possibles.
- Le PDF reste inchangÃ© aprÃ¨s l'impression â continuer, enregistrer ou rÃ©imprimer avec d'autres rÃ©glages. Sans `output`, il ne fait qu'imprimer.
- **Nouvelles commandes :** `printers` (imprimantes avec Ã©tat et imprimante par dÃ©faut) et `caps <imprimante>` (toutes les options du pilote avec leurs choix, les formats de papier et l'option responsable du papier, bac, support, recto verso, couleur, bac de sortie et les finisseurs â agrafage, perforation, pliage, dos carrÃ© cousu, coupe, dÃ©calage).
- En interne : la session d'impression vit dÃ©sormais sans Qt dans `pdfdruck/session.py` pour que la CLI puisse l'utiliser ; le programme la reÃ§oit via `gui/common.py` comme avant.
- Paquet de tests : les enchaÃ®nements 30 et 31 sont des essais Ã  blanc (`dry_run`) et participent Ã  Â« tout tester Â» ; dans le dossier sÃ©parÃ© `ablaeufe-echt-drucken/` se trouvent deux enchaÃ®nements qui impriment vraiment (non exÃ©cutÃ©s automatiquement).

## 1.14.0
### Ligne de commande : enchaÃ®nements
- **Plusieurs travaux Ã  la suite dans un fichier JSON versionnÃ©** (Â« enchaÃ®nement Â», version de format 1) : les Ã©tapes s'exÃ©cutent l'une aprÃ¨s l'autre, chacune travaille avec le rÃ©sultat de la prÃ©cÃ©dente. La sortie n'est Ã©crite que si tout a rÃ©ussi.
- **Nouvelles commandes :** `run` (exÃ©cuter un enchaÃ®nement, aussi avec plusieurs entrÃ©es â les images et fichiers Office sont convertis au prÃ©alable et fusionnÃ©s avec les PDF), `check` (valider sans exÃ©cuter, toutes les erreurs en une fois), `schema` (schÃ©ma JSON du fichier d'enchaÃ®nement ou d'un travail), `inspect` (informations du document : pages, formats, format final/fond perdu, constats du prÃ©vol â avec `--check`), `version --json` (version, version d'API et de format, travaux disponibles).
- **Variables** dans le chemin de sortie : `${â¦}` depuis `--var` ; intÃ©grÃ©es `${input}`, `${dir}`, `${stem}`, `${date}` et `${workflow_dir}`.
- **Les fautes de frappe sont des erreurs :** les rÃ©glages inconnus et les types incorrects sont signalÃ©s, rien ne retombe silencieusement sur une valeur par dÃ©faut.
- **Pour les programmes externes :** Ã©vÃ©nements JSON stables (`start` â `step` â `progress` â `step_done` â `done`) et codes d'erreur fixes (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) avec Ã©tape et travail ; la version d'API et de format est dans `version --json`. L'interface est documentÃ©e dans [docs/cli-api.md](docs/cli-api.md) (anglais, avec rÃ©sumÃ© en allemand) â le contrat contraignant pour les programmes externes, liÃ© depuis tous les README.

## 1.13.2
### BoÃ®te d'impression : aperÃ§u en arriÃ¨re-plan
- **AperÃ§u sans attente :** la feuille est montÃ©e et dessinÃ©e dans le processus de rendu dÃ©sormais â la fenÃªtre n'attend plus. Avec un gros fichier, l'aperÃ§u prend 0,001 s dans la fenÃªtre principale au lieu de blocages allant jusqu'Ã  6 s auparavant. Si quelque chose change pendant qu'un calcul est encore en cours, seul l'Ã©tat le plus rÃ©cent est dessinÃ© jusqu'au bout.
- L'attente reste : l'aperÃ§u n'est fini qu'aprÃ¨s 2â5 s, car le dessin de la page elle-mÃªme prend ce temps. Mais la fenÃªtre reste utilisable pendant ce temps.
- **Copies multiples (p. ex. step & repeat) :** la page n'est rendue qu'une fois au lieu d'une fois par copie â environ deux fois plus vite. L'image s'Ã©carte minimalement car c'est une image tramÃ©e ; seule une trame trÃ¨s fine laisse voir un lÃ©ger moirÃ©. L'impression continue Ã  partir de l'original.
- **Sans copies multiples,** l'aperÃ§u est identique au pixel prÃ¨s Ã  avant (comparÃ© pour pages simples, 9 sur 1, brochure, plieurs et duplex).
- **Format final/fond perdu** vient maintenant des donnÃ©es de page sans charger les pages â les valeurs sont les mÃªmes qu'avant.
- **AperÃ§u des plieurs** est Ã©galement calculÃ© en arriÃ¨re-plan.
- **Toujours dans la fenÃªtre principale :** passer Ã  Â« Brochure en plieurs Â» prend encore environ 0,9 s ; la gÃ©nÃ©ration des plieurs n'a pas Ã©tÃ© externalisÃ©e.
- **Vue de page :** les grandes images de page sont mises Ã  l'Ã©chelle grossiÃ¨rement immÃ©diatement au zoom ; l'image propre arrive en arriÃ¨re-plan. La limite supÃ©rieure de l'image de page reste inchangÃ©e Ã  16 mÃ©gapixels.

### Fusionner sous Windows
- **Une seule fenÃªtre :** si plusieurs fichiers arrivent en mÃªme temps, ils atterrissent tous dans la mÃªme fenÃªtre. TestÃ© avec 12 appels lancÃ©s simultanÃ©ment : 1 fenÃªtre, 12 fichiers, triÃ©s par nom.
- **Nouveaux boutons :** Â« Ajouter un dossier â¦ Â», monter/descendre et Â« Trier par nom Â». Les fichiers peuvent aussi Ãªtre glissÃ©s dedans ; la fenÃªtre affiche combien elle en contient.
- **Pour de nombreux plans :** le mieux est Â« Envoyer vers â Passermark â fusionner Â» â il transmet tous les fichiers d'un coup et est crÃ©Ã© une seule fois au premier dÃ©marrage. Sinon, ajouter directement le dossier entier dans la fenÃªtre.
- **Barre latÃ©rale :** les pages sÃ©lectionnÃ©es peuvent Ãªtre dÃ©placÃ©es. La barre jaune montre oÃ¹ elles atterriront ; au bord, la barre dÃ©file automatiquement.

## 1.13.1
### Correctif de vitesse
- LÃ©gÃ¨res amÃ©liorations de vitesse dans la nouvelle vue (rendu).

## 1.13.0
### Vue plus rapide (refonte du rendu)
- **Rendu dans un processus sÃ©parÃ© :** les pages sont rendues par un processus en arriÃ¨re-plan (`passermark-cli render-server`) ; l'interface n'attend plus jamais. Une seule demande est en vol Ã  la fois â en feuilletant vite, les demandes pÃ©rimÃ©es ne s'accumulent plus. Si le processus plante, il redÃ©marre ; s'il ne dÃ©marre pas (ou si le PDF est protÃ©gÃ© par mot de passe), la vue rend dans le programme comme avant.
- **Une image par page :** chaque page est rendue une fois Ã  peu prÃ¨s au double de la taille d'affichage ; les niveaux de zoom en deÃ§Ã  et les vignettes en sont seulement mis Ã  l'Ã©chelle. Les images d'une page sont dÃ©compressÃ©es une seule fois, au lieu d'une fois par niveau de zoom et par vignette.
- **Le zoom fort ne rend que la partie visible,** au pixel prÃ¨s mÃªme en vue pivotÃ©e. Ã 400 % la page est briÃ¨vement floue puis nette (auparavant agrandie et floue).
- **Enregistrer sur le mÃªme fichier fonctionne maintenant sous Windows :** le fichier est lu en mÃ©moire et reste libre sur le disque.
- **Mode Ã©dition :** pendant le dÃ©placement, l'objet suit en semi-transparent ; aprÃ¨s application, les anciennes images restent comme espaces rÃ©servÃ©s et sont renouvelÃ©es en arriÃ¨re-plan, la page Ã©ditÃ©e d'abord. Avant, tout devenait blanc et toutes les vignettes Ã©taient rendues Ã  nouveau dans la fenÃªtre principale.
- **Le contrÃ´le automatique lit directement les fichiers non modifiÃ©s** â Ã  l'ouverture, le rÃ©enregistrement dans la fenÃªtre principale disparaÃ®t.
- DÃ©pannage : avec `PASSERMARK_RENDER=local`, tout fonctionne comme avant â un moyen rapide de savoir si la cause est le nouveau processus de rendu.
- Limite connue : relÃ¢cher un objet en mode Ã©dition prend encore environ 1 s sur les pages lourdes (le contrÃ´le de sÃ©curitÃ© compare la page avant et aprÃ¨s). Un Ã©lÃ©ment utilisÃ© sur plusieurs pages peut changer partout par une modification ; c'est pourquoi aprÃ¨s l'Ã©dition toutes les pages sont rendues Ã  nouveau en arriÃ¨re-plan, celle Ã©ditÃ©e en premier.

## 1.12.6
### Ajustements du prÃ©vol
- Petits ajustements de Â« RÃ©duire la taille du fichier Â» (`shrink`) et des contrÃ´les du prÃ©vol ; traductions complÃ©tÃ©es ; manuel de la CLI (DE/EN) mis Ã  jour.

## 1.12.5
### Licences
- L'installateur et l'AppImage incluent dÃ©sormais tous les avis de licence des tiers (paquets Python, Qt LGPL-3.0, Ghostscript AGPL-3.0 avec rÃ©fÃ©rence au code source, bibliothÃ¨ques systÃ¨me embarquÃ©es), consultables via la nouvelle entrÃ©e de menu Aide â Licences.
- README : nouvelle section sur les licences des tiers, code source disponible sur demande.
### Documentation
- Le manuel de la CLI (DE/EN) est mis Ã  jour avec `shrink` et `flatten_softmask`.

## 1.12.4
### RÃ©duire la taille du fichier (nouveau)
- Accessible depuis l'onglet Â« Taille du fichier Â» ou Document â Â« RÃ©duire la taille du fichier â¦ Â», y compris pour les fichiers non signalÃ©s comme trop volumineux.
- Chaque mesure s'active et se dÃ©sactive individuellement :
  - **Sans perte, activÃ© par dÃ©faut :** rÃ©Ã©crire (supprime les anciennes versions), supprimer les ressources inutilisÃ©es, fusionner les doublons (polices, images, profils ICC), retirer les donnÃ©es d'Ã©dition et les vignettes, recompresser les images sans perte (retire aussi le ZIP autour du JPEG si plus petit).
  - **DÃ©sactivÃ© par dÃ©faut :** 16 â 8 bits, supprimer les piÃ¨ces jointes, supprimer le contenu des calques masquÃ©s.
  - **Sous-Ã©chantillonnage optionnel :** Ã  300/240/150/100 dpi avec seuil et qualitÃ© JPEG, mesurÃ© au plus grand placement. Les masques doux sont mis Ã  l'Ã©chelle en mÃªme temps.
- Le rÃ©sultat s'ouvre dans une nouvelle fenÃªtre et l'original reste inchangÃ©. Si le rÃ©sultat n'est pas plus petit, le fichier est conservÃ© tel quel.
- CLI : `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 â¦]`
- Exemple : un fichier de 34 Mo avec le mÃªme profil CMJN intÃ©grÃ© 90 fois est descendu Ã  0,5 Mo, identique au pixel prÃ¨s.

## 1.12.3
### PrÃ©vol (preflight)
- **Nouvel onglet Â« Taille du fichier Â» :** montre oÃ¹ vont les octets : images, polices, profils colorimÃ©triques, donnÃ©es d'Ã©dition Illustrator/Photoshop, vignettes, piÃ¨ces jointes, contenu des pages.
  - Liste aussi les anciennes versions enregistrÃ©es, les doublons et les plus grandes images avec leur rÃ©solution effective.
  - Avertit des fichiers trÃ¨s volumineux (plus de 20 Mo par surface A4) et des doublons volumineux.

## 1.12.2
### PrÃ©vol (preflight)
- **DÃ©gradÃ©s transparents (masque doux dans les motifs) :** dÃ©tectÃ©s et rÃ©parables. Certains RIP/traceurs les impriment sous forme d'une zone noire qui recouvre les images situÃ©es dessous. La nouvelle rÃ©paration Â« Convertir les dÃ©gradÃ©s transparents en images (300 dpi) Â» ne rend que les dÃ©gradÃ©s concernÃ©s, avec ce qui se trouve dessous, sous forme d'une image opaque. Le texte et les vecteurs au-dessus restent intacts. Ghostscript n'est pas nÃ©cessaire.
- **Photos HDR (gain map) :** une photo HDR de tÃ©lÃ©phone ouverte avec les deux images est maintenant dÃ©tectÃ©e par le contrÃ´le. RÃ©paration : Â« Supprimer les pages auxiliaires HDR â¦ Â», avec taille au choix et fusion optionnelle du gain map.
- **Nouvel onglet Â« Images et couleurs Â» :**
  - Espace colorimÃ©trique par image et par page (RVB, CMJN, niveaux de gris, tons directs), y compris le nom exact du profil ICC et l'intention de rendu (output intent).
  - RÃ©solution effective par placement, Ã©galement pour les images utilisÃ©es plusieurs fois ou dans des formulaires.
  - Taille maximale recommandÃ©e Ã  300 et 150 dpi, plus l'Ã©chelle maximale par page.
  - Avertissements pour basse rÃ©solution et informations sur le contenu RVB et les tons directs.

## 1.12.1
- **Ãdition : plusieurs objets et lignes Ã  la fois.** Â« Agrandir / dÃ©placer â¦ Â», Â« Supprimer
  l'objet Â», Â« Appliquer Â» (police et taille) et Â« Supprimer la ligne Â» s'appliquent dÃ©sormais Ã 
  tous les objets ou lignes choisis, plus seulement Ã  un seul. Avec plusieurs lignes sÃ©lectionnÃ©es,
  le champ texte est verrouillÃ© â modifier le texte ne fonctionne qu'avec une seule ligne
- **Ãdition : changer la couleur.** Nouveau bouton Â« Couleur â¦ Â» pour les lignes de texte et les
  objets vectoriels, au choix CMJN (par dÃ©faut, pour l'impression) ou RVB ; pour les vecteurs,
  remplissage et contour se rÃ¨glent sÃ©parÃ©ment. Le noir 0/0/0/100 reste du noir pur. La couleur est
  posÃ©e directement dans le contenu de la page â tout ce qui est hors de la sÃ©lection reste
  inchangÃ©, y compris les objets qui n'ont fait qu'hÃ©riter leur couleur
- **Ãdition : vue d'ensemble.** Les onglets affichent le nombre (Â« Texte (12) Â», Â« Objets (40) Â») ;
  dans l'onglet Â« Objets Â» un filtre par vecteurs ou images est disponible, avec le nombre par type.
  Avec un filtre actif, un clic sur la page ne sÃ©lectionne que ce type
- **Photos HDR de tÃ©lÃ©phone (iPhone, Android) reconnues.** Ces JPG contiennent Ã  cÃ´tÃ© de la photo
  une carte de luminance grise pour les Ã©crans HDR. Auparavant, cela devenait une deuxiÃ¨me page
  d'une autre taille â aux couleurs fausses au traceur. DÃ©sormais un avis s'affiche Ã  l'ouverture ;
  Â« RÃ©parer Â» donne une page avec la photo inchangÃ©e, taille au choix (comme l'image auxiliaire ou
  comme enregistrÃ©e dans la photo). La carte de luminance peut Ãªtre intÃ©grÃ©e en option. Sans
  demande (ligne de commande, impression directe), la rÃ©paration est automatique
- **CorrigÃ© : taille de police du texte sur tracÃ©.** AprÃ¨s modification, la liste continuait
  d'afficher l'ancienne taille et chaque nouvelle modification agrandissait encore (24 â 36 â
  54 pt). La taille rÃ©elle s'affiche maintenant ; les arcs courts avec peu de lettres sont
  Ã©galement reconnus comme texte sur tracÃ©. Â« Appliquer Â» sans modification laisse la page
  intacte
- **CorrigÃ© : ordre Z.** Â« Un pas devant Â» sur l'objet le plus haut signalait Ã  tort Â« structure de
  la page non reconnue Â» â maintenant tout reste simplement tel quel
- **CorrigÃ© : faire glisser du texte avec la souris** s'interrompait avec un message d'erreur sur
  certains PDF (p. ex. de Chrome)
- Traductions ajoutÃ©es pour la disposition des poses dans le dialogue d'impression (anglais,
  hongrois, espagnol, franÃ§ais)

## 1.11.3
- **BoÃ®te de dialogue VDP relookÃ©e.** Les donnÃ©es variables affichent le mÃªme visage que le
  dialogue d'impression : quatre sections numÃ©rotÃ©es repliables (champs, donnÃ©es, numÃ©rotation,
  sortie) et, en haut, une Â« Guide Â» repliÃ©e. Les explications des champs deviennent des
  info-bulles et n'apparaissent sous le champ que via le nouveau commutateur Â« Afficher les
  textes d'aide Â». L'ancienne note de sortie renvoie dÃ©sormais Ã  l'ordre du dialogue
  d'impression (Poses, Â« Page suivante sur chaque pose Â»). Le widget CollapsibleSection vit
  dans common.py, partagÃ© par les deux dialogues.
- **BoÃ®te de dialogue d'impression sans onglets.** Le sÃ©lecteur de mode en haut (Â« Que faut-il
  imprimer ? Â») guide dÃ©sormais dans une seule colonne continue : prÃ©rÃ©glage, mode, panneau du
  mode, mise Ã  l'Ã©chelle (Â« Comment sur la feuille ? Â»), traits de coupe, papier/sortie, finisseur,
  gestion des couleurs. L'ancienne navigation par onglets disparaÃ®t.
- **Le pas rÃ©pÃ©tÃ© (Step & Repeat) devient un mode Ã  part.** Â« Nutzen Â» rejoint le sÃ©lecteur de mode
  Ã  cÃ´tÃ© des pages simples, plusieurs par feuille, livret et affiche â avec un texte explicatif
  comme les autres modes. L'ancienne case Ã  cocher est remplacÃ©e par le bouton de mode ; le panneau
  Nutzen apparaÃ®t au mÃªme endroit que les autres panneaux de mode.
- **Â« Comment sur la feuille ? Â»** mise Ã  l'Ã©chelle et orientation forment un seul groupe :
  ajuster/taille d'origine/rÃ©duire/personnalisÃ©, rotation, rotation automatique, centrage, marges.
  Le choix d'Ã©chelle (ajuster/taille rÃ©elle/â¦) est visible et effectif dans tous les modes : ajuster = valeur par dÃ©faut du mode, taille rÃ©elle/rÃ©duire/personnalisÃ©
  remplace la mise Ã  l'Ã©chelle du mode â les champs du mode (Ã©chelle par tuile, Ã©chelle Nutzen, affiche) restent en place.
- **Miroir et options du pilote repliables.** Les deux sections restent bien visibles avec un
  titre clair et ne se dÃ©plient qu'au besoin â toutes les options inchangÃ©es.
- **Reliure livret : Â« Standard Â» en premier.** La piqÃ»re Ã  cheval classique (Â« toutes les feuilles
  imbriquÃ©es, pliÃ©es une fois Â») ouvre dÃ©sormais la liste des types sous le nom clair Â« Standard Â» â
  le compteur Â« feuilles par cahier Â» n'apparaÃ®t que pour les cahiers groupÃ©s et ne peut plus
  suggÃ©rer un rÃ©glage sans effet.
- **Sections repliables uniformes.** Chaque bloc de la nouvelle colonne â prÃ©rÃ©glage, sÃ©lecteur de
  mode (Â« Que faut-il imprimer ? Â»), Â« Comment sur la feuille ? Â», traits de coupe, papier/sortie,
  finisseur, gestion des couleurs, miroir, pilote â porte le mÃªme en-tÃªte repliable, Ã  taille
  identique. Les boutons de mode sont empilÃ©s verticalement : toutes les Ã©tiquettes restent
  lisibles ; le panneau du mode se rÃ©duit au mode visible (plus d'espace vide). On peut toujours
  quitter le mode Â« Nutzen Â».
- **Traductions :** 26 messages nouveaux/complÃ©tÃ©s par langue (EN/DE/ES/FR/HU) ; les chaÃ®nes
  1.11.1 manquantes dans les catalogues ES/FR/HU/EN ont Ã©tÃ© complÃ©tÃ©es. Les anciens prÃ©rÃ©glages
  restent entiÃ¨rement compatibles (handling size/multiple/sr se chargent toujours).

## 1.11.2
- **Ãtape 2 : monter la feuille Ã  nouveau.** La feuille terminÃ©e de l'Ã©tape 1 est montÃ©e une seconde fois
  sur un format cible librement choisi (formats de l'appareil ou dimensions personnalisÃ©es en mm) â
  ligne par ligne, toujours centrÃ©e, contenu inchangÃ© ; le rÃ©sultat peut Ãªtre Ã©mis comme nouveau document
  via un bouton (nouvel onglet), l'aperÃ§u le montre comme Ã  l'Ã©tape 1 et le dialogue se ferme ensuite.
  La rotation et l'orientation de l'Ã©tape 1 s'appliquent aussi Ã  l'Ã©tape 2. Grille : 0 Ã 0 = automatique
  (autant que possible).
- **Utiliser les traits de coupe existants.** Avec les documents dotÃ©s d'un format final (TrimBox), les
  cÃ´tÃ©s extÃ©rieurs du bloc de poses montrent le vrai bord du document â les traits de coupe existants
  restent visibles ; les traits propres restent activables par case Ã  cocher comme avant.
- **Monter la grille exactement.** Une grille dÃ©finie (p. ex. 3 Ã 3) reste toujours exacte Ã  l'Ã©tape 1 et
  Ã  l'Ã©tape 2 â si elle ne tient pas sur la feuille, elle est rognÃ©e symÃ©triquement au bord avec un
  avertissement, jamais annulÃ©e.
- **Format cible planifiÃ© sans marges :** p. ex. deux feuilles A4 de l'Ã©tape 1 tiennent proprement sur un A3.
- Le chemin d'impression et l'orientation de l'Ã©tape 1 restent inchangÃ©s.

## 1.11.1
- **Formats personnalisÃ©s : uniquement Â« Enregistrer en PDF Â».** Les formats crÃ©Ã©s soi-mÃªme ne sont plus
  envoyÃ©s aux imprimantes â les pilotes et spoolers Windows n'acceptent souvent pas les tailles personnalisÃ©es
  (feuilles blanches, abandons) ; avec Â« Enregistrer en PDF Â» (â), ils restent entiÃ¨rement utilisables
- **Rognage : deux nouveaux modes.** Â« Rogner les bords Â» : rogner la page sur les quatre cÃ´tÃ©s en mm, sans
  format cible ; Â« Supprimer l'espace blanc Â» : dÃ©tecte le contenu visible (bruit JPEG compris), le nouveau
  format de page rÃ©sulte du cadre du contenu Â± marge (nÃ©gative possible), le contenu reste 1:1 (seulement dÃ©placÃ©)

## 1.11.0
- **DonnÃ©es variables â fenÃªtres (groupes de pages).** Pour les gabarits multi-pages, chaque champ appartient
  Ã  une fenÃªtre (p. ex. Â« rectos (nom), versos (code QR) Â») ; les fenÃªtres peuvent Ãªtre crÃ©Ã©es, renommÃ©es et
  supprimÃ©es â leurs champs rejoignent alors la premiÃ¨re fenÃªtre. SÃ©lection des pages par fenÃªtre : toutes,
  impaires (rectos), paires (versos) ou plages (Â« 1,3-5 ou impaires 1-50 Â») ; sans sÃ©lection propre, la couche
  de base Â« toutes les pages Â» s'applique. RÃ©partition Â« feuille par feuille Â» (d'abord toutes les pages avec
  l'enregistrement 1) ou Â« page par page Â» (d'abord la page 1 avec tous les enregistrements) ; affichage
  Â« {0} enregistrements â {1} pages Â» et avertissement Â« â {0} pages sans fenÃªtre ! Â»
- **AperÃ§u VDP :** format final en vert, fond perdu en rouge ; cadre intÃ©rieur rÃ©glable (ligne guide)
- **Indicateur de page Â« actuelle / total Â»** dans la barre d'outils ; saisir un numÃ©ro et EntrÃ©e pour y aller
- **RÃ¨gles, mesure et affichage du format final en permanence dans la barre d'outils principale** â dans
  tous les espaces de travail
- **Format final et fond perdu dans la vue principale :** bordure intÃ©rieure (format final) en vert au lieu
  de rouge, fond perdu en pointillÃ© rouge discret au lieu d'une surface pleine
- **Mesure avec aimantation :** avec Ctrl maintenue, le rÃ©ticule s'aimante aux lignes de coupe et intÃ©rieures
  (bord de page, format final, fond perdu) ainsi qu'aux bords d'images et aux lignes vectorielles â jamais
  au texte ; le rÃ©ticule d'aperÃ§u colle au bord tant que la souris ne s'en Ã©loigne nettement ; Maj verrouille
  toujours horizontal/vertical/45Â°

## 1.10.7
- **CutContour : formes de base sans calcul.** Nouveau placement Â« Sur le format final (sans calcul) Â» :
  rectangle, rectangle arrondi, cercle â¦ sont posÃ©s directement sur le format final (TrimBox, sinon la page) â
  pas de rendu, pas de dÃ©tection du motif, pas de processus de travail, en une fraction de seconde. Distance,
  taille, dÃ©calage et glissement Ã  la souris fonctionnent comme avant. Le calcul n'a lieu qu'avec Â« Contour Â»
  ou lorsque la forme est placÃ©e autour du motif ou par objet. Ligne de commande : `--set fit=trim`
- **Valeur par dÃ©faut dans CutContour :** rectangle sur le format final (tant qu'aucun dernier rÃ©glage
  personnel n'est enregistrÃ©)

## 1.10.6
- **Correctif Windows : CutContour restait bloquÃ© Ã  0 %** (depuis 1.10.5). Le passage de la sortie en ligne
  de commande en UTF-8 est de nouveau supprimÃ© ; le correctif pour Â« Diviser les pages Â» reste (messages de
  progression en ASCII pur)
- CutContour : plus d'erreur si un calcul d'aperÃ§u arrive aprÃ¨s la fermeture de la fenÃªtre
  (Â« expected LP_struct_fpdf_document_t â¦ NoneType Â»)

## 1.10.5
- **Correctif Windows :** Â« Diviser les pages Â» (et toute tÃ¢che dont le message contient des caractÃ¨res comme
  Â« â Â») s'interrompait avec `UnicodeEncodeError â¦ cp1252`. La ligne de commande bascule dÃ©sormais elle-mÃªme
  sa sortie en UTF-8 ; les messages de progression vers l'interface sont en ASCII pur
- `SECURITY.md`, `CONTRIBUTING.md` et les modÃ¨les GitHub pour les rapports de bug et les suggestions inclus
  dans le paquet

## 1.10.4
- README bilingue : `README.md` (anglais) et `README.de.md` (allemand), Ã  jour (diviser les pages, donnÃ©es
  variables, saisie des donnÃ©es, toutes les tÃ¢ches en ligne de commande) et avec une note sur l'Ã©tat du projet
- Exemple de configuration `data/defaults.example.json` avec des noms d'imprimantes neutres

## 1.10.3
- **Diviser les pages via le clic droit :** sÃ©lectionner des pages dans la barre latÃ©rale â clic droit â
  **Diviser** â Â« Couper en deux verticalement Â» / Â« Couper en deux horizontalement Â» â immÃ©diatement, uniquement
  les pages sÃ©lectionnÃ©es, sans page de comparaison. Â« Grille / plus d'options â¦ Â» ouvre le dialogue avec la
  sÃ©lection prÃ©rÃ©glÃ©e

## 1.10.2
- **DonnÃ©es variables â recto et verso :** nouveau Â« Pages par enregistrement Â» (sous 2.) : 2 = pages 1+2 â
  enregistrement 1, 3+4 â enregistrement 2 â¦ â que le modÃ¨le ait 2 pages ou dÃ©jÃ  toutes les cartes (p. ex.
  200 pages pour 100 cartes de visite). Les champs Â« Uniquement sur ces pages Â» connaissent dÃ©sormais
  **impaire** et **pair**, combinables avec des plages (Â« impair 1-50 Â»). Exemple 7 : carte de visite avec le
  nom au recto et une carte QR au verso
- **Autres variables :** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. Le bouton **?** Ã  cÃ´tÃ© du
  contenu les affiche toutes avec une valeur d'exemple, un double-clic insÃ¨re. Les colonnes CSV de mÃªme nom
  ont prioritÃ©
- Un double-clic sur une colonne **remplace** un {{nr}} inchangÃ© au lieu de le laisser devant
- **Diviser les pages** (Pages â Diviser les pages â¦, espace de travail Ãdition) : couper en deux
  verticalement/horizontalement ou en grille, toutes/actuelles/pages sÃ©lectionnÃ©es ou plage, uniquement les
  doubles pages, ordre de droiteâgauche ; avec aperÃ§u des traits de coupe. **Diviser les doubles pages** en un
  clic pour les brochures mal exportÃ©es. Sans perte (le contenu n'est ni copiÃ© ni tramÃ©), les pages tournÃ©es
  telles qu'on les voit ; avec un format final la division se fait dedans et le fond perdu reste dehors.
  Ligne de commande : tÃ¢che `split`
- **Barre latÃ©rale :** les vignettes tournent avec Â« Pivoter la vue Ã  gauche/droite Â»
- **CorrigÃ© : l'ouverture depuis l'extÃ©rieur atterrissait dans une fenÃªtre verrouillÃ©e** (Windows, clic
  droit/double-clic pendant qu'un outil est ouvert dans une fenÃªtre) â dÃ©sormais sa propre fenÃªtre. Cause :
  l'ouverture dans la fenÃªtre de dÃ©marrage vide laissait un onglet vide invisible ; la fenÃªtre vide est
  maintenant utilisÃ©e elle-mÃªme. Les rÃ©sultats d'une fenÃªtre verrouillÃ©e s'ouvrent aussi dans leur propre
  fenÃªtre

## 1.10.1
- **Utiliser directement son propre CSV avec d'autres noms de colonnes :** DonnÃ©es variables â Ouvrir CSV
  reconnaÃ®t Ã  quoi convient le tableau (Â« Le tableau convient Ã  : QR â carte de visite Â»), **CrÃ©er le champ
  adaptÃ©** crÃ©e le code QR avec ce type. Les colonnes sont associÃ©es automatiquement â y compris les noms
  anglais, hongrois, espagnols, franÃ§ais et les en-tÃªtes des exports de contacts d'**Outlook, Google et
  Thunderbird**. Le CSV reste inchangÃ©
- **Associer les colonnes â¦** dans le champ QR avec un type : choisir la colonne par donnÃ©e, Â« laisser vide Â»
  ou automatique ; avec aperÃ§u du contenu final. Sous le type s'affiche ce qui vient d'oÃ¹ et ce qui manque.
  L'association est enregistrÃ©e dans le prÃ©rÃ©glage (`qr_map`) et vaut aussi en ligne de commande
- Saisie des donnÃ©es : un CSV aux noms de colonnes Ã©trangers ne reÃ§oit plus de colonnes en double ; l'en-tÃªte
  montre l'association (Â« First Name â Vorname Â»). `datencheck` reconnaÃ®t aussi les noms de colonnes
  Ã©trangers
- Dossier d'exemples : `kontakte-outlook.csv` (voici Ã  quoi ressemble un export Outlook) ; le guide
  complÃ©tÃ© avec Â« Son propre CSV avec d'autres noms de colonnes Â»

## 1.10.0
- **Saisir les donnÃ©es** (espace de travail DonnÃ©es variables, menu Manipulation de document, ou dans le
  dialogue DonnÃ©es variables sous 2.) : crÃ©er le tableau de donnÃ©es directement dans Passermark. Les colonnes
  adaptÃ©es par type â **carte de visite QR (vCard), accÃ¨s Wi-Fi, e-mail, adresse web, appel, SMS,
  rendez-vous, lieu**, texte QR libre, **Code 128**, **EAN-13**, texte avec colonnes propres. Chaque ligne est
  vÃ©rifiÃ©e immÃ©diatement (donnÃ©es obligatoires, chiffre de contrÃ´le EAN, umlauts dans le Code 128, date â¦), Ã 
  droite le code fini de la ligne choisie. Coller depuis Excel avec Ctrl+V, dupliquer des lignes, remplir une
  colonne avec une sÃ©rie de numÃ©ros (crÃ©e aussi les lignes), colonnes propres. Enregistrer en CSV (UTF-8 avec
  BOM, point-virgule â Excel lit correctement les umlauts)
- **Â« Utiliser dans les donnÃ©es variables Â»** reprend le tableau comme source de donnÃ©es et crÃ©e le champ
  adaptÃ©
- **Champ QR Â« Type de code QR Â» :** contenu tel que saisi ou composÃ© Ã  partir des colonnes du tableau (vCard,
  Wi-Fi, mailto, tel, SMS, rendez-vous, gÃ©o). Le CSV reste lisible ; Passermark construit le contenu du code
  lors de la gÃ©nÃ©ration
- **Zone de silence :** le code QR et le Code 128 ont dÃ©sormais une bordure blanche dans le champ
  (dÃ©sactivable). Sans elle, les codes proches d'un autre contenu Ã©taient mal lisibles. *PrÃ©rÃ©glages
  existants : le code QR devient un peu plus petit dans le champ Ã  cause de cela*
- **Un EAN-13 Ã  13 chiffres avec un mauvais chiffre de contrÃ´le est dÃ©sormais une erreur** (avec le bon numÃ©ro
  dans le message) â auparavant le dernier chiffre Ã©tait remplacÃ© en silence
- Ligne de commande : `datenarten`, `datenvorlage <type> [fichier.csv]`, `datencheck <fichier.csv> [type]`
  (code retour 1 en cas de problÃ¨me) ; dans le prÃ©rÃ©glage `qr_type` par champ QR
- Exemples 5 (carte de visite depuis une liste de contacts) et 6 (accÃ¨s Wi-Fi) ; le guide Â« DonnÃ©es variables Â»
  avec une nouvelle section Â« Saisir les donnÃ©es Â», guide CLI complÃ©tÃ©
- Les tests relisent dÃ©sormais rÃ©ellement les codes gÃ©nÃ©rÃ©s : QR et EAN-13 avec OpenCV (si installÃ©), Code 128
  avec son propre lecteur avec somme de contrÃ´le
- CorrigÃ© : les donnÃ©es variables prenaient Â« une copie du document entier par enregistrement Â» sans choisir
  la distribution au lieu de Â« l'enregistrement suivant sur chaque page Â»

