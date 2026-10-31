// The page has one agent chat. A request for a place to stay goes to the booking agent (discover, check, hold,
// approve); a question about any other business goes to the Hive's cards. The words decide, in all four languages.

const STAY =
  /\b(hotels?|hôtels?|hostels?|rooms?|nights?|stay|beds?|check-in|zimmer|nacht|nächte|übernachtung\w*|unterkunft|bett|chambres?|nuits?|hébergement|lit|camera|camere|notte|notti|alloggio|albergo|letto)\b/i;
const BUSINESS = /\b(baselhack|adobe|bekenya|4xor|endress)\b/i;

/** "stay" for the booking agent, "ask" for the Hive's cards. */
export function routeFor(text: string, inStayConversation: boolean): "stay" | "ask" {
  if (BUSINESS.test(text)) return "ask";
  if (STAY.test(text) || inStayConversation) return "stay";
  return "ask";
}
