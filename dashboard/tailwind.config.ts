/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 CloudTIX Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
 * ║   github   ──  https://github.com/Fufi1925/Oskar-Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import type { Config } from "tailwindcss";

// Existing pages share the new brand palette. Status and error colors remain
// distinct so people can still recognize operational feedback.
const monochrome = {
  50: "#fafafa", 100: "#f5f5f5", 200: "#e5e5e5", 300: "#d4d4d4",
  400: "#b0b0b0", 500: "#737373", 600: "#525252", 700: "#404040",
  800: "#262626", 900: "#171717", 950: "#0a0a0a",
};

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
        slate: monochrome,
        blue: monochrome,
        indigo: monochrome,
        violet: monochrome,
        primary: {
          DEFAULT: "#737373",
          hover: "#636363",
          glow: "rgba(255, 255, 255, 0.1)",
        },
        secondary: {
          DEFAULT: "#0a0a0a",
          light: "#101010",
        },
        accent: {
          red: "rgba(255, 255, 255, 0.06)",
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
