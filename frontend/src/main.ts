import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '@/styles/theme.css'

import App from './App.vue'

const app = createApp(App)

// 禁用 Vue DevTools
app.config.devtools = false

app.use(createPinia())
app.use(ElementPlus)
app.mount('#app')
