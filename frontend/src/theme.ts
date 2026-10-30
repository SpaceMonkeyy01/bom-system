import { createTheme, rem } from '@mantine/core'

/** Tokens from DESIGN.md. Colour means status; navy is for actions only. */
export const tokens = {
  paper: '#eef3f6',
  sheet: '#ffffff',
  muted: '#f3f5f8',
  accent: '#e7f0f5',
  sidebarActive: '#d9e8ef',
  ink: '#1d2b3a',
  slate: '#5f6e82',
  rule: '#dce1e8',
  input: '#cbd3dd',
  cascade: '#00435c',
  sky: '#85b4c9',
} as const

export type Tone = 'done' | 'missing' | 'pending' | 'neutral' | 'info' | 'mutedTone'

/** [text, fill] per status tone; always paired with a word, never colour alone. */
export const status: Record<Tone, [string, string]> = {
  done: ['#1e7f4f', '#e3f4ea'],
  missing: ['#b3261e', '#fbe5e3'],
  pending: ['#8f5400', '#fdf0d9'],
  neutral: ['#5d6b7a', '#eef1f5'],
  info: ['#3e5c7e', '#e4edf7'],
  mutedTone: ['#6b4fa0', '#efeaf8'],
}

export const theme = createTheme({
  fontFamily: '"Atkinson Hyperlegible Next", ui-sans-serif, system-ui, sans-serif',
  fontFamilyMonospace: '"JetBrains Mono", ui-monospace, monospace',
  headings: {
    fontFamily: 'Jost, "Atkinson Hyperlegible Next", sans-serif',
    fontWeight: '600',
    sizes: {
      h1: { fontSize: rem(24), lineHeight: '32px' },
      h2: { fontSize: rem(16), lineHeight: '24px', fontWeight: '700' },
    },
  },
  fontSizes: { xs: rem(12), sm: rem(14), md: rem(14), lg: rem(16), xl: rem(24) },
  lineHeights: { xs: '16px', sm: '20px', md: '20px', lg: '24px', xl: '32px' },
  primaryColor: 'cascade',
  primaryShade: 6,
  colors: {
    // index 6 is the brand navy; lighter indices are the tints
    cascade: ['#e7f0f5', '#d9e8ef', '#b9d3df', '#85b4c9', '#4f8aa6', '#1f6581', '#00435c', '#003a50', '#002c3d', '#001f2c'],
  },
  black: tokens.ink,
  radius: { xs: '2.4px', sm: '4.4px', md: '4.4px', lg: '6.4px', xl: '6.4px' },
  defaultRadius: 'md',
  spacing: { xs: rem(4), sm: rem(8), md: rem(12), lg: rem(16), xl: rem(24) },
  other: { ...tokens, status },
  components: {
    Button: { defaultProps: { radius: 'md' }, styles: { root: { fontWeight: 700 } } },
    Paper: { defaultProps: { withBorder: true, shadow: 'none', radius: 'lg' } },
    Table: { styles: { th: { fontSize: 12, lineHeight: '16px', color: tokens.slate, background: tokens.muted, fontWeight: 700 } } },
    Input: { styles: { input: { borderColor: tokens.input } } },
    Anchor: { defaultProps: { underline: 'hover' } },
  },
})
