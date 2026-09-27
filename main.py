"""
================================================================================
ANTSTRIKE COCKPIT INFRASTRUCTURE — FLIGHT MANAGEMENT SYSTEM (FMS) & TCAS
Architecture: 4-Force Dynamic Ant Colony Optimization (ACO)
Features: True Airspeed Wind Vector Matrix & Haversine Spherical Odometer
Safety: Traffic Collision Avoidance System (TCAS) with Intruder Advisories
================================================================================
"""

import tkinter as tk
from tkinter import messagebox, ttk
import random
import math

# --- PARAMÈTRES ACO DE RECHERCHE MÉTÉOROLOGIQUE ---
ALPHA, BETA, EVAPORATION, Q = 1.0, 3.0, 0.1, 100.0
NB_FOURMIS = 15

# FORMULE SPHÉRIQUE DE HAVERSINE (Distance Réelle Terrestre en Kilomètres)
def calculer_distance_gps(v1, v2):
    lat1, lon1 = math.radians(v1[0]), math.radians(v1[1])
    lat2, lon2 = math.radians(v2[0]), math.radians(v2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return 6371.0 * c 

# CALCUL DU CAP DE NAVIGATION (Azimut de vol de 0° à 359°)
def calculer_cap_navigation(v1, v2):
    lat1, lon1 = math.radians(v1[0]), math.radians(v1[1])
    lat2, lon2 = math.radians(v2[0]), math.radians(v2[1])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    cap = (math.degrees(math.atan2(y, x)) + 360) % 360
    return cap

# ESTIMATION DU TEMPS DE VOL EFFECTIF (EET) SELON LE VENT ET L'ALTITUDE
def evaluer_temps_de_vol(v1, v2, airspeed, alt_feet, direction_vent, force_vent):
    dist = calculer_distance_gps(v1, v2)
    cap_vol = calculer_cap_navigation(v1, v2)
    
    # Ajustement de la vitesse de l'air selon l'altitude (True Airspeed)
    tas = airspeed * (1.0 + (alt_feet / 10000) * 0.02)
    
    # Calcul de la composante du vent (Face ou Arrière)
    angle_relatif = math.radians(direction_vent - cap_vol)
    composante_vent = force_vent * math.cos(angle_relatif)
    
    ground_speed = tas + composante_vent
    if ground_speed <= 50: ground_speed = 50  # Vitesse minimale de sécurité
    
    temps_minutes = (dist / ground_speed) * 60
    return temps_minutes, dist

def simuler_fourmi(nb, temps_matrice, dist_matrice, phero):
    path = [random.randint(0, nb-1)]
    while len(path) < nb:
        act = path[-1]
        probs = []
        tot = 0.0
        for p in range(nb):
            if p not in path:
                vis = 1.0 / max(temps_matrice[act][p], 1e-4)
                note = (phero[act][p] ** ALPHA) * (vis ** BETA)
                probs.append((p, note))
                tot += note
        if tot == 0:
            restants = [x for x in range(nb) if x not in path]
            prox = restants if restants else 0
        else:
            flotte = random.uniform(0, tot)
            cum = 0.0; prox = probs[-1]
            for v, p in probs:
                cum += p
                if cum >= flotte: prox = v; break
        path.append(prox)
    
    t_tot = sum(temps_matrice[path[k]][path[k+1]] for k in range(nb-1)) + temps_matrice[path[-1]][path]
    d_tot = sum(dist_matrice[path[k]][path[k+1]] for k in range(nb-1)) + dist_matrice[path[-1]][path]
    return path, t_tot, d_tot

def calculer_plan_vol_optimal(villes, airspeed, altitude, dir_vent, force_vent):
    nb = len(villes)
    if nb < 3: return list(range(nb)), 0.0, 0.0
    
    temps_matrice = [[0.0]*nb for _ in range(nb)]
    dist_matrice = [[0.0]*nb for _ in range(nb)]
    for i in range(nb):
        for j in range(nb):
            if i != j:
                t, d = evaluer_temps_de_vol(villes[i], villes[j], airspeed, altitude, dir_vent, force_vent)
                temps_matrice[i][j] = t
                dist_matrice[i][j] = d
                
    pheromones = [[1.0]*nb for _ in range(nb)]
    meilleur_temps = float('inf')
    meilleure_route = []
    meilleure_distance = 0.0
    
    for _ in range(25):
        toutes_routes, tous_temps, toutes_dists = [], [], []
        for _ in range(NB_FOURMIS):
            r, t, d = simuler_fourmi(nb, temps_matrice, dist_matrice, pheromones)
            toutes_routes.append(r); tous_temps.append(t); toutes_dists.append(d)
            if t < meilleur_temps:
                meilleur_temps = t
                meilleure_route = r
                meilleure_distance = d
        for i in range(nb):
            for j in range(nb): pheromones[i][j] *= (1.0 - EVAPORATION)
        for route, t_vol in zip(toutes_routes, tous_temps):
            depot = Q / max(t_vol, 1e-4)
            for k in range(nb): 
                p_idx = route[k]; p_next = route[(k+1)%nb]
                pheromones[p_idx][p_next] += depot
            
    return meilleure_route, meilleur_temps, meilleure_distance

class CockpitDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("FMS / TCAS NAVIGATION DISPLAY — COCKPIT AVIONICS")
        self.root.geometry("1150x640")
        self.root.configure(bg="#050505")
        self.villes = []
        
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#0c0c0d", fieldbackground="#0c0c0d", foreground="#33FF33")
        
        self.p_cmd = tk.Frame(root, bg="#0d0d0f", width=360, bd=2, relief="ridge")
        self.p_cmd.pack(side="left", fill="y", padx=10, pady=10)
        self.p_cmd.pack_propagate(False)
        
        tk.Label(self.p_cmd, text="✈️ FLIGHT NAV COMPUTER", font=("Courier", 12, "bold"), bg="#0d0d0f", fg="#33FF33").pack(pady=10)
        
        f_inputs = tk.Frame(self.p_cmd, bg="#0d0d0f")
        f_inputs.pack(fill="x", padx=10)
        
        tk.Label(f_inputs, text="WAYPOINT LAT (X) :", bg="#0d0d0f", fg="#888", font=("Courier", 9)).grid(row=0, column=0, sticky="w")
        self.e_lat = tk.Entry(f_inputs, bg="#141416", fg="#fff", insertbackground="white", bd=1, font=("Courier", 10))
        self.e_lat.grid(row=0, column=1, pady=3, padx=5)
        
        tk.Label(f_inputs, text="WAYPOINT LON (Y) :", bg="#0d0d0f", fg="#888", font=("Courier", 9)).grid(row=1, column=0, sticky="w")
        self.e_lon = tk.Entry(f_inputs, bg="#141416", fg="#fff", insertbackground="white", bd=1, font=("Courier", 10))
        self.e_lon.grid(row=1, column=1, pady=3, padx=5)
        
        tk.Button(self.p_cmd, text="[ WPT INSERT ]", command=self.inserer_wpt, bg="#1c1c22", fg="#00FF00", font=("Courier", 9, "bold")).pack(fill="x", padx=10, pady=5)
        
        tk.Label(self.p_cmd, text="--- ATMOSPHERIC CONTROLS ---", bg="#0d0d0f", fg="#555", font=("Courier", 9)).pack(pady=5)
        
        f_cruise = tk.Frame(self.p_cmd, bg="#0d0d0f")
        f_cruise.pack(fill="x", padx=10)
        
        tk.Label(f_cruise, text="AIRSPEED (KTS):", bg="#0d0d0f", fg="#aaa", font=("Courier", 9)).grid(row=0, column=0, sticky="w")
        self.s_speed = tk.Scale(f_cruise, from_=150, to=500, orient="horizontal", bg="#0d0d0f", fg="#00FF00", highlightthickness=0)
        self.s_speed.set(300)
        self.s_speed.grid(row=0, column=1, fill="x", expand=True)
        
        tk.Label(f_cruise, text="ALTITUDE (FT) :", bg="#0d0d0f", fg="#aaa", font=("Courier", 9)).grid(row=1, column=0, sticky="w")
        self.s_alt = tk.Scale(f_cruise, from_=5000, to=40000, resolution=500, orient="horizontal", bg="#0d0d0f", fg="#00FF00", highlightthickness=0)
        self.s_alt.set(24000)
        self.s_alt.grid(row=1, column=1, fill="x", expand=True)
        
        tk.Label(f_cruise, text="WIND DIR (DEG):", bg="#0d0d0f", fg="#aaa", font=("Courier", 9)).grid(row=2, column=0, sticky="w")
        self.s_wdir = tk.Scale(f_cruise, from_=0, to=359, orient="horizontal", bg="#0d0d0f", fg="#00FF00", highlightthickness=0)
        self.s_wdir.set(90)
        self.s_wdir.grid(row=2, column=1, fill="x", expand=True)
        
        tk.Label(f_cruise, text="WIND SPD (KT) :", bg="#0d0d0f", fg="#aaa", font=("Courier", 9)).grid(row=3, column=0, sticky="w")
        self.s_wspd = tk.Scale(f_cruise, from_=0, to=120, orient="horizontal", bg="#0d0d0f", fg="#00FF00", highlightthickness=0)
        self.s_wspd.set(45)
        self.s_wspd.grid(row=3, column=1, fill="x", expand=True)
        
        self.tree = ttk.Treeview(self.p_cmd, columns=("ID", "LAT", "LON"), show="headings", height=4)
        self.tree.heading("ID", text="WPT"); self.tree.heading("LAT", text="LAT"); self.tree.heading("LON", text="LON")
        self.tree.column("ID", width=45, anchor="center"); self.tree.column("LAT", width=110, anchor="center"); self.tree.column("LON", width=110, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        
        tk.Button(self.p_cmd, text="⚡ EXECUTE FLIGHT PLAN & SCAN TRAFFIC", command=self.calculer_plan, bg="#33FF33", fg="black", font=("Courier", 10, "bold")).pack(fill="x", padx=10, pady=3)
        tk.Button(self.p_cmd, text="RESET DATA", command=self.clear, bg="#aa2222", fg="white", font=("Courier", 9)).pack(fill="x", padx=10, pady=3)
        
        self.p_radar = tk.Frame(root, bg="#050505")
        self.p_radar.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        tk.Label(self.p_radar, text="📡 NAV MULTI-FUNCTION DISPLAY (HUD RADAR & TCAS)", font=("Courier", 12, "bold"), bg="#050505", fg="#fff").pack(anchor="w")
        
        self.canvas = tk.Canvas(self.p_radar, bg="#040804", highlightbackground="#113311", highlightthickness=2)
        self.canvas.pack(fill="both", expand=True, pady=5)
        
        self.f_telemetrie = tk.Frame(self.p_radar, bg="#09090b", bd=1, relief="solid")
        self.f_telemetrie.pack(fill="x", pady=5)
        self.lbl_report = tk.Label(self.f_telemetrie, text="FMS STATUS: IDLE \nTCAS MATRIX: AIRSPACE SCANNED - CLEAN", font=("Courier", 10, "bold"), bg="#09090b", fg="#33FF33", justify="left")
        self.lbl_report.pack(anchor="w", padx=10, pady=5)
        
        self.tracer_grille_radar()

    # MODIFICATION LINEAIRE SANS BOUCLE INVISIBLE POUR EVITER LES ERREURS TERM
    def tracer_grille_radar(self):
        self.canvas.delete("all")
        w, h = 600, 400
        cx, cy = w // 2, h // 2
        
        # Dessin direct des cercles concentriques aéronautiques
        self.canvas.create_oval(cx-40, cy-40, cx+40, cy+40, outline="#0e220e", width=1, dash=(4,4))
        self.canvas.create_oval(cx-80, cy-80, cx+80, cy+80, outline="#0e220e", width=1, dash=(4,4))
        self.canvas.create_oval(cx-120, cy-120, cx+120, cy+120, outline="#0e220e", width=1, dash=(4,4))
        self.canvas.create_oval(cx-160, cy-160, cx+160, cy+160, outline="#0e220e", width=1, dash=(4,4))
        
        self.canvas.create_line(cx, 0, cx, h, fill="#0e220e", width=1)
        self.canvas.create_line(0, cy, w, cy, fill="#0e220e", width=1)

    def inserer_wpt(self):
        try:
            lat = float(self.e_lat.get())
            lon = float(self.e_lon.get())
            idx = len(self.villes)
            self.villes.append((lat, lon))
            self.tree.insert("", "end", values=(f"WPT{idx}", lat, lon))
            self.e_lat.delete(0, tk.END); self.e_lon.delete(0, tk.END)
            self.dessiner_elements()
        except ValueError:
            messagebox.showerror("FMS COMPILER ERROR", "COORDINATES MUST BE FLOATS.")

    def dessiner_elements(self):
        self.tracer_grille_radar()
        if not self.villes: return
        lats = [v[0] for v in self.villes]
        lons = [v[1] for v in self.villes]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        w = self.canvas.winfo_width() if self.canvas.winfo_width() > 10 else 600
        h = self.canvas.winfo_height() if self.canvas.winfo_height() > 10 else 400
        
        for i, (lat, lon) in enumerate(self.villes):
            x = int((lon - min_lon) / (max_lon - min_lon + 1e-6) * (w - 140) + 70) if max_lon != min_lon else w // 2
            y = int((max_lat - lat) / (max_lat - min_lat + 1e-6) * (h - 140) + 70) if max_lat != min_lat else h // 2
            self.canvas.create_polygon(x, y-7, x-6, y+5, x+6, y+5, fill="", outline="#00FF00", width=2)
            self.canvas.create_text(x, y-16, text=f"WPT{i}", fill="#00FF00", font=("Courier", 9, "bold"))

    def calculer_plan(self):
        if len(self.villes) < 3:
            messagebox.showwarning("FMS LINK", "MINIMUM 3 WAYPOINTS REQUIRED FOR CALCULATION.")
            return
            
        speed = self.s_speed.get()
        alt = self.s_alt.get()
        wdir = self.s_wdir.get()
        wspd = self.s_wspd.get()
        
        ordre, temps_total, dist_totale = calculer_plan_vol_optimal(self.villes, speed, alt, wdir, wspd)
        self.dessiner_elements()
        
        lats = [v[0] for v in self.villes]
        lons = [v[1] for v in self.villes]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        
        for k in range(len(ordre)):
            idx1, idx2 = ordre[k], ordre[(k+1) % len(ordre)]
            v1, v2 = self.villes[idx1], self.villes[idx2]
            
            t_etape, d_etape = evaluer_temps_de_vol(v1, v2, speed, alt, wdir, wspd)
            cap_etape = calculer_cap_navigation(v1, v2)
            
            x1 = int((v1[1] - min_lon) / (max_lon - min_lon + 1e-6) * (w - 140) + 70) if max_lon != min_lon else w // 2
            y1 = int((max_lat - v1[0]) / (max_lat - min_lat + 1e-6) * (h - 140) + 70) if max_lat != min_lat else h // 2
            x2 = int((v2[1] - min_lon) / (max_lon - min_lon + 1e-6) * (w - 140) + 70) if max_lon != min_lon else w // 2
            y2 = int((max_lat - v2[0]) / (max_lat - min_lat + 1e-6) * (h - 140) + 70) if max_lat != min_lat else h // 2
            
            self.canvas.create_line(x1, y1, x2, y2, fill="#00E5FF", width=3, arrow=tk.LAST)
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            self.canvas.create_text(mx, my - 10, text=f"HDG {int(cap_etape)}° | {int(t_etape)} MIN", fill="#FFFF00", font=("Courier", 8, "bold"))
            
        alerte_tcas = False
        
        for i in range(2):
            lat_intru = random.uniform(min_lat - 0.05, max_lat + 0.05)
            lon_intru = random.uniform(min_lon - 0.05, max_lon + 0.05)
            alt_intru_feet = alt + random.choice([-2000, -1000, 0, 1500, 3000])
            
            dist_secu = calculer_distance_gps(self.villes[ordre[0]], (lat_intru, lon_intru))
            
            x_intru = int((lon_intru - min_lon) / (max_lon - min_lon + 1e-6) * (w - 140) + 70)
            y_intru = int((max_lat - lat_intru) / (max_lat - min_lat + 1e-6) * (h - 140) + 70)
            
            if dist_secu < 30.0:
                couleur_tcas = "#FF0000"
                alerte_tcas = True
            else:
                couleur_tcas = "#FFCC00"
            
            diff_altitude = int((alt_intru_feet - alt) / 100)
            signe = "+" if diff_altitude >= 0 else ""
            
            self.canvas.create_polygon(x_intru, y_intru-6, x_intru+6, y_intru, x_intru, y_intru+6, x_intru-6, y_intru, fill=couleur_tcas, outline="#fff", width=1)
            self.canvas.create_text(x_intru + 18, y_intru, text=f"{signe}{diff_altitude}", fill=couleur_tcas, font=("Courier", 8, "bold"))

        tcas_report = "⚠️ TCAS ALERT: TRAFFIC! SQUAWK 7700! MONITOR ALTITUDE LAYER" if alerte_tcas else "TCAS MATRIX: AIRSPACE SCANNED - CLEAN"
        
        route_str = " -> ".join(f"WPT{i}" for i in ordre) + f" -> WPT{ordre[0]}"
        heures, minutes = divmod(int(temps_total), 60)
        self.lbl_report.config(text=f" FMS STATUS : ACTIVE FLIGHT PLAN COMPLETED\n 🗺️ AIRWAY ROUTE : {route_str}\n 📊 LOG MATRIX : {dist_totale:.2f} KM | FLIGHT TIME : {heures}H {minutes}MIN\n {tcas_report}")

    def clear(self):
        self.villes = []
        for x in self.tree.get_children(): self.tree.delete(x)
        self.tracer_grille_radar()
        self.lbl_report.config(text="FMS STATUS: IDLE \nAIR DATA MATRIX: UNLOADED")

if __name__ == "__main__":
    root = tk.Tk()
    app = CockpitDashboard(root)
    root.mainloop()
