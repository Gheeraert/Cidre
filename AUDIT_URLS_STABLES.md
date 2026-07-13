# Audit et specification des URL stables

## 1. Resume executif

CIDRE produit actuellement la plupart de ses URL publiques a partir de slugs
Excel, avec plusieurs fallbacks automatiques. Le comportement est simple, mais
pas encore suffisamment stable pour garantir qu'une URL publiee ne sera jamais
reattribuee silencieusement.

Les reproductions confirment une instabilite forte pour les livres qui partagent
un meme slug explicite : `livres/meme-slug.html` peut designer le livre A dans
un classeur, puis le livre B apres simple reordonnancement des lignes. La meme
famille de risque existe pour les livres sans slug ni ISBN, car le suffixe
`-2`, `-3`, etc. depend de l'ordre des lignes.

Les collections, revues et pages ne sont pas unicisees de la meme facon. Les
collisions physiques sont aujourd'hui bloquees par la validation centralisee
(`DUPLICATE_OUTPUT_TARGET`), ce qui evite l'ecrasement silencieux dans la chaine
reelle. En revanche, certains fallbacks restent fragiles : une collection sans
`collection_id` ni `slug` peut produire `collections/.html` si on appelle le
rendu directement, et une page editoriale change d'URL des que son slug change.

La recommandation principale est de centraliser le calcul des routes publiques,
puis d'adopter une regle simple : le slug explicite reste la source de verite
visible de l'URL lorsqu'il existe, mais les collisions ne doivent plus etre
resolues par ordre de ligne. Pour les livres sans slug explicite, l'ISBN/GTIN
normalise peut servir d'identifiant stable de fallback lorsque disponible. Pour
les collections et revues, `collection_id` et `journal_id` sont les meilleurs
identifiants metier existants. Pour preserver les URL deja publiees et gerer les
renommages volontaires, un petit registre persistant des URL, accompagne de
pages d'alias/redirection statiques, semble la solution la moins risquee a moyen
terme. Il peut etre introduit apres une premiere passe de detection, sans
modifier immediatement le modele Excel.

Cette passe est documentaire uniquement : aucun code de production, test
permanent, classeur ou artefact genere n'est modifie.

## 2. Perimetre

Analyse incluse :

- producteurs de slugs, chemins publics et fragments internes ;
- consommateurs HTML, JS et JSON des URL internes ;
- reproductions temporaires par classeurs minimaux ;
- inventaire des deux classeurs disponibles localement :
  `gabarit/purh_site_excel_gabarit.xlsx` et `20260630_purh_master_v25.xlsx` ;
- specification d'invariants et d'options d'architecture pour une future passe.

Hors perimetre :

- aucun changement de comportement Python ;
- aucun changement de slug, HTML, CSS, JavaScript ou JSON ;
- aucune nouvelle colonne Excel ;
- aucune redirection implementee ;
- aucun test permanent ajoutant un verrou sur le comportement actuel ;
- aucun travail FTP, ONIX, SEO, manifeste, ZIP ou catalogue sans JavaScript.

## 3. Architecture actuelle des URL

La chaine pertinente est :

1. `cidre/orchestrator.py:47-60` lit le classeur, la configuration, les livres,
   pages, collections, revues, contacts et actualites.
2. `cidre/excel_data.py` normalise les donnees et calcule deja certains slugs,
   notamment les livres dans `load_books()`.
3. `cidre/validation.py:455-531` verifie les collisions de cibles de sortie
   pour les pages publiees, collections actives, revues actives et pages
   automatiques.
4. `cidre/orchestrator.py:114-224` purge selectivement les sorties gerees, puis
   appelle les generateurs HTML/JSON.
5. Les liens internes sont ensuite consommes dans les gabarits Python et dans
   le JavaScript embarque.

Les noms de fichiers automatiques a la racine sont :

- `index.html` ;
- `catalogue.html` ;
- `nouveautes.html` ;
- `a-paraitre.html` ;
- `actualites.html`.

Les index de sections sont :

- `collections/index.html` ;
- `revues/index.html`.

Ces cibles sont declarees dans `ROOT_AUTOMATIC_TARGETS` et
`SECTION_INDEX_TARGETS` (`cidre/validation.py:38-48`). `contact.html` n'est pas
une cible automatique dans la chaine actuelle : `build_contacts()` existe dans
`cidre/build.py:684-718`, mais l'orchestrateur ne l'appelle pas
(`cidre/orchestrator.py:217-218`).

## 4. Inventaire des producteurs

