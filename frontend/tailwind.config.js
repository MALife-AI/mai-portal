/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 미래에셋 다크 네이비 팔레트
        surface: {
          DEFAULT: '#0f1729',
          50: '#141e33',
          100: '#1a2640',
          200: '#1f2e4d',
          300: '#2a3d5e',
          400: '#3a4f72',
          500: '#5a7494',
          600: '#8a9fb8',
          700: '#a3b5c9',
          800: '#bcc9d9',
          900: '#d4dee9',
        },
        // 미래에셋 시그니처 오렌지
        gold: {
          DEFAULT: '#F37021',
          50: '#fef3eb',
          100: '#fde0cc',
          200: '#fbcaa8',
          300: '#f9b07e',
          400: '#f69050',
          500: '#F37021',
          600: '#d95e15',
          700: '#b34c10',
          800: '#8c3b0c',
          900: '#662b08',
        },
        // 미래에셋 블루 데이터 컬러
        slate: {
          data: '#4A90D9',
          light: '#6BAAE8',
          dim: '#2C5F9E',
          dark: '#1B3A6B',
        },
        // 상태 컬러
        status: {
          success: '#34C759',
          warning: '#F5A623',
          error: '#FF3B30',
          info: '#4A90D9',
          neutral: '#8a9fb8',
        },
      },
      fontFamily: {
        pretendard: ['Pretendard', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        display: ['Playfair Display', 'serif'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      borderRadius: {
        'sm': '2px',
        DEFAULT: '4px',
        'md': '6px',
        'lg': '8px',
        'xl': '12px',
      },
      boxShadow: {
        'glow-gold': '0 0 20px rgba(243, 112, 33, 0.3)',
        'glow-blue': '0 0 20px rgba(74, 144, 217, 0.3)',
        'panel': '0 4px 24px rgba(0, 0, 0, 0.4)',
        'card': '0 2px 8px rgba(0, 0, 0, 0.3)',
        'inset-subtle': 'inset 0 1px 0 rgba(255,255,255,0.05)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-in-left': 'slideInLeft 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideInLeft: {
          '0%': { transform: 'translateX(-20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        slideInRight: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'shimmer-gradient': 'linear-gradient(90deg, transparent 25%, rgba(255,255,255,0.05) 50%, transparent 75%)',
      },
    },
  },
  plugins: [],
}
