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

Une fois le modèle prêt, CIDRE génère un ensemble de fichiers dans un répertoire dist/. Les contenus textuels sont généralement traités (Markdown → HTML) puis injectés dans un gabarit.

CIDRE peut aussi publier le dossier dist/ par FTP (déploiement simple) et exporter des métadonnées (par ex. ONIX), selon la même logique: on repart du modèle normalisé pour produire un flux.

Le dispositif reste léger, souverain, maintenable et sécurisé.

**Exemple en production**
Site des Presses universitaires de Rouen et du Havre
http://purh.ovh

**Site public de téléchargement**
Téléchargement des exécutables et utilisation
http://purh.ovh/cidre

---

## Fonctionnalités

- Génération d’un site **100% statique**
- Lecture d’un classeur tableur structuré (onglets “CONFIG”, “PAGES”, “COLLECTIONS”, “REVUES”, “CONTACTS” + onglet catalogue)
- Pages générées :  
  - `index.html` (accueil)  
  - `catalogue.html` (recherche + filtres côté navigateur)  
  - `nouveautes.html`, `a-paraitre.html`  
  - `collections/…`, `revues/…`  
  - pages fixes (politique éditoriale, mentions légales, etc.)
- Export d’un `assets/catalogue.json` en JSON consommé en front (recherche / filtres / tri sans backend)
- Gestion des couvertures (copie, fallback si manquante)
- Option de publication (FTP) si activée dans le script / la config
- Utilisation simple : chargement de l'Excel et génération automatique depuis une interface tkinter (boîte de dialogue)
- validateur onix autonome pour vérifier la validité du fichier généré

---

## Prérequis

- **Python 3.10+** recommandé
- Un environnement virtuel (venv/uv/conda) est conseillé
- Librairie markdown (pip install markdown)
- Librairie pandas (pip install pandas)
- Librairie openpyxl (pip install openpyxl)

> Les dépendances exactes sont définies dans `requirements.txt`.

---

## Installation

```bash
git clone https://github.com/<org>/<repo>.git
cd <repo>

python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

---

## Démarrage rapide

1) Placez votre fichier tableur (par ex. `site_tableur_template.xlsx`) à la racine ou dans `data/`.

2) Placez les logos mentionnés dans la feuille "config" du tableur dans le même répertoire que le fichier tableur

3) Placez les couvertures dans un dossier (ex. `covers/`).

4) Lancez la génération. Soit vous utiliser l'interface graphique gui_tk.py, soit ainsi:

```bash
python build_site.py --tableur purh_site_tableur_template_v2.xlsx --out dist --covers-dir covers
```

4) Ouvrez `dist/index.html` dans un navigateur, ou servez en local :

```bash
python -m http.server 8000 --directory dist
```

Puis visitez : `http://localhost:8000`

## Lancement facile par interface graphique
1. Depuis un IDE comme Pycharm, lancez l'interface graphique tkinter avec gui_tk.py

2. Remplir la boîte de dialogue (chemin du fichier tableur, chemin du dossier de couvertures, cases à cocher)

3. Générer le site

4. Un petit serveur se lance et la page d'accueil s'ouvre automatiquement

---

## Commandes principales

### Générer le site

```bash
python build_site.py --tableur <classeur.xlsx> --out dist --covers-dir covers
```

### Publication (optionnelle)

Si la feuille "config" propose des informations de publication FTP :

```bash
python build_site.py --tableur <classeur.xlsx> --out dist --covers-dir covers --publish-ftp
```

> ⚠️ Ne commitez **jamais** de mots de passe FTP dans le dépôt.  
> Utilisez des variables d’environnement ou un fichier local ignoré par Git (ex. `.env`, `config.local.yml`).

---

## Structure attendue du classeur tableur

Le générateur s’appuie sur un classeur dont la structure est volontairement **stable**.  
Les onglets “éditoriaux” pilotent la navigation et les contenus fixes ; l’onglet “catalogue” pilote les livres.

### Onglets

- **CONFIG** : identité de la structure (nom, baseline, logos, liens, options, etc.)
- **PAGES** : pages fixes (slug, titre, contenu, ordre, menu, etc.)
- **COLLECTIONS** : métadonnées collections + texte de présentation
- **REVUES** : métadonnées revues + texte de présentation
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

## Sorties générées

Dans le dossier `dist/` :

- `index.html`
- `catalogue.html`
- `nouveautes.html`
- `a-paraitre.html`
- `collections/` (pages collection)
- `revues/` (pages revue)
- `pages/` (pages fixes, selon votre architecture)
- `assets/`
  - `catalogue.json`
  - CSS/JS/images copiés depuis le thème
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
Copiez le contenu de `dist/` sur le serveur (Apache/Nginx) :
- base URL = dossier racine du site
- aucun runtime requis côté serveur

### Option B — GitHub Pages
- déployez `dist/` sur la branche `gh-pages` (ou via GitHub Actions)
- attention aux chemins relatifs (le script peut avoir une option `--base-url` selon les versions)

### Option C — FTP
- à réserver si vous n’avez pas d’accès SSH/CI
- sécurisez la gestion des identifiants

---

## Bonnes pratiques éditoriales

- Garder **un identifiant stable** (`id13`) même si le titre change
- Vérifier que `slug` ne change pas après mise en ligne (sinon liens cassés)
- Normaliser les champs texte (guillemets, espaces insécables, italique si balisage prévu)
- Centraliser la vérité : **l’tableur est la source**, pas le HTML généré

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

---

## Sécurité / données

- Ne commitez pas d’exports contenant des données personnelles inutiles.
- Ne commitez jamais d’identifiants FTP / tokens / secrets.
- Si le fichier tableur contient des contacts nominaux, privilégiez des données “institutionnelles”.

---

## Feuille de route (indicative)

- [ ] Validation “qualité de données” (rapport : champs manquants, slugs dupliqués, prix vides…)
- [ ] Export ONIX (ou passerelle ONIX → tableur) selon le flux métier
- [ ] Génération de pages “fiches auteurs / contributeurs”
- [ ] CI GitHub Actions : build + déploiement automatique
- [ ] Accessibilité : contrastes, navigation clavier, ARIA

---

## Licence et crédits

Voir fichier Licence

---

## Crédits

Développé par Tony Gheeraert pour les Presses universitaires de Rouen et du Havre et dans le cadre de la Chaire d'excellence en édition numérique, pour un usage “presses universitaires” avec une logique **générique** :  
données dans tableur, génération statique, déploiement simple, maintenance pérenne.
