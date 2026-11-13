import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

// Single, static Vercel project. No FastAPI process or API proxy is required.
export default defineConfig({
  plugins: [react()],
  server: {port: 5173, host: '0.0.0.0'},
});
