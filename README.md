# JARVIS 2.1 · Trading Brain für Gold und Bitcoin

**Neu: MT5-Demo-Agent für XAUUSD und BTCUSD mit Handelsgedächtnis und stündlicher Quellenrecherche.**

[Trading-Einrichtung und Funktionsgrenzen](docs/control-center/TRADING.md)

Vorhandene Installation: JARVIS beenden, `git pull --ff-only origin jarvis-2.0-development`, dann `EINRICHTEN_TRADING.bat` und `START_JARVIS.bat`. MT5 im separaten Demokonto öffnen und im neuen Trading Brain verbinden. Erst eine ausdrückliche Demo-Freigabe startet automatische Orders. Echtgeldkonten bleiben gesperrt.

Die Recherche läuft bei eingeschaltetem PC/JARVIS regelmäßig über Fed, EZB und Bitcoin Core. Das lokale Modell erstellt Briefings und wertet das Journal aus; es trainiert sich nicht selbst und besitzt keinen Orderzugriff. Die erste EMA/ATR-Strategie ist experimentell und nicht als profitabel nachgewiesen.

Ein gemeinsamer Workspace für Windows-PC und Smartphone: lokale KI, Content Studio, Aufgaben, Gedächtnis, freigegebene Aktionen und verbundene Dienste.

**Entwicklungsbranch:** `jarvis-2.0-development` · **Start:** `EINRICHTEN.bat`, danach `START_JARVIS.bat`.

[Einrichtung für PC und Handy](docs/control-center/EINRICHTUNG.md) · [Architektur und Prüfstand](docs/control-center/ARCHITEKTUR.md) · [Ursprünglicher Jarvis-CLI](docs/control-center/LEGACY_README.md)

## Enthalten

- Responsive Oberfläche mit Anmeldung und Web-App-Hülle für den Home-Bildschirm.
- Ollama-Chat, lokale Skripte und Arbeitspläne; optionaler OpenAI-Chat mit expliziter Kostenbestätigung.
- Persistente Aufgaben, Erinnerungen, Chatverlauf und getrennt gespeicherte Zugangsdaten.
- Content-Projekte mit Runway-Szenen, kostenfreier Timing-Vorschau, FFmpeg-Export und Untertiteln.
- Adapter für Telegram, SMTP, YouTube, TikTok und Instagram, ausgeführt über eine Freigabeliste.
- Einmalig terminierbare Aufträge, isolierter Browser-Lesezugriff, Workspace-Dateien und registrierte Python-Bots.
- Privater Handy-Zugang über Tailscale Serve; keine Router-Portfreigabe.

## Ehrlicher Stand

Dies ist ein nutzbarer Entwicklungsstand, kein fertig zertifizierter universeller autonomer Agent. Externe Konten müssen eingerichtet werden; Anbieter-Genehmigungen, API-Guthaben und gültige Tokens bleiben erforderlich. TikTok-Publishing hängt insbesondere von den Audit-Regeln ab. Die Anbieter-Adapter sind ohne persönliche Konten nicht live abgenommen. OAuth-Setup, Token-Erneuerung, öffentliche Instagram-Medienablage, wiederkehrende Automationen und beliebige Windows-/Browsersteuerung sind noch nicht automatisiert.

Der PC führt die Arbeit aus und muss für den Handy-Zugriff eingeschaltet sein. Lokale KI hat keine API-Gebühren. OpenAI und Runway sind optionale, separat bezahlte Dienste.

## Schnellstart

```powershell
git clone --branch jarvis-2.0-development https://github.com/lukasmarcelkoenig-boop/Jarvis.git
cd Jarvis
.\EINRICHTEN.bat
.\START_JARVIS.bat
```

Python 3.12 und Git vorher installieren. Anschließend `http://127.0.0.1:8765` öffnen. Privater Anmeldecode: `.jarvis-data/LOGIN_CODE.txt`. Ollama und Smartphone-Verbindung sind in der [vollständigen Anleitung](docs/control-center/EINRICHTUNG.md) erklärt.

Persönliche Daten und Schlüssel gehören ausschließlich in `.jarvis-data`, niemals in einen Commit. Der ursprüngliche MIT-lizenzierte Jarvis-Code bleibt neben dem neuen Paket `jarvis_control` erhalten.
