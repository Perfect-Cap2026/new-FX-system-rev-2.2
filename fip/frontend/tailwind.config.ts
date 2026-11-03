import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14232F",      // page
        deck: "#1A2C3A",     // panels
        rule: "#2B4354",     // borders
        paper: "#ECE7DA",    // primary text
        mist: "#93A7B4",     // secondary text
        bull: "#3FB39B",
        bear: "#E0705F",
        brass: "#CFA85A",    // trade levels / setups
      },
      fontFamily: { sans: ['"Schibsted Grotesk"', "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
