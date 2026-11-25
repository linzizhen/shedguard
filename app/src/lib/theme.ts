/**
 * ShedGuard 设计令牌。
 *
 * 方向：Paper Minimal（纸感极简，2026-11-19，P34 视觉重做，用户三选一定稿）。
 *
 * 三代演进的由来，避免以后又绕回去：
 * - v1 黏土风：3px 粗边 + 重阴影 + 暖橙，用户说「丑」。
 * - v2 Swiss：细边 + 柔阴影 + 8pt 间距，仍然是白卡片叠白卡片，层次平、像未完成的 Demo。
 * - v3 纸感极简（当前）：**不用卡片边框，靠留白、字号层级与 1px 纸线分层**；
 *   主按钮是近黑的实心圆/胶囊，琥珀色只做 8px 方形小标记与极少量强调。
 *
 * 修改原则：颜色、字号、间距、圆角只在本文件定义，组件与页面不得写裸值。
 */

export const colors = {
  /** 页面底色：纸白（略带暖调，不是纯白） */
  background: '#FBF9F6',
  /** 浮起层：比纸底亮一档，只在需要「一张纸压在另一张纸上」时用 */
  card: '#FFFFFF',
  /** 主文字 / 主按钮底色：近黑，不是纯黑（纯黑在纸底上过硬） */
  foreground: '#14140F',
  /** 正文：比标题浅一点，长段落用它 */
  body: '#2A2A22',
  /** 主色即近黑，保留旧键名，避免全仓 import 报错 */
  primary: '#14140F',
  primaryDark: '#14140F',
  /** 主色的浅底：选中态、图标底座、chip 背景 */
  primarySoft: '#EDE9E1',
  /** 主色上的文字（近黑底上的字） */
  onPrimary: '#FBF9F6',
  /** 次强调：深一档的墨，只做装饰线或次级文字 */
  secondary: '#2A2A22',
  /** 唯一的彩色强调：琥珀。只用于 8px 方形标记、极少数链接与进度点 */
  accent: '#C08A45',
  accentSoft: '#F6EFE2',
  /** 1px 纸线：所有分隔都靠它，不用边框 */
  border: '#E4DFD5',
  divider: '#E9E4DA',
  /** 更浅的填充：输入框、折叠区、空态底座 */
  muted: '#F2EEE7',
  /** 次要文字：对纸底 5.1:1 */
  mutedForeground: '#7A766E',
  /** 更弱的说明文字，只用于 ≥12px 的辅助信息 */
  faintForeground: '#9A968E',
  /** 最弱：Tab 未选中图标、占位符 */
  ghostForeground: '#A8A49C',
  destructive: '#B3261E',
  destructiveSoft: '#F7E4E1',
  success: '#3F6B45',
  successSoft: '#E6EEE4',
  warning: '#96631F',
  warningSoft: '#F7EEDD',
} as const;

/** 圆角：纸感靠「胶囊」与「近乎直角」两个极端，中间值少用 */
export const radius = {
  /** 方形小标记 */
  xs: 2,
  /** 输入框、小方块 */
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  /** 胶囊：次按钮、chip、徽章 */
  pill: 999,
} as const;

/** 8pt 间距刻度（纸感极简靠大留白，xxl/xxxl 会比 v2 用得多） */
export const space = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  /** 大段落之间 */
  huge: 48,
} as const;

/** 字号与行高：所有文本都从这里取，避免每屏各写一套 */
export const type = {
  /** 页面主标题：大字重、负字距，纸感的骨架 */
  display: { fontSize: 33, lineHeight: 40, fontWeight: '700' as const, letterSpacing: -1 },
  /** 区块大标题 / 结果结论 */
  title: { fontSize: 24, lineHeight: 32, fontWeight: '700' as const, letterSpacing: -0.5 },
  /** 卡片标题 */
  heading: { fontSize: 17, lineHeight: 24, fontWeight: '700' as const, letterSpacing: -0.2 },
  /** 正文 */
  body: { fontSize: 15, lineHeight: 24, fontWeight: '400' as const },
  /** 紧凑正文（列表第二行） */
  bodySm: { fontSize: 13.5, lineHeight: 21, fontWeight: '400' as const },
  /** 说明文字 */
  caption: { fontSize: 12.5, lineHeight: 19, fontWeight: '500' as const },
  /** 分组小标题：大写字母 + 大字距，纸感的关键细节 */
  label: { fontSize: 11, lineHeight: 16, fontWeight: '700' as const, letterSpacing: 2 },
  /** 按钮文字 */
  button: { fontSize: 15, lineHeight: 22, fontWeight: '700' as const, letterSpacing: 0.3 },
} as const;

/**
 * 阴影：纸感极简几乎不用阴影。
 * card 保留键名但完全透明（旧页面若还引用它，视觉上就是「无阴影」）。
 * raised 只给首页那颗大圆按钮，让它像一枚压下去的印章。
 */
export const shadow = {
  card: {
    shadowColor: '#14140F',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0,
    shadowRadius: 0,
    elevation: 0,
  },
  raised: {
    shadowColor: '#14140F',
    shadowOffset: { width: 0, height: 26 },
    shadowOpacity: 0.42,
    shadowRadius: 48,
    elevation: 12,
  },
} as const;

/** 兼容旧引用：卡片阴影（现在是空的） */
export const clayShadow = shadow.card;

/** 兼容旧引用：按压态。纸感用不透明度变化，不做位移 */
export const clayPress = {
  opacity: 0.62,
} as const;

/** 细描边统一值 */
export const hairline = 1;
