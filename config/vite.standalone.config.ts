/**
 * Vite 配置 —— Standalone 构建
 *
 * 关键差异：
 *   - alias 将 useBackend / useSettings 重定向到 standalone/src/hooks/ 版本
 *     （fetch 直调，不依赖 Electron IPC / window.backend）
 *   - 输出目录为 standalone/web/（由 PyInstaller 打包进二进制）
 *   - base: './' 使静态资源路径相对化
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // 覆盖这两个 hook：用 fetch 版替换 Electron IPC 版
      '@/hooks/useBackend': path.resolve(__dirname, '../standalone/src/hooks/useBackend.ts'),
      '@/hooks/useSettings': path.resolve(__dirname, '../standalone/src/hooks/useSettings.ts'),
      // 其余 @/* 仍指向主 src/
      '@': path.resolve(__dirname, '../src'),
    },
  },
  build: {
    outDir: 'standalone/web',
    emptyOutDir: true,
  },
  // 生产构建时不启动 dev server，base 用 '/' 即可（同源托管）
  base: '/',
})
