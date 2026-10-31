// A search asks the hub first. Radius 1 is what reaches the neighbouring hub; the folders are the
// fallback for when that call cannot be made.

import { api } from "../api";
import { sceneFromDiscovery, type Scene } from "./cardView";

/** The offerings the live hubs return for this request, or null when they have nothing to draw. */
export async function hubScene(query: string): Promise<Scene | null> {
  const found = await api.discover({ query, radius: 1 });
  if (!found.matches.length) return null;
  const cards: Record<string, unknown> = {};
  await Promise.all(
    found.matches.map(async (match) => {
      let body: Record<string, unknown> = match.card ? { ...match.card } : {};
      if (!match.card) {
        try {
          body = { ...(await api.card(match.id)) };
        } catch {
          body = {};
        }
      }
      cards[match.id] = {
        ...body,
        id: match.id,
        name: body.name ?? match.name,
        description: body.description ?? match.description,
        rating: body.rating ?? match.rating,
        rating_count: body.rating_count ?? match.rating_count,
      };
    }),
  );
  return sceneFromDiscovery(query, found.matches, cards);
}
