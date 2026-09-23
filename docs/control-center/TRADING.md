# JARVIS Trading Brain 2.1 — Gold und Bitcoin

JARVIS hat jetzt einen eigenen MT5-Agenten, Handelsgedächtnis, ein Trading-Cockpit und einen regelmäßig laufenden Research-Agenten. Das bisherige Content Studio bleibt erreichbar. Der neue Trading-Agent unterstützt ausschließlich **Demokonten** und ist bei jedem JARVIS-Neustart zunächst pausiert.

## Auf deinem vorhandenen PC aktualisieren

JARVIS mit Strg+C im Serverfenster beenden. In PowerShell:

```powershell
cd "$HOME\Jarvis"
git pull --ff-only origin jarvis-2.0-development
.\EINRICHTEN_TRADING.bat
.\START_JARVIS.bat
```

Keine Quellcodedateien manuell kopieren. Das Setup ergänzt `MetaTrader5==5.0.6180` in der bestehenden Python-3.12-Umgebung. Die MetaTrader-Bibliothek ist Windows-spezifisch; die übrige Oberfläche kann auch ohne sie starten.

## MetaTrader 5 verbinden

1. Das **MT5-Desktop-Terminal deines Brokers** installieren bzw. öffnen. Die mobile MT5-App reicht für den Python-Agenten nicht.
2. Ein **separates Demokonto** anmelden. Keine anderen Bots oder manuellen Positionen auf diesem Konto laufen lassen. JARVIS selbst speichert kein Broker-Passwort; er benutzt die bestehende Terminal-Anmeldung.
3. In der MT5-Marktübersicht Gold und Bitcoin suchen und die genauen Symbolnamen notieren. Je nach Broker heißen sie beispielsweise `XAUUSD`, `XAUUSD.a`, `GOLD`, `BTCUSD` oder `BTCUSDm`. Der Produktname allein garantiert keinen bestimmten Kontrakt oder Handelszeitraum. Die Kontraktspezifikation im Terminal prüfen.
4. Beide Charts öffnen, **M15** auswählen und Historie laden. JARVIS benötigt mindestens 100 abgeschlossene Kerzen. Für die historische Prüfung werden bis zu 3.000 Kerzen angefragt; das Terminal kann weniger liefern.
5. Im JARVIS-Browser `http://127.0.0.1:8765/#trading` öffnen. Bei alter Ansicht mit Strg+F5 neu laden.
6. Unter **Demo-Agent einrichten** die Symbole eintragen. Bei mehreren installierten Terminals den vollständigen Pfad zu deiner `terminal64.exe` angeben.
7. **MT5 verbinden / aktualisieren** klicken. Demokonto und Broker-Kurse kontrollieren. Der Agent startet dabei noch nicht.
8. Erst für den gewünschten Demotest im MT5-Terminal Algo-Trading und Zugriff der externen Python-API erlauben. Die Bezeichnung der Optionen kann je nach Terminal-Sprache abweichen.
9. Die ausdrückliche Demo-Bestätigung im Control Center aktivieren und **Demo-Agent starten** drücken.

Echtgeld- und Contest-Konten werden im Verbindungsweg und erneut direkt vor jeder Order abgewiesen. Es gibt keinen UI-Schalter zum Entsperren von Echtgeld. Die Demo-Freigabe gilt für automatische Orders innerhalb der eingestellten Strategie und Grenzen; für diese Demo-Orders ist keine zusätzliche Einzel-Freigabe nötig.

## Regeln dieses ersten Agenten

Dies ist eine transparente **experimentelle Vergleichsstrategie**, kein nachgewiesen profitabler Bot:

- Nur abgeschlossene M15-Kerzen; Prüfung ungefähr alle 30 Sekunden.
- Kauf bei neuem EMA20-Kreuz über EMA50, Verkauf bei neuem Kreuz darunter. Ohne neues Kreuz wartet der Agent.
- Stop-Abstand mindestens zweimal ATR14; Broker-Mindestabstände und Spread werden berücksichtigt. Take-Profit ungefähr zweimal Stop-Abstand.
- Ausgangskonfiguration: 0,25 % Risiko je Trade, 2 % Tagesverlustgrenze, höchstens 3 Orderversuche pro UTC-Tag, Montag bis Freitag. Dies sind vorsichtige **Demo-Softwarevorgaben**, keine persönliche Anlageempfehlung.
- Risikoberechnung über `order_calc_profit` in Kontowährung. 20 % Reserve im berechneten Budget für Kosten; Lotgrößen werden abgerundet. Liegt das Broker-Mindestlot über dem Budget, wird kein Trade eröffnet.
- Maximal zwei offene Positionen insgesamt, höchstens eine pro Symbol. Fremde Positionen, offene Pending Orders oder Positionen ohne Stop blockieren neue Orders.
- Maximales berechnetes offenes Anfangsrisiko 1 % des Eigenkapitals. Margin, Spread und Tick-Alter werden geprüft. Ticks älter als 90 Sekunden werden nicht gehandelt.
- Nur vom Broker unterstützte IOC/FOK-Ausführung; keine automatische Suche durch wiederholte Orderversuche.

