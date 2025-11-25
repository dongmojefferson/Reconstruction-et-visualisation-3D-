# GMQ710 – Reconstruction 3D Sémantique du Campus de l'UdeS (CityJSON)
## Objectifs
Ce projet vise à développer un pipeline de traitement géospatial entièrement automatisé en Python capable de produire une maquette numérique 3D (Jumeau Numérique) du campus de l'Université de Sherbrooke.

L'objectif principal est de fusionner des données hétérogènes (vecteurs 2D et rasters d'élévation) pour générer une scène 3D sémantique standardisée. Le script doit :

* Calculer précisément la hauteur des bâtiments (LoD1) par analyse zonale.

* Reconstituer la végétation dense (forêt) et les arbres isolés.

* Exporter le résultat au format CityJSON 2.0 pour assurer l'interopérabilité et la conservation des attributs sémantiques.
## Données utilisées
| Source | type | Format | Utilité |
| :--- | :--- | :--- | :--- |
| **MNEHR (MNS)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Surface : fournit l'altitude des toits et de la canopée. |
| **MNEHR (MNT)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Terrain : fournit l'altitude du sol nu ($Z_{base}$). |
| **OpenStreetMap** | Vecteur | GeoJSON | Empreintes 2D des bâtiments utilisées comme base pour l'extrusion. |
## Approche / Méthodologie envisagéePour réaliser le projet, nous avons implémenté une approche algorithmique par soustraction et analyse spatiale :
* Étape 1 : Prétraitement et Harmonisation. Chargement des données et reprojection uniforme dans le système de coordonnées projeté local (NAD83 / UTM Zone 19N - EPSG:26919).
* Étape 2 : Calcul du nDSM. Création du Modèle de Hauteur Normalisé par l'opération matricielle $MNS - MNT$ pour obtenir la hauteur hors-sol des objets.
* Étape 3 : Modélisation des Bâtiments (LoD1). Analyse zonale pour extraire la hauteur maximale du nDSM à l'intérieur de chaque empreinte OSM. Génération de la géométrie solide (toit, murs, sol) et extrusion depuis l'altitude du MNT.
* Étape 4 : Extraction de la Végétation. Filtrage du nDSM pour identifier les pixels de végétation (Hauteur > 2.5m et situés hors des bâtiments). Conversion de ces pixels en objets géométriques (voxels/arbres) pour densifier la forêt.
* Étape 5 : Exportation Sémantique. Structuration et écriture des données au format CityJSON 2.0, incluant les métadonnées et l'optimisation des sommets (quantization).
## Outils et langages prévus :
* Langage(s) : Python 3
* Bibliothèques :
   - Rasterio (Traitement d'images matricielles)
   - Geopandas & Shapely (Manipulation vectorielle et géométrique)
   - Numpy (Calculs matriciels rapides)
   - Json (Génération standardisée du fichier de sortie)
## Répartition des tâches dans l’équipe
Jefferson Dongmo Somtsi : Développement de la logique d'analyse raster (calcul nDSM), algorithmes d'extraction de la végétation et gestion des systèmes de coordonnées.
Qarek Mbengmo Donfack : Développement de la structure CityJSON (classes VerticesManager, géométries solides), intégration des bâtiments OSM et validation de la visualisation 3D.
## Questions à résoudre
Question #1 (Optimisation Rendu) : Le format CityJSON génère une géométrie explicite pour chaque arbre, ce qui rend le fichier lourd (> 3 millions d'arbres sur le campus). Est-il préférable pour le rendu final de passer à une approche par instanciation de points (GeoPackage + Modèle 3D unique dans QGIS) ou de convertir le CityJSON en 3D Tiles ?
