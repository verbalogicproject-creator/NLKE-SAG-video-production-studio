import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Surface
        'bg-0':           'rgb(var(--bg-0) / <alpha-value>)',
        'bg-1':           'rgb(var(--bg-1) / <alpha-value>)',
        'bg-2':           'rgb(var(--bg-2) / <alpha-value>)',
        'border-base':    'rgb(var(--border) / <alpha-value>)',
        'border-strong':  'rgb(var(--border-strong) / <alpha-value>)',

        // Ink
        'ink-0': 'rgb(var(--ink-0) / <alpha-value>)',
        'ink-1': 'rgb(var(--ink-1) / <alpha-value>)',
        'ink-2': 'rgb(var(--ink-2) / <alpha-value>)',
        'ink-3': 'rgb(var(--ink-3) / <alpha-value>)',

        // Accent
        'amber':      'rgb(var(--amber) / <alpha-value>)',
        'amber-hot':  'rgb(var(--amber-hot) / <alpha-value>)',
        'amber-dim':  'rgb(var(--amber-dim) / <alpha-value>)',

        // Signal
        'signal-live': 'rgb(var(--signal-live) / <alpha-value>)',
        'signal-ok':   'rgb(var(--signal-ok) / <alpha-value>)',
        'signal-warn': 'rgb(var(--signal-warn) / <alpha-value>)',
      },
      fontFamily: {
        display: 'var(--font-display)',
        mono: 'var(--font-mono)',
      },
      borderRadius: {
        sm: 'var(--radius)',
        DEFAULT: 'var(--radius)',
      },
      transitionDuration: {
        fast: 'var(--dur-fast)',
        DEFAULT: 'var(--dur)',
        slow: 'var(--dur-slow)',
      },
      transitionTimingFunction: {
        mech: 'var(--ease)',
      },
      animation: {
        'live-pulse': 'live-pulse 1.2s ease-in-out infinite',
      },
      keyframes: {
        'live-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.3' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
