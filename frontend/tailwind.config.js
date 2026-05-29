/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "outline": "#849495",
        "primary-fixed": "#7df4ff",
        "on-error": "#690005",
        "background": "#131315",
        "secondary-fixed": "#ffd7f5",
        "tertiary-fixed": "#ffe16d",
        "tertiary": "#fff5de",
        "on-primary-container": "#006970",
        "on-secondary": "#5b005b",
        "secondary-container": "#fe00fe",
        "inverse-on-surface": "#313032",
        "surface": "#131315",
        "surface-dim": "#131315",
        "error": "#ffb4ab",
        "secondary": "#ffabf3",
        "surface-variant": "#353437",
        "on-primary-fixed": "#002022",
        "on-surface": "#e5e1e4",
        "surface-bright": "#39393b",
        "outline-variant": "#3b494b",
        "on-tertiary-fixed-variant": "#544600",
        "primary-container": "#00f0ff",
        "on-tertiary-fixed": "#221b00",
        "surface-container-lowest": "#0e0e10",
        "on-primary-fixed-variant": "#004f54",
        "on-surface-variant": "#b9cacb",
        "on-secondary-container": "#500050",
        "primary-fixed-dim": "#00dbe9",
        "on-primary": "#00363a",
        "inverse-surface": "#e5e1e4",
        "primary": "#dbfcff",
        "tertiary-fixed-dim": "#e9c400",
        "error-container": "#93000a",
        "surface-container-highest": "#353437",
        "surface-container-high": "#2a2a2c",
        "on-error-container": "#ffdad6",
        "on-secondary-fixed-variant": "#810081",
        "on-background": "#e5e1e4",
        "surface-tint": "#00dbe9",
        "secondary-fixed-dim": "#ffabf3",
        "surface-container-low": "#1c1b1e",
        "inverse-primary": "#006970",
        "on-secondary-fixed": "#380038",
        "on-tertiary": "#3a3000",
        "on-tertiary-container": "#705d00",
        "surface-container": "#201f22",
        "tertiary-container": "#ffd700"
      },
      borderRadius: {
        "DEFAULT": "0.25rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px"
      },
      spacing: {
        "margin-desktop": "40px",
        "margin-mobile": "16px",
        "gutter": "16px",
        "unit": "4px",
        "skew-angle": "-12deg"
      },
      fontFamily: {
        "headline-lg-mobile": ["Anton"],
        "chat-msg": ["Hanken Grotesk"],
        "label-caps": ["Space Grotesk"],
        "body-md": ["Hanken Grotesk"],
        "headline-lg": ["Anton"],
        "display-lg": ["Anton"],
        "display-xl": ["Anton"]
      },
      fontSize: {
        "headline-lg-mobile": ["24px", { "lineHeight": "28px", "fontWeight": "400" }],
        "chat-msg": ["14px", { "lineHeight": "20px", "fontWeight": "500" }],
        "label-caps": ["12px", { "lineHeight": "16px", "letterSpacing": "0.1em", "fontWeight": "700" }],
        "body-md": ["16px", { "lineHeight": "24px", "fontWeight": "400" }],
        "headline-lg": ["32px", { "lineHeight": "36px", "fontWeight": "400" }],
        "display-lg": ["64px", { "lineHeight": "60px", "letterSpacing": "-0.02em", "fontWeight": "400" }],
        "display-xl": ["84px", { "lineHeight": "80px", "letterSpacing": "-0.04em", "fontWeight": "400" }]
      },
      backgroundImage: {
        'halftone': 'radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px)',
        'speedlines': 'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(0, 240, 255, 0.05) 10px, rgba(0, 240, 255, 0.05) 20px)'
      }
    }
  },
  plugins: [],
}