| Type d'entite | Fichier public | Source principale | Fallback | Risque actuel | Consommateurs |
| --- | --- | --- | --- | --- | --- |
| Accueil | `index.html` | automatique | aucun | stable | navigation, liens "Nouveautes" |
| Catalogue | `catalogue.html` | automatique | aucun | stable, collision page bloquee | navigation, accueil, recherche JS |
| Nouveautes | `nouveautes.html` | automatique | aucun | stable | navigation, accueil |
| A paraitre | `a-paraitre.html` | automatique | aucun | stable | navigation |
| Actualites | `actualites.html` | automatique | aucun | stable, `PAGES actualites/actus` ignore | navigation, carrousel, actualites JSON |
| Page editoriale | `<slug>.html` | `PAGES.slug` publie | aucun | changement de slug = nouvelle URL ; anciennes pages declarees auparavant peuvent rester si elles ne sont plus declarees | navigation pour slugs connus, liens manuels |
| Livre | `livres/<slug>.html` | `CATALOGUE.slug` slugifie | `titre_norm` + ISBN si ISBN, sinon titre seul | collisions resolues selon l'ordre ; URL peut etre reattribuee | cartes HTML, catalogue JS, actualites, badges |
| Collection | `collections/<slug>.html` | `COLLECTIONS.slug` actif | `collection_id`; si onglet absent, noms de collections des livres | collision bloquee dans la chaine ; fallback sur nom si onglet absent | index collections, badges livres |
| Revue | `revues/<slug>.html` | `REVUES.slug` actif | `title`, puis `journal_id`, puis `revue` | collision bloquee dans la chaine ; fallback titre instable | index revues, badges livres |
| Ancre actualite | `actualites.html#actu-<id>` | titre d'actualite slugifie | `actu`, puis suffixe par ordre | ordre et titre peuvent changer l'ancre | carrousel d'accueil |
| `catalogue.json` | `assets/catalogue.json` | livres charges | aucun | expose les slugs livres courants | `DEFAULT_JS`, recherche catalogue |
| `actualites.json` | `assets/actualites.json` | actualites chargees + `id13_to_slug` | `./actualites.html` | lien livre suit le slug courant ; ancre suit le titre courant | page actualites, carrousel |

### Livres

Le calcul des slugs de livres est fait dans `load_books()` :

- `id13` est normalise par `normalize_id13()` (`cidre/excel_data.py:631`) ;
- `collection_id` est slugifie, ou derive de `collection`
  (`cidre/excel_data.py:637-641`) ;
- `_source_slug` conserve le slug saisi, apres `slugify()`
  (`cidre/excel_data.py:647`) ;
- si `slug` est absent, le fallback est `slugify(titre_norm)` et, si `id13`
  existe, `-{id13}` est ajoute (`cidre/excel_data.py:651-657`) ;
- dans tous les cas, `ensure_unique_slug()` ajoute `-2`, `-3`, etc. selon le
  set `used` parcouru dans l'ordre des lignes (`cidre/excel_data.py:648-660`,
  `cidre/utils.py:483-490`) ;
- les pages sont ecrites sous `livres/<slug>.html`
  (`cidre/build.py:498-499`).

`slugify()` transforme un slug explicite : minuscules, suppression des accents,
remplacement des caracteres non alphanumeriques par `-`, compression des tirets
et limite a 80 caracteres (`cidre/utils.py:348-354`). Un slug explicite n'est
donc pas conserve octet pour octet.

Conclusion livres :

- un slug explicite est transforme ;
- les collisions sont resolues selon l'ordre des lignes ;
- deux livres au meme slug peuvent echanger leurs URL apres reordonnancement ;
- l'ajout ou le retrait d'une ligne avant des doublons peut changer les suffixes ;
- sans ISBN, deux titres identiques produisent `titre.html` et `titre-2.html`
  selon l'ordre ;
- avec ISBN et slug absent, l'ISBN rend le fallback plus stable, mais modifier
  l'ISBN modifie l'URL ;
- l'ISBN normalise peut servir d'identifiant stable quand il est present, mais
  il n'est pas universel : la validation actuelle accepte son absence comme
  avertissement, pas comme blocage.

### Collections

`load_collections()` lit seulement les colonnes et normalise les contenus
editoriaux (`cidre/excel_data.py:66-82`). Le calcul effectif de chemin est dans
`build_collections()` :

- si l'onglet `COLLECTIONS` est vide, les collections sont derivees des noms de
  collection des livres, triees alphabetiquement, avec `collection_id = slug =
  slugify(nom)` (`cidre/build.py:506-513`) ;
- les lignes sont filtrees sur `is_active`, puis triees par `name`
  (`cidre/build.py:515-522`) ;
- l'index lie vers `./{slug or collection_id}.html`
  (`cidre/build.py:524-526`) ;
- la page detail est ecrite sous `collections/{slug or cid}.html`
  (`cidre/build.py:536-597`).

`build_collection_slug_map()` reproduit la route publique pour les badges des
livres (`cidre/excel_data.py:215-250`). Les collections inactives sont mappees
vers une chaine vide, pour rendre un badge sans lien.

Conclusion collections :

- modifier `slug` modifie l'URL ;
- si `slug` est absent mais `collection_id` present, modifier le nom ne modifie
  pas l'URL ;
- si l'onglet `COLLECTIONS` est absent ou vide, l'URL vient du nom de collection
  dans les livres : modifier ce nom modifie l'URL ;
- l'ordre des lignes n'affecte pas une collection ayant une cible unique, car le
  rendu trie par nom ;
- les doublons de cible sont bloques dans la chaine reelle par
  `DUPLICATE_OUTPUT_TARGET`.

### Revues

`load_revues()` accepte plusieurs alias de colonnes, puis calcule :

