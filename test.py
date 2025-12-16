#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GMQ710 - PROJET FINAL : CAMPUS UDE (Version Finale)
Objectifs :
1. Découpage précis sur la zone du Campus (Coordonnées fournies).
2. Export Bâtiments -> CityJSON (bâtis_campus_Uds.city.json).
3. Export Végétation -> GeoJSON (végétation_campus_Uds.geojson) avec :
   - Dédoublonnage spatial pour éviter le crash QGIS.
   - Forçage du CRS EPSG:26919 pour le bon géopositionnement.
"""

import os
import json
import logging
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.mask import mask
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree

# ------------------------------------------------------------------------------
# 1. CONFIGURATION
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Chemin d'accès (Vérifiez que c'est le bon sur votre machine)
BASE_PATH = r"E:\Cours_Université_de_Sherbrooke\Cours_Maîtrise_1\Automne_2025\gmq710\projet"

# Fichiers d'entrée
DSM_FILE = "dsm_1m_utm19_w_22_102.tif"
DTM_FILE = "dtm_1m_utm19_w_22_102.tif"
OSM_FILE = "buildings_sherbrooke_osm.geojson"

# Fichiers de sortie (Noms demandés)
OUT_CITYJSON = "bâtis_campus_Uds.city.json"
OUT_GEOJSON_VEG = "végétation_campus_Uds.geojson"

# Paramètres techniques
TARGET_CRS_EPSG = 26919
TARGET_CRS = f'EPSG:{TARGET_CRS_EPSG}'

MIN_HEIGHT_BLD = 3.0
MIN_HEIGHT_TREE = 2.5

# Paramètres d'optimisation de la végétation (Anti-Crash)
TREE_STEP_PIXEL = 2       # Réduction grille : 1 point tous les 2 pixels
MIN_DIST_VEG_M = 3.5      # Réduction spatiale : Distance min de 3.5m entre arbres

# Coordonnées de la zone Campus UdeS (WGS84)
CAMPUS_COORDS = [
    (-71.933067, 45.381338),
    (-71.924435, 45.381351),
    (-71.924429, 45.377744),
    (-71.932799, 45.377691)
]

# ------------------------------------------------------------------------------
# 2. FONCTIONS UTILITAIRES
# ------------------------------------------------------------------------------

def filter_close_points_spatial(gdf, min_dist_m):
    """
    Dédoublonnage spatial utilisant STRtree.
    Garde un seul arbre dans un rayon donné pour alléger le rendu 3D.
    """
    if len(gdf) == 0: return gdf
    
    logger.info(f"   ... Dédoublonnage spatial en cours (Dist min: {min_dist_m}m)...")
    geoms = list(gdf.geometry)
    tree = STRtree(geoms)
    
    picked_indices = []
    used_indices = set()

    for i, p in enumerate(geoms):
        if i in used_indices: 
            continue
        picked_indices.append(i)
        # Trouve les voisins dans le rayon et les marque comme "déjà vus"
        indices_neighbors = tree.query(p.buffer(min_dist_m))
        for idx in indices_neighbors:
            if idx != i: used_indices.add(idx)

    result = gdf.iloc[picked_indices].copy().reset_index(drop=True)
    logger.info(f"   -> {len(result)} arbres conservés sur {len(gdf)} initiaux.")
    return result

class CityJSONWriter:
    """Classe pour générer un fichier CityJSON valide (LOD1 Solids)"""
    def __init__(self):
        self.vertices = []
        self.lookup = {}
        self.city_objects = {}

    def add_vertex(self, x, y, z):
        # Stockage en entiers (cm) pour précision et compression
        pt = (int(x * 100), int(y * 100), int(z * 100))
        if pt in self.lookup: return self.lookup[pt]
        idx = len(self.vertices)
        self.vertices.append(pt)
        self.lookup[pt] = idx
        return idx

    def add_building(self, uid, geometry, height):
        self.city_objects[uid] = {
            "type": "Building",
            "attributes": {"measuredHeight": round(height, 2)},
            "geometry": [geometry]
        }

    def save(self, path, bbox):
        data = {
            "type": "CityJSON",
            "version": "1.1",
            "metadata": {
                "referenceSystem": f"urn:ogc:def:crs:EPSG::{TARGET_CRS_EPSG}",
                "geographicalExtent": bbox
            },
            "transform": {
                "scale": [0.01, 0.01, 0.01],
                "translate": [0, 0, 0]
            },
            "CityObjects": self.city_objects,
            "vertices": self.vertices
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

def create_solid(polygon, z_min, height, writer):
    """Extrusion d'un polygone en volume (Solid)"""
    z_max = z_min + height
    boundaries = []
    try:
        coords = list(polygon.exterior.coords)
        if coords[0] == coords[-1]: coords.pop()
        
        # Sol (inversé pour orientation normale)
        floor = [writer.add_vertex(x, y, z_min) for x, y in reversed(coords)]
        boundaries.append([floor])
        # Toit
        roof = [writer.add_vertex(x, y, z_max) for x, y in coords]
        boundaries.append([roof])
        # Murs
        for i in range(len(coords)):
            p1, p2 = coords[i], coords[(i+1)%len(coords)]
            idx = [
                writer.add_vertex(p1[0], p1[1], z_min),
                writer.add_vertex(p2[0], p2[1], z_min),
                writer.add_vertex(p2[0], p2[1], z_max),
                writer.add_vertex(p1[0], p1[1], z_max)
            ]
            boundaries.append([idx])
        return {"type": "Solid", "lod": "1", "boundaries": [boundaries]}
    except: return None

