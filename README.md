# GMQ710 – Reconstruction 3D Sémantique du Campus de l'UdeS (CityJSON)

## Objectifs
Ce projet a permis de développer un pipeline de traitement géospatial automatisé en Python pour produire une maquette numérique 3D (Jumeau Numérique) du campus de l'Université de Sherbrooke.

L'objectif principal est la fusion de données hétérogènes pour générer une scène 3D sémantique :
* **Bâtiments** : Calcul de la hauteur (LoD1) par analyse zonale et extrusion.
* **Végétation** : Identification de la canopée et des arbres isolés.
* **Optimisation** : Exportation hybride (CityJSON/GeoJSON) pour garantir la fluidité de l'affichage 3D.

## Données utilisées
| Source | Type | Format | Utilité |
| :--- | :--- | :--- | :--- |
| **MNEHR (MNS)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Surface (altitude des sommets). |
| **MNEHR (MNT)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Terrain (altitude du sol nu). |
| **OpenStreetMap** | Vecteur | GeoJSON | Empreintes 2D des bâtiments pour l'extrusion. |

## Méthodologie et Script Final
L'approche algorithmique suit ces étapes clés :
1. **Prétraitement** : Reprojection uniforme en NAD83 / UTM Zone 19N (EPSG:26919).
2. **Calcul du nDSM** : Génération du modèle de hauteur normalisé ($MNS - MNT$).
3. **Modélisation des Bâtis (CityJSON 2.0)** : 
    - Analyse zonale (percentile 95) pour une hauteur robuste.
    - Gestion des **MultiPolygons** pour la validité géométrique.
    - Exportation de 45 bâtiments en format `Solid`.
4. **Extraction de la Végétation (GeoJSON)** : 
    - Filtrage des pixels > 2.5m hors empreintes bâties.
    - **Dédoublonnage spatial** (distance min. 3.5m) pour isoler les individus.
    - Exportation de 3 264 arbres en points 3D (X, Y, Z + attribut hauteur).

## Validation et Tests
Pour garantir la robustesse du pipeline, un script de test (`test_pipeline.py`) a été implémenté. Il permet de :
* **Vérifier l'intégrité des imports** et de la syntaxe Python.
* **Valider la présence des fichiers sources** (DSM, DTM, OSM) et leurs chemins.
* **Contrôler le système de coordonnées (CRS)** : Alerte si l'étiquette EPSG est absente tout en vérifiant la validité des coordonnées projetées.
* **Prévenir les échecs** avant le lancement du traitement lourd.

## Outils et bibliothèques
* **Langage** : Python 3.8
* **Bibliothèques** : `rasterio`, `geopandas`, `shapely`, `fiona`, `numpy`, `json`.

## Répartition des tâches
* **Jefferson Dongmo Somtsi** : Développement de la structure CityJSON, gestion des géométries complexes, résolution des conflits Git et intégration du script de test.
* **Qarek Mbengmo Donfack** : Logique d'analyse spatiale, statistiques du nDSM et filtrage de la végétation.

## Questions résolues
**Optimisation du rendu** : Le problème de lourdeur a été résolu par l'exportation de la végétation en GeoJSON. Cela permet à QGIS d'utiliser la symbologie 3D native, affichant les milliers d'arbres de manière fluide sans saturer la mémoire vive, contrairement à un export géométrique explicite en CityJSON.