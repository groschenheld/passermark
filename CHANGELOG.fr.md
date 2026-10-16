# Journal des modifications – Passermark

**English :** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · **Français** · [Español](CHANGELOG.es.md)

> Ce journal contient les versions depuis **1.10.0** en français. L'historique complet :
> [CHANGELOG.md](CHANGELOG.md) (anglais) ou [CHANGELOG.de.md](CHANGELOG.de.md) (allemand).

## 1.13.0
### Vue plus rapide (refonte du rendu)
- **Rendu dans un processus séparé :** les pages sont rendues par un processus en arrière-plan (`passermark-cli render-server`) ; l'interface n'attend plus jamais. Une seule demande est en vol à la fois – en feuilletant vite, les demandes périmées ne s'accumulent plus. Si le processus plante, il redémarre ; s'il ne démarre pas (ou si le PDF est protégé par mot de passe), la vue rend dans le programme comme avant.
- **Une image par page :** chaque page est rendue une fois à peu près au double de la taille d'affichage ; les niveaux de zoom en deçà et les vignettes en sont seulement mis à l'échelle. Les images d'une page sont décompressées une seule fois, au lieu d'une fois par niveau de zoom et par vignette.
- **Le zoom fort ne rend que la partie visible,** au pixel près même en vue pivotée. À 400 % la page est brièvement floue puis nette (auparavant agrandie et floue).
- **Enregistrer sur le même fichier fonctionne maintenant sous Windows :** le fichier est lu en mémoire et reste libre sur le disque.
- **Mode édition :** pendant le déplacement, l'objet suit en semi-transparent ; après application, les anciennes images restent comme espaces réservés et sont renouvelées en arrière-plan, la page éditée d'abord. Avant, tout devenait blanc et toutes les vignettes étaient rendues à nouveau dans la fenêtre principale.
- **Le contrôle automatique lit directement les fichiers non modifiés** – à l'ouverture, le réenregistrement dans la fenêtre principale disparaît.

