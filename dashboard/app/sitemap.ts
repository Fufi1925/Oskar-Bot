import type { MetadataRoute } from 'next'

// WICHTIG: Passe die Basis-URL an, falls sie sich ändert
const BASE_URL = 'https://universtiy-bot.up.railway.app'

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${BASE_URL}/`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 1,
    },
    {
      url: `${BASE_URL}/premium`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: `${BASE_URL}/dashboard`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.6,
    },
    {
      url: `${BASE_URL}/login`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    // Weitere Routen hier ergänzen, falls vorhanden
    // z.B. /docs, /commands, /support, /terms, /privacy
  ]
}
