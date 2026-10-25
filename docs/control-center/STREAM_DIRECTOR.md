# JARVIS Stream Director – Installieren & Grenzen

Entwicklungszweig: \`feature/stream-director-2026\`. Bestehende Trading-/Content-Funktionen werden nicht ersetzt.

## 1. Einmalige Installation (Windows)

JARVIS vorher beenden. Im Terminal im JARVIS-Ordner:

\`\`\`powershell
git fetch origin
git switch --track origin/feature/stream-director-2026
.\EINRICHTEN_STREAM.bat
.\START_JARVIS.bat
\`\`\`

Wenn bereits auf dem Feature-Branch: \`git pull --ff-only origin feature/stream-director-2026\` statt \`git switch --track\`. Nicht mit lokalen uncommitted Änderungen wechseln. Für ein Update des Basisprogramms zuvor \`EINRICHTEN.bat\` ausführen.

## 2. OBS vorbereiten

- OBS Studio mit obs-websocket 5 benutzen.
- \`Werkzeuge > WebSocket-Servereinstellungen\`: Server auf Port 4455, Passwort setzen. JARVIS verbindet ausschließlich mit \`127.0.0.1\`.
- \`Einstellungen > Ausgabe > Replay Buffer\` aktivieren. Wiederholung mindestens **120 Sekunden**; OBS benötigt genügend Arbeitsspeicher.
- OBS-Stream normal starten. Stream Director öffnet bzw. startet den Replay Buffer, wenn der Stream in OBS aktiv ist.
- Laufwerk für OBS-Aufnahmen und JARVIS-Shorts möglichst nicht C: verwenden. JARVIS löscht OBS-Dateien **standardmäßig nicht**.

## 3. Twitch optional anbinden

Für die Twitch-API ist ein auf deinen Kanal autorisiertes **User Access Token** und die **Client-ID derselben Twitch-Anwendung** nötig. Für EventSub-Chat-Analyse benötigt das Token \`user:read:chat\`. Die Tokens werden im lokalen JARVIS-Geheimnisspeicher, nicht im Git-Repository abgelegt. Bei Ablauf muss das Token vorerst manuell ersetzt werden; geführtes OAuth/Refresh ist noch nicht eingebaut. Twitch-Authentifizierung erfolgt nicht mit deinem Stream-Key!

Im Control Center auf **Stream Director** gehen, Twitch-Login, Client-ID, User-Token, OBS-Passwort und Speicherort hinterlegen. **Einstellungen speichern**, **OBS testen**, **Stream Director starten**.

Bei fehlenden Twitch-Zugangsdaten funktioniert die lokale OBS-Audio-Erkennung trotzdem; Chat-Signale bleiben deaktiviert.

## 4. Automatische Videos

- Alle 35 bis 180 Sekunden lässt JARVIS einen OBS Replay-Buffer-Schnappschuss speichern, solange OBS live ist.
- FFmpeg wertet die Audiospur lokal aus; optionale Twitch-Chat-Spitzen erhöhen die Priorität.
- Der beste Lautstärkemoment wird als Vorschlag bewertet. Überlappende Highlights werden gedrosselt; nur bis zu einer konfigurierten Anzahl pro Stream werden verarbeitet.
- Separate Hintergrund-Warteschlange exportiert MP4 im Hochformat mit unscharfem Hintergrund und komplett sichtbarem 16:9-Gameplay samt eingebetteter OBS-Facecam.
- Fertige Shorts unter \`<Ausgabeordner>/shorts/<clip-id>/final.mp4\`; im Dashboard ansehen und speichern.
- Der Button **Jetzt Clip sichern** speichert einen Replay auch ohne Mindestscore.

**Aktueller Funktionsumfang:** akustische Highlight-Heuristik und Chataktivität, kein trainiertes Spielverständnis und keine zuverlässige automatische Erkennung von Bosskills, Mimik oder Seltenheitsgraden. Das automatische Transkribieren/Einbrennen von Untertiteln und intelligentes Facecam-Reframing sind noch nicht Teil dieser Ausbaustufe. Die Erkennung ist experimentell und muss an echte eigene Streamaufnahmen angepasst werden.

## 5. Publishing

Automatische YouTube-Uploads können nach Verbindung eines bestehenden YouTube-Kontos, Auswahl einer Privatsphäre und ausdrücklicher gesonderter Bestätigung aktiviert werden. Es werden bestehende JARVIS-Publisher-Aufträge mit Dateihash- und Konto-Snapshot erstellt. **Standardmäßig bleibt die Uploadautomatik aus.** Die Google-API-Authentifizierung und Tokens müssen vorab funktionieren; abgelaufene Tokens können Uploads verhindern. Uploads auf TikTok und Instagram über die bisherigen Adapter bleiben vorerst bei deren bestehenden manuell freigegebenen Workflows. Fehlgeschlagene/unklare Uploads müssen geprüft werden, keine blinde Wiederholung.

## 6. Betrieb & Risiken

- OBS-Replay-Originaldateien können viel Speicher belegen. Die Option \`keep_obs_replays=false\` entfernt von JARVIS gespeicherte Originale nach dem Rendering; standardmäßig eingeschaltet lassen, bis alles geprüft wurde.
- Wenn du in OBS Fullscreen 16:9 aufzeichnest, bleibt das Gameplay beim vertikalen Export vollständig sichtbar – es wird nicht willkürlich abgeschnitten.
- Video-Rendering beansprucht CPU/GPU. Deshalb arbeitet es nicht im einzelnen Hauptworker, sondern im separaten Thread mit begrenzter Encoder-Threadzahl. Für schwächere PCs zunächst 720×1280.
- Keine Dauerüberwachung, wenn JARVIS oder der PC aus sind. Twitch API und OBS brauchen aktive Verbindungen.
- Das bestehende Publishing-Backend limitiert Einzelvideos auf 50 MB und hat keine automatische Token-Erneuerung. Dieser Stand wurde nicht mit deinem Twitch-/OBS-Konto auf dem PC end-to-end live abgenommen.

## 7. Erste Prüfung

1. OBS starten und manuell streamen (alternativ Teststream).
2. OBS und Twitch unter Stream Director konfigurieren.
3. OBS testen; beide Statuswerte prüfen.
4. Stream Director starten; 1–2 Minuten laufen lassen.
5. Für einen garantierten Test „Jetzt Clip sichern“ wählen.
6. MP4 im Dashboard prüfen, danach Score-Schwelle feinjustieren.
7. YouTube-Automatik erst nach erfolgreichem privaten Testupload aktivieren.