Mesuré avec le fichier de test de 309 Mo (combien de temps l'interface gelait) :

| | 1.12.1 | 1.13.0 |
|---|---|---|
| Ouvrir | 5,6 s | 1,1 s |
| Zoom (3 niveaux) | 1,5 s | 0,02 s |
| Tourner la page | 1,4 s | 0,02 s |
| 400 % | 1,7 s, flou | 0,03 s, net |
| Déplacer un objet | – | 0,01 s, l'objet suit comme image |

- Dépannage : avec `PASSERMARK_RENDER=local`, tout fonctionne comme avant – un moyen rapide de savoir si la cause est le nouveau processus de rendu.
- Limite connue : relâcher un objet en mode édition prend encore environ 1 s sur les pages lourdes (le contrôle de sécurité compare la page avant et après). Un élément utilisé sur plusieurs pages peut changer partout par une modification ; c'est pourquoi après l'édition toutes les pages sont rendues à nouveau en arrière-plan, celle éditée en premier.

## 1.12.6
### Ajustements du prévol
- Petits ajustements de « Réduire la taille du fichier » (`shrink`) et des contrôles du prévol ; traductions complétées ; manuel de la CLI (DE/EN) mis à jour.

## 1.12.5
### Licences
- L'installateur et l'AppImage incluent désormais tous les avis de licence des tiers (paquets Python, Qt LGPL-3.0, Ghostscript AGPL-3.0 avec référence au code source, bibliothèques système embarquées), consultables via la nouvelle entrée de menu Aide → Licences.
- README : nouvelle section sur les licences des tiers, code source disponible sur demande.
### Documentation
- Le manuel de la CLI (DE/EN) est mis à jour avec `shrink` et `flatten_softmask`.

## 1.12.4
### Réduire la taille du fichier (nouveau)
- Accessible depuis l'onglet « Taille du fichier » ou Document → « Réduire la taille du fichier … », y compris pour les fichiers non signalés comme trop volumineux.
- Chaque mesure s'active et se désactive individuellement :
  - **Sans perte, activé par défaut :** réécrire (supprime les anciennes versions), supprimer les ressources inutilisées, fusionner les doublons (polices, images, profils ICC), retirer les données d'édition et les vignettes, recompresser les images sans perte (retire aussi le ZIP autour du JPEG si plus petit).
  - **Désactivé par défaut :** 16 → 8 bits, supprimer les pièces jointes, supprimer le contenu des calques masqués.
  - **Sous-échantillonnage optionnel :** à 300/240/150/100 dpi avec seuil et qualité JPEG, mesuré au plus grand placement. Les masques doux sont mis à l'échelle en même temps.
- Le résultat s'ouvre dans une nouvelle fenêtre et l'original reste inchangé. Si le résultat n'est pas plus petit, le fichier est conservé tel quel.
- CLI : `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 …]`
- Exemple : un fichier de 34 Mo avec le même profil CMJN intégré 90 fois est descendu à 0,5 Mo, identique au pixel près.

## 1.12.3
### Prévol (preflight)
- **Nouvel onglet « Taille du fichier » :** montre où vont les octets : images, polices, profils colorimétriques, données d'édition Illustrator/Photoshop, vignettes, pièces jointes, contenu des pages.
  - Liste aussi les anciennes versions enregistrées, les doublons et les plus grandes images avec leur résolution effective.
  - Avertit des fichiers très volumineux (plus de 20 Mo par surface A4) et des doublons volumineux.

## 1.12.2
### Prévol (preflight)
- **Dégradés transparents (masque doux dans les motifs) :** détectés et réparables. Certains RIP/traceurs les impriment sous forme d'une zone noire qui recouvre les images situées dessous. La nouvelle réparation « Convertir les dégradés transparents en images (300 dpi) » ne rend que les dégradés concernés, avec ce qui se trouve dessous, sous forme d'une image opaque. Le texte et les vecteurs au-dessus restent intacts. Ghostscript n'est pas nécessaire.
- **Photos HDR (gain map) :** une photo HDR de téléphone ouverte avec les deux images est maintenant détectée par le contrôle. Réparation : « Supprimer les pages auxiliaires HDR … », avec taille au choix et fusion optionnelle du gain map.
- **Nouvel onglet « Images et couleurs » :**
  - Espace colorimétrique par image et par page (RVB, CMJN, niveaux de gris, tons directs), y compris le nom exact du profil ICC et l'intention de rendu (output intent).
  - Résolution effective par placement, également pour les images utilisées plusieurs fois ou dans des formulaires.
  - Taille maximale recommandée à 300 et 150 dpi, plus l'échelle maximale par page.
  - Avertissements pour basse résolution et informations sur le contenu RVB et les tons directs.

## 1.12.1
- **Édition : plusieurs objets et lignes à la fois.** « Agrandir / déplacer … », « Supprimer
  l'objet », « Appliquer » (police et taille) et « Supprimer la ligne » s'appliquent désormais à
  tous les objets ou lignes choisis, plus seulement à un seul. Avec plusieurs lignes sélectionnées,
  le champ texte est verrouillé – modifier le texte ne fonctionne qu'avec une seule ligne
- **Édition : changer la couleur.** Nouveau bouton « Couleur … » pour les lignes de texte et les
  objets vectoriels, au choix CMJN (par défaut, pour l'impression) ou RVB ; pour les vecteurs,
  remplissage et contour se règlent séparément. Le noir 0/0/0/100 reste du noir pur. La couleur est
  posée directement dans le contenu de la page – tout ce qui est hors de la sélection reste
  inchangé, y compris les objets qui n'ont fait qu'hériter leur couleur
- **Édition : vue d'ensemble.** Les onglets affichent le nombre (« Texte (12) », « Objets (40) ») ;
  dans l'onglet « Objets » un filtre par vecteurs ou images est disponible, avec le nombre par type.
  Avec un filtre actif, un clic sur la page ne sélectionne que ce type
- **Photos HDR de téléphone (iPhone, Android) reconnues.** Ces JPG contiennent à côté de la photo
  une carte de luminance grise pour les écrans HDR. Auparavant, cela devenait une deuxième page
  d'une autre taille – aux couleurs fausses au traceur. Désormais un avis s'affiche à l'ouverture ;
  « Réparer » donne une page avec la photo inchangée, taille au choix (comme l'image auxiliaire ou
  comme enregistrée dans la photo). La carte de luminance peut être intégrée en option. Sans
  demande (ligne de commande, impression directe), la réparation est automatique
- **Corrigé : taille de police du texte sur tracé.** Après modification, la liste continuait
  d'afficher l'ancienne taille et chaque nouvelle modification agrandissait encore (24 → 36 →
  54 pt). La taille réelle s'affiche maintenant ; les arcs courts avec peu de lettres sont
  également reconnus comme texte sur tracé. « Appliquer » sans modification laisse la page
  intacte
- **Corrigé : ordre Z.** « Un pas devant » sur l'objet le plus haut signalait à tort « structure de
  la page non reconnue » – maintenant tout reste simplement tel quel
- **Corrigé : faire glisser du texte avec la souris** s'interrompait avec un message d'erreur sur
  certains PDF (p. ex. de Chrome)
- Traductions ajoutées pour la disposition des poses dans le dialogue d'impression (anglais,
  hongrois, espagnol, français)

## 1.11.3
- **Boîte de dialogue VDP relookée.** Les données variables affichent le même visage que le
  dialogue d'impression : quatre sections numérotées repliables (champs, données, numérotation,
  sortie) et, en haut, une « Guide » repliée. Les explications des champs deviennent des
  info-bulles et n'apparaissent sous le champ que via le nouveau commutateur « Afficher les
  textes d'aide ». L'ancienne note de sortie renvoie désormais à l'ordre du dialogue
  d'impression (Poses, « Page suivante sur chaque pose »). Le widget CollapsibleSection vit
  dans common.py, partagé par les deux dialogues.
