/**
 * ShedGuard 设计令牌 —— Claymorphism（黏土风）。
 *
 * 来源：ui-ux-pro-max 生成的设计系统（2026-11-09）。
 * 自定义字体（Varela Round / Nunito Sans）待接入 expo-font，当前用系统字体。
 */

export const colors = {
  /** 主色：活力橙 */
  primary: '#F97316',
  primaryDark: '#EA580C',
  /** 次级橙 */
  secondary: '#FB923C',
  /** 强调蓝：预测卡片、链接 */
  accent: '#2563EB',
  /** 页面底色：奶油 */
  background: '#FFF7ED',
  /** 主文字：深棕 */
  foreground: '#9A3412',
  /** 卡片 */
  card: '#FFFFFF',
  /** 描边：浅橙 */
  border: '#FED7AA',
  /** 弱化底色 */
  muted: '#F5F5F4',
  mutedForeground: '#A8A29E',
  destructive: '#DC2626',
  success: '#16A34A',
  warning: '#D97706',
} as const;

export const radius = {
  md: 16,
  lg: 20,
  xl: 24,
} as const;

/** 黏土风外阴影：柔和、无硬线（iOS shadow* + Android elevation） */
export const clayShadow = {
  shadowColor: '#9A3412',
  shadowOffset: { width: 4, height: 4 },
  shadowOpacity: 0.16,
  shadowRadius: 8,
  elevation: 4,
} as const;

/** 黏土风按压态：向内收 1px，模拟软按压 */
export const clayPress = {
  transform: [{ translateX: 2 }, { translateY: 2 }],
  shadowOffset: { width: 2, height: 2 },
  elevation: 2,
} as const;
