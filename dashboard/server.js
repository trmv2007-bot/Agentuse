#!/usr/bin/env node
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.DASHBOARD_PORT || 3000);
const HOST = process.env.DASHBOARD_HOST || '127.0.0.1';
const IS_LOCAL_ONLY = ['127.0.0.1', '::1', 'localhost'].includes(HOST);
const USERNAME = process.env.MC_DASHBOARD_USERNAME || 'admin';
const PASSWORD = process.env.MC_DASHBOARD_PASSWORD;
const CSRF_TOKEN = crypto.randomBytes(32).toString('hex');
const CONFIG = path.join(ROOT, 'server.properties');
const START_SCRIPT = path.join(ROOT, 'scripts', 'start-server.sh');
const SERVER_DIR = path.join(ROOT, 'server');
const BACKUPS_DIR = path.join(ROOT, 'backups');
const MAX_LOG_LINES = 500;
let serverProcess = null, startedAt = null, logs = [], players = [], serverType = 'paper';
if (!IS_LOCAL_ONLY && !PASSWORD) { console.error('Set MC_DASHBOARD_PASSWORD before exposing the dashboard remotely.'); process.exit(1); }

function addLog(line) {
  line = String(line); logs.push(`[${new Date().toISOString().replace('T', ' ').replace('Z', '')}] ${line}`); if (logs.length > MAX_LOG_LINES) logs = logs.slice(-MAX_LOG_LINES);
  const match = line.match(/There are \d+ of \d+ players online:\s*(.*)$/);
  if (match) players = match[1].trim() ? match[1].split(',').map(x => x.trim()).filter(Boolean) : [];
}
function isRunning() { return !!serverProcess && serverProcess.exitCode === null; }
function memory() {
  if (!isRunning()) return null;
  try { const text = fs.readFileSync(`/proc/${serverProcess.pid}/status`, 'utf8'); const value = text.match(/^VmRSS:\s+(\d+) kB$/m); return value ? Math.round(Number(value[1]) / 1024) : null; } catch { return null; }
}
function status() { return { running:isRunning(), pid:isRunning()?serverProcess.pid:null, startedAt, type:serverType, players, javaMemoryMB:memory(), systemMemoryMB:Math.round((os.totalmem()-os.freemem())/1048576), csrfToken:CSRF_TOKEN }; }
function authenticated(req, res) {
  if (IS_LOCAL_ONLY) return true;
  const raw = req.headers.authorization || '', decoded = raw.startsWith('Basic ') ? Buffer.from(raw.slice(6), 'base64').toString() : '', split=decoded.indexOf(':');
  const user=split < 0 ? '' : decoded.slice(0,split), pass=split < 0 ? '' : decoded.slice(split+1);
  const valid = Buffer.byteLength(user)===Buffer.byteLength(USERNAME) && Buffer.byteLength(pass)===Buffer.byteLength(PASSWORD) && crypto.timingSafeEqual(Buffer.from(user),Buffer.from(USERNAME)) && crypto.timingSafeEqual(Buffer.from(pass),Buffer.from(PASSWORD));
  if (!valid) { res.writeHead(401, {'WWW-Authenticate':'Basic realm="Minecraft Dashboard"'}); res.end('Authentication required'); return false; } return true;
}
function json(res, code, data) { res.writeHead(code, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}); res.end(JSON.stringify(data)); }
function body(req) { return new Promise((resolve,reject)=>{let data='';req.on('data',c=>{data+=c;if(data.length>262144)req.destroy();});req.on('end',()=>{try{resolve(data?JSON.parse(data):{});}catch{reject(new Error('Invalid JSON'));}});req.on('error',reject);}); }
function validCsrf(req,res) { if(req.headers['x-csrf-token']===CSRF_TOKEN)return true; json(res,403,{error:'Reload the dashboard and try again.'});return false; }
function start(type) {
  if(isRunning()) throw new Error('The server is already running.');
  if(!['paper','vanilla'].includes(type)) throw new Error('Select Paper or Vanilla.');
  serverType=type; players=[];
  const env={...process.env, SERVER_TYPE:type, SERVER_DIR, CONFIG_FILE:CONFIG, PLUGINS_DIR:path.join(ROOT,'plugins')};
  serverProcess=spawn(START_SCRIPT,[],{cwd:ROOT,env,stdio:['pipe','pipe','pipe']}); startedAt=new Date().toISOString(); addLog(`Starting ${type} server (PID ${serverProcess.pid}).`);
  serverProcess.stdout.on('data',d=>d.toString().split(/\r?\n/).filter(Boolean).forEach(addLog)); serverProcess.stderr.on('data',d=>d.toString().split(/\r?\n/).filter(Boolean).forEach(x=>addLog(`ERROR: ${x}`)));
  serverProcess.on('error',e=>addLog(`ERROR: ${e.message}`)); serverProcess.on('exit',(code,signal)=>{addLog(`Server exited (code ${code}, signal ${signal||'none'}).`);serverProcess=null;startedAt=null;players=[];});
}
function command(text) { if(!isRunning())throw new Error('The server is not running.'); if(!/^[^\r\n]{1,300}$/.test(text))throw new Error('Command must be one line, up to 300 characters.'); serverProcess.stdin.write(`${text}\n`); addLog(`> ${text}`); }
function backup() {
  if(!fs.existsSync(path.join(SERVER_DIR,'world')))throw new Error('No world exists yet. Start the server first.');
  fs.mkdirSync(BACKUPS_DIR,{recursive:true}); const name=`world-${new Date().toISOString().replace(/[:.]/g,'-')}.tar.gz`, output=path.join(BACKUPS_DIR,name);
  const worlds=['world','world_nether','world_the_end'].filter(folder=>fs.existsSync(path.join(SERVER_DIR,folder)));
  return new Promise((resolve,reject)=>{const tar=spawn('tar',['-C',SERVER_DIR,'-czf',output,...worlds],{stdio:'ignore'});tar.on('error',()=>reject(new Error('Backup needs the tar command installed.')));tar.on('exit',c=>c===0?(addLog(`Created backup ${name}.`),resolve(name)):reject(new Error('Backup could not be created.')));});
}
function backups() { if(!fs.existsSync(BACKUPS_DIR))return []; return fs.readdirSync(BACKUPS_DIR).filter(n=>/^[\w.-]+\.tar\.gz$/.test(n)).map(name=>({name,size:fs.statSync(path.join(BACKUPS_DIR,name)).size})).sort((a,b)=>b.name.localeCompare(a.name)); }
function servePublic(res,file,type){fs.readFile(path.join(__dirname,'public',file),(e,d)=>{if(e)return json(res,404,{error:'Not found'});res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(d);});}