- `journal_id` normalise en texte ;
- `title` fallback sur `journal_id` ;
- `slug` fallback sur `slug`, puis `title`, puis `journal_id`, puis `revue`
  (`cidre/excel_data.py:160-181`).

`build_revues()` recalcule le meme principe pour les lignes actives, trie par
`order` puis titre, et ecrit `revues/<slug>.html`
(`cidre/build.py:610-681`). `build_revue_slug_map()` fournit aux fiches livres
la route reelle d'une revue active, ou une chaine vide pour une revue inactive
(`cidre/excel_data.py:188-212`).

Conclusion revues :

- un slug explicite est la source la plus previsible ;
- sans slug, `title` est un fallback lisible mais instable ;
- sans titre, `journal_id` est stable ;
- les collisions de cible sont bloquees par validation dans la chaine reelle.

### Pages editoriales

`load_pages()` ne calcule pas de fallback (`cidre/excel_data.py:55-63`).
`build_pages()` :

- copie le DataFrame ;
- applique `norm_bool` a `is_published`, si la colonne existe ;
- ignore les lignes non publiees ;
- ignore les slugs vides ;
- ignore `actualites` et `actus` ;
- ecrit `<slug>.html` pour chaque page publiee ;
- ajoute le bloc contact pour `commander` et `commandes` ;
- garantit seulement un fallback `open-access.html` si aucune page ne l'a cree
  (`cidre/build.py:721-765`).

Alias reconnus en entree pour la cle de navigation :

- `open-access` et `open_access` ;
- `commander` et `commandes` ;
- `actualites` et `actus`, mais ces deux slugs sont ignores par `build_pages`
  car la page est produite ailleurs.

Les variantes reconnues ne sont pas toutes des URL publiques equivalentes :
`commander.html` et `commandes.html` peuvent toutes deux etre produites si les
deux lignes existent, alors que la navigation pointe vers `commander.html`
(`cidre/html_templates.py:31`). `open-access.html` est produit par fallback ;
`open_access.html` n'est produit que si la ligne Excel existe.

### Actualites

`build_actualites_json()` construit deux familles d'URL :

- un fragment interne `id`, calcule par `slugify(title)` ou `actu`, puis
  `ensure_unique_slug()` selon l'ordre des actualites
  (`cidre/excel_data.py:408-419`) ;
- un `href` interne vers le livre si `id13` correspond a un livre charge :
  `./livres/{slug}.html`, sinon `./actualites.html`
  (`cidre/excel_data.py:390-424`) ;
- le champ `link` est une URL externe normalisee
  (`cidre/excel_data.py:426-444`).

`build_actualites_page()` cree les ancres
`<article id="actu-{id}">` et lie le titre/image vers `href`
(`cidre/excel_data.py:562-584`). Le carrousel d'accueil lie vers
`./actualites.html#actu-${id}` (`cidre/default_assets.py:588-590`).

Conclusion actualites :

- la page publique est `actualites.html` ;
- les fragments `#actu-...` dependent du titre et de l'ordre en cas de doublon ;
- un changement de slug de livre change le `href` de l'actualite associee ;
- les URL externes restent distinctes du systeme d'URL internes.

## 5. Inventaire des consommateurs

| Consommateur | Source de verite actuelle | Lieu |
| --- | --- | --- |
| Navigation globale | chemins codés (`index.html`, `catalogue.html`, etc.) | `cidre/html_templates.py:22-32` |
| Cartes Python accueil/nouveautes/collections/revues | `book.slug` | `cidre/build.py:168-221` |
| Fiches livres | nom de fichier `book.slug`; badges via maps collections/revues | `cidre/build.py:378-499` |
| Index collections | `collection.slug or collection_id` | `cidre/build.py:524-526` |
| Badges collections des livres | `build_collection_slug_map()` | `cidre/build.py:423-429` |
| Index revues | `revue.slug` | `cidre/build.py:623-626` |
| Badges revues des livres | `build_revue_slug_map()` | `cidre/build.py:412-418` |
| Catalogue HTML/JS | `assets/catalogue.json`, champ `slug` | `cidre/default_assets.py:411-445` |
| `assets/catalogue.json` | `book.slug`, `id13`, metadonnees livres | `cidre/build.py:122-164` |
| `assets/actualites.json` | actualites + map `id13 -> book.slug` | `cidre/excel_data.py:387-448` |
| Page actualites | `actualites.json.href`, `actualites.json.id` | `cidre/excel_data.py:542-603` |
| Carrousel actualites | `actualites.json.id` vers fragment | `cidre/default_assets.py:577-607` |
| Boutons commande | `order_url`, `order_url_template`, `id13`, mailto ou PDF | `cidre/html_templates.py:156-178` |
| Liens libraires/OpenEdition | `id13`, `openedition_url` | `cidre/html_templates.py:182-207` |

Les liens externes observes (`openedition_url`, `order_url`, `link`,
`logo_*_link`, `footer_logo_href`, sites de revues, mailto) ne sont pas des URL
internes a stabiliser, mais ils sont exposes dans le rendu.

## 6. Reproductions et resultats

