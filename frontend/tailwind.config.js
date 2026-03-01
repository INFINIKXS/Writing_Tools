/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                accent: {
                    DEFAULT: '#00e68a',
                    hover: '#00cc7a',
                    light: '#33ffaa',
                    dim: 'rgba(0, 230, 138, 0.15)',
                    glow: 'rgba(0, 230, 138, 0.3)',
                },
                dark: {
                    base: '#000000',
                    surface: '#0a0a0a',
                    card: '#050505',
                    cardHover: '#111111',
                    border: 'rgba(0, 230, 138, 0.12)',
                }
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
