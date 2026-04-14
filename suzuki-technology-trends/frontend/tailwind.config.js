/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // CADDi Drawerブランドカラー（青と白のキューブデザインに基づく）
        'caddi': {
          'blue': '#2563eb',      // メインブルー（キューブの青）
          'blue-dark': '#1e40af', // ダークブルー（ホバー用）
          'blue-light': '#3b82f6', // ライトブルー
          'gray': '#6b7280',      // グレー（テキスト用）
          'gray-dark': '#374151', // ダークグレー
        },
      },
    },
  },
  plugins: [],
}