Les reproductions ont ete faites avec des classeurs temporaires dans
`.url_audit_tmp`, generes par script Python et non commites. Les generations ont
utilise la vraie API `build_site(..., force_alerts=True)` quand la validation
permettait de continuer. Les collisions techniques bloquees ont ete observees
soit via `build_site`, soit via les fonctions de rendu direct pour documenter le
risque que la validation empeche aujourd'hui.

### Cas A - Reordonnancement de deux livres au meme slug explicite

Entree 1 : A puis B, tous deux `slug = meme-slug`, ISBN differents.

Sortie 1 :

- `livres/meme-slug.html` contient `Livre A` ;
- `livres/meme-slug-2.html` contient `Livre B` ;
- `assets/catalogue.json` contient :
  - `9782877750001`, `Livre A`, `meme-slug` ;
  - `9782877750002`, `Livre B`, `meme-slug-2`.

Entree 2 : B puis A.

Sortie 2 :

- `livres/meme-slug.html` contient `Livre B` ;
- `livres/meme-slug-2.html` contient `Livre A` ;
- `assets/catalogue.json` contient :
  - `9782877750002`, `Livre B`, `meme-slug` ;
  - `9782877750001`, `Livre A`, `meme-slug-2`.

Conclusion : oui, le reordonnancement peut faire qu'une URL auparavant attribuee
au livre A designe ensuite le livre B. Gravite : forte, car reattribution
silencieuse possible si l'alerte est forcee.

### Cas B - Insertion d'un troisieme livre

Entree : C puis A puis B, meme slug explicite `meme-slug`.

Sortie :

- `livres/meme-slug.html` contient `Livre C` ;
- `livres/meme-slug-2.html` contient `Livre A` ;
- `livres/meme-slug-3.html` contient `Livre B`.

Conclusion : inserer un livre avant des doublons decale les suffixes et migre
les URL. Gravite : forte.

### Cas C - Suppression ou desactivation du premier doublon

Suppression de A, B seul :

- `livres/meme-slug.html` contient `Livre B`.

Desactivation de A dans une ligne precedente, B conserve :

- `livres/meme-slug-2.html` contient `Livre B`.

Explication : `load_books()` calcule les slugs avant le filtrage `active_site`
(`cidre/excel_data.py:646-660`, filtrage `cidre/excel_data.py:714-724`).
Une suppression physique et une desactivation ne produisent donc pas le meme
resultat.

Conclusion : supprimer le premier doublon peut faire revenir `slug-2` a `slug`;
desactiver le premier garde le suffixe. Gravite : forte et comportement peu
intuitif.

### Cas D - Slugs absents

Titre identique avec ISBN differents :

- A/B produit `livres/m-me-titre-9782877750101.html` et
  `livres/m-me-titre-9782877750102.html` ;
- B/A produit les memes noms de fichiers pour les memes ISBN, seul l'ordre de
  `catalogue.json` change.

Titre identique sans ISBN :

- A/B produit `livres/m-me-titre.html` puis `livres/m-me-titre-2.html` ;
- B/A produit les memes noms de fichiers, mais comme les deux lignes n'ont pas
  d'identifiant stable, le proprietaire reel de chaque URL est indiscernable.

Modification du titre sans slug :

- `Titre modifie` + ISBN `9782877750101` produit
  `livres/titre-modifi-9782877750101.html`.

Modification de l'ISBN sans slug :

- meme titre + ISBN `9782877750199` produit
  `livres/m-me-titre-9782877750199.html`.

Conclusion : avec ISBN, le fallback est stable au reordonnancement mais change
si le titre ou l'ISBN change. Sans ISBN, les suffixes dependent de l'ordre et il
n'existe pas de proprietaire fiable. Gravite : moyenne a forte selon publication.

### Cas E - Collections

Rendu direct observe :

- slug explicite : `collection_id = id-col`, `slug = slug-public` produit
  `collections/slug-public.html` ;
- slug absent, `collection_id = id-col` produit `collections/id-col.html` ;
- slug et identifiant absents, nom present, produit `collections/.html` en rendu
  direct ;
- deux collections actives au slug `dup` ecraseraient `collections/dup.html` en
  rendu direct.

Chaine reelle avec validation :

- deux collections actives au slug `dup` provoquent
  `ValidationBlockingError: DUPLICATE_OUTPUT_TARGET ... collections/dup.html`.

Conclusion : la validation evite aujourd'hui l'ecrasement silencieux. Le
fallback `collection_id` est acceptable si l'identifiant existe ; sans identifiant
ni slug, la route est invalide et devrait etre bloquee ou alertee avant rendu.
Gravite : faible dans la chaine reelle pour les doublons, moyenne pour les
donnees incompletes si un appel direct contourne la validation.

### Cas F - Revues

Rendu direct observe :

- slug explicite : `revues/slug-revue.html` ;
- slug absent, `journal_id = jid`, titre absent : `revues/jid.html` ;
- slug et identifiant absents, titre present : `revues/titre-seul.html` ;
- deux revues actives au slug `dup` ecraseraient `revues/dup.html` en rendu
  direct.

Chaine reelle avec validation :

- deux revues actives au slug `dup` provoquent
  `ValidationBlockingError: DUPLICATE_OUTPUT_TARGET ... revues/dup.html`.

