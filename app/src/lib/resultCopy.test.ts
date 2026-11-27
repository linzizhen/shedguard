/**
 * 结果文案的单元测试（纯函数，不依赖 React Native 与浏览器）。
 *
 * 跑法：在 `app` 目录下 `node src/lib/resultCopy.test.ts`
 * （Node 24 能直接跑 TypeScript；`node --test` 在本机沙箱里 spawn 子进程会被拒，故直接执行文件。
 *   `resultCopy.ts` 只有一个 `import type`，会被 Node 的类型擦除去掉，所以 `@/lib/types` 别名不会真的被解析。）
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { alertTitle, recordLabel, resultCopy } from './resultCopy.ts';
import type { QualityReason, ShedState } from './resultCopy.ts';

const STATES: ShedState[] = ['normal', 'opaque', 'shedding', 'unknown'];
const QUALITY_REASONS: QualityReason[] = [
  'too_blurry',
  'too_dark',
  'overexposed',
  'no_subject',
];

test('四种状态各有一句人话结论与建议', () => {
  for (const state of STATES) {
    const copy = resultCopy(state);

    assert.ok(copy.headline.length > 0, `${state} 缺结论`);
    assert.ok(copy.advice.length > 0, `${state} 缺建议`);
  }
});

test('状态与语气一一对应，不发脾气也不卖萌', () => {
  assert.equal(resultCopy('shedding').tone, 'shedding');
  assert.equal(resultCopy('opaque').tone, 'wait');
  assert.equal(resultCopy('normal').tone, 'good');
  assert.equal(resultCopy('unknown').tone, 'unclear');
});

test('质量原因优先于状态，且四条各不相同', () => {
  const headlines = QUALITY_REASONS.map((reason) => resultCopy('unknown', reason).headline);

  assert.equal(new Set(headlines).size, QUALITY_REASONS.length, '四条原因的结论重复了');

  // 后端保证 quality_reason 非空时 state 恒为 unknown；即使传错也不能退回笼统文案。
  for (const reason of QUALITY_REASONS) {
    assert.notEqual(
      resultCopy('shedding', reason).headline,
      resultCopy('shedding').headline,
      `${reason} 没有覆盖掉状态文案`,
    );
    assert.equal(resultCopy('shedding', reason).tone, 'unclear');
  }
});

test('质量原因为空时按状态走', () => {
  assert.equal(resultCopy('shedding', null).headline, '它正在蜕皮');
  assert.equal(resultCopy('shedding', undefined).headline, '它正在蜕皮');
});

test('文案里不出现内部术语', () => {
  const banned = ['置信度', '概率', 'unknown', 'shedding', 'opaque', '蒙白'];

  for (const state of STATES) {
    const copy = resultCopy(state);
    for (const word of banned) {
      assert.ok(!copy.headline.includes(word), `${state} 的结论含内部术语 ${word}`);
      assert.ok(!copy.advice.includes(word), `${state} 的建议含内部术语 ${word}`);
    }
  }
  for (const reason of QUALITY_REASONS) {
    const copy = resultCopy('unknown', reason);
    for (const word of banned) {
      assert.ok(!copy.headline.includes(word), `${reason} 的结论含内部术语 ${word}`);
    }
  }
});

test('提醒标题说人话，且带上宠物名', () => {
  assert.equal(alertTitle('shedding_detected', '小橘'), '小橘可能开始蜕皮了');
  assert.equal(alertTitle('shedding_detected', null), '你的守宫可能开始蜕皮了');
  assert.equal(alertTitle('device_silent', '小橘'), '设备可能离线了');
  assert.equal(alertTitle('no_detection', '小橘'), '最近没看到守宫');
});

test('记录标签只有两种', () => {
  assert.equal(recordLabel('2026-11-20'), '已蜕完');
  assert.equal(recordLabel(null), '正在蜕皮');
});
