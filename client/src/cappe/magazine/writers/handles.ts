/** A handle from a magazine's name: lowercase words joined by hyphens, as
 *  the server's handle rule wants (services/magazine/writers.py). */
export function handleFrom(name: string): string {
  return name.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30).replace(/-+$/, '')
}