- **Boîte de dialogue d'impression sans onglets.** Le sélecteur de mode en haut (« Que faut-il
  imprimer ? ») guide désormais dans une seule colonne continue : préréglage, mode, panneau du
  mode, mise à l'échelle (« Comment sur la feuille ? »), traits de coupe, papier/sortie, finisseur,
  gestion des couleurs. L'ancienne navigation par onglets disparaît.
- **Le pas répété (Step & Repeat) devient un mode à part.** « Nutzen » rejoint le sélecteur de mode
  à côté des pages simples, plusieurs par feuille, livret et affiche – avec un texte explicatif
  comme les autres modes. L'ancienne case à cocher est remplacée par le bouton de mode ; le panneau
  Nutzen apparaît au même endroit que les autres panneaux de mode.
- **« Comment sur la feuille ? »** mise à l'échelle et orientation forment un seul groupe :
  ajuster/taille d'origine/réduire/personnalisé, rotation, rotation automatique, centrage, marges.
  Le choix d'échelle (ajuster/taille réelle/…) est visible et effectif dans tous les modes : ajuster = valeur par défaut du mode, taille réelle/réduire/personnalisé
  remplace la mise à l'échelle du mode – les champs du mode (échelle par tuile, échelle Nutzen, affiche) restent en place.
- **Miroir et options du pilote repliables.** Les deux sections restent bien visibles avec un
  titre clair et ne se déplient qu'au besoin – toutes les options inchangées.
- **Reliure livret : « Standard » en premier.** La piqûre à cheval classique (« toutes les feuilles
  imbriquées, pliées une fois ») ouvre désormais la liste des types sous le nom clair « Standard » –
  le compteur « feuilles par cahier » n'apparaît que pour les cahiers groupés et ne peut plus
  suggérer un réglage sans effet.