# ------------------------------------------------------------------------------
# 3. EXÉCUTION PRINCIPALE
# ------------------------------------------------------------------------------

def main():
    logger.info("=== DÉMARRAGE DU TRAITEMENT : CAMPUS UDE ===")
    
    # Chemins complets
    dsm_p = os.path.join(BASE_PATH, DSM_FILE)
    dtm_p = os.path.join(BASE_PATH, DTM_FILE)
    osm_p = os.path.join(BASE_PATH, OSM_FILE)

    # 1. Définition de la Zone et Projection
    logger.info("1. Configuration de la zone...")
    poly_wgs84 = Polygon(CAMPUS_COORDS)
    gdf_zone = gpd.GeoDataFrame(index=[0], geometry=[poly_wgs84], crs="EPSG:4326")
    gdf_zone_proj = gdf_zone.to_crs(TARGET_CRS)
    crop_geom = [gdf_zone_proj.geometry[0]]

    # 2. Lecture et Découpage des Rasters
    logger.info("2. Lecture et découpage des Rasters...")
    try:
        with rasterio.open(dsm_p) as src:
            dsm, transform = mask(src, crop_geom, crop=True)
            dsm = dsm[0] # Bande 1
        with rasterio.open(dtm_p) as src:
            dtm, _ = mask(src, crop_geom, crop=True)
            dtm = dtm[0] # Bande 1
    except Exception as e:
        logger.error(f"Erreur fichiers TIF : {e}")
        return

    # Calcul Hauteur (nDSM)
    ndsm = dsm - dtm
    ndsm[ndsm < 0] = 0
    
    # Métadonnées pour l'export
    min_z = float(np.min(dtm[dtm > -100])) # Évite les valeurs NoData
    max_z = float(np.max(dsm))
    bbox = [
        gdf_zone_proj.total_bounds[0], gdf_zone_proj.total_bounds[1], min_z,
        gdf_zone_proj.total_bounds[2], gdf_zone_proj.total_bounds[3], max_z
    ]

    # 3. Traitement des Bâtiments (Vers CityJSON)
    logger.info("3. Extraction des Bâtiments...")
    bats = gpd.read_file(osm_p).to_crs(TARGET_CRS)
    bats = bats[bats.intersects(crop_geom[0])] # Filtre spatial
    
    writer = CityJSONWriter()
    mask_bat = np.zeros(dsm.shape, dtype='uint8')
    count_bat = 0

    for idx, row in bats.iterrows():
        geom = row.geometry
        if geom.is_empty: continue
        try:
            # Création masque pour ce bâtiment
            m = rasterize([geom], out_shape=dsm.shape, transform=transform, fill=0, default_value=1, dtype='uint8')
            mask_bat = np.maximum(mask_bat, m)
            
            # Hauteur médiane/max
            h_vals = ndsm[m==1]
            if h_vals.size == 0: continue
            
            h = float(np.percentile(h_vals, 90)) # 90e percentile pour la hauteur
            z = float(dtm[m==1].min())

            if h >= MIN_HEIGHT_BLD:
                polys = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
                for i, p in enumerate(polys):
                    solid = create_solid(p, z, h, writer)
                    if solid:
                        writer.add_building(f"Bat_{idx}_{i}", solid, h)
                        count_bat += 1
        except: pass
        
    out_cj_path = os.path.join(BASE_PATH, OUT_CITYJSON)
    writer.save(out_cj_path, bbox)
    logger.info(f"   -> Bâtiments exportés : {OUT_CITYJSON} ({count_bat} objets)")

    # 4. Traitement de la Végétation (Vers GeoJSON)
    logger.info("4. Extraction de la Végétation...")
    # Masque : Hauteur > 2.5m ET Pas un bâtiment ET Pas de valeur aberrante
    veg_mask = (ndsm > MIN_HEIGHT_TREE) & (mask_bat == 0) & (dsm > -100)
    rows, cols = np.where(veg_mask)
    
    # 4a. Réduction par grille (Rapide)
    if TREE_STEP_PIXEL > 1:
        rows = rows[::TREE_STEP_PIXEL]
        cols = cols[::TREE_STEP_PIXEL]
        
    xs, ys = rasterio.transform.xy(transform, rows, cols, offset='center')
    pts, hs, zs = [], [], []
    
    for x, y, r, c in zip(xs, ys, rows, cols):
        pts.append(Point(x, y))
        hs.append(round(float(ndsm[r, c]), 2))
        zs.append(round(float(dtm[r, c]), 2))
        
    if pts:
        gdf_veg = gpd.GeoDataFrame({'hauteur': hs, 'z_sol': zs}, geometry=pts, crs=TARGET_CRS)
        
        # 4b. Dédoublonnage spatial (Important pour QGIS)
        gdf_veg = filter_close_points_spatial(gdf_veg, MIN_DIST_VEG_M)
        
        # 4c. Création des features GeoJSON avec CRS explicite
        veg_features = []
        for _, row in gdf_veg.iterrows():
            veg_features.append({
                "type": "Feature",
                "properties": {
                    "hauteur": row.hauteur, 
                    "altitude": row.z_sol
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [row.geometry.x, row.geometry.y, row.z_sol]
                }
            })
            
        # Structure GeoJSON complète avec CRS
        geojson_output = {
            "type": "FeatureCollection",
            "name": "Vegetation_Campus_UdeS",
            "crs": { 
                "type": "name", 
                "properties": { "name": "urn:ogc:def:crs:EPSG::26919" } 
            },
            "features": veg_features
        }

        out_gj_path = os.path.join(BASE_PATH, OUT_GEOJSON_VEG)
        with open(out_gj_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_output, f)
            
        logger.info(f"   -> Végétation exportée : {OUT_GEOJSON_VEG} ({len(veg_features)} arbres)")
        logger.info("   -> CRS EPSG:26919 forcé dans l'en-tête GeoJSON.")

    else:
        logger.warning("Aucune végétation détectée.")

    logger.info("=== TERMINÉ AVEC SUCCÈS ===")

if __name__ == "__main__":
    main()