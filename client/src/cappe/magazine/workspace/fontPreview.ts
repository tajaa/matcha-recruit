/** The few letters of a face's own name, from Google, so a font list shows
 *  every face in its own type without loading whole fonts. */
/** A face's name set in that face; `text`: other words to set in it (a Gummfit
 *  cut's name, shown in the family it is cut from). */
export const previewHref = (name: string, text = name) =>
  `https://fonts.googleapis.com/css2?family=${encodeURIComponent(name)}&text=${encodeURIComponent(text)}&display=swap`

export const WEIGHT_NAMES: Record<number, string> = {
  100: 'Thin', 200: 'Extra light', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'Semibold', 700: 'Bold', 800: 'Extra bold',
  900: 'Black', 1000: 'Extra black',
}
