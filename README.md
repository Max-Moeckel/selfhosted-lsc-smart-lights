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
│   ├── devices.json          # Echte Keys (NICHT committet)
│   ├── wakeup.example.json   # Vorlage (committet)
│   ├── wakeup.json           # Laufzeit-Einstellungen (NICHT committet)
│   ├── settings.example.json # Vorlage: Szenen-Profile (committet)
│   └── settings.json         # Profile, per UI editierbar (NICHT committet)
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

### Wake-up Light (Sonnenaufgang)

Oben in der Weboberfläche: zu einer eingestellten **Startzeit** fährt die gewählte Lampe
über **10–60 Minuten** Helligkeit (1 → 100 %) und Farbtemperatur (warm → neutral) hoch.
Wochentage wählbar, „2-min-Test" für eine schnelle Vorschau.

Die Einstellungen liegen in `config/wakeup.json` und werden über die Oberfläche
gespeichert (deshalb read-write gemountet). Die Datei ist Laufzeit-Status und **nicht
committet** — vor dem ersten Start aus der Vorlage anlegen:
`cp config/wakeup.example.json config/wakeup.json`. Der Scheduler läuft als
Hintergrund-Thread im Container — deshalb startet gunicorn bewusst mit **einem** Worker,
damit der Wecker nicht doppelt feuert.

### Auf Synology deployen

1. Projektordner auf die NAS kopieren (z.B. `/volume1/docker/smart-light/`).
2. Config-Dateien aus den Vorlagen anlegen (beide werden als Volume gemountet und
   müssen auf dem Host existieren — sonst legt Docker an ihrer Stelle ein Verzeichnis an):

```bash
cd /volume1/docker/smart-light
cp config/devices.example.json  config/devices.json    # dann echte Local Keys eintragen
cp config/wakeup.example.json   config/wakeup.json     # Standardwerte, per UI änderbar
cp config/settings.example.json config/settings.json   # Szenen-Profile
```

3. In **Container Manager** ein Projekt aus der `docker-compose.yml` anlegen — oder per SSH:

```bash
docker compose up -d --build
```

4. Aufrufen unter `http://<synology-ip>:8080`

`config/devices.json` (Local Keys) wird **read-only** gemountet, `config/wakeup.json`
und `config/settings.json` (Szenen-Profile, per UI editierbar) **read-write**. Alle
bleiben auf dem Host — durch die `.dockerignore` landet `config/` nie im Build-Context
oder Image. Die Lampen-IPs müssen aus dem Netz der Synology erreichbar sein (gleiches
LAN/VLAN).

---

## Sicherheitshinweis

`config/devices.json` enthält die **Local Keys** der Geräte und steht in `.gitignore`.  
**Niemals committen.** Nach dem Tuya-Wizard auch den **Access Secret** im Portal rotieren.