- **Sections repliables uniformes.** Chaque bloc de la nouvelle colonne – préréglage, sélecteur de
  mode (« Que faut-il imprimer ? »), « Comment sur la feuille ? », traits de coupe, papier/sortie,
  finisseur, gestion des couleurs, miroir, pilote – porte le même en-tête repliable, à taille
  identique. Les boutons de mode sont empilés verticalement : toutes les étiquettes restent
  lisibles ; le panneau du mode se réduit au mode visible (plus d'espace vide). On peut toujours
  quitter le mode « Nutzen ».
- **Traductions :** 26 messages nouveaux/complétés par langue (EN/DE/ES/FR/HU) ; les chaînes
  1.11.1 manquantes dans les catalogues ES/FR/HU/EN ont été complétées. Les anciens préréglages
  restent entièrement compatibles (handling size/multiple/sr se chargent toujours).

## 1.11.2
- **Étape 2 : monter la feuille à nouveau.** La feuille terminée de l'étape 1 est montée une seconde fois
  sur un format cible librement choisi (formats de l'appareil ou dimensions personnalisées en mm) –
  ligne par ligne, toujours centrée, contenu inchangé ; le résultat peut être émis comme nouveau document
  via un bouton (nouvel onglet), l'aperçu le montre comme à l'étape 1 et le dialogue se ferme ensuite.
  La rotation et l'orientation de l'étape 1 s'appliquent aussi à l'étape 2. Grille : 0 × 0 = automatique
  (autant que possible).
- **Utiliser les traits de coupe existants.** Avec les documents dotés d'un format final (TrimBox), les
  côtés extérieurs du bloc de poses montrent le vrai bord du document – les traits de coupe existants
  restent visibles ; les traits propres restent activables par case à cocher comme avant.
- **Monter la grille exactement.** Une grille définie (p. ex. 3 × 3) reste toujours exacte à l'étape 1 et
  à l'étape 2 – si elle ne tient pas sur la feuille, elle est rognée symétriquement au bord avec un
  avertissement, jamais annulée.
- **Format cible planifié sans marges :** p. ex. deux feuilles A4 de l'étape 1 tiennent proprement sur un A3.
- Le chemin d'impression et l'orientation de l'étape 1 restent inchangés.

## 1.11.1
- **Formats personnalisés : uniquement « Enregistrer en PDF ».** Les formats créés soi-même ne sont plus
  envoyés aux imprimantes – les pilotes et spoolers Windows n'acceptent souvent pas les tailles personnalisées
  (feuilles blanches, abandons) ; avec « Enregistrer en PDF » (★), ils restent entièrement utilisables
- **Rognage : deux nouveaux modes.** « Rogner les bords » : rogner la page sur les quatre côtés en mm, sans
  format cible ; « Supprimer l'espace blanc » : détecte le contenu visible (bruit JPEG compris), le nouveau
  format de page résulte du cadre du contenu ± marge (négative possible), le contenu reste 1:1 (seulement déplacé)

## 1.11.0
- **Données variables – fenêtres (groupes de pages).** Pour les gabarits multi-pages, chaque champ appartient
  à une fenêtre (p. ex. « rectos (nom), versos (code QR) ») ; les fenêtres peuvent être créées, renommées et
  supprimées – leurs champs rejoignent alors la première fenêtre. Sélection des pages par fenêtre : toutes,
  impaires (rectos), paires (versos) ou plages (« 1,3-5 ou impaires 1-50 ») ; sans sélection propre, la couche
  de base « toutes les pages » s'applique. Répartition « feuille par feuille » (d'abord toutes les pages avec
  l'enregistrement 1) ou « page par page » (d'abord la page 1 avec tous les enregistrements) ; affichage
  « {0} enregistrements → {1} pages » et avertissement « – {0} pages sans fenêtre ! »
- **Aperçu VDP :** format final en vert, fond perdu en rouge ; cadre intérieur réglable (ligne guide)
- **Indicateur de page « actuelle / total »** dans la barre d'outils ; saisir un numéro et Entrée pour y aller
- **Règles, mesure et affichage du format final en permanence dans la barre d'outils principale** – dans
  tous les espaces de travail
- **Format final et fond perdu dans la vue principale :** bordure intérieure (format final) en vert au lieu
  de rouge, fond perdu en pointillé rouge discret au lieu d'une surface pleine
- **Mesure avec aimantation :** avec Ctrl maintenue, le réticule s'aimante aux lignes de coupe et intérieures
  (bord de page, format final, fond perdu) ainsi qu'aux bords d'images et aux lignes vectorielles – jamais
  au texte ; le réticule d'aperçu colle au bord tant que la souris ne s'en éloigne nettement ; Maj verrouille
  toujours horizontal/vertical/45°

## 1.10.7
- **CutContour : formes de base sans calcul.** Nouveau placement « Sur le format final (sans calcul) » :
  rectangle, rectangle arrondi, cercle … sont posés directement sur le format final (TrimBox, sinon la page) –
  pas de rendu, pas de détection du motif, pas de processus de travail, en une fraction de seconde. Distance,
  taille, décalage et glissement à la souris fonctionnent comme avant. Le calcul n'a lieu qu'avec « Contour »
  ou lorsque la forme est placée autour du motif ou par objet. Ligne de commande : `--set fit=trim`
- **Valeur par défaut dans CutContour :** rectangle sur le format final (tant qu'aucun dernier réglage
  personnel n'est enregistré)

## 1.10.6
- **Correctif Windows : CutContour restait bloqué à 0 %** (depuis 1.10.5). Le passage de la sortie en ligne
  de commande en UTF-8 est de nouveau supprimé ; le correctif pour « Diviser les pages » reste (messages de
  progression en ASCII pur)
- CutContour : plus d'erreur si un calcul d'aperçu arrive après la fermeture de la fenêtre
  (« expected LP_struct_fpdf_document_t … NoneType »)

## 1.10.5
- **Correctif Windows :** « Diviser les pages » (et toute tâche dont le message contient des caractères comme
  « → ») s'interrompait avec `UnicodeEncodeError … cp1252`. La ligne de commande bascule désormais elle-même
  sa sortie en UTF-8 ; les messages de progression vers l'interface sont en ASCII pur
- `SECURITY.md`, `CONTRIBUTING.md` et les modèles GitHub pour les rapports de bug et les suggestions inclus
  dans le paquet

## 1.10.4
- README bilingue : `README.md` (anglais) et `README.de.md` (allemand), à jour (diviser les pages, données
  variables, saisie des données, toutes les tâches en ligne de commande) et avec une note sur l'état du projet
- Exemple de configuration `data/defaults.example.json` avec des noms d'imprimantes neutres

## 1.10.3
- **Diviser les pages via le clic droit :** sélectionner des pages dans la barre latérale → clic droit →
  **Diviser** → « Couper en deux verticalement » / « Couper en deux horizontalement » – immédiatement, uniquement
  les pages sélectionnées, sans page de comparaison. « Grille / plus d'options … » ouvre le dialogue avec la
  sélection préréglée

## 1.10.2
- **Données variables – recto et verso :** nouveau « Pages par enregistrement » (sous 2.) : 2 = pages 1+2 →
  enregistrement 1, 3+4 → enregistrement 2 … – que le modèle ait 2 pages ou déjà toutes les cartes (p. ex.
  200 pages pour 100 cartes de visite). Les champs « Uniquement sur ces pages » connaissent désormais
  **impaire** et **pair**, combinables avec des plages (« impair 1-50 »). Exemple 7 : carte de visite avec le
  nom au recto et une carte QR au verso
- **Autres variables :** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. Le bouton **?** à côté du
  contenu les affiche toutes avec une valeur d'exemple, un double-clic insère. Les colonnes CSV de même nom
  ont priorité
- Un double-clic sur une colonne **remplace** un {{nr}} inchangé au lieu de le laisser devant
- **Diviser les pages** (Pages → Diviser les pages …, espace de travail Édition) : couper en deux
  verticalement/horizontalement ou en grille, toutes/actuelles/pages sélectionnées ou plage, uniquement les
  doubles pages, ordre de droite→gauche ; avec aperçu des traits de coupe. **Diviser les doubles pages** en un
  clic pour les brochures mal exportées. Sans perte (le contenu n'est ni copié ni tramé), les pages tournées
  telles qu'on les voit ; avec un format final la division se fait dedans et le fond perdu reste dehors.
  Ligne de commande : tâche `split`
- **Barre latérale :** les vignettes tournent avec « Pivoter la vue à gauche/droite »
- **Corrigé : l'ouverture depuis l'extérieur atterrissait dans une fenêtre verrouillée** (Windows, clic
  droit/double-clic pendant qu'un outil est ouvert dans une fenêtre) – désormais sa propre fenêtre. Cause :
  l'ouverture dans la fenêtre de démarrage vide laissait un onglet vide invisible ; la fenêtre vide est
  maintenant utilisée elle-même. Les résultats d'une fenêtre verrouillée s'ouvrent aussi dans leur propre
  fenêtre

## 1.10.1
- **Utiliser directement son propre CSV avec d'autres noms de colonnes :** Données variables → Ouvrir CSV
  reconnaît à quoi convient le tableau (« Le tableau convient à : QR – carte de visite »), **Créer le champ
  adapté** crée le code QR avec ce type. Les colonnes sont associées automatiquement – y compris les noms
  anglais, hongrois, espagnols, français et les en-têtes des exports de contacts d'**Outlook, Google et
  Thunderbird**. Le CSV reste inchangé
- **Associer les colonnes …** dans le champ QR avec un type : choisir la colonne par donnée, « laisser vide »
  ou automatique ; avec aperçu du contenu final. Sous le type s'affiche ce qui vient d'où et ce qui manque.
  L'association est enregistrée dans le préréglage (`qr_map`) et vaut aussi en ligne de commande
- Saisie des données : un CSV aux noms de colonnes étrangers ne reçoit plus de colonnes en double ; l'en-tête
  montre l'association (« First Name → Vorname »). `datencheck` reconnaît aussi les noms de colonnes
  étrangers
- Dossier d'exemples : `kontakte-outlook.csv` (voici à quoi ressemble un export Outlook) ; le guide
  complété avec « Son propre CSV avec d'autres noms de colonnes »

## 1.10.0
- **Saisir les données** (espace de travail Données variables, menu Manipulation de document, ou dans le
  dialogue Données variables sous 2.) : créer le tableau de données directement dans Passermark. Les colonnes
  adaptées par type – **carte de visite QR (vCard), accès Wi-Fi, e-mail, adresse web, appel, SMS,
  rendez-vous, lieu**, texte QR libre, **Code 128**, **EAN-13**, texte avec colonnes propres. Chaque ligne est
  vérifiée immédiatement (données obligatoires, chiffre de contrôle EAN, umlauts dans le Code 128, date …), à
  droite le code fini de la ligne choisie. Coller depuis Excel avec Ctrl+V, dupliquer des lignes, remplir une
  colonne avec une série de numéros (crée aussi les lignes), colonnes propres. Enregistrer en CSV (UTF-8 avec
  BOM, point-virgule – Excel lit correctement les umlauts)
- **« Utiliser dans les données variables »** reprend le tableau comme source de données et crée le champ
  adapté
- **Champ QR « Type de code QR » :** contenu tel que saisi ou composé à partir des colonnes du tableau (vCard,
  Wi-Fi, mailto, tel, SMS, rendez-vous, géo). Le CSV reste lisible ; Passermark construit le contenu du code
  lors de la génération
- **Zone de silence :** le code QR et le Code 128 ont désormais une bordure blanche dans le champ
  (désactivable). Sans elle, les codes proches d'un autre contenu étaient mal lisibles. *Préréglages
  existants : le code QR devient un peu plus petit dans le champ à cause de cela*
- **Un EAN-13 à 13 chiffres avec un mauvais chiffre de contrôle est désormais une erreur** (avec le bon numéro
  dans le message) – auparavant le dernier chiffre était remplacé en silence
- Ligne de commande : `datenarten`, `datenvorlage <type> [fichier.csv]`, `datencheck <fichier.csv> [type]`
  (code retour 1 en cas de problème) ; dans le préréglage `qr_type` par champ QR
- Exemples 5 (carte de visite depuis une liste de contacts) et 6 (accès Wi-Fi) ; le guide « Données variables »
  avec une nouvelle section « Saisir les données », guide CLI complété
- Les tests relisent désormais réellement les codes générés : QR et EAN-13 avec OpenCV (si installé), Code 128
  avec son propre lecteur avec somme de contrôle
- Corrigé : les données variables prenaient « une copie du document entier par enregistrement » sans choisir
  la distribution au lieu de « l'enregistrement suivant sur chaque page »
