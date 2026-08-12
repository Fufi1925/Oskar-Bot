/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        /**
         * Die Slate-Palette, neutralisiert.
         *
         * Tailwinds eigenes Slate ist deutlich blau (#1e293b hat 20
         * Punkte Abstand zwischen Rot und Blau). Auf 536 Rändern und
         * hunderten Textfarben summierte sich das zu dem Marineton,
         * der überall durchschlug.
         *
         * Diese Werte sind fast neutral, mit einem Hauch Blau in den
         * dunklen Stufen — schwarz mit leichtem Blaustich, wie in den
         * Vorlagen. Die Namen bleiben, also mussten die Klassen in den
         * Komponenten nicht angefasst werden.
         */
        slate: {
          50: "#f7f7f8",
          100: "#ebebed",
          200: "#d3d3d8",
          300: "#b1b3ba",
          400: "#82858e",
          500: "#63666f",
          600: "#4b4d55",
          700: "#33343b",
          800: "#1e1f22",
          900: "#131318",
          950: "#0a0a0c",
        },
        primary: {
          DEFAULT: "#5865f2", // Blurple
          hover: "#4752c4",
          glow: "rgba(88, 101, 242, 0.5)",
        },
        secondary: {
          DEFAULT: "#0a0a0c", // Deep Navy/Black
          light: "#0a0a0c",
        },
        accent: {
          red: "rgba(88, 101, 242, 0.1)",
          glass: "rgba(255, 255, 255, 0.03)",
        }
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic":
          "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
      },
    },
  },
  plugins: [],
};
export default config;