Conclusion : la validation evite l'ecrasement. Le fallback par titre reste
instable si le titre editorial change ; `journal_id` est un meilleur proprietaire
technique. Gravite : faible a moyenne.

### Cas G - Pages editoriales

Changement de slug sur generation fraiche :

- `page-x` produit `page-x.html` ;
- `page-y` produit `page-y.html`.

Regeneration dans un meme `dist` :

- apres generation de `page-x`, puis generation avec seulement `page-y`, les
  deux fichiers restent presents : `page-x.html` et `page-y.html`.

Explication : la purge ajoute les pages actuellement declarees dans `PAGES`
(`cidre/orchestrator.py:145-151`). Une ancienne page qui n'est plus declaree
n'est pas connue et n'est donc pas purgee.

Collision avec page automatique :

- une page publiee `catalogue` provoque
  `DUPLICATE_OUTPUT_TARGET ... catalogue.html`.

Page `contact` :

- une page publiee `contact` est autorisee et produit `contact.html`, car
  `contact.html` n'est pas une page automatique dans la chaine actuelle.

Conclusion : les collisions avec pages automatiques sont bloquees ; les
renommages volontaires de pages ne suppriment pas forcement les anciennes URL
dans une regeneration existante. Gravite : moyenne.

### Actualites liees a un livre

Livre `9782877750301` avec `slug = slug-un` :

- `actualites.json.href = ./livres/slug-un.html` ;
- `actualites.json.id = actu-livre`.

Meme ISBN avec `slug = slug-deux` :

- `actualites.json.href = ./livres/slug-deux.html` ;
- `actualites.json.id = actu-livre`.

Conclusion : une actualite reference un livre par ISBN dans Excel, mais l'URL
exposee suit le slug courant du livre. Si l'ancienne URL livre n'est pas
preservee, l'actualite mise a jour ne casse pas, mais les liens externes deja
publies vers l'ancien livre cassent. Gravite : depend de la publication.

## 7. Instabilites confirmees

1. Les doublons de slugs livres sont resolus par ordre de ligne.
2. Un reordonnancement peut reattribuer `livres/<slug>.html` a un autre livre.
3. L'insertion d'un livre avant des doublons peut decaler tous les suffixes.
4. La suppression physique et la desactivation d'une ligne livre ne produisent
   pas le meme suffixage.
5. Les livres sans slug changent d'URL si le titre change.
6. Les livres sans slug changent d'URL si l'ISBN change, car l'ISBN fait partie
   du fallback.
7. Les actualites exposent un lien livre derive du slug courant.
8. Les ancres d'actualites dependent du titre et de l'ordre en cas de doublon.
9. Renommer une page editoriale produit une nouvelle URL ; l'ancienne peut rester
   dans un `dist` existant si elle n'est plus declaree.
10. En rendu direct, collections et revues peuvent ecraser une cible identique ;
    la chaine reelle evite cela par validation.

## 8. Risques theoriques non reproduits ou ecartes

- Une page publiee `catalogue` n'ecrase pas silencieusement `catalogue.html` :
  la validation bloque avant generation.
- Une collection active de slug `index` ou une revue active de slug `index` est
  censee entrer en collision avec `collections/index.html` ou `revues/index.html`
  via les cibles reservees de validation.
- `contact.html` n'est pas un producteur automatique aujourd'hui ; une page
  Excel `contact` est autorisee.
- Le reordonnancement de deux livres sans slug mais avec ISBN differents ne
  change pas le nom de fichier de chaque ISBN observe, meme si l'ordre de
  `catalogue.json` change.
- Le tri des collections et revues rend l'ordre de lignes moins critique pour
  les index, tant que les cibles sont distinctes.

## 9. Invariants proposes

### Obligatoires

1. Une URL publique publiee ne change pas a cause d'un simple reordonnancement
   de lignes.
2. L'ajout, le retrait ou la desactivation d'une autre entite ne change pas l'URL
   des entites existantes.
3. Une URL ne peut jamais etre reattribuee silencieusement a une autre entite.
4. Un slug explicitement renseigne est traite de maniere previsible :
   transformation documentee, collision signalee, pas de suffixe d'ordre.
5. Une collision est signalee comme probleme de donnees ou de migration, plutot
   que resolue par `-2` selon l'ordre.
6. Le changement volontaire d'une URL est detectable et consigne.
7. Les liens internes utilisent une source de verite unique des routes publiques.
8. Une generation fraiche et une regeneration produisent les memes URL a donnees
   identiques.
9. Le systeme reste statique, sans base de donnees.

### Recommandations

1. Les anciennes URL doivent etre conservees par redirection ou page d'alias
   statique lorsque c'est raisonnable.
2. Les entites sans identifiant stable doivent produire une alerte forte tant que
   l'URL ne peut pas etre garantie.
3. Les pages editoriales devraient distinguer "renommage volontaire" et "nouvelle
   page".

### Options futures

1. Autoriser une liste d'anciens slugs dans Excel.
2. Produire un rapport de migration d'URL avant generation.
3. Ajouter une commande d'audit qui compare un registre d'URL publiees au classeur
   courant.

## 10. Options comparees

### Option A - Slug explicite obligatoire

Avantages :

