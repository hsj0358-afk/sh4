// 의존성 없는 정적 서버. 개발 중 모바일 실기기에서 열어보기 위한 것.
//   npm start  →  http://localhost:5173

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';
import { networkInterfaces } from 'node:os';

const ROOT = resolve(new URL('..', import.meta.url).pathname);
const PORT = Number(process.env.PORT || 5173);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let path = decodeURIComponent(url.pathname);
    if (path.endsWith('/')) path += 'index.html';

    const target = join(ROOT, normalize(path));
    if (!target.startsWith(ROOT)) {
      res.writeHead(403).end('forbidden');
      return;
    }

    const info = await stat(target).catch(() => null);
    if (!info || !info.isFile()) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' }).end('없는 길입니다.');
      return;
    }

    const body = await readFile(target);
    res.writeHead(200, {
      'content-type': TYPES[extname(target)] || 'application/octet-stream',
      'cache-control': 'no-cache',
    });
    res.end(body);
  } catch (err) {
    res.writeHead(500).end(String(err));
  }
});

server.listen(PORT, () => {
  const lan = Object.values(networkInterfaces())
    .flat()
    .filter((i) => i && i.family === 'IPv4' && !i.internal)
    .map((i) => `  http://${i.address}:${PORT}`);
  console.log(`《잃어버린 세계의 지도》 개발 서버`);
  console.log(`  http://localhost:${PORT}`);
  if (lan.length) console.log(lan.join('\n'), '\n  (같은 네트워크의 휴대폰에서 열어보세요)');
});
