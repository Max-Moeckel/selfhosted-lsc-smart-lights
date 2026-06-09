# smart-light

Lokales CLI zur LAN-Steuerung von zwei LSC-Smart-Geräten (Tuya-Plattform) — komplett ohne Cloud und App.

## Geräte

| Name      | Typ                     |
|-----------|-------------------------|
| `ceiling` | LSC Smart Ceiling Light (CCT) |
| `bulb`    | LSC A65 CCT Glühbirne   |

---

## Setup

### 1. Venv + Abhängigkeiten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install tinytuya
```

### 2. Tuya-Cloud-Credentials holen

Einmalig nötig, um die **Local Keys** der Geräte auszulesen.

1. Account anlegen: <https://iot.tuya.com>
2. Projekt erstellen → **Cloud → Development**
3. Notiere: **Access ID** (= API Key) und **Access Secret**
4. Unter *Devices → Link Tuya App Account* dein Gerätekonto verknüpfen

### 3. Wizard ausführen

```bash
source .venv/bin/activate
python -m tinytuya wizard
```

Eingaben:
- **Tuya API Key** → Access ID
- **Tuya API Secret** → Access Secret
- **Tuya Cloud Region** → `eu` (Western Europe Data Center)
- Geräte-IDs werden automatisch aus deinem verknüpften App-Konto geladen

Der Wizard schreibt `snapshot.json` mit Local Keys.

> ⚠️ Rotiere deinen Access Secret **nach dem Wizard** im Tuya-Portal, da er jetzt lokal gespeichert ist.

### 4. Netzwerk-Scan

```bash
python -m tinytuya scan
```

Findet lokale IPs und Protokoll-Versionen (3.3 / 3.4 / 3.5) aller Geräte.

### 5. Config schreiben

```bash
python setup_devices.py
```

Liest `snapshot.json` und schreibt `config/devices.json` (enthält Local Keys → **nie committen**).

Alternativ manuell nach `config/devices.example.json` als Vorlage.

---

## CLI-Befehle

```bash
# Status beider Lampen
python lsc.py status

# An/Aus
python lsc.py ceiling on
python lsc.py ceiling off
python lsc.py bulb on

# Helligkeit (0 = min, 100 = max)
python lsc.py ceiling bright 80

# Farbtemperatur (0 = warmweiß, 100 = kaltweiß)
python lsc.py ceiling temp 30

# Rohe DPS zum Debuggen
python lsc.py ceiling dps
python lsc.py bulb dps
```

Wenn ein Gerät offline ist, gibt das CLI `OFFLINE` aus und bricht nicht ab.

---

## Dateistruktur

```
smart-light/
├── lsc.py                    # CLI
├── setup_devices.py          # Config-Generator nach Wizard
├── config/
│   ├── devices.example.json  # Vorlage (committet)
│   └── devices.json          # Echte Keys (NICHT committet)
├── .gitignore
└── README.md
```

---

## Webapp (Docker / Synology)

Eine simple Weboberfläche (`app.py`, Flask) steuert beide Lampen — An/Aus, Helligkeit, Farbtemperatur, mit Live-Status.

### Lokal testen

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py          # http://localhost:8080
```

### Auf Synology deployen

1. Projektordner auf die NAS kopieren (z.B. `/volume1/docker/smart-light/`), inkl. `config/devices.json`
2. In **Container Manager** ein Projekt aus der `docker-compose.yml` anlegen — oder per SSH:

```bash
cd /volume1/docker/smart-light
docker compose up -d --build
```

3. Aufrufen unter `http://<synology-ip>:8080`

Die `config/devices.json` mit den Local Keys wird **read-only als Volume gemountet** und landet nie im Image. Die Lampen-IPs müssen aus dem Netz der Synology erreichbar sein (gleiches LAN/VLAN).

---

## Sicherheitshinweis

`config/devices.json` enthält die **Local Keys** der Geräte und steht in `.gitignore`.  
**Niemals committen.** Nach dem Tuya-Wizard auch den **Access Secret** im Portal rotieren.