- tres simple a expliquer ;
- URLs lisibles ;
- pas besoin de registre au depart.

Limites :

- charge editoriale importante ;
- migration necessaire pour les livres existants sans slug ;
- ne resout pas seule la preservation des anciennes URL ;
- les doublons doivent devenir des alertes fortes ou blocages de collision.

Evaluation : bonne premiere barriere, mais insuffisante seule.

### Option B - URL fondee sur un identifiant metier

Exemples :

- livres : ISBN/GTIN ;
- collections : `collection_id` ;
- revues : `journal_id`.

Avantages :

- stable au reordonnancement ;
- deja present dans de nombreuses donnees ;
- compatible avec un generateur statique.

Limites :

- ISBN absent pour certains livres ;
- ISBN peut changer en cas de correction ;
- URL moins lisible ;
- les pages editoriales n'ont pas encore d'identifiant distinct du slug.

Evaluation : bonne source de propriete, mais a combiner avec un slug lisible ou
un registre pour les cas absents/modifies.

### Option C - Slug lisible plus identifiant stable

Exemple conceptuel :

```text
livres/titre-lisible-978xxxxxxxxxx.html
```

Avantages :

- lisible et stable au reordonnancement ;
- deja proche du fallback actuel pour livres sans slug ;
- collisions rares quand l'identifiant existe.

Limites :

- longueur parfois importante ;
- changement de titre modifie encore la partie lisible si aucune regle de
  conservation n'est appliquee ;
- ISBN absent ou corrige reste problematique ;
- risque d'URL peu elegante.

Evaluation : interessante pour nouveaux livres sans slug, mais ne suffit pas a
preserver les URL deja publiees.

### Option D - Registre persistant des URL

Exemple :

```text
url_registry.json
```

Contenu possible :

- type d'entite ;
- identifiant proprietaire (`id13`, `collection_id`, `journal_id`, slug page) ;
- URL canonique ;
- anciennes URL ;
- date ou commentaire de migration.

Avantages :

- preserve les URL publiees sans imposer une colonne Excel immediate ;
- detecte les reattributions ;
- compatible avec generation transactionnelle : le registre peut etre lu avant
  generation et ecrit dans le staging avec le reste du site ;
- portable avec un executable autonome si le fichier reste voisin du classeur ou
  du dossier de sortie.

Limites :

- nouvelle source de verite a synchroniser ;
- risque de divergence si Excel est copie sans registre ;
- demande une strategie claire pour les suppressions ;
- plus complexe que la seule obligation de slug.

Evaluation : meilleure option pour garantir la non-reattribution des URL deja
publiees, a introduire progressivement apres centralisation des routes.

### Option E - Anciennes URL declarees dans Excel

Exemples conceptuels :

- `previous_slugs` ;
- `redirect_from`.

Avantages :

- visible par les editrices ;
- pas de fichier externe a synchroniser ;
- utile pour des redirections explicites.

Limites :

- modifie le modele Excel ;
- charge editoriale accrue ;
- risque d'erreur de saisie ;
- moins adapte a la detection automatique des reattributions.

Evaluation : utile plus tard, mais pas comme premiere solution.

## 11. Strategie de redirection

Options auditees :

| Strategie | Avantages | Limites |
| --- | --- | --- |
| Page HTML avec `meta refresh` et lien canonique | fonctionne sur FTP generique, statique, simple | moins propre qu'une vraie 301, delai possible, SEO imparfait |
| Page HTML minimale avec lien explicite | accessible, sans JS, robuste | pas de redirection automatique |
| `.htaccess` Apache | vraie redirection 301 possible | depend de l'hebergeur, pas portable FTP generique |
| Fichier de redirections hebergeur | propre sur plateformes compatibles | non universel |
| Conservation d'une page d'alias | tres compatible statique | duplication de contenu si mal canonicalisee |
| Simple rapport sans redirection | zero risque technique | ne preserve pas les visiteurs ni les moteurs |

Recommandation adaptee a CIDRE :

1. produire d'abord un rapport de changements d'URL ;
2. pour les anciennes URL confirmees, generer des pages HTML d'alias statiques
   contenant un lien explicite vers la nouvelle URL, un `meta refresh` court et
   un `link rel="canonical"` ;
3. garder `.htaccess` comme export optionnel futur, jamais comme mecanisme
   unique ;
4. bloquer les chaines ou boucles de redirections lors de la validation.

Cette strategie fonctionne sans JavaScript et avec un hebergement FTP generique.

## 12. Compatibilite avec l'existant

### Gabarit local

Inventaire observe sur `gabarit/purh_site_excel_gabarit.xlsx` :

- feuille livres detectee : `Master_Site` ;
- livres actifs : 10 ;
- slugs livres explicites : 10 ;
- slugs livres issus de fallback : 0 ;
- suffixes automatiques observes : 0 ;
- collections actives : 3, toutes avec slug explicite ;
- revues actives : 1 ;
- pages publiees : 8.

Exemples d'URL livres :

- `livres/archives-et-territoires-01.html` ;
- `livres/diter-au-xxie-si-cle-02.html` ;
- `livres/normandie-savante-03.html`.

Pages publiees observees :

