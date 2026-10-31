"""What the agents say in their own words, in the app's four languages.

Model runs answer in the traveller's language by themselves; this covers everything the backend writes itself: the
offline planner, the rules-off demo, the approval and the rule-check second opinion. Names, rooms and reasons
inside a reply come from the cards and stay as the business wrote them.
"""

from typing import Any

LOCALES = ("en", "de", "fr", "it")

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "none_fit": "No business fits all your constraints. Closest: {why}.",
        "none_passed": "No listing I found passed my checks, so I did not book.",
        "set_aside": " I set aside {business} from {source}: {reasons}.",
        "sold_out": "{name} just sold out for those dates.",
        "best_fit": "Best fit: {name}, {unit} at CHF {total} for {nights} nights. Why: {reasons}.",
        "runner_up": " Runner-up: {name} ({why}).",
        "ready": "Ready to book {name}, {unit}, {check_in} to {check_out}, CHF {total} total. Why: {reasons}.",
        "verified": " Verified claims: {claims}.",
        "claim_by": "{claim} by {by}",
        "booked": "Booked {name}, {unit}, CHF {total} total. Reference {ref}; the signed receipt is your "
        "proof of stay.",
        "book_failed": "Booking failed: {error}",
        "out_of_steps": "I ran out of steps before finishing.",
        "declined": "The model declined this request.",
        "off.nothing": "Rules off: nothing matched, so there was nothing to book.",
        "off.no_room": "Rules off: {name} has no room for those dates.",
        "off.would": "Rules off: I would now book {name}, {unit}, CHF {total} total, without asking you. "
        "Nothing was sent.",
        "opinion.unread": "The booking agent never read this card, so nothing was verified.",
        "opinion.signature": "{name}'s signature did not verify.",
        "opinion.missing": "{name} does not list: {missing}.",
        "opinion.budget": "CHF {price} a night is above the CHF {budget} budget.",
        "opinion.agree": "Every requested feature is on the signed card and the price fits.",
    },
    "de": {
        "none_fit": "Kein Betrieb erfüllt alle Ihre Wünsche. Am nächsten: {why}.",
        "none_passed": "Kein gefundenes Angebot hat meine Prüfung bestanden, darum habe ich nicht gebucht.",
        "set_aside": " {business} von {source} habe ich beiseitegelegt: {reasons}.",
        "sold_out": "{name} ist für diese Daten soeben ausgebucht.",
        "best_fit": "Am besten passt {name}, {unit} für CHF {total} für {nights} Nächte. Warum: {reasons}.",
        "runner_up": " Zweite Wahl: {name} ({why}).",
        "ready": "Bereit zur Buchung: {name}, {unit}, {check_in} bis {check_out}, CHF {total} total. Warum: {reasons}.",
        "verified": " Bestätigte Angaben: {claims}.",
        "claim_by": "{claim}, bestätigt von {by}",
        "booked": "Gebucht: {name}, {unit}, CHF {total} total. Referenz {ref}; die signierte Quittung belegt Ihren "
        "Aufenthalt.",
        "book_failed": "Buchung fehlgeschlagen: {error}",
        "out_of_steps": "Mir sind die Schritte ausgegangen, bevor ich fertig war.",
        "declined": "Das Modell hat diese Anfrage abgelehnt.",
        "off.nothing": "Regeln aus: Nichts passte, also gab es nichts zu buchen.",
        "off.no_room": "Regeln aus: {name} hat für diese Daten kein Zimmer.",
        "off.would": "Regeln aus: Ich würde jetzt {name}, {unit}, CHF {total} total buchen, ohne Sie zu fragen. "
        "Gesendet wurde nichts.",
        "opinion.unread": "Der Buchungsagent hat diese Karte nie gelesen, also wurde nichts geprüft.",
        "opinion.signature": "Die Signatur von {name} liess sich nicht bestätigen.",
        "opinion.missing": "{name} führt nicht: {missing}.",
        "opinion.budget": "CHF {price} pro Nacht liegt über dem Budget von CHF {budget}.",
        "opinion.agree": "Jeder gewünschte Punkt steht auf der signierten Karte, und der Preis passt.",
    },
    "fr": {
        "none_fit": "Aucun établissement ne remplit toutes vos conditions. Le plus proche : {why}.",
        "none_passed": "Aucune offre trouvée n'a passé mes contrôles, je n'ai donc rien réservé.",
        "set_aside": " J'ai écarté {business} de {source} : {reasons}.",
        "sold_out": "{name} vient d'être complet pour ces dates.",
        "best_fit": "Meilleur choix : {name}, {unit} à CHF {total} pour {nights} nuits. Pourquoi : {reasons}.",
        "runner_up": " Deuxième choix : {name} ({why}).",
        "ready": "Prêt à réserver {name}, {unit}, du {check_in} au {check_out}, CHF {total} au total. "
        "Pourquoi : {reasons}.",
        "verified": " Informations attestées : {claims}.",
        "claim_by": "{claim}, attesté par {by}",
        "booked": "Réservé : {name}, {unit}, CHF {total} au total. Référence {ref} ; le reçu signé prouve "
        "votre séjour.",
        "book_failed": "La réservation a échoué : {error}",
        "out_of_steps": "Je n'ai plus d'étapes disponibles avant d'avoir terminé.",
        "declined": "Le modèle a refusé cette demande.",
        "off.nothing": "Règles désactivées : rien ne correspondait, il n'y avait donc rien à réserver.",
        "off.no_room": "Règles désactivées : {name} n'a pas de chambre pour ces dates.",
        "off.would": "Règles désactivées : je réserverais maintenant {name}, {unit}, CHF {total} au total, sans vous "
        "demander. Rien n'a été envoyé.",
        "opinion.unread": "L'agent de réservation n'a jamais lu cette carte, rien n'a donc été vérifié.",
        "opinion.signature": "La signature de {name} n'a pas pu être vérifiée.",
        "opinion.missing": "{name} n'indique pas : {missing}.",
        "opinion.budget": "CHF {price} par nuit dépasse le budget de CHF {budget}.",
        "opinion.agree": "Chaque élément demandé figure sur la carte signée et le prix convient.",
    },
    "it": {
        "none_fit": "Nessuna struttura soddisfa tutte le Sue condizioni. La più vicina: {why}.",
        "none_passed": "Nessuna offerta trovata ha superato i miei controlli, quindi non ho prenotato.",
        "set_aside": " Ho scartato {business} da {source}: {reasons}.",
        "sold_out": "{name} è appena esaurito per queste date.",
        "best_fit": "La scelta migliore: {name}, {unit} a CHF {total} per {nights} notti. Perché: {reasons}.",
        "runner_up": " Seconda scelta: {name} ({why}).",
        "ready": "Pronto a prenotare {name}, {unit}, dal {check_in} al {check_out}, CHF {total} in totale. "
        "Perché: {reasons}.",
        "verified": " Dati attestati: {claims}.",
        "claim_by": "{claim}, attestato da {by}",
        "booked": "Prenotato: {name}, {unit}, CHF {total} in totale. Riferimento {ref}; la ricevuta firmata prova il "
        "Suo soggiorno.",
        "book_failed": "Prenotazione non riuscita: {error}",
        "out_of_steps": "Ho esaurito i passaggi prima di finire.",
        "declined": "Il modello ha rifiutato questa richiesta.",
        "off.nothing": "Regole disattivate: nulla corrispondeva, quindi non c'era niente da prenotare.",
        "off.no_room": "Regole disattivate: {name} non ha camere per queste date.",
        "off.would": "Regole disattivate: ora prenoterei {name}, {unit}, CHF {total} in totale, senza chiederLe nulla. "
        "Non è stato inviato niente.",
        "opinion.unread": "L'agente di prenotazione non ha mai letto questa scheda, quindi non è stato "
        "verificato nulla.",
        "opinion.signature": "La firma di {name} non è stata verificata.",
        "opinion.missing": "{name} non indica: {missing}.",
        "opinion.budget": "CHF {price} a notte supera il budget di CHF {budget}.",
        "opinion.agree": "Ogni elemento richiesto è sulla scheda firmata e il prezzo va bene.",
    },
}


def locale_from(accept_language: str) -> str:
    """The first of our four languages in an Accept-Language header, in the order given; English otherwise."""
    for part in accept_language.split(","):
        base = part.split(";")[0].strip()[:2].lower()
        if base in LOCALES:
            return base
    return "en"


NAMES = {"en": "English", "de": "German (Swiss spelling, ss not ß)", "fr": "French", "it": "Italian"}


def language_line(locale: str) -> str:
    """For a model's instructions: answer in the app's language unless the traveller writes in another one."""
    language = NAMES.get(locale, "English")
    return f"\nThe app is set to {language}: reply in it, unless the traveller writes in another language."


def say(locale: str, key: str, **values: Any) -> str:
    """One reply in the given language, with its placeholders filled."""
    return TEXT.get(locale, TEXT["en"])[key].format(**values)
