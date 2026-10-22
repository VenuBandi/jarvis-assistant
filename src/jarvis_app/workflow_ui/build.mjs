import {build} from 'esbuild';
await build({entryPoints:['app.jsx'],bundle:true,minify:true,sourcemap:false,outfile:'../frontend/workflow/app.js',loader:{'.jsx':'jsx'},define:{'process.env.NODE_ENV':'"production"'},legalComments:'eof'});