- `politique-editoriale.html` ;
- `soumission.html` ;
- `science-ouverte.html` ;
- `collections.html` ;
- `revues.html` ;
- `contacts.html` ;
- `presentation.html` ;
- `commander.html`.

### Classeur local `20260630_purh_master_v25.xlsx`

Inventaire observe :

- feuille livres detectee : `Master_Site` ;
- livres actifs : 1123 ;
- slugs livres explicites : 1116 ;
- slugs livres issus de fallback : 7 ;
- slugs livres avec suffixe final `-2`, `-3`, etc. observes : 21 ;
- collections actives : 50, toutes avec slug explicite ;
- revues actives : 11 ;
- pages publiees : 5.

Exemples de slugs suffixes observes :

- `cahiers-du-ciriec-france-n-1-9791024013930-2` ;
- `la-reconstruction-en-normandie-et-en-basse-saxe-apres-la-seconde-guerre-mondiale-2` ;
- `cahiers-du-criar-centre-de-recherches-iberiques-et-ibero-americaines-de-l-univer-9`.

Ces suffixes ne prouvent pas tous une reattribution effective sur le site
publie, mais ils signalent des zones a inventorier avant migration.

### Inconnues

Il manque l'inventaire du site reellement publie :

- URL deja indexees ;
- anciennes URL ayant circule ;
- eventuelles pages conservees manuellement ;
- comportement exact de l'hebergeur pour `.htaccess` ou redirections.

## 13. Recommandation

Source de verite proposee :

- livre : proprietaire = ISBN/GTIN normalise quand present ; URL visible =
  slug explicite si present, sinon slug lisible derive une seule fois et conserve
  par registre ; sans ISBN, demander un slug explicite ou un identifiant interne ;
- collection : proprietaire = `collection_id`; URL visible = slug explicite si
  present, sinon `collection_id` ;
- revue : proprietaire = `journal_id`; URL visible = slug explicite si present,
  sinon `journal_id`, et seulement en dernier recours le titre ;
- page : proprietaire = slug explicite actuel tant qu'aucun identifiant distinct
  n'existe ; un changement de slug doit etre traite comme renommage volontaire.

Regles recommandees :

- si le slug est absent pour un livre avec ISBN, generer une URL stable incluant
  l'ISBN ou reprendre l'URL existante du registre ;
- si le slug est absent pour un livre sans ISBN, produire une alerte forte :
  l'editrice doit fournir un slug ou un identifiant ;
- en cas de doublon de slug visible, ne pas suffixer selon l'ordre ; signaler et
  demander resolution ou choix explicite ;
- si le titre change, ne pas changer l'URL existante sans intention explicite ;
- si l'ISBN change, traiter comme correction d'identifiant : comparer au registre
  et signaler un possible changement de proprietaire ;
- preserver les URL deja publiees via registre et pages d'alias statiques ;
- ne pas modifier immediatement le modele Excel ; commencer par un registre
  persistant et des rapports ;
- envisager plus tard des colonnes Excel `redirect_from` ou `previous_slugs`
  seulement si l'ergonomie le justifie.

Chemin de migration le moins risque :

1. centraliser les routes publiques sans changer les sorties ;
2. produire un rapport d'URL et de proprietaires ;
3. initialiser un registre depuis les URL actuelles ;
4. bloquer ou alerter les reattributions ;
5. ajouter les redirections statiques pour les changements volontaires.

## 14. Plan d'implementation

### Passe 1 - Centralisation du calcul des routes publiques

Fichiers probables :

- `cidre/routes.py` ou module equivalent ;
- appels depuis `cidre/excel_data.py`, `cidre/build.py`, `cidre/validation.py`,
  `cidre/orchestrator.py`.

Risques :

- divergence temporaire entre route calculee et route rendue ;
- modification involontaire du HTML/JSON.

Tests requis :

- equivalence stricte des artefacts avec l'etat actuel ;
- inventaire des routes pour livres, pages, collections, revues, actualites.

Critere d'acceptation :

- aucune sortie deterministe ne change.

### Passe 2 - Detection des instabilites et collisions

Fichiers probables :

- `cidre/validation.py` ;
- nouveau rapport d'audit routes.

Risques :

- trop d'alertes sur les classeurs existants ;
- confusion entre warning, alerte et blocage.

Tests requis :

- doublons livres explicites ;
- livres sans ISBN ;
- changement de proprietaire d'URL simule.

Critere d'acceptation :

- l'instabilite est signalee sans changer la generation.

### Passe 3 - Stabilisation des livres

Fichiers probables :

- module routes ;
- `load_books()` ou post-traitement apres chargement ;
- validation.

Risques :

- changement massif d'URL si migration mal preparee ;
- livres sans ISBN.

Tests requis :

- cas A, B, C, D de cet audit ;
- comparaison avec registre initialise.

Critere d'acceptation :

- aucune URL existante n'est reattribuee.

### Passe 4 - Stabilisation des collections et revues

Fichiers probables :

- routes ;
- `build_collection_slug_map()` ;
- `build_revue_slug_map()` ;
- validation.

Risques :

- collections derivees automatiquement quand onglet absent ;
- revues sans `journal_id`.

Tests requis :

