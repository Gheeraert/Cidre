# CIDRE
**Générateur de site statique pour maisons d'édition scientifique (ou indépendantes)**

**Catalogue Internet - Documentation - Recherche - Edition**

Ce dépôt contient un **générateur de site web statique** (sans base de données, sans backend) destiné aux maisons d’édition académiques : à partir d’un **fichier tableur** unique (métadonnées + pages éditoriales), le script produit un site statique HTML complet (catalogue, pages “collections”, “revues”, pages fixes, couvertures, etc.), prêt à être déployé sur un serveur universitaire ou via GitHub Pages. Il gère aussi les sorties Onix pour les relations avec les diffuseurs (FMSH, AFPU, etc.).

**Objectif**
Il s'agit de créer un outil souverain, léger, sans dépendance lourde, pilotable depuis un simple tableur et une boîte de dialogue, conformément à l'esprit de l'édition numérique durable et low-tech (sobriété, pérennité, maintenance facile, flux éditorial maîtrisé, single source publishing).

**Principe**
Un clic sur une boîte de dialogue déploie un site complet de maison d'édition, à partir d'un seul fichier tableur correctement structuré et rempli.

Le principe est inspiré du Pressoir, générateur en production aux Presses de Montréal et aux Presses universitaires de Rouen et du Havre: https://www.arthurperret.fr/veille/2023-12-24-le-pressoir.html

CIDRE est une chaîne d’éditorialisation où un tableur joue le rôle d’interface de gouvernance des métadonnées, et où le site statique est le produit. CIDRE part d’un fichier Excel unique qui joue trois rôles : Réservoir de données structurées, Interface de pilotage, contrat de structure. Quand on lance CIDRE, le script charge les onglets, nettoie et normalise, harmonise les colonnes, fabrique des champs dérivés indispensables au web statique.

À partir des DataFrames, CIDRE construit une représentation JSON qui devient la source unique de vérité pour la génération. Le catalogue en json permet ensuite d’avoir une navigation, des listes, et des “index” utiles au moteur de recherche (côté client, sans serveur). Autrement dit : CIDRE fabrique un modèle de données éditorial à partir du tableur.

Une fois le modèle prêt, CIDRE génère un ensemble de fichiers dans le dossier de sortie choisi par l'utilisateur. Les contenus textuels sont généralement traités (Markdown → HTML) puis injectés dans un gabarit.

CIDRE peut aussi publier le dossier de sortie par FTP (déploiement simple) et exporter des métadonnées (par ex. ONIX), selon la même logique: on repart du modèle normalisé pour produire un flux.

Le dispositif reste léger, souverain, maintenable et sécurisé.