http.createServer(async(req,res)=>{
  if(!authenticated(req,res))return; const url=new URL(req.url,`http://${req.headers.host}`);
  try {
    if(req.method==='GET'&&url.pathname==='/')return servePublic(res,'index.html','text/html; charset=utf-8');
    if(req.method==='GET'&&url.pathname==='/app.js')return servePublic(res,'app.js','application/javascript; charset=utf-8');
    if(req.method==='GET'&&url.pathname==='/style.css')return servePublic(res,'style.css; charset=utf-8');
    if(req.method==='GET'&&url.pathname==='/api/status')return json(res,200,status());
    if(req.method==='GET'&&url.pathname==='/api/logs')return json(res,200,{logs});
    if(req.method==='GET'&&url.pathname==='/api/config')return json(res,200,{content:fs.existsSync(CONFIG)?fs.readFileSync(CONFIG,'utf8'):''});
    if(req.method==='GET'&&url.pathname==='/api/backups')return json(res,200,{backups:backups()});
    if(req.method==='GET'&&url.pathname.startsWith('/api/backup/')) { const name=path.basename(decodeURIComponent(url.pathname.slice(12))); if(!/^[\w.-]+\.tar\.gz$/.test(name)||!fs.existsSync(path.join(BACKUPS_DIR,name)))return json(res,404,{error:'Backup not found'}); res.writeHead(200,{'Content-Type':'application/gzip','Content-Disposition':`attachment; filename="${name}"`}); return fs.createReadStream(path.join(BACKUPS_DIR,name)).pipe(res); }
    if(req.method==='POST'&&url.pathname.startsWith('/api/')) { if(!validCsrf(req,res))return; const data=await body(req);
      if(url.pathname==='/api/start'){start(String(data.type));return json(res,202,status());} if(url.pathname==='/api/stop'){command('stop');return json(res,202,status());} if(url.pathname==='/api/restart'){command('stop');const type=serverType;setTimeout(()=>{if(!isRunning())try{start(type);}catch(e){addLog(`ERROR: ${e.message}`);}},6000);return json(res,202,{ok:true});}
      if(url.pathname==='/api/command'){command(String(data.command||''));return json(res,200,status());} if(url.pathname==='/api/players'){command('list');return json(res,202,{ok:true});} if(url.pathname==='/api/whitelist'){const name=String(data.name||'');if(!/^[A-Za-z0-9_]{3,16}$/.test(name))throw new Error('Enter a valid Minecraft username.');command(`whitelist ${data.action==='remove'?'remove':'add'} ${name}`);return json(res,202,{ok:true});}
      if(url.pathname==='/api/op'){const name=String(data.name||'');if(!/^[A-Za-z0-9_]{3,16}$/.test(name))throw new Error('Enter a valid Minecraft username.');command(`op ${name}`);return json(res,202,{ok:true});} if(url.pathname==='/api/backup'){const name=await backup();return json(res,201,{name});}
      if(url.pathname==='/api/config'){if(isRunning())return json(res,409,{error:'Stop the server before saving settings.'});const text=String(data.content||'');if(text.length>65536)return json(res,413,{error:'Settings file is too large.'});fs.writeFileSync(CONFIG,text.endsWith('\n')?text:`${text}\n`,{mode:0o600});addLog('Saved server.properties.');return json(res,200,{ok:true});}
    } json(res,404,{error:'Not found'});
  }catch(e){addLog(`ERROR: ${e.message}`);json(res,400,{error:e.message});}
}).listen(PORT,HOST,()=>console.log(`Minecraft dashboard: http://${HOST}:${PORT}`));
