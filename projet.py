#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GMQ710 - PROJET FINAL : Pipeline 3D (Optimisé)
Correction : Calcul automatique de l'échantillonnage pour éviter le crash.
"""

import os
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

# ------------------------------------------------------------------------------
# 1. CONFIGURATION
# ------------------------------------------------------------------------------
BASE_PATH = r"E:\Cours_Université_de_Sherbrooke\Cours_Maîtrise_1\Automne_2025\gmq710\projet"

DSM_FILE = "dsm_1m_utm19_w_22_102.tif"
DTM_FILE = "dtm_1m_utm19_w_22_102.tif"
OSM_FILE = "buildings_sherbrooke_osm.geojson"
OUTPUT_FILENAME = "scene_sherbrooke_optimized.city.json"

TARGET_CRS_EPSG = 26919
TARGET_CRS = f'EPSG:{TARGET_CRS_EPSG}'

MIN_HEIGHT_BLD = 3.0
MIN_HEIGHT_TREE = 2.5

# --- SÉCURITÉ ANTI-CRASH ---
# Le script ajustera le "step" pour ne pas dépasser ce nombre d'arbres environ.
# 200 000 est une bonne limite pour que QGIS reste fluide.
MAX_TARGET_TREES = 200000 

# ------------------------------------------------------------------------------
# 2. CLASSES ET FONCTIONS
# ------------------------------------------------------------------------------

class VerticesManager:
    def __init__(self):
        self.vertices = []
        self.lookup = {}
    
    def add(self, x, y, z):
        # Arrondi 2 décimales pour réduire encore la taille
        pt = (round(x, 2), round(y, 2), round(z, 2))
        if pt in self.lookup:
            return self.lookup[pt]
        idx = len(self.vertices)
        self.vertices.append(pt)
        self.lookup[pt] = idx
        return idx

def create_building_lod1(polygon, z_min, height, vertices_manager):
    z_max = z_min + height
    boundaries = []
    try:
        coords = list(polygon.exterior.coords)
        if coords[0] == coords[-1]: coords.pop() 
        floor = [vertices_manager.add(x, y, z_min) for x, y in reversed(coords)]
        boundaries.append([floor])
        roof = [vertices_manager.add(x, y, z_max) for x, y in coords]
        boundaries.append([roof])
        for i in range(len(coords)):
            p1 = coords[i]
            p2 = coords[(i + 1) % len(coords)]
            idx1 = vertices_manager.add(p1[0], p1[1], z_min)
            idx2 = vertices_manager.add(p2[0], p2[1], z_min)
            idx3 = vertices_manager.add(p2[0], p2[1], z_max)
            idx4 = vertices_manager.add(p1[0], p1[1], z_max)
            boundaries.append([[idx1, idx2, idx3, idx4]])
        return {"type": "Solid", "lod": "1", "boundaries": [boundaries]}
    except: return None

def create_tree_geometry(x, y, z_base, height, vertices_manager, width=1.0):
    w = width / 2
    z_top = z_base + height
    corners = [(x-w, y-w), (x+w, y-w), (x+w, y+w), (x-w, y+w)]
    boundaries = []
    boundaries.append([[vertices_manager.add(px, py, z_base) for px, py in reversed(corners)]])
    boundaries.append([[vertices_manager.add(px, py, z_top) for px, py in corners]])
    for i in range(4):
        p1 = corners[i]
        p2 = corners[(i+1)%4]
        pts = [vertices_manager.add(p1[0], p1[1], z_base), vertices_manager.add(p2[0], p2[1], z_base),
               vertices_manager.add(p2[0], p2[1], z_top), vertices_manager.add(p1[0], p1[1], z_top)]
        boundaries.append([pts])
    return {"type": "Solid", "lod": "1", "boundaries": [boundaries]}

# ------------------------------------------------------------------------------
# 3. EXÉCUTION
# ------------------------------------------------------------------------------

def run():
    print(f"=== DÉMARRAGE OPTIMISÉ ===")
    
    dsm_path = os.path.join(BASE_PATH, DSM_FILE)
    dtm_path = os.path.join(BASE_PATH, DTM_FILE)
    osm_path = os.path.join(BASE_PATH, OSM_FILE)
    
    print("1. Lecture Raster...")
    with rasterio.open(dsm_path) as src:
        dsm = src.read(1)
        transform = src.transform
        bounds = src.bounds
    with rasterio.open(dtm_path) as src:
        dtm = src.read(1)
        
    ndsm = dsm - dtm
    ndsm[ndsm < 0] = 0
    min_z_total, max_z_total = float(dtm.min()), float(dsm.max())

    print("2. Lecture Bâtiments...")
    buildings_gdf = gpd.read_file(osm_path).to_crs(TARGET_CRS)
    
    city_objects = {}
    v_manager = VerticesManager()
    mask_buildings = np.zeros(dsm.shape, dtype='uint8')

    # --- BÂTIMENTS ---
    print("   Traitement des bâtiments...")
    count_bat = 0
    for idx, row in buildings_gdf.iterrows():
        geom = row.geometry
        if geom.is_empty: continue
        try:
            mask_b = rasterize([geom], out_shape=dsm.shape, transform=transform, fill=0, default_value=1, dtype='uint8')
            mask_buildings = np.maximum(mask_buildings, mask_b) 
            h_vals = ndsm[mask_b == 1]
            if h_vals.size == 0: continue
            h_bat = float(h_vals.max())
            z_base = float(dtm[mask_b == 1].min())

            if h_bat >= MIN_HEIGHT_BLD:
                simple_geom = geom.simplify(0.5, preserve_topology=True)
                polys = [simple_geom] if simple_geom.geom_type == 'Polygon' else simple_geom.geoms
                for i, poly in enumerate(polys):
                    geom_dict = create_building_lod1(poly, z_base, h_bat, v_manager)
                    if geom_dict:
                        obj_id = f"Bat_{idx}_{i}"
                        city_objects[obj_id] = {
                            "type": "Building",
                            "attributes": {"measuredHeight": round(h_bat, 2)},
                            "geometry": [geom_dict]
                        }
                        count_bat += 1
        except: pass

    # --- VÉGÉTATION ---
    print("\n3. Analyse de la végétation...")
    veg_mask = (ndsm > MIN_HEIGHT_TREE) & (mask_buildings == 0)
    rows, cols = np.where(veg_mask)
    total_potential_pixels = len(rows)
    
    print(f"   -> Pixels de végétation détectés : {total_potential_pixels:,}")
    
    # --- CALCUL AUTOMATIQUE DU STEP ---
    # Si on a 3.5 millions de pixels et qu'on en veut 200 000 max :
    # Step = 3 500 000 / 200 000 = 17.5 -> On prend 1 pixel sur 18
    if total_potential_pixels > MAX_TARGET_TREES:
        calculated_step = int(np.ceil(total_potential_pixels / MAX_TARGET_TREES))
        print(f"   -> ⚠️ TROP DE DONNÉES ! Ajustement automatique du 'step' à {calculated_step}.")
    else:
        calculated_step = 1
        print(f"   -> Quantité raisonnable, densité 100% conservée.")

    rows = rows[::calculated_step]
    cols = cols[::calculated_step]
    
    final_count = len(rows)
    print(f"   -> Génération de {final_count:,} arbres (C'est gérable !)...")

    # Ajustement visuel : si on saute des pixels, on fait les arbres un peu plus larges
    # pour qu'ils "remplissent" l'espace visuellement.
    tree_width = 1.0 * calculated_step * 0.7 
    # (Ex: si step=10, l'arbre fera 7m de large pour combler les trous)

    count_tree = 0
    for r, c in zip(rows, cols):
        h_tree = float(ndsm[r, c])
        z_base = float(dtm[r, c])
        x, y = rasterio.transform.xy(transform, r, c, offset='center')
        
        geom_dict = create_tree_geometry(x, y, z_base, h_tree, v_manager, width=tree_width)
        
        obj_id = f"Veg_{count_tree}"
        city_objects[obj_id] = {
            "type": "SolitaryVegetationObject",
            "attributes": { "height": round(h_tree, 1) },
            "geometry": [geom_dict]
        }
        count_tree += 1
        if count_tree % 20000 == 0: print(f"    ... {count_tree} faits")

    # --- EXPORT ---
    print(f"\n4. Sauvegarde ({count_bat} Bâtiments, {count_tree} Arbres)...")
    scale_inv = 100
    # On réduit la précision des entiers pour gagner de la place
    vertices_int = [[int(v[0]*scale_inv), int(v[1]*scale_inv), int(v[2]*scale_inv)] for v in v_manager.vertices]

    metadata = {
        "referenceSystem": f"urn:ogc:def:crs:EPSG::{TARGET_CRS_EPSG}",
        "geographicalExtent": [
            bounds.left, bounds.bottom, min_z_total,
            bounds.right, bounds.top, max_z_total
        ]
    }
    json_data = {
        "type": "CityJSON",
        "version": "2.0",
        "metadata": metadata,
        "transform": {
            "scale": [0.01, 0.01, 0.01], # Echelle adaptée à l'arrondi (cm)
            "translate": [0, 0, 0]
        },
        "CityObjects": city_objects,
        "vertices": vertices_int
    }

    out_path = os.path.join(BASE_PATH, OUTPUT_FILENAME)
    try:
        with open(out_path, 'w') as f:
            json.dump(json_data, f)
        print(f"--- TERMINE : {out_path} ---")
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    run()