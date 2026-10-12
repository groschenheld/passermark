# Journal des modifications – Passermark

**English :** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · **Français** · [Español](CHANGELOG.es.md)

> Ce journal contient les versions **1.10.x** en français. L'historique complet :
> [CHANGELOG.md](CHANGELOG.md) (anglais) ou [CHANGELOG.de.md](CHANGELOG.de.md) (allemand).

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
