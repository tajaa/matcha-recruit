import { useEffect } from 'react'

type SEOOptions = {
  title: string
  description: string
  canonical?: string
  og?: {
    title?: string
    description?: string
    image?: string
  }
  jsonLd?: object
}

function setMeta(name: string, content: string) {
  let el = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.name = name
    document.head.appendChild(el)
  }
  el.content = content
  return el
}

function setOgMeta(property: string, content: string) {
  let el = document.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.content = content
  return el
}

function setCanonical(href: string) {
  let el = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.rel = 'canonical'
    document.head.appendChild(el)
  }
  el.href = href
  return el
}

function setJsonLd(data: object) {
  let el = document.querySelector<HTMLScriptElement>('script[data-seo="json-ld"]')
  if (!el) {
    el = document.createElement('script')
    el.type = 'application/ld+json'
    el.setAttribute('data-seo', 'json-ld')
    document.head.appendChild(el)
  }
  el.textContent = JSON.stringify(data)
  return el
}

export function useSEO({ title, description, canonical, og, jsonLd }: SEOOptions) {
  useEffect(() => {
    const prevTitle = document.title
    document.title = title

    const descEl = setMeta('description', description)
    const ogTitleEl = setOgMeta('og:title', og?.title ?? title)
    const ogDescEl = setOgMeta('og:description', og?.description ?? description)
    const ogTypeEl = setOgMeta('og:type', 'website')
    let ogUrlEl: HTMLMetaElement | null = null
    let canonicalEl: HTMLLinkElement | null = null
    let jsonLdEl: HTMLScriptElement | null = null
    let ogImageEl: HTMLMetaElement | null = null

    if (canonical) {
      canonicalEl = setCanonical(canonical)
      ogUrlEl = setOgMeta('og:url', canonical)
    }
    if (og?.image) {
      ogImageEl = setOgMeta('og:image', og.image)
    }
    if (jsonLd) {
      jsonLdEl = setJsonLd(jsonLd)
    }

    return () => {
      document.title = prevTitle
      descEl.remove()
      ogTitleEl.remove()
      ogDescEl.remove()
      ogTypeEl.remove()
      canonicalEl?.remove()
      ogUrlEl?.remove()
      ogImageEl?.remove()
      jsonLdEl?.remove()
    }
  }, [title, description, canonical, og?.title, og?.description, og?.image, jsonLd])
}
