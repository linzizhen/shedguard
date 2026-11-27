/**
 * 面向普通用户的文案：把状态码翻译成一句人话结论 + 一句该怎么做。
 * 原则：不出现「置信度」「概率」「蒙白」「unknown」等术语。
 */
import type { QualityReason, ShedState } from '@/lib/types';

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

/** 输入质量门没通过时的针对性文案：说清是哪一种问题，而不是笼统「没看清」。 */
const QUALITY_COPY: Record<QualityReason, ResultCopy> = {
  too_blurry: {
    tone: 'unclear',
    headline: '这张有点糊',
    advice: '手机拿稳一点，等它对上焦再拍一张。',
    emojiIcon: 'help-circle',
  },
  too_dark: {
    tone: 'unclear',
    headline: '光线太暗了',
    advice: '开个灯，或者把它拿到亮一点的地方再拍。',
    emojiIcon: 'help-circle',
  },
  overexposed: {
    tone: 'unclear',
    headline: '太亮了，看不清',
    advice: '避开直射的灯或者反光，再拍一张。',
    emojiIcon: 'help-circle',
  },
  no_subject: {
    tone: 'unclear',
    headline: '没找到守宫',
    advice: '把它放进取景框里，拍全身再试一次。',
    emojiIcon: 'help-circle',
  },
};

export function resultCopy(state: ShedState, qualityReason?: QualityReason | null): ResultCopy {
  if (qualityReason) return QUALITY_COPY[qualityReason] ?? COPY.unknown;
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
