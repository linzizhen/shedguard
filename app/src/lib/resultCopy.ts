/**
 * 面向普通用户的文案：把状态码翻译成一句人话结论 + 一句该怎么做。
 * 原则：不出现「置信度」「概率」「蒙白」「unknown」等术语。
 */
import type { ShedState } from '@/lib/types';

export type ResultTone = 'good' | 'wait' | 'shedding' | 'unclear';

export interface ResultCopy {
  tone: ResultTone;
  headline: string;
  advice: string;
  emojiIcon: 'checkmark-circle' | 'time' | 'sparkles' | 'help-circle';
}

const COPY: Record<ShedState, ResultCopy> = {
  shedding: {
    tone: 'shedding',
    headline: '它正在蜕皮',
    advice: '接下来 2–3 天别帮它撕皮，把湿度调高一点。蜕完记得在这里记一条。',
    emojiIcon: 'sparkles',
  },
  opaque: {
    tone: 'wait',
    headline: '它可能快蜕皮了',
    advice: '身上发白是蜕皮前的信号。这几天多留意，湿度保持高一点。',
    emojiIcon: 'time',
  },
  normal: {
    tone: 'good',
    headline: '看起来还没到蜕皮',
    advice: '皮肤颜色正常。过两三天再拍一张对比一下。',
    emojiIcon: 'checkmark-circle',
  },
  unknown: {
    tone: 'unclear',
    headline: '这张没看清',
    advice: '靠近一点、光线亮一点，再拍一张试试。',
    emojiIcon: 'help-circle',
  },
};

export function resultCopy(state: ShedState): ResultCopy {
  return COPY[state] ?? COPY.unknown;
}

/** 提醒类型的人话标题 */
export function alertTitle(kind: string, petName?: string | null): string {
  const who = petName && petName.length > 0 ? petName : '你的守宫';
  if (kind === 'device_silent') return '设备可能离线了';
  if (kind === 'no_detection') return '最近没看到守宫';
  return `${who}可能开始蜕皮了`;
}

/** 蜕皮记录状态的短标签 */
export function recordLabel(completedOn: string | null): string {
  return completedOn ? '已蜕完' : '正在蜕皮';
}
