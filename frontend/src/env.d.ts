/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 高德地图 JS API key（Web端(JS API)平台） */
  readonly VITE_AMAP_JS_KEY?: string
  /** 高德地图 JS API 安全密钥（securityJsCode） */
  readonly VITE_AMAP_SECURITY_CODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
