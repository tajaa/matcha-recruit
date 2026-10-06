// Store currencies and country names for the shipping settings.

/** Two-decimal currencies only (prices are stored in hundredths). Mirrors
 *  server/app/cappe/services/shipping.py SITE_CURRENCIES. */
export const STORE_CURRENCIES = ['USD', 'CAD', 'EUR', 'GBP', 'AUD', 'NZD', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'MXN', 'SGD', 'HKD']

const regionNames = (() => {
  try { return new Intl.DisplayNames(['en'], { type: 'region' }) } catch { return null }
})()

/** "CA" → "Canada"; the code itself when the browser can't name it. */
export function countryName(code: string): string {
  try { return regionNames?.of(code) ?? code } catch { return code }
}