**Tagesgrenze:** Grundlage ist der erste in JARVIS beobachtete Eigenkapitalwert des UTC-Tages, dauerhaft gespeichert. Das ist kein rekonstruierter Mitternachts-Kontostand. Ein-/Auszahlungen können diese einfache Messung beeinflussen. Die Grenze stoppt neue Einstiege, sie schließt bestehende Positionen nicht. Kurslücken, Slippage und Gebühren können die kalkulierten Grenzen überschreiten, auch im Demo-Feed.

**Pause:** verhindert weitere Einstiege nach Abschluss eines bereits laufenden Versands. Offene Positionen und ihre brokerseitigen Stops bleiben bestehen. Zum Schließen oder Ändern bestehender Positionen das MT5-Terminal verwenden. Es gibt keinen versteckten „alles schließen“-Befehl.

## Gedächtnis und Big Brain

Gespeichert werden Analyseentscheidungen, Broker-/Kontoidentität, Orderparameter, Risikoberechnung, Rückmeldungen und eigene Broker-Deals. Beim Verbinden und während aktivem Agenten werden die letzten 90 Tage eigener Deals abgeglichen. Bereits bekannte Deals werden nicht doppelt eingetragen. Die Anzeige des verbuchten Ergebnisses ist ein begrenzter Ausschnitt aus höchstens 500 gespeicherten Deals und keine vollständige Kontorendite; Teilfüllungen sind einzelne Deals.

**Gedächtnis auswerten** lässt das lokale Ollama-Modell daraus Beobachtungen, Datenlücken und testbare Lernhypothesen formulieren. Der normale Chat erhält ebenfalls begrenzten Trading- und Research-Kontext. Modellantworten können irren. Sie besitzen weder Orderzugriff noch Schreibzugriff auf die Risikokonfiguration. Es gibt kein automatisch optimiertes Modell, keine selbstständige Änderung von Strategieregeln und keine erfundene Erfolgswahrscheinlichkeit.

Ein lokales größeres Modell kann später unter Einrichtung ausgewählt werden. Die konkrete Eignung hängt von deiner Hardware ab. Ollama muss für Briefings und Brain-Auswertungen laufen; der regelbasierte Demo-Agent braucht keine kostenpflichtige KI-API.

## Regelmäßige Internet-Recherche

Der Research-Agent startet automatisch mit JARVIS und prüft standardmäßig **alle 60 Minuten** drei feste Primärquellen:

