# JARVIS 2.0 auf Windows und Handy

Dieser Entwicklungsstand ergänzt den ursprünglichen Jarvis-CLI um ein gemeinsames Control Center für PC und Smartphone. Alles wird auf deinem PC gespeichert. Das Handy ist die Fernbedienung und braucht kein eigenes KI-Modell.

## 1. Einmal auf dem PC einrichten

1. [Git für Windows](https://git-scm.com/downloads/win) und [Python 3.12](https://www.python.org/downloads/windows/) installieren. Bei Python **Python Launcher** und **Add Python to PATH** auswählen.
2. PowerShell öffnen und ausführen:

   ```powershell
   git clone --branch jarvis-2.0-development https://github.com/lukasmarcelkoenig-boop/Jarvis.git
   cd Jarvis
   .\EINRICHTEN.bat
   ```

3. [Ollama für Windows](https://ollama.com/download/windows) installieren und öffnen. In PowerShell:

   ```powershell
   ollama pull qwen2.5:3b
   ```

   Das kleine Startmodell funktioniert auch, wenn deine Grafikkarte nicht eindeutig identifiziert ist. Mit 32 GB RAM kannst du anschließend größere lokale Modelle ausprobieren; Geschwindigkeit hängt von CPU/GPU und Modell ab. Im Control Center lässt sich das Modell ändern. Cloud-Modelle werden im lokalen Modus abgewiesen.
4. `START_JARVIS.bat` doppelklicken. Das Fenster geöffnet lassen. Im Browser `http://127.0.0.1:8765` öffnen.
5. Datei `.jarvis-data/LOGIN_CODE.txt` öffnen und den Code auf der Anmeldeseite eintragen. Dies ist dein privater Zugang, kein OpenAI-Schlüssel.
6. **Einrichtung → Ollama-Verbindung prüfen**. Danach im Chat eine Nachricht senden.

Es werden keine alten ZIP-Dateien benötigt. Die historischen CLI-Abhängigkeiten aus `requirements.txt` sind für das neue Control Center nicht erforderlich. Die Umgebung `.venv-control` bleibt getrennt.

## 2. Auf dem Handy verwenden

1. [Tailscale](https://tailscale.com/download) auf Windows und auf dem Handy installieren. Auf beiden Geräten mit demselben eigenen Tailscale-Konto anmelden.
2. Auf dem PC in PowerShell:

   ```powershell
   tailscale serve --bg http://127.0.0.1:8765
   ```

3. Falls Tailscale zum Aktivieren von HTTPS auffordert, dem angezeigten Einrichtungslink folgen. Die ausgegebene `https://dein-pc.dein-netz.ts.net`-Adresse kopieren.
4. **Am PC** im Control Center unter **Einrichtung → Handy-Adresse** diese vollständige HTTPS-Adresse speichern.
5. Tailscale auf dem Handy aktivieren, die Adresse in Safari/Chrome öffnen und mit deinem JARVIS-Code anmelden.
6. iPhone: **Teilen → Zum Home-Bildschirm**. Android: Browsermenü **Zum Startbildschirm hinzufügen**, je nach Browser.

JARVIS läuft als responsive Web-App mit Home-Bildschirm-Verknüpfung. Es ist keine App-Store-App. PC und JARVIS müssen laufen; Energiesparmodus unterbricht den Zugang. Tailscale Serve bleibt privat im eigenen Netz. **Nicht `tailscale funnel` verwenden**, keine Router-Portfreigabe anlegen. Die Oberfläche speichert private Inhalte nicht für Offline-Nutzung. Browser-Anmeldungen laufen nach zwölf Stunden ab.

## 3. Erster Content-Durchlauf

1. **Content Studio** öffnen, Thema/Zielgruppe/Stil eingeben und Skript lokal erstellen lassen.
2. Den Szenenplan prüfen. Er enthält Titel, Caption, deutsche Sprechertexte und englische Bildbeschreibungen. Im aufklappbaren JSON-Editor korrigieren; alternativ einen eigenen Plan importieren.
3. **Vorschau** anfordern und unter **Freigaben** freigeben. Die Vorschau benutzt Farbflächen und eingebrannte Untertitel. Sie erzeugt keine kostenpflichtigen Videos.
4. Optional eigenen **Runway-API-Schlüssel** in Einrichtung speichern. Runway-Guthaben ist separat von ChatGPT/OpenAI.
5. **Runway beauftragen** erstellt einen Freigabe-Entwurf mit Szenenplan-Fingerabdruck und Projektlimit. Erst nach Freigabe werden Szenen erzeugt. Schätzung für `gen4.5`: 0,12 USD/Sekunde vor Steuern, geprüft am 22.09.2026. Zwei 5-Sekunden-Szenen ca. 1,20 USD. Anbieterpreise können sich ändern; Limit ist die interne Reservierungsgrenze für dieses Projekt, keine globale Kontosperre.
6. Danach **Video exportieren** und freigeben. Ausgabe: 720×1280, H.264/AAC, Untertitel, optional Windows-Sprecherstimme. Die Sprecherstimme lässt sich pro Projekt in der Oberfläche abschalten. Eigene Musikdateien zuerst im Workspace ablegen und dort ihren relativen Dateinamen eintragen.
7. MP4 direkt in der Oberfläche ansehen/herunterladen. Dateien stehen zusätzlich in `.jarvis-data/content/<projekt>/export`.
8. Unter **Veröffentlichen** das verbundene Konto, Sichtbarkeit und Angaben auswählen. Den fertigen Auftragsentwurf mit Titel/Caption/Konto prüfen und separat freigeben.

Es gibt keine automatische Behauptung, dass ein Upload öffentlich sichtbar ist. Ein angenommener Upload kann noch verarbeitet werden. Bei unklaren Antworten steht der Auftrag auf **Ergebnis prüfen**. Vor einem neuen Auftrag zuerst beim Anbieter nachsehen, damit keine doppelten Posts oder Kosten entstehen. Bereits beauftragte Szenenpläne sind gesperrt; bekannte Runway-Task-IDs werden bei Fortsetzung wiederverwendet.

## 4. Dienste verbinden

Zugänge unter **Einrichtung → Dienst verbinden** speichern. Ohne diese Einrichtung erfolgen keine Live-Uploads oder Nachrichten. Die Adapter sind implementiert, aber ohne deine Konten nicht live geprüft. OAuth-Anmeldung und automatische Token-Erneuerung sind in diesem Entwicklungsstand noch nicht integriert: Du benötigst gültige Tokens deiner eigenen Anbieter-App und erneuerst sie bei Ablauf.

| Dienst | Benötigt | Grenzen dieses Stands |
|---|---|---|
| Ollama | Installiertes lokales Modell | Chat, Planer und Skripte lokal; kein Cloud-Fallback |
| OpenAI | API-Schlüssel und eigenes API-Guthaben | Optionaler Cloud-Chat; pro Anfrage explizite Kostenbestätigung, Tagesanzahl; ChatGPT-Abos enthalten keine API-Nutzung |
| Runway | Eigener API-Schlüssel mit Guthaben | `gen4.5`, 2–6 Szenen à 5 Sekunden; Downloads und Tasks persistent |
| Telegram | Bot-Token von BotFather und konkrete Chat-ID | Empfänger muss den Bot kontaktieren bzw. ihn zur Gruppe hinzufügen; keine Nachrichten an beliebige Telefonnummern |
| E-Mail | E-Mail-Adresse, SMTP-Host, App-Passwort | SMTP über TLS auf Port 465; Annahme durch Server ist keine Zustellbestätigung |
| YouTube | OAuth-Access-Token mit `youtube.upload` | Eigene Google-Cloud-App und ggf. Verifizierung; YouTube kann nicht auditierte Uploads auf privat beschränken; Video maximal 50 MB |
| TikTok | Creator-Access-Token mit `video.publish` und genehmigte App | Creator-Infos zuerst in der Oberfläche abrufen. Nicht auditierte Apps typischerweise nur SELF_ONLY. Persönliche interne Upload-Tools können die Audit-Anforderungen nicht erfüllen. Öffentliche Veröffentlichung ist daher **nicht garantiert**. Maximal 50 MB; Interaktionen deaktiviert; KI-Kennzeichnung gesetzt |
| Instagram | Professionelles Konto, Instagram-Login-Token, Instagram-Benutzer-ID, gültige Graph-API-Version | Eigene Meta-App, erforderliche Publishing-Berechtigungen; Reel muss zusätzlich unter einer öffentlichen HTTPS-MP4-Adresse liegen. Die private Tailscale-Adresse eignet sich dafür nicht |

Für Instagram musst du das fertige MP4 beispielsweise in deinen eigenen öffentlich lesbaren Objektspeicher hochladen. Das Control Center hostet keine öffentlichen Medien und besitzt keinen eingebauten Objektspeicher-Connector. Auch die Berechtigungen der Anbieter lassen sich nicht durch JARVIS ersetzen.

## 5. Aufgaben, Agenten und Automationen

- **Gedächtnis:** dauerhaft gespeicherte Notizen werden als Kontext im Chat verwendet. Kein Training von Modellgewichten.
- **Aufgaben:** erstellen, erledigen, wieder öffnen. **Planer** erstellt Textpläne mit Ollama; er führt sie nicht selbstständig aus.
- **Freigaben:** Einzelaufträge sofort oder bis zu einem Jahr im Voraus ausführen. Der PC muss laufen. Überfällige freigegebene Aufträge werden beim nächsten Start ausgeführt. Erinnerungen erscheinen im Control Center, nicht als Handy-Push. Wiederkehrende Regeln sind noch nicht enthalten.
- **Eigene Bots:** geprüfte `.py`-Datei in `.jarvis-data/workspace` ablegen und registrieren. Start/Stopp freigeben. Start führt dieses Skript mit deinen Benutzerrechten aus. Bei Dateiveränderungen neu registrieren. JARVIS erzeugt oder startet nicht eigenständig beliebigen Code. Logs: `.jarvis-data/bot-logs`.
- **Web-Werkzeug:** öffentliche HTTPS-Seiten im isolierten Chromium lesen und fotografieren. Keine Übernahme deines persönlichen Browserprofils, keine automatische Anmeldung, kein universeller Kauf-/Klick-Agent.
- **Datei-Werkzeug:** neue Text/Markdown/JSON/CSV-Dateien im Arbeitsordner anlegen; existierende Dateien werden nicht überschrieben.
- **Voice:** Browser-Sprachausgabe; Spracheingabe soweit vom Browser unterstützt, sonst Mikrofon der Handy-Tastatur. Browser-Spracherkennung kann einen Cloud-Dienst verwenden. Kein permanentes Wakeword.

## 6. Daten, Updates und Fehler

Alle persönlichen Daten liegen in `.jarvis-data` und sind durch `.gitignore` von Git ausgeschlossen. Unter Windows werden API-Schlüssel mit DPAPI an deinen Windows-Benutzer gebunden. Auf anderen Systemen schützt nur die Dateiberechtigung; dort ist der Secret-Speicher nicht verschlüsselt. Datenbank, Chat, Videos und Anmeldecode sind lokale Dateien. Sicherungen nur privat aufbewahren und bei gestopptem JARVIS anlegen. Ein DPAPI-Backup kann auf einem anderen Windows-Benutzer neue Schlüssel verlangen.

Updates: JARVIS beenden, `UPDATE_JARVIS.bat` starten, danach `START_JARVIS.bat`. Das Update verwendet `git pull --ff-only`, überschreibt keine Konflikte und bleibt auf dem Entwicklungsbranch. Bei eigenen Quellcodeänderungen Git-Konflikte bewusst lösen. Es gibt noch keine automatische Datenbank-Rückmigration.

| Meldung | Lösung |
|---|---|
| Ollama nicht erreichbar | Ollama starten, `ollama list`, Modellnamen im Control Center prüfen |
| OpenAI 429 / kein Guthaben | Lokalen Modus nutzen oder API-Abrechnung prüfen; ein ChatGPT-Abo behebt das nicht |
| Browser fehlt | `.venv-control\Scripts\python.exe -m playwright install chromium` |
| Handy: Host nicht freigegeben | Exakte Tailscale-HTTPS-Adresse zuerst am PC speichern |
| Handy: keine Verbindung | PC wach, JARVIS läuft, beide Tailscale-Geräte verbunden? |
| Freigabe läuft lange | Ein Worker arbeitet nacheinander; Videoerzeugung kann mehrere Minuten dauern |
| Ergebnis prüfen | Anbieterstatus manuell prüfen; keinen identischen Auftrag blind wiederholen |
| Windows-Stimme fehlt | Deutsche Sprachausgabe in Windows installieren; alternativ Sprecherstimme im Projekt abschalten |

Anmeldecode zurücksetzen: JARVIS beenden und `.venv-control\Scripts\python.exe -m jarvis_control.reset_login` ausführen. Bestehende Browser-Sitzungen werden ungültig.

## Für Entwickler

```powershell
.venv-control\Scripts\python.exe -m unittest discover -s jarvis_control/tests -v
```

Architektur und Prüfstand: [ARCHITEKTUR.md](ARCHITEKTUR.md). Der ursprüngliche CLI-Code und seine MIT-Lizenz bleiben erhalten. Das Control Center ist ein neuer, separat startbarer Teil desselben Repositories.

## Offizielle Dokumentation

- [Ollama API](https://docs.ollama.com/api/chat)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Runway API](https://docs.dev.runwayml.com/guides/using-the-api/) und [Preise](https://docs.dev.runwayml.com/guides/pricing/)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [YouTube Upload](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)
- [TikTok Direct Post](https://developers.tiktok.com/doc/content-posting-api-get-started)
- [Instagram Publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing)
