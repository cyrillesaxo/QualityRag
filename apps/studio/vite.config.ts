import {defineConfig} from 'vite';
export default defineConfig({server:{proxy:{'/v1':{target:'http://127.0.0.1:5055',changeOrigin:true},'/health':{target:'http://127.0.0.1:5055',changeOrigin:true}}}});
