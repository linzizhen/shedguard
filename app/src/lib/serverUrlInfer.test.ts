/**
 * 地址推断的单元测试（纯函数，不依赖 React Native 与浏览器）。
 *
 * 跑法：在 `app` 目录下 `node src/lib/serverUrlInfer.test.ts`
 * （Node 24 能直接跑 TypeScript；`node --test` 在本机沙箱里 spawn 子进程会被拒，故直接执行文件。）
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { inferServerUrl } from './serverUrlInfer.ts';

test('显式配置的地址优先于页面来源', () => {
  const url = inferServerUrl('http://192.168.1.9:8010', {
    origin: 'https://demo.trycloudflare.com',
    port: '',
  });

  assert.equal(url, 'http://192.168.1.9:8010');
});

test('显式配置会去掉首尾空格', () => {
  assert.equal(
    inferServerUrl('  http://127.0.0.1:8010  ', null),
    'http://127.0.0.1:8010',
  );
});

test('没有页面（原生端）且没配置时返回空串，交给用户填写', () => {
  assert.equal(inferServerUrl('', null), '');
});

test('页面自己就是服务端时，用页面来源', () => {
  assert.equal(
    inferServerUrl('', { origin: 'https://abc-def.trycloudflare.com', port: '' }),
    'https://abc-def.trycloudflare.com',
  );
});

test('页面跑在 Metro 开发端口上时不采用它', () => {
  for (const port of ['8081', '19006', '19000']) {
    assert.equal(
      inferServerUrl('', { origin: `http://127.0.0.1:${port}`, port }),
      '',
      `端口 ${port} 应被排除`,
    );
  }
});

test('普通端口（含服务端默认的 8010）照常采用', () => {
  assert.equal(
    inferServerUrl('', { origin: 'http://192.168.1.9:8010', port: '8010' }),
    'http://192.168.1.9:8010',
  );
});

test('origin 为空时不硬造地址', () => {
  assert.equal(inferServerUrl('', { origin: '', port: '' }), '');
});