| Quelle | Aufgabe | Grenze |
|---|---|---|
| [Federal Reserve](https://www.federalreserve.gov/feeds/feeds.htm) | Offizielle US-Geldpolitik-Meldungen | Kein vollständiger Wirtschafts-/Terminfeed |
| [EZB](https://www.ecb.europa.eu/home/html/rss.en.html) | Presse, Reden, geldpolitischer Kontext | Meldungen können für Gold/Bitcoin nur indirekt relevant sein |
| [Bitcoin Core](https://bitcoincore.org/en/rss/) | Entwicklung und technische Hintergründe | Keine Börsenkurse, keine vollständigen Krypto-Nachrichten |

Zusätzlich enthält das Cockpit verifizierte Lernlinks zu **CME Group, Bitcoin.org, MetaQuotes und den EZB-Erklärseiten**. Diese Lernseiten werden auf Klick geöffnet; sie werden nicht dauerhaft komplett kopiert.

Der automatische Ablauf lädt Feed-Titel, Links, Datumsangaben und kurze Auszüge. Er speichert Quelle, Publikationsdatum und Abrufzeit, vermeidet Duplikate und nutzt HTTP-Cache-Header. Alte oder undatierte Meldungen sind gekennzeichnet. Neue Einträge können ein lokales KI-Briefing auslösen; bei fehlendem Ollama bleibt das Quellenarchiv trotzdem nutzbar. Ein Briefing ist eine KI-Einordnung der **Feed-Auszüge**, keine Zusammenfassung eines gelesenen Volltexts.

Intervall: 15 bis 1.440 Minuten, in der Oberfläche einstellbar. **Jetzt recherchieren** fordert einen zusätzlichen Lauf an. Automatik und KI-Zusammenfassung können separat abgeschaltet werden. Ein bereits laufender Abruf wird dadurch nicht rückwirkend abgebrochen. Archiv: maximal 2.000 Quellen-Einträge und 200 Briefings. Quellenfehler/HTTP-Sperren werden einzeln angezeigt, niemals als erfolgreicher Abruf ausgegeben.

„Permanent“ bedeutet: Hintergrundbetrieb während JARVIS und der PC laufen. Im Ruhemodus oder bei ausgeschaltetem PC findet keine Recherche statt. Beim nächsten Start prüft JARVIS, ob ein Lauf fällig ist. Das ist ein kuratierter Quellenmonitor, keine lückenlose Suche des gesamten Internets. Noch kein News-Sperrkalender, kein automatisch belegter News-Trade und kein Modelltraining. Externe Webseiten dürfen keine Handelsregeln ändern.

## Historische Prüfung

Im Symbolfeld **Historischen Test starten** wählen. Ergebnis und verwendeter Zeitraum erscheinen weiter unten. Die Simulation arbeitet chronologisch mit nächster Kerzenöffnung als Einstieg; bei Stop und Ziel in derselben OHLC-Kerze gilt konservativ der Stop zuerst. Angegeben werden abgeschlossene Trades, Ergebnis in R und maximaler simulierter Rückgang in R.

R ist das ursprünglich geplante Kursrisiko des jeweiligen Trades. Der Test rechnet mit dem heutigen Spread als fester Näherung über die gesamte Historie. Variable Slippage, Swaps, historische Spreadspitzen, Broker-Lotregeln und echte Fill-Simulation fehlen. Offene Endpositionen werden gesondert angegeben und nicht in geschlossene Ergebnisse eingerechnet. Kein Look-ahead über die aktuelle Testkerze; dennoch kein Nachweis eines zukünftigen Handelsvorteils oder Ersatz für längere Demo-/Out-of-sample-Tests.

## Unklare Orders und Neustarts

Vor Versand wird jede Kombination aus Konto, Symbol und Signalkerze dauerhaft reserviert. Diese Kombination wird auch nach Neustart nicht erneut gesendet. Bei Timeout, fehlender Broker-Antwort oder nicht bestätigtem Rückgabecode wird der Auftrag auf **review** gesetzt und der Agent pausiert.

Vor erneutem Start die Order im MT5-Terminal abgleichen. Danach im Ordergedächtnis **Ergebnis im Terminal geprüft** markieren und die Prüfung dokumentieren. Dies entsperrt künftige Signale, wiederholt aber die unklare Order nicht. Der Agent setzt nie von allein nach einem Neustart fort.

## Handy

Der vorhandene private Tailscale-Zugang funktioniert auch für das Trading Brain. Du kannst vom Handy Status und Research lesen, Konfiguration speichern und Demo-Agent starten/pausieren. MT5 und JARVIS laufen weiterhin auf deinem Windows-PC. Die Kontrolle erfolgt über dieselbe authentifizierte Oberfläche; kein Broker-Passwort wird zum Handy übertragen.

## Prüfstand

**54 automatisierte Tests bestanden.** Geprüft: bestehende Funktionen plus Demo-/Echtgeldsperre, Bestätigung, Lot-Rundung, NaN-/Infinity-Abweisung, veraltete Daten, Kontowechsel direkt vor Versand, Tagesgrenze, Margin/Spread, Pending Orders, fehlende Stops, einmaliger Versand je Signalkerze, Wiederanlaufsperre bei unklarem Ergebnis, Tagesbasis, konservativer Backtest und Research-Parsing/Linkgrenzen. MT5 wird dabei durch einen simulierten Broker ersetzt; es wurden **keine Broker-Orders** gesendet.

Die Browserprüfung hat neun Ansichten in Desktop-/Handybreite ohne JavaScript-Fehler oder horizontalen Seitenüberlauf geprüft. Demo-Verbindung, Konfiguration, Start/Pause und Rechercheintervall wurden mit einem simulierten MT5-Konto betätigt. Die drei echten RSS-Feeds wurden erfolgreich gelesen und geparst.

Das Windows-Paket für Python 3.12 wurde auf Verfügbarkeit geprüft. Echte MT5-Terminal-/Broker-Verbindung und Demofills müssen auf deinem PC geprüft werden. Ohne diesen Abnahmeschritt ist die Integration nicht live bestätigt. Ein bestandener Softwaretest belegt keine profitable Strategie.
