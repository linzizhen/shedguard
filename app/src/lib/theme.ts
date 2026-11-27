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
  /**
   * 三档弱化文字（P37 重排，2026-11-27）。
   * 原来三档相邻只差 0x08 左右，屏幕上分不出梯度；现在每档只承担一个角色，不得越级：
   * - mutedForeground：说明 / 段落（配合 type.note 14px）
   * - faintForeground：辅助提示 / 元信息（配合 type.hint 12.5px）
   * - ghostForeground：占位符 / 未选中图标 / 已弱化到背景层的信息
   */
  mutedForeground: '#5F5B54',
  faintForeground: '#8A857C',
  ghostForeground: '#B5B0A6',
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
  /** 组内间距：同一件事的几行文字之间 */
  tight: 12,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  /** 组间间距：两件不同的事之间，必须明显大于 tight */
  group: 40,
  /** 大段落之间 */
  huge: 48,
} as const;

/**
 * 字号与行高：**九档，一档一个角色**，页面里不得出现任意字号。
 *
 * P37（2026-11-27）之前的问题：15 / 13.5 / 12.5 三档只差 1–1.5px，
 * 手机上肉眼分不出二级与三级；13.5 这一档还同时兼了「段落说明」「列表副文案」
 * 「表单提示」四种角色，层级自然塌掉。现在拆成：
 *
 * | 角色 | 令牌 | 字号/行高 | 灰阶 |
 * |---|---|---|---|
 * | 页面主标题 | display | 33/40 | foreground |
 * | 结论 / 区块大标题 | title | 24/32 | foreground |
 * | 卡片 / 行标题 | heading | 17/24 | foreground |
 * | 正文 | body | 15/24 | body |
 * | 说明（一段话） | note | 14/22 | mutedForeground |
 * | 辅助（提示、元信息） | hint | 12.5/18 | faintForeground |
 * | 标签（日期、计数） | caption | 12/18 | faintForeground / ghost |
 * | 分组小标题 | label | 11/16 | faintForeground |
 * | 按钮文字 | button | 15/22 | 见按钮 |
 */
export const type = {
  /** 页面主标题：大字重、负字距，纸感的骨架 */
  display: { fontSize: 33, lineHeight: 40, fontWeight: '700' as const, letterSpacing: -1 },
  /** 区块大标题 / 结果结论 */
  title: { fontSize: 24, lineHeight: 32, fontWeight: '700' as const, letterSpacing: -0.5 },
  /** 卡片标题 */
  heading: { fontSize: 17, lineHeight: 24, fontWeight: '700' as const, letterSpacing: -0.2 },
  /** 正文 */
  body: { fontSize: 15, lineHeight: 24, fontWeight: '400' as const },
  /** 说明：一段连贯的话（原 bodySm，13.5 提到 14，与辅助档拉开 1.5px） */
  note: { fontSize: 14, lineHeight: 22, fontWeight: '400' as const },
  /** 兼容旧名：bodySm 就是 note，不许再单独调它的字号 */
  bodySm: { fontSize: 14, lineHeight: 22, fontWeight: '400' as const },
  /** 辅助：一行提示、元信息、列表副文案 */
  hint: { fontSize: 12.5, lineHeight: 18, fontWeight: '400' as const },
  /** 标签：日期、计数、徽章文字（只给短语，不给句子） */
  caption: { fontSize: 12, lineHeight: 18, fontWeight: '500' as const },
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