**Exemple en production**
Site des Presses universitaires de Rouen et du Havre
[https://purh.univ-rouen.fr/](https://purh.univ-rouen.fr/)

**Site public de téléchargement**
Téléchargement des exécutables et utilisation
[https://purh.univ-rouen.fr/cidre](https://purh.univ-rouen.fr/cidre)

---

## Fonctionnalités

- Génération d’un site **100% statique**
- Lecture d’un classeur tableur structuré (onglets “CONFIG”, “PAGES”, “COLLECTIONS”, “REVUES”, “CONTACTS” + onglet catalogue)
- Pages générées :  
  - `index.html` (accueil)  
  - `catalogue.html` (recherche + filtres côté navigateur)
  - `actualites.html` (+ carrousel sur page d'accueil)
  - `nouveautes.html`, `a-paraitre.html`  
  - fiches individuelles dans `livres/`
  - `collections/…`, `revues/…`  
  - pages fixes (politique éditoriale, mentions légales, etc.)
- Export d’un `catalogue.json` réutilisable ; le catalogue HTML reste lisible sans JavaScript,
  avec recherche, filtres et affichage progressif activés côté navigateur lorsque JavaScript est disponible
- Gestion des couvertures (copie, fallback si manquante)
- Pages de collections et de revues, avec présentation des numéros associés lorsqu'ils sont renseignés
- Export ONIX et validation ONIX autonome
- Référencement statique : URL canoniques, métadonnées de partage, données structurées, `robots.txt` et sitemap lorsque `site_url` est valide
- Option de publication FTP si activée dans la configuration
- Utilisation simple : chargement de l'Excel et génération automatique depuis une interface tkinter (boîte de dialogue)

---

## Prérequis

- **Python 3.12** est la version de référence, utilisée par la CI et pour le verrou des dépendances.
- Un environnement virtuel est recommandé.

> `requirements.txt` liste les dépendances directes ; `requirements-lock.txt` fige les versions exactes validées.

---

## Installation

```bash
git clone https://github.com/Gheeraert/Cidre.git
cd Cidre

python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

python -m pip install -r requirements-lock.txt
```

### Dépendances Python verrouillées

`requirements.txt` liste les dépendances directes de CIDRE et leurs bornes.
`requirements-lock.txt` fige les versions exactes directes et transitives
testées ensemble.

`pip-tools` sert uniquement à régénérer ce verrou ; il n'est pas une dépendance
d'exécution de CIDRE.

Pour compiler les exécutables Windows (`build_exe.bat`), préparez
l'environnement de compilation avec :

```bat
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Pour régénérer le verrou, utilisez un environnement Python 3.12 propre :

```bash
python -m venv .venv-lock
.venv-lock\Scripts\python.exe -m pip install --upgrade pip
.venv-lock\Scripts\python.exe -m pip install pip-tools==7.5.3
.venv-lock\Scripts\python.exe -m piptools compile requirements.txt --output-file requirements-lock.txt
```

Après toute régénération de `requirements-lock.txt`, exécutez la suite
complète avant de committer :

```bash
python -m pytest
```

---

## Démarrage rapide

1) Copiez le gabarit officiel `gabarit/purh_site_excel_gabarit.xlsx` (ne travaillez pas directement dans le gabarit) et remplissez votre copie.

2) Placez les logos et fichiers complémentaires dans un dossier source d'assets, par exemple `assets-source/`.

3) Placez les couvertures dans un dossier (ex. `covers/`).

4) Lancez la génération. Vous pouvez utiliser l'interface graphique `gui_tk.py`, ou la CLI :

```powershell
.venv\Scripts\python.exe build_site.py --excel chemin\vers\classeur.xlsx --out site-sortie --covers-dir covers --assets-dir assets-source
```

5) Ouvrez `site-sortie/index.html` dans un navigateur, ou servez en local :

```bash
python -m http.server 8000 --directory site-sortie
```

Puis visitez : `http://localhost:8000`

## Lancement facile par interface graphique
1. Depuis un IDE comme Pycharm, lancez l'interface graphique tkinter avec gui_tk.py

2. Remplir la boîte de dialogue (chemin du fichier tableur, chemin du dossier de couvertures, cases à cocher)

3. Générer le site

4. Un petit serveur se lance et la page d'accueil s'ouvre automatiquement

## Profils de génération

La GUI permet de charger et d'enregistrer un **Profil de génération** au format JSON.
Ce fichier mémorise uniquement les chemins locaux utiles : classeur Excel, dossier de
sortie, dossier des couvertures et dossier source des assets. Il ne contient aucun
mot de passe FTP, aucune option de publication et aucun contenu du classeur.

Exemple :

```json
{
  "schema_version": 1,
  "excel_path": "C:/PURH/catalogue.xlsx",
  "output_dir": "C:/PURH/site-public",
  "covers_dir": "C:/PURH/covers",
  "assets_dir": "C:/PURH/assets-source"
}
```

Le profil sert seulement à remplir plus vite les champs de la boîte de dialogue.
L'Excel reste l'unique source de vérité éditoriale.

## Validation et génération transactionnelle

CIDRE valide les données avant de générer le site. Les erreurs bloquantes
interrompent la génération. Les alertes contournables doivent être confirmées ;
en CLI, l'option `--force` permet de générer malgré ces alertes lorsqu'elles ne
sont pas bloquantes.

Un rapport `validation.csv` est produit dans le dossier de sortie. Le mode :

```powershell
.venv\Scripts\python.exe build_site.py --excel <classeur.xlsx> --out site-sortie --validate-only
```

écrit le rapport de validation et les données nécessaires sans générer tout le
site.

Lors d'une génération complète, le site est d'abord construit dans un dossier
temporaire voisin du dossier de sortie. Le dossier de sortie existant n'est
remplacé qu'après une construction complète. Si la construction échoue avant ce
remplacement, le site précédent reste en place. Si le basculement final échoue,
CIDRE tente de restaurer automatiquement le dossier précédent.

Cette garantie concerne la génération locale. Elle ne rend pas transactionnelle
une publication FTP distante.

## Stabilité des URL des livres

Avant une génération, CIDRE compare les couples `id13 -> slug` du nouvel Excel avec
le dernier `catalogue.json` présent dans le dossier de sortie. Si un ISBN déjà publié
changerait de slug, CIDRE signale une alerte forte `BOOK_SLUG_CHANGED` et recommande
de recopier dans la colonne `slug` l'ancien slug déjà publié.

CIDRE ne modifie jamais automatiquement l'Excel, ne crée pas de registre historique
et ne génère pas de redirection HTML. En CLI, une génération est interrompue sans
`--force`; l'option `--force` permet de confirmer un changement volontaire.

## Référencement et partage social

Trois clés facultatives de la feuille `CONFIG` complètent le référencement du
site statique :

- `site_url` : URL publique absolue du site, par exemple
  `https://purh.univ-rouen.fr` ; elle permet de générer les URL canoniques,
  le sitemap et l'adresse du sitemap dans `robots.txt`.
- `site_description` : courte description éditoriale générale, utilisée sur
  l'accueil et comme repli sobre.
- `social_image` : image générique de partage, sous la forme d'un chemin publié
  (par exemple `assets/social-share.jpg`) ou d'une URL absolue. Elle est
  facultative et n'est publiée que lorsqu'elle est exploitable.

Sans `site_url` valide, CIDRE continue à produire le site, mais n'émet pas de
canonical ni de sitemap contenant des URL relatives. `robots.txt` reste généré
sans adresse de sitemap. Avec une URL valide, CIDRE génère à la racine
`sitemap.xml` et `robots.txt`, ainsi que des métadonnées de partage et des
données structurées sobres. Ces mécanismes ne créent aucune redirection.

---

## Commandes principales

### Générer le site

```powershell
.venv\Scripts\python.exe build_site.py --excel <classeur.xlsx> --out dist --covers-dir covers
```

> `--tableur` (ancien nom de l'option) reste accepté comme alias de `--excel`.

### Publication (optionnelle)

Si la feuille "config" propose des informations de publication FTP :

```powershell
.venv\Scripts\python.exe build_site.py --excel <classeur.xlsx> --out dist --covers-dir covers --publish-ftp
```

> ⚠️ Les identifiants FTP (ftp_host, ftp_user, ftp_password…) sont lus dans la feuille CONFIG du classeur.  
> Ne commitez **jamais** dans le dépôt un classeur contenant un mot de passe FTP.

### Éditeur d'actualités

Un petit éditeur graphique permet de gérer la feuille ACTUS du classeur sans ouvrir Excel :

```powershell
.venv\Scripts\python.exe actualites_editor.py chemin\vers\classeur.xlsx
```

- l'ISBN du livre associé, le visuel et le lien externe sont facultatifs et indépendants ;
- l'éditeur écrit uniquement dans la feuille `ACTUS` ; il consulte le catalogue pour vérifier les ISBN et retrouver les ouvrages associés, sans lire ni modifier la feuille `CONFIG` ;
- les images importées sont rangées automatiquement dans `assets/actu/` à côté du classeur ;
- les anciens emplacements sont encore acceptés en lecture pour compatibilité, mais `assets/actu/` est l'emplacement recommandé ;
- une sauvegarde horodatée du classeur est créée avant la première modification de la session ;
- l'enregistrement passe par un fichier temporaire puis un remplacement sûr du classeur ;
- Excel doit être fermé pendant l'enregistrement.

---

## Structure attendue du classeur tableur

Le générateur s’appuie sur un classeur dont la structure est volontairement **stable**.  
Les onglets “éditoriaux” pilotent la navigation et les contenus fixes ; l’onglet “catalogue” pilote les livres.
Se reporter au gabarit officiel : `gabarit/purh_site_excel_gabarit.xlsx` (à copier avant utilisation).

### Onglets

- **CONFIG** : identité de la structure (nom, baseline, logos, liens, options, etc.)
- **PAGES** : pages fixes (slug, titre, contenu, ordre, menu, etc.)
- **COLLECTIONS** : métadonnées collections + texte de présentation
- **ACTUS** : Brèves et actualités, qui peuvent alimenter un carrousel sur la page d'accueil
- **REVUES** : métadonnées revues + texte de présentation. L'onglet peut s'appeler `REVUE` ou `REVUES` (les deux sont acceptés). Il doit contenir **une seule** colonne d'identification, `revue_id` (ne conservez pas `revue_id` et `journal_id` en même temps : la génération s'arrête avec un message d'erreur)
- **CONTACTS** : adresses, réseaux sociaux, informations institutionnelles
- **CATALOGUE** (nom libre) : liste des titres (une ligne = un livre)

> Le script peut chercher automatiquement “le bon onglet catalogue” selon une convention (ou via CONFIG). Mais d'une façon générale ne changez pas la structure du tableur.

---

## Colonnes catalogue (principes)

### Identifiants & URLs
- `id13` : identifiant interne (stable)
- `slug` : slug de l’ouvrage (si absent, peut être généré à partir du titre)
- `collection`, `collection_id`

### Titres & crédits
- `titre_norm`, `sous_titre_norm`
- `credit_ligne` (ex. “Sous la direction de …”, “Édition établie par …”)

### Dates & statuts
- `date_parution_norm`
- `availability` (statut machine)
- `availability_label` (libellé affiché si besoin)
- `home_featured` (mise en avant accueil)

### Prix
- `price` (prix courant — recommandé)
- `prix_ttc`, `devise` (compatibilité anciennes versions)

### Couverture & contenus
- `cover_file` (nom de fichier dans `covers/`)
- `Description courte`, `Description longue`, `Table des matières`
- `order_url` (lien de commande, boutique, distributeur…)

### Format & description matérielle (optionnel)
- `format_site`
- `Largeur`, `Hauteur`, `Epaisseur`, `Poids`
- `Nombre de pages (pages totales imprimées)` / `Nombre de pages`

---

## Activation / masquage des titres (point important)

Selon les versions du template tableur, l’activation du titre peut s’appuyer sur :

- `Actif pour site` (historique)
- `active_site` (templates GitHub / versions récentes)

Le générateur doit **faire coexister** ces deux logiques pour éviter qu’un titre soit publié “par accident”.

Recommandation :
- Utilisez **une seule colonne de vérité** dans votre classeur (idéalement `active_site`)
- Et laissez le script créer/compléter l’alias si nécessaire

> Si `active_site = 0`, le titre ne doit **pas** sortir, même si `Actif pour site` est vide.

---

## Organisation des fichiers sources

À côté du classeur Excel, les fichiers référencés par la CONFIG et les actualités
sont recherchés en priorité dans un dossier `assets/` :

```text
dossier-du-classeur/
├─ classeur.xlsx
├─ assets/
│  ├─ actu/        images des actualités (dossier d'import de l'éditeur)
│  ├─ social/      icônes des réseaux (instagram.svg, …)
│  ├─ docs/        PDF (ex. bon de commande, avec order_pdf_filename = docs/bon.pdf)
│  └─ logo.png, favicon.ico…   logos et favicon à la racine de assets/
└─ covers/         couvertures
```

Les anciens emplacements restent acceptés en repli pour compatibilité : fichiers
posés à la racine du dossier du classeur, ou dans les anciens dossiers `actu/`,
`social/`, `images/`.

## Dossier source des assets

Le dossier source des assets est optionnel. Il peut être sélectionné dans la GUI
ou fourni en CLI avec `--assets-dir`.

Son contenu est copié dans `<dossier-de-sortie>/assets/`, sans copier le nom du
dossier source lui-même. Placez directement à sa racine les logos et les
sous-dossiers utiles :

```text
assets-source/
├── logo_purh.jpg
├── logo_univ.png
├── docs/
├── images/
├── actu/
└── social/
```

La copie est une fusion non destructive : les fichiers déjà présents dans
`assets/` sont conservés s'ils sont absents de la source, et remplacés si la
source fournit le même chemin relatif. Les couvertures de livres restent
séparées dans le dossier des couvertures. `catalogue.json` et `actualites.json`
sont générés automatiquement à la racine du site ; ne les placez pas dans ce
dossier source.

## Sorties générées

Dans le dossier de sortie choisi :

- `index.html`
- `catalogue.html`
- `actualites.html`
- `nouveautes.html`
- `a-paraitre.html`
- `livres/` (fiches livres)
- `collections/` (pages collection)
- `revues/` (pages revue)
- `catalogue.json`, `actualites.json`
- `validation.csv`
- `robots.txt`
- `sitemap.xml` si `site_url` est valide
- `assets/`
  - `actu/` (images des actualités)
  - `social/` (icônes des réseaux)
  - `docs/` (PDF déclarés avec un sous-chemin `docs/…`)
  - logos et favicon à la racine
- `covers/` (couvertures copiées)

---

## Personnalisation

### Données (sans coder)
Tout ce qui est identité / navigation / textes fixes doit venir du tableur :
- nom de la structure, baseline
- liens institutionnels
- pages “À propos”, “Politique éditoriale”, “Soumettre un manuscrit”, etc.
- collections / revues

### Thème (si vous voulez aller plus loin)
Le thème (HTML/CSS/JS) est modifiable sans toucher à la structure des données :
- ajuster la charte (couleurs, typo, spacing)
- améliorer le rendu du catalogue / fiches titres
- enrichir le front (tri, facettes supplémentaires)

---

## Déploiement

### Option A — Serveur web (recommandé en université)
Copiez le contenu du dossier de sortie sur le serveur (Apache/Nginx) :
- base URL = dossier racine du site
- aucun runtime requis côté serveur

### Option B — GitHub Pages
- déployez le dossier de sortie sur la branche `gh-pages` (ou via GitHub Actions)
- vérifiez les chemins de publication et la valeur de `site_url` si vous utilisez les métadonnées SEO

### Option C — FTP
- à réserver si vous n’avez pas d’accès SSH/CI
- sécurisez la gestion des identifiants

---

## Bonnes pratiques éditoriales

- Garder **un identifiant stable** (`id13`) même si le titre change
- Vérifier que `slug` ne change pas après mise en ligne (sinon liens cassés)
- Normaliser les champs texte (guillemets, espaces insécables, italique si balisage prévu)
- Centraliser la vérité : **le tableur est la source**, pas le HTML généré

---

## Débogage / FAQ

### “Un titre apparaît alors que je l’ai désactivé”
Vérifiez la colonne d’activation :
- `active_site` (préférée) OU `Actif pour site`
- évitez les cellules vides ambiguës : utilisez 0/1 ou VRAI/FAUX de façon cohérente

### “Il manque des prix”
Vérifiez quelle colonne est utilisée par votre version du script :
- `price` (recommandé)
- sinon `prix_ttc` + `devise`

### “Ma couverture n’apparaît pas”
- `cover_file` doit correspondre exactement au nom du fichier dans `covers/`
- vérifier extension (`.jpg`, `.png`, `.webp`) et casse (Linux sensible)

---

## Contribuer

Les contributions sont bienvenues (issues, PR) :

1. Créez une branche (`feature/…` ou `fix/…`)
2. Ajoutez des tests si pertinent
3. Décrivez clairement l’impact (données / thème / compatibilité tableur)

## CI et maintenance des dépendances

GitHub Actions exécute la suite de tests à chaque push et pull request. La CI
utilise Python 3.12 et installe les dépendances depuis `requirements-lock.txt`.

Dependabot vérifie mensuellement les mises à jour des dépendances `pip`. Les
mises à jour sont proposées sous forme de pull requests et doivent être validées
par la CI ; aucune fusion automatique n'est configurée.

---

## Feuille de route (indicative)

- [ ] Génération de pages “fiches auteurs / contributeurs”
- [ ] Poursuite de l'audit et des améliorations d'accessibilité

---

## Licence et crédits

Voir fichier Licence

---

## Crédits

Développé par Tony Gheeraert pour les Presses universitaires de Rouen et du Havre et dans le cadre de la Chaire d'excellence en édition numérique, pour un usage “presses universitaires” avec une logique **générique** :  
données dans tableur, génération statique, déploiement simple, maintenance pérenne.
