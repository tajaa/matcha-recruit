declare module 'virtual:mz-frame' {
  /** The editor that runs inside a page being edited (frame/index.ts), as
   *  one script, and its stylesheet: bundled by vite-mz-frame.ts, empty in
   *  tests. */
  export const frameScript: string
  export const frameStyle: string
}
