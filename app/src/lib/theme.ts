/**
 * ShedGuard 设计令牌。
 *
 * 方向：Minimalism & Swiss（2026-11-18，P32 视觉重做）。上一版是 3px 粗边 + 重阴影的
 * 黏土风，观感偏「玩具」，用户在真机上直说「丑」。这一版收紧为细边 + 柔阴影 +
 * 明确的字号层级与 8pt 间距，保留原来的暖橙配色（ui-ux-pro-max 给出的配色与旧版一致）。
 *
 * 修改原则：颜色、字号、间距只在本文件定义，组件与页面不得写裸值。
 */

export const colors = {
  /** 主色：暖橙（品牌色，用于主按钮与强调） */
  primary: '#F97316',
  primaryDark: '#C2410C',
  /** 主色的浅色底：用于选中态、图标底座 */
  primarySoft: '#FFEDD5',
  /** 次级橙（少用，只做装饰） */
  secondary: '#FB923C',
  /** 强调蓝：结果徽章、链接 */
  accent: '#2563EB',
  accentSoft: '#DBEAFE',
  /** 页面底色：奶油 */
  background: '#FFF7ED',
  /** 主文字：深棕，标题用 */
  foreground: '#7C2D12',
  /** 正文文字：比标题深，满足 4.5:1 */
  body: '#431407',
  /** 卡片 */
  card: '#FFFFFF',
  /** 细描边：暖灰，不再是明显的橙色框 */
  border: '#F0E2D3',
  /** 更浅的分隔线 */
  divider: '#F6EDE4',
  /** 弱化底色（输入框、折叠区） */
  muted: '#FDF3EA',
  /** 弱化文字：暖灰，对白底 5.2:1、对奶油底 4.9:1 */
  mutedForeground: '#6B6259',
  /** 更弱的说明文字，只用于 ≥12px 的辅助信息 */
  faintForeground: '#8A8177',
  destructive: '#DC2626',
  destructiveSoft: '#FEE2E2',
  success: '#15803D',
  successSoft: '#DCFCE7',
  warning: '#B45309',
  warningSoft: '#FEF3C7',
} as const;

/** 圆角：越小越「硬」，卡片与按钮统一走 lg/md */
export const radius = {
  sm: 10,
  md: 14,
  lg: 18,
  xl: 26,
  pill: 999,
} as const;

/** 8pt 间距刻度 */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

/** 字号与行高：所有文本都从这里取，避免每屏各写一套 */
export const type = {
  /** 页面主标题 */
  display: { fontSize: 28, lineHeight: 36, fontWeight: '800' as const, letterSpacing: -0.4 },
  /** 区块大标题 / 结果结论 */
  title: { fontSize: 21, lineHeight: 29, fontWeight: '800' as const, letterSpacing: -0.2 },
  /** 卡片标题 */
  heading: { fontSize: 17, lineHeight: 24, fontWeight: '700' as const },
  /** 正文 */
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' as const },
  /** 紧凑正文（列表第二行） */
  bodySm: { fontSize: 14, lineHeight: 21, fontWeight: '400' as const },
  /** 说明文字 */
  caption: { fontSize: 13, lineHeight: 19, fontWeight: '500' as const },
  /** 分组小标题 */
  label: { fontSize: 12, lineHeight: 16, fontWeight: '700' as const, letterSpacing: 0.8 },
  /** 按钮文字 */
  button: { fontSize: 16, lineHeight: 22, fontWeight: '700' as const },
} as const;

/** 柔阴影：偏移向下、不透明度低，接近纸片浮起的感觉 */
export const shadow = {
  card: {
    shadowColor: '#7C2D12',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 14,
    elevation: 2,
  },
  raised: {
    shadowColor: '#7C2D12',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.12,
    shadowRadius: 22,
    elevation: 6,
  },
} as const;

/** 兼容旧引用：卡片阴影 */
export const clayShadow = shadow.card;

/** 兼容旧引用：按压态。旧版是位移 2px 的黏土按压，这里改成轻微下沉 */
export const clayPress = {
  opacity: 0.9,
  transform: [{ scale: 0.995 }],
} as const;

/** 细描边统一值 */
export const hairline = 1;
