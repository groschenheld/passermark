# Contributing / Mitmachen

**English** · [Deutsch](#deutsch) · [Magyar](#magyar) · [Français](#français) · [Español](#español)

Passermark is a private project, developed alongside daily prepress work. Feedback is very welcome – please
understand that answers and new features come without any guarantee.

## Reporting a bug

Open an issue with the **Bug report** form. It asks for what is needed to reproduce the problem:

- Passermark version (title bar) and how it was installed (Windows setup, AppImage, `install.sh`),
- operating system,
- printer and driver (for print problems: CUPS queue/PPD, IPP driverless or Windows driver; print server?),
- steps, expected and actual result,
- the error log, if there is one (**Help → Open error logs**),
- if possible a PDF that shows the problem. Please remove or replace confidential content first.

**Security problems** are not reported in public issues – see [SECURITY.md](SECURITY.md).

## Suggesting a feature

Use the **Feature request** form and describe the job you want to get done (e.g. "a customer sends 100 business
cards as one PDF …") rather than only the button you imagine. That helps to find a solution that fits.

## Pull requests

Please **open an issue first and wait for a reply** before writing code. Unannounced pull requests may be closed
without review – not because they are bad, but because I can only maintain what fits the overall plan.

If we agree on a change:

- one topic per pull request, small is better,
- Python 3.10 compatible, no new dependencies without discussing them,
- tests: add or adapt `tests/test_<name>.py` and run them (`python3 tests/test_<name>.py`),
- user-visible texts go through `tr("…")` (German source text) – translations are added afterwards,
- by submitting a pull request you agree that your contribution is licensed under GPL-3.0-or-later.

## Translations

The program is available in German, English, Hungarian, Spanish and French. Corrections to existing translations
are welcome as an issue (screenshot + better wording).

---

## Deutsch

Passermark ist ein privates Projekt, entwickelt neben der täglichen Arbeit in der Druckvorstufe. Rückmeldungen
sind sehr willkommen – bitte hab Verständnis, dass Antworten und neue Funktionen ohne Garantie kommen.

### Fehler melden

Ein Issue mit dem Formular **Fehler melden / Bug report** öffnen. Es fragt ab, was zum Nachstellen nötig ist:

- Passermark-Version (Titelleiste) und wie installiert (Windows-Setup, AppImage, `install.sh`),
- Betriebssystem,
- Drucker und Treiber (bei Druckproblemen: CUPS-Warteschlange/PPD, IPP ohne Treiber oder Windows-Treiber;
  Druckserver?),
- Schritte, erwartetes und tatsächliches Ergebnis,
- das Fehlerprotokoll, falls vorhanden (**Hilfe → Fehlerprotokolle öffnen**),
- wenn möglich ein PDF, das den Fehler zeigt. Vertrauliche Inhalte bitte vorher entfernen oder ersetzen.

**Sicherheitsprobleme** bitte nicht in öffentlichen Issues melden – siehe [SECURITY.md](SECURITY.md).

### Funktion vorschlagen

Das Formular **Funktion vorschlagen / Feature request** verwenden und die Aufgabe beschreiben, die erledigt werden
soll (z. B. „ein Kunde schickt 100 Visitenkarten als ein PDF …“) – nicht nur den Knopf, den du dir vorstellst.
So findet sich eher eine Lösung, die passt.

### Pull Requests

Bitte **zuerst ein Issue öffnen und auf eine Antwort warten**, bevor du Code schreibst. Unangekündigte Pull
Requests werden eventuell ohne Prüfung geschlossen – nicht weil sie schlecht sind, sondern weil ich nur pflegen
kann, was in den Gesamtplan passt.

Wenn wir uns auf eine Änderung einigen:

- ein Thema je Pull Request, klein ist besser,
- kompatibel mit Python 3.10, keine neuen Abhängigkeiten ohne Absprache,
- Tests: `tests/test_<name>.py` ergänzen oder anpassen und ausführen (`python3 tests/test_<name>.py`),
- sichtbare Texte über `tr("…")` (deutscher Ausgangstext) – Übersetzungen kommen danach dazu,
- mit einem Pull Request stimmst du zu, dass dein Beitrag unter GPL-3.0-or-later steht.

### Übersetzungen

Das Programm gibt es auf Deutsch, Englisch, Ungarisch, Spanisch und Französisch. Verbesserungen bestehender
Übersetzungen gern als Issue (Bildschirmfoto + bessere Formulierung).

---

## Magyar

A Passermark magánprojekt, a napi nyomdai előkészítési munka mellett fejlesztve. Minden észrevételt szívesen
fogadok – kérjük, légy megértő, hogy a válaszok és az új funkciók garancia nélkül érkeznek.

### Hiba bejelentése

Nyiss egy issue-t a **Hibabejelentés / Bug report** űrlappal. Megkérdezi, mi kell a reprodukáláshoz:

- Passermark-verzió (címsor) és hogyan lett telepítve (Windows-setup, AppImage, `install.sh`),
- operációs rendszer,
- nyomtató és illesztőprogram (nyomtatási problémáknál: CUPS-sor/PPD, IPP illesztő nélkül vagy
  Windows-illesztő; nyomtatószerver?),
- lépések, várt és tényleges eredmény,
- a hibanapló, ha van (**Súgó → Hibák naplóinak megnyitása**),
- ha lehetséges, egy PDF, amely megmutatja a hibát. A bizalmas tartalmakat kérjük előbb távolítsd el vagy
  cseréld ki.

**Biztonsági problémákat** kérjük ne nyilvános issue-ban jelents – lásd [SECURITY.md](SECURITY.md).

### Funkció javaslása

Használd a **Funkció javaslása / Feature request** űrlapot, és írd le a feladatot, amelyet el akarsz
végeztetni (pl. „egy ügyfél 100 névjegykártyát küld egy PDF-ben …”) – ne csak a gombot, amit elképzelsz.
Így könnyebb olyan megoldást találni, amely illik.

### Pull Requestek

Kérjük, **előbb nyiss issue-t és várj válaszra**, mielőtt kódot írsz. Be nem jelentett pull requesteket
esetleg ellenőrzés nélkül lezárok – nem azért, mert rosszak, hanem mert csak azt tudom karbantartani, ami
az átfogó tervbe illik.

Ha megegyezünk egy változtatásban:

- egy téma pull requestenként, a kisebb jobb,
- Python 3.10-kompatibilis, új függőségek egyeztetés nélkül nem,
- tesztek: `tests/test_<név>.py` kiegészítése vagy igazítása és futtatása (`python3 tests/test_<név>.py`),
- a látható szövegek `tr("…")`-en mennek át (német forrásszöveg) – a fordítások utána kerülnek hozzá,
- pull request beküldésével elfogadod, hogy a hozzájárulásod GPL-3.0-or-later alatt áll.

### Fordítások

A program magyarul, németül, angolul, spanyolul és franciául érhető el. A meglévő fordítások javításait
szívesen fogadom issue-ként (képernyőkép + jobb megfogalmazás).

---

## Français

Passermark est un projet privé, développé à côté du travail quotidien de prépresse. Les retours sont très
bienvenus – merci de comprendre que les réponses et les nouvelles fonctions sont fournies sans garantie.

### Signaler un bug

Ouvrez une issue avec le formulaire **Bug report**. Il demande ce qu'il faut pour reproduire le problème :

- version de Passermark (barre de titre) et mode d'installation (setup Windows, AppImage, `install.sh`),
- système d'exploitation,
- imprimante et pilote (pour les problèmes d'impression : file/PPD CUPS, IPP sans pilote ou pilote Windows ;
  serveur d'impression ?),
- étapes, résultat attendu et réel,
- le journal d'erreurs, s'il existe (**Aide → Ouvrir les journaux d'erreurs**),
- si possible un PDF qui montre le problème. Merci de retirer ou remplacer le contenu confidentiel
  au préalable.

**Les problèmes de sécurité** ne se signalent pas dans des issues publics – voir [SECURITY.md](SECURITY.md).

### Proposer une fonctionnalité

Utilisez le formulaire **Feature request** et décrivez la tâche à accomplir (p. ex. « un client envoie 100
cartes de visite dans un seul PDF … ») plutôt que seulement le bouton que vous imaginez. Cela aide à trouver
une solution adaptée.

### Pull requests

Merci **d'ouvrir d'abord une issue et d'attendre une réponse** avant d'écrire du code. Les pull requests non
annoncées peuvent être fermées sans examen – non parce qu'elles sont mauvaises, mais parce que je ne peux
maintenir que ce qui s'intègre au plan d'ensemble.

Si nous nous mettons d'accord sur un changement :

- un sujet par pull request, petit c'est mieux,
- compatible Python 3.10, pas de nouvelles dépendances sans en avoir discuté,
- tests : ajouter ou adapter `tests/test_<nom>.py` et les exécuter (`python3 tests/test_<nom>.py`),
- les textes visibles passent par `tr("…")` (texte source allemand) – les traductions sont ajoutées ensuite,
- en soumettant une pull request, vous acceptez que votre contribution soit sous GPL-3.0-or-later.

### Traductions

Le programme est disponible en français, allemand, anglais, hongrois et espagnol. Les corrections des
traductions existantes sont bienvenues en issue (capture d'écran + meilleure formulation).

---

## Español

Passermark es un proyecto privado, desarrollado junto al trabajo diario de preprensa. Los comentarios son
muy bienvenidos – por favor, ten en cuenta que las respuestas y las nuevas funciones se ofrecen sin
garantía.

### Informar de un error

Abre un issue con el formulario **Informe de error / Bug report**. Pregunta lo necesario para reproducir el
problema:

- versión de Passermark (barra de título) y cómo se instaló (setup de Windows, AppImage, `install.sh`),
- sistema operativo,
- impresora y controlador (para problemas de impresión: cola/PPD de CUPS, IPP sin controlador o controlador
  de Windows; ¿servidor de impresión?),
- pasos, resultado esperado y real,
- el registro de errores, si existe (**Ayuda → Abrir registros de errores**),
- si es posible, un PDF que muestre el error. Por favor, elimina o sustituye antes el contenido confidencial.

**Los problemas de seguridad** no se informan en issues públicos – véase [SECURITY.md](SECURITY.md).

### Proponer una función

Usa el formulario **Propuesta de función / Feature request** y describe la tarea que quieres resolver (p.
ej. «un cliente envía 100 tarjetas de visita en un solo PDF …») en lugar de solo el botón que imaginas.
Así es más fácil encontrar una solución que encaje.

### Pull requests

Por favor, **abre primero un issue y espera una respuesta** antes de escribir código. Las pull requests no
anunciadas pueden cerrarse sin revisión – no porque sean malas, sino porque solo puedo mantener lo que
encaja en el plan general.

Si nos ponemos de acuerdo en un cambio:

- un tema por pull request, mejor pequeño,
- compatible con Python 3.10, sin nuevas dependencias sin acordarlo,
- pruebas: añadir o adaptar `tests/test_<nombre>.py` y ejecutarlas (`python3 tests/test_<nombre>.py`),
- los textos visibles pasan por `tr("…")` (texto fuente alemán) – las traducciones se añaden después,
- al enviar una pull request aceptas que tu contribución esté bajo GPL-3.0-or-later.

### Traducciones

El programa está disponible en español, alemán, inglés, húngaro y francés. Las correcciones a las
traducciones existentes son bienvenidas como issue (captura de pantalla + mejor formulación).
