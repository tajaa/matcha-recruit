import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // Gummfit Studio draws pages into the dashboard itself (no frame): its one
    // HTML write is render/sink.ts, fed only by the page renderer.
    files: ['src/cappe/studio/**/*.{ts,tsx}'],
    ignores: ['src/cappe/studio/render/sink.ts', 'src/cappe/studio/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-properties': ['error',
        { property: 'innerHTML', message: 'Write HTML only through studio/render/sink.ts.' },
        { property: 'outerHTML', message: 'Write HTML only through studio/render/sink.ts.' },
        { property: 'insertAdjacentHTML', message: 'Write HTML only through studio/render/sink.ts.' }],
      'no-restricted-syntax': ['error',
        { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'Write HTML only through studio/render/sink.ts.' }],
    },
  },
])
