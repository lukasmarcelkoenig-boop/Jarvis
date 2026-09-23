# Erweiterung 2.1

Trading-/Research-Architektur und neue Grenzen: [TRADING.md](TRADING.md). `trading/service.py` verwaltet den separaten Demo-Worker, `mt5_gateway.py` den Demokonto-Zugriff, `strategy.py` die feste Signal-/Backtest-Logik und `research.py` den separaten Recherche-Worker. Die folgende Dokumentation beschreibt zusätzlich die weiterbestehende 2.0-Basis.

# Architektur und Prüfstand

## Aufbau

| Datei / Ordner | Verantwortung |
|---|---|
| `jarvis_control/__main__.py` | Lokaler Start, Port 8765, Einzelinstanz |
| `server.py` | FastAPI, Anmeldung, Host/Origin-Prüfung, Eingabevalidierung, Medienzugriff |
| `state.py` | SQLite, Sessions, Aufträge, Daten, DPAPI-Schlüsselspeicher unter Windows |
| `engine.py` | Serieller Worker, KI-Router, registrierte Aktionen und Bot-Prozesse |
| `connectors.py` | Telegram, SMTP, YouTube, TikTok, Instagram |
| `browser.py` | Isolierter öffentlicher HTTPS-Lesezugriff und Screenshot |
| `core/local_ai.py` | Ollama lokal, Erkennung von Cloud-Modellverweisen |
| `core/content.py` | Szenenplan, Projekte, Reservierung und fortsetzbare Runway-Queue |
| `core/runway.py` | Runway-API, Task-Status, validierte Video-Downloads |
| `core/media.py` | FFmpeg, Untertitel, Windows-Stimme, optional Musik |
| `static/` | Responsive HTML/CSS/JavaScript-Oberfläche, Manifest und Home-Bildschirm-Verknüpfung |
| `reset_login.py` | Lokale Code-Rotation und Sitzungswiderruf |
| `tests/` | API-, Zustands-, Content- und Connector-Vertragstests |

Ein Owner, ein PC, ein Prozess, ein Worker. SQLite speichert Aufträge vor ihrer Ausführung. Kein Redis, keine Container, kein Node-Build auf dem PC nötig. Der Worker führt Aufträge nacheinander aus; lange Videos blockieren nachfolgende KI-/Tool-Aufträge, während die Oberfläche erreichbar bleibt. Dies ist eine bewusste einfache erste Architektur, keine verteilte Jobplattform.

## Freigaben und Fehler

`draft → approved → running → done` mit zusätzlichen Zuständen `failed`, `review`, `cancelled`. Freigabe ist eine bedingte Datenbankänderung; mehrfaches Klicken führt nicht zur mehrfachen Ausführung desselben Auftrags. Separate neu erstellte Aufträge sind dagegen eigenständige Freigaben und können dieselbe Aktion erneut ausführen.

Runway reserviert die geschätzten Kosten vor dem Request. Eine unklare Submit-Antwort sperrt automatische Wiederholung. Projekt-Fingerabdruck, Konto-Snapshot, Videodatei-Hash und Bot-Skript-Hash verhindern bestimmte Änderungen nach der Freigabe. Die endgültige Instagram-Quelle ist eine externe URL; deren unveränderter Inhalt kann nicht durch den lokalen Video-Hash garantiert werden.

Beim Neustart werden unterbrochene Jobs auf `review` gesetzt. Kein automatischer erneuter Nachrichtenversand oder Upload. Provider-IDs/Upload-Sitzungen bleiben gespeichert. Eine vollständige automatisierte Upload-Wiederaufnahme ist noch nicht enthalten. Bot-Prozesse werden nur während dieser Serverlaufzeit verwaltet; ein nach einem Absturz weiterlaufender Bot wird nicht automatisch wiedererkannt oder beendet.

## Zugriff

Standardbindung ausschließlich an `127.0.0.1`. Ein konfigurierter privater Tailscale-Host wird zusätzlich als HTTP-Host akzeptiert. Tailscale Serve übernimmt HTTPS; kein öffentlicher Port. Anmeldung mit zufälligem Owner-Code, Sitzungen als gehashte Tokens in der Datenbank und HttpOnly/SameSite-Cookies. Schreibzugriffe verlangen eigenen Header und prüfen vorhandenen Origin. Private APIs haben `Cache-Control: no-store`; der Service Worker speichert keine Nutzerdaten offline.

Das ist kein Ersatz für Betriebssystemschutz: Wer deinen Windows-Benutzer, Anmeldecode oder PC kontrolliert, kann JARVIS kontrollieren. Registrierte Python-Bots sind bewusst ausführbarer eigener Code. Im Chat gibt es keine Tools, die durch eine Modellantwort oder Webseite direkt ausgelöst werden könnten.

## Tatsächlich geprüft

- 28 automatisierte Python-Tests: unter anderem Authentifizierung, Logout, CSRF/Host-Abweisung, Cloud-Einwilligung, Pfadgrenzen, Geheimnis-Redaktion, Terminierung, einmalige Job-Claims, Neustartbehandlung, veränderte Bot-Dateien und Projekte, Runway-Wire-Format, Reservierung, doppelte/unklare Submit-Antworten sowie Telegram/YouTube/TikTok-Request-Verträge.
- Browserprüfung mit Chromium: Anmeldung, Aufgabe und Erinnerung speichern, Datei-Auftrag vorbereiten/freigeben und tatsächliche Datei-Erstellung; acht Ansichten in Desktop- und Handybreite, keine JavaScript-Fehler und kein horizontaler Seitenüberlauf.
- Echter FFmpeg-Vorschau-Export: 2 Szenen, 10,02 Sekunden, 720×1280, H.264 und AAC; Untertitel eingebrannt. Zusätzlich verfügt der mitgelieferte imageio-FFmpeg-Build über den benötigten subtitles-Filter.
- Prüfung auf Syntaxfehler, Git-Whitespace-Fehler und unbeabsichtigte Zugangsdaten vor Commit.

Nicht hier live geprüft: Windows-Installation/DPAPI/System.Speech, persönliche Ollama-Hardware, Tailscale auf einem echten Smartphone, echte bezahlte Runway-/OpenAI-Anfragen, echte Plattform-Uploads und Nachrichten. Für diese Schritte sind dein PC und deine Dienstzugänge erforderlich. Der Testlauf ist keine Garantie für fehlerfreie oder unbegrenzt autonome Ausführung.

## Weiterentwicklungsgrenzen

Noch ausstehend sind geführte OAuth-Verbindungen und Token-Erneuerung, App-Audits, wiederkehrende Regeln, Handy-Push, anbieterübergreifende Kostenabrechnung und breitere geprüfte Desktop-/Browseraktionen. Die vorhandenen Adapter ersetzen diese Voraussetzungen nicht. Neue Tools sollten über validierte Auftragsdaten und denselben Freigabeweg angebunden werden.
