import type { MetadataRoute } from 'next'
import { websiteOrigin } from '@/lib/website'

// The same public origin is used for login and absolute links.

export default function sitemap(): MetadataRoute.Sitemap {
  const BASE_URL = websiteOrigin()
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
      url: `${BASE_URL}/ideas`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.8,
    },
    {
      url: `${BASE_URL}/team`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    // Weitere Routen hier ergänzen, falls vorhanden
    // z.B. /docs, /commands, /support, /terms, /privacy
  ]
}