- slug explicite ;
- fallback identifiant ;
- fallback nom/titre ;
- inactifs ;
- doublons.

Critere d'acceptation :

- `collection_id` et `journal_id` deviennent les proprietaires techniques.

### Passe 5 - Gestion des anciennes URL

Fichiers probables :

- nouveau `url_registry.json` ou emplacement configure ;
- orchestrateur transactionnel pour lire avant staging et ecrire apres succes.

Risques :

- desynchronisation registre/classeur ;
- suppression volontaire d'entite.

Tests requis :

- renommage volontaire ;
- suppression ;
- restauration apres echec de generation transactionnelle.

Critere d'acceptation :

- changement d'URL detecte et conserve sans reattribution.

### Passe 6 - Generation de redirections

Fichiers probables :

- module de rendu d'alias ;
- validation des boucles ;
- purge selective des alias geres.

Risques :

- collision alias/canonique ;
- boucle de redirection.

Tests requis :

- alias simple ;
- chaine interdite ;
- collision avec page existante.

Critere d'acceptation :

- anciennes URL publiees menent explicitement a la nouvelle URL.

### Passe 7 - Verification de tous les consommateurs

Fichiers probables :

- `cidre/build.py` ;
- `cidre/default_assets.py` ;
- `cidre/html_templates.py` ;
- generation JSON.

Risques :

- un consommateur continue d'utiliser `slug` brut au lieu de la route centrale.

Tests requis :

- recherche de `livres/`, `collections/`, `revues/`, `actualites.html#` ;
- comparaison HTML/JSON.

Critere d'acceptation :

- les liens internes viennent tous de la source centrale.

### Passe 8 - Migration des classeurs existants

Fichiers probables :

- aucun changement automatique de classeur au depart ;
- rapport CSV/Markdown de migration.

Risques :

- imposer une charge editoriale trop forte ;
- modifier les donnees source.

Tests requis :

- gabarit ;
- `20260630_purh_master_v25.xlsx`.

Critere d'acceptation :

- liste claire des lignes a corriger ou confirmer.

### Passe 9 - Integration avec la generation transactionnelle

Fichiers probables :

- `cidre/orchestrator.py` ;
- `cidre/output_transaction.py` seulement si necessaire.

Risques :

- ecrire un registre partiel en cas d'echec ;
- nettoyer des alias non geres.

Tests requis :

- echec avant commit transactionnel ;
- echec apres generation d'alias ;
- conservation de l'ancien `dist`.

Critere d'acceptation :

- registre et alias ne sont installes qu'apres generation complete.

## 15. Questions restant ouvertes

1. Quel est l'inventaire exact des URL deja publiees en production ?
2. L'hebergeur accepte-t-il `.htaccess` et les redirections 301 ?
3. Les livres sans ISBN du classeur principal ont-ils un autre identifiant stable
   utilisable ?
4. Faut-il conserver les pages orphelines volontaires placees manuellement dans
   `dist`, ou les declarer explicitement ?
5. Les slugs explicites actuels doivent-ils etre consideres comme engagement
   contractuel d'URL publiee ?
6. Une correction d'ISBN doit-elle etre traitee comme la meme entite ou comme un
   nouveau livre ?
7. Faut-il exposer un rapport de migration dans la GUI avant d'ajouter des
   redirections ?

## 16. Commandes et methodes de verification

Controle Git initial :

```powershell
git status --short --branch
git branch --show-current
git log --oneline --decorate -5
git merge-base HEAD securisation
git rev-parse securisation
```

Resultat initial :

- branche active : `urls-stables` ;
- merge-base avec `securisation` :
  `e5835b93636a3c82d337b40d02f13bd858383a24` ;
- historique contenant :
  - `e5835b9 Durcit le nettoyage de la transaction de sortie` ;
  - `f8dc8a8 Sécurise la génération transactionnelle de dist`.

Cartographie du code :

```powershell
rg -n "def load_books|def load_collections|def load_revues|slugify|ensure_unique_slug|_source_slug|titre_norm|id13|journal_id|collection_id" cidre\excel_data.py cidre -g "*.py"
rg -n "def build_pages|def build_books|def build_collections|def build_revues|build_collection_slug_map|build_revue_slug_map|catalogue.json|actualites.json|href|link|actualites|open-access|open_access|commander|commandes" cidre -g "*.py"
rg -n "livres/|collections/|revues/|\.html|#|url|slug" cidre -g "*.py"
```

Reproductions :

- creation de classeurs temporaires avec `openpyxl` ;
- generation via `build_site(..., force_alerts=True)` ;
- lecture des fichiers `livres/*.html`, `assets/catalogue.json` et
  `assets/actualites.json` ;
- rendu direct de collections/revues seulement pour documenter le comportement
  que la validation empeche dans la chaine reelle.

Inventaire local :

- chargement de `gabarit/purh_site_excel_gabarit.xlsx` ;
- chargement de `20260630_purh_master_v25.xlsx` ;
- comptage des slugs explicites via `_source_slug` ;
- reperage des suffixes automatiques par expression reguliere.

Tous les fichiers temporaires de reproduction doivent rester non suivis et etre
supprimes avant commit.
