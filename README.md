# GMQ710 – Reconstruction 3D Sémantique du Campus de l'UdeS (CityJSON)

## Objectifs
Ce projet vise à développer un pipeline de traitement géospatial entièrement automatisé en Python capable de produire une maquette numérique 3D (Jumeau Numérique) du campus de l'Université de Sherbrooke.

L'objectif principal est de fusionner des données hétérogènes (vecteurs 2D et rasters d'élévation) pour générer une scène 3D sémantique standardisée. Le script doit :
* Calculer précisément la hauteur des bâtiments (LoD1) par analyse zonale.
* Reconstituer la végétation dense (forêt) et les arbres isolés.
* Exporter les bâtiments au format CityJSON et la végétation en GeoJSON pour assurer l'interopérabilité et l'optimisation des performances.

## Données utilisées
| Source | Type | Format | Utilité |
| :--- | :--- | :--- | :--- |
| **MNEHR (MNS)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Surface : fournit l'altitude des toits et de la canopée. |
| **MNEHR (MNT)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Terrain : fournit l'altitude du sol nu (Z). |
| **OpenStreetMap** | Vecteur | GeoJSON | Empreintes 2D des bâtiments utilisées comme base pour l'extrusion. |

## Approche / Méthodologie finale
Pour réaliser le projet, nous avons implémenté une approche algorithmique par soustraction et analyse spatiale rigoureuse :

* **Étape 1 : Prétraitement et Harmonisation.** Chargement des données et reprojection uniforme dans le système de coordonnées projeté local (NAD83 / UTM Zone 19N - EPSG:26919).
* **Étape 2 : Calcul du nDSM.** Création du Modèle de Hauteur Normalisé par l'opération matricielle $MNS - MNT$ pour obtenir la hauteur réelle des objets hors-sol.
* **Étape 3 : Modélisation des Bâtiments (CityJSON).** - Analyse zonale pour extraire le percentile 95 des hauteurs du nDSM par empreinte.
    - Gestion avancée des géométries : traitement des **MultiPolygones** pour assurer la validité des solides.
    - Génération de géométries de type `Solid` (incluant planchers, murs et toits) avec extrusion à partir de l'altitude du MNT.
* **Étape 4 : Extraction de la Végétation (GeoJSON).** - Filtrage du nDSM pour identifier les pixels de végétation (Hauteur > 2.5m) situés à l'extérieur des zones bâties.
    - Conversion des centroïdes de pixels en points 3D pour éviter la surcharge géométrique des modèles 3D explicites.
* **Étape 5 : Structuration et Exportation.** Écriture des données dans une structure hybride : CityJSON pour les bâtis (sémantique riche) et GeoJSON pour la végétation (performance de rendu).

## Outils et bibliothèques utilisés
* **Langage** : Python 3.8
* **Bibliothèques de traitement spatial** :
    - `rasterio` : Lecture et manipulation des rasters MNS/MNT.
    - `geopandas` : Gestion des couches vectorielles et des systèmes de coordonnées.
    - `shapely` : Manipulation des géométries (Polygon, MultiPolygon) et calculs topologiques.
    - `fiona` : Moteur de lecture/écriture pour les formats vectoriels.
* **Bibliothèques de calcul et structure** :
    - `numpy` : Opérations matricielles rapides sur les données d'élévation.
    - `json` : Structuration et encodage du dictionnaire CityJSON.
    - `os` : Gestion des chemins d'accès et des fichiers.

## Répartition des tâches dans l’équipe
* **Jefferson Dongmo Somtsi** : Développement de la structure CityJSON, gestion des MultiPolygones, résolution des erreurs topologiques et gestion du dépôt Git.
* **Qarek Mbengmo Donfack** : Développement de la logique d'analyse zonale, calcul des statistiques du nDSM et filtrage de la végétation.

## Questions résolues
**Optimisation du Rendu (Question #1) :** Le format CityJSON avec géométries explicites pour chaque arbre rendait le fichier trop lourd pour QGIS. Nous avons adopté une stratégie d'exportation hybride : les bâtiments sont en CityJSON, tandis que la végétation est exportée en points au format GeoJSON. Cela permet d'utiliser la symbologie 3D de QGIS pour représenter des milliers d'arbres de manière fluide.