const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const runtime = path.join(root, 'tools/video-runtime/node_modules');
const {bundle} = require(path.join(runtime, '@remotion/bundler'));
const {selectComposition, renderMedia} = require(path.join(runtime, '@remotion/renderer'));
(async()=>{
  const project=path.resolve(process.argv[2]);
  process.chdir(path.join(root,'tools/video-runtime'));
  const inputProps=JSON.parse(fs.readFileSync(path.join(project,'props.json'),'utf8'));
  const serveUrl=await bundle({entryPoint:path.join(project,'composition.tsx'),publicDir:fs.existsSync(path.join(project,'public'))?path.join(project,'public'):null,
    webpackOverride:config=>({...config,resolve:{...config.resolve,modules:[runtime,...(config.resolve?.modules||['node_modules'])]}})});
  const composition=await selectComposition({serveUrl,id:inputProps.compositionId||'Video',inputProps});
  await renderMedia({serveUrl,composition,inputProps,codec:'h264',outputLocation:path.join(project,'video.mp4'),concurrency:2,overwrite:false});
})().catch(error=>{console.error(error);process.exitCode=1;});
