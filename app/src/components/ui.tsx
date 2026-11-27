/**
 * 通用 UI 组件。
 *
 * P34 纸感极简（2026-11-19）：
 * - **没有卡片边框**。分层靠留白、1px 纸线与字号层级，不再用「白卡片叠白卡片」。
 * - 主按钮是近黑实心胶囊；次按钮是 1px 纸线的胶囊；文字链接是下划线。
 * - 分组标题走大写 + 2px 字距的 Eyebrow，是这套视觉最容易被认出的细节。
 * - 唯一彩色是琥珀 Marker（8px 方形），只做状态标记，不做大色块。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type StyleProp,
  type SwitchProps,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { clayPress, colors, hairline, radius, space, type } from '@/lib/theme';

/** 页面骨架：安全区 + 纸底色 + 可滚动内容 */
export function Screen({
  children,
  scroll = true,
}: {
  children: ReactNode;
  /** 需要自定义滚动（如拍照页要固定底部按钮）时关掉 */
  scroll?: boolean;
}) {
  if (!scroll) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.staticContent}>{children}</View>
      </SafeAreaView>
    );
  }
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

/** 顶部小字品牌行：大写字母 + 大字距，右侧可放一个圆形头像位 */
export function BrandBar({ right }: { right?: ReactNode }) {
  return (
    <View style={styles.brandBar}>
      <Text style={styles.brandText}>SHEDGUARD</Text>
      {right}
    </View>
  );
}

/** 分组小标题：大写 + 2px 字距，代替粗体小节标题 */
export function Eyebrow({ children }: { children: ReactNode }) {
  return <Text style={styles.eyebrow}>{children}</Text>;
}

/** 兼容旧名：SectionTitle 等同 Eyebrow */
export const SectionTitle = Eyebrow;

/**
 * 说明文字：一段连贯的话（14/22，中灰）。
 * **不要拿它做标题**，也不要和 Hint 混用——职责只有「解释刚才那件事」。
 */
export function Note({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[styles.note, style]}>{children}</Text>;
}

/** 辅助文字：一行提示、元信息（12.5/18，浅灰）。只放短语，不放整段话。 */
export function Hint({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[styles.hint, style]}>{children}</Text>;
}

/**
 * 分组容器：**组间 40 留白 + Eyebrow 标题 + 组内 12 行距**。
 * 一屏里有两件以上的事时用它，靠留白分组，不靠边框或卡片。
 */
export function Group({
  title,
  children,
  style,
}: {
  title?: string;
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.group, style]}>
      {title ? <Text style={styles.eyebrow}>{title}</Text> : null}
      <View style={styles.groupBody}>{children}</View>
    </View>
  );
}

/** 页面标题：大字 + 一行说明（纸感的主视觉靠它撑） */
export function PageHeader({
  title,
  subtitle,
  eyebrow,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
}) {
  return (
    <View style={styles.pageHeader}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text style={styles.pageTitle}>{title}</Text>
      {subtitle ? <Text style={styles.pageSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

/**
 * 内容块：**没有边框、没有阴影**。
 * tone='soft' 是一层比纸底深一档的填充；tone='plain' 完全透明，只做间距容器。
 */
export function Card({
  children,
  style,
  tone = 'plain',
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  tone?: 'plain' | 'soft' | 'outline';
}) {
  return (
    <View
      style={[
        styles.block,
        tone === 'soft' && styles.blockSoft,
        tone === 'outline' && styles.blockOutline,
        style,
      ]}
    >
      {children}
    </View>
  );
}

/** 8px 琥珀方形标记：状态点，纸感里唯一的彩色 */
export function Marker({ tone = 'accent' }: { tone?: 'accent' | 'success' | 'warning' | 'danger' }) {
  return <View style={[styles.marker, markerTone[tone]]} />;
}

/** 主按钮：近黑实心胶囊 */
export function PrimaryButton({
  title,
  onPress,
  loading = false,
  danger = false,
  disabled = false,
  style,
}: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  danger?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={loading || disabled}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.button,
        danger ? styles.buttonDanger : styles.buttonPrimary,
        disabled && !danger ? styles.buttonDisabled : null,
        pressed && clayPress,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={colors.onPrimary} />
      ) : (
        <Text style={[styles.buttonText, disabled ? styles.buttonTextDisabled : null]}>{title}</Text>
      )}
    </Pressable>
  );
}

/**
 * 开关。
 *
 * react-native-web 的 Switch 有两个坑：开启态的轨道色只认 `trackColor.true`（不是 `activeTrackColor`），
 * 而开启态的滑块色只认 `activeThumbColor`（默认是青色 #009688，`thumbColor` 只在关闭态生效）。
 * 所以统一收在这里，避免每个页面各写一遍、各漏一处。
 */
const WEB_SWITCH_PROPS =
  Platform.OS === 'web'
    ? ({ activeThumbColor: colors.card } as unknown as SwitchProps)
    : ({} as SwitchProps);

export function Toggle({
  value,
  onValueChange,
  disabled = false,
}: {
  value: boolean;
  onValueChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <Switch
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      trackColor={{ true: colors.foreground, false: colors.border }}
      thumbColor={colors.card}
      {...WEB_SWITCH_PROPS}
    />
  );
}

/** 次按钮：1px 纸线胶囊，透明底 */
export function SecondaryButton({
  title,
  onPress,
  disabled = false,
  style,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.button,
        styles.buttonSecondary,
        disabled && styles.buttonDisabled,
        pressed && clayPress,
        style,
      ]}
    >
      <Text style={styles.buttonSecondaryText}>{title}</Text>
    </Pressable>
  );
}

/** 带图标的胶囊按钮：首页「从相册选」「接摄像头」这类并排操作 */
export function IconButton({
  icon,
  title,
  onPress,
  style,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  onPress: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.button, styles.buttonSecondary, styles.iconButton, pressed && clayPress, style]}
    >
      <Ionicons name={icon} size={16} color={colors.body} />
      <Text style={styles.buttonSecondaryText}>{title}</Text>
    </Pressable>
  );
}

/** 文字链接：下划线，纸感里唯一的「轻操作」样式 */
export function TextLink({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="link" hitSlop={8}>
      {({ pressed }) => (
        <Text style={[styles.textLink, pressed && clayPress]}>{title}</Text>
      )}
    </Pressable>
  );
}

/** 表单字段：标签 + 下划线输入（纸感不用带框输入框） */
export function Field({ label, ...inputProps }: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        placeholderTextColor={colors.ghostForeground}
        {...inputProps}
      />
    </View>
  );
}

/** 空态：琥珀标记 + 主文案 + 副文案，不用图标底座 */
export function EmptyState({
  title,
  subtitle,
  icon,
}: {
  title: string;
  subtitle?: string;
  /** 保留旧签名，纸感里不使用图标 */
  icon?: keyof typeof Ionicons.glyphMap;
}) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyRule} />
      <Text style={styles.emptyTitle}>{title}</Text>
      {subtitle ? <Text style={styles.emptySubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

/** 可点行：标题/说明 + 右侧箭头，行间用 1px 纸线分隔 */
export function ListRow({
  icon,
  title,
  hint,
  onPress,
  right,
  last = false,
}: {
  /** 保留旧签名，纸感里不用图标 */
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  hint?: string;
  onPress?: () => void;
  right?: ReactNode;
  last?: boolean;
}) {
  const content = (
    <>
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{title}</Text>
        {hint ? <Text style={styles.rowHint}>{hint}</Text> : null}
      </View>
      {right ??
        (onPress ? (
          <Ionicons name="chevron-forward" size={17} color={colors.ghostForeground} />
        ) : null)}
    </>
  );

  if (!onPress) {
    return <View style={[styles.row, !last && styles.rowDivider]}>{content}</View>;
  }

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.row, !last && styles.rowDivider, pressed && clayPress]}
    >
      {content}
    </Pressable>
  );
}

/**
 * 状态徽章：纸感里不用色块填充，改用「小方块 + 细边胶囊」。
 * 琥珀只给需要注意的状态。
 */
export function Badge({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'accent';
}) {
  return (
    <View style={[styles.badge, badgeTone[tone].border]}>
      <Text style={[styles.badgeText, badgeTone[tone].text]}>{label}</Text>
    </View>
  );
}

/** 分隔线：1px 纸线 */
export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.divider, style]} />;
}

const markerTone = {
  accent: { backgroundColor: colors.accent },
  success: { backgroundColor: colors.success },
  warning: { backgroundColor: colors.warning },
  danger: { backgroundColor: colors.destructive },
} as const;

const badgeTone = {
  neutral: { border: { borderColor: colors.border }, text: { color: colors.mutedForeground } },
  primary: { border: { borderColor: colors.foreground }, text: { color: colors.foreground } },
  success: { border: { borderColor: colors.success }, text: { color: colors.success } },
  warning: { border: { borderColor: colors.warning }, text: { color: colors.warning } },
  danger: { border: { borderColor: colors.destructive }, text: { color: colors.destructive } },
  accent: { border: { borderColor: colors.accent }, text: { color: colors.accent } },
} as const;

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: space.xxl,
    paddingTop: space.sm,
    paddingBottom: space.huge,
    gap: space.xxl,
  },
  staticContent: {
    flex: 1,
    paddingHorizontal: space.xxl,
    paddingTop: space.sm,
  },
  brandBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: space.sm,
    marginBottom: space.xs,
  },
  brandText: {
    ...type.label,
    letterSpacing: 2.6,
    color: colors.faintForeground,
  },
  eyebrow: {
    ...type.label,
    color: colors.faintForeground,
  },
  pageHeader: {
    marginTop: space.lg,
    gap: space.sm,
  },
  pageTitle: {
    ...type.display,
    color: colors.foreground,
  },
  pageSubtitle: {
    ...type.note,
    color: colors.mutedForeground,
    maxWidth: 320,
  },
  note: {
    ...type.note,
    color: colors.mutedForeground,
  },
  hint: {
    ...type.hint,
    color: colors.faintForeground,
  },
  group: {
    // Screen 的 contentContainerStyle 已有 24 的基础间距；这里再补 16，
    // 两件不同的事之间视觉上是 40（space.group），既符合刻度也不会叠成 64 那么散。
    marginTop: space.lg,
    gap: space.md,
  },
  groupBody: {
    gap: space.tight,
  },
  block: {
    gap: space.md,
  },
  blockSoft: {
    backgroundColor: colors.muted,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  blockOutline: {
    borderWidth: hairline,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  marker: {
    width: 8,
    height: 8,
    borderRadius: radius.xs,
  },
  button: {
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: space.sm,
    paddingHorizontal: space.xl,
    minHeight: 52,
  },
  buttonPrimary: {
    backgroundColor: colors.foreground,
  },
  buttonDanger: {
    backgroundColor: colors.destructive,
  },
  buttonDisabled: {
    backgroundColor: colors.muted,
    borderWidth: hairline,
    borderColor: colors.divider,
  },
  buttonText: {
    ...type.button,
    color: colors.onPrimary,
  },
  buttonTextDisabled: {
    color: colors.faintForeground,
  },
  buttonSecondary: {
    borderWidth: hairline,
    borderColor: colors.border,
    minHeight: 50,
  },
  buttonSecondaryText: {
    ...type.button,
    color: colors.body,
  },
  iconButton: {
    flex: 1,
    paddingHorizontal: space.md,
  },
  textLink: {
    ...type.caption,
    fontWeight: '700',
    color: colors.foreground,
    textDecorationLine: 'underline',
  },
  field: {
    gap: space.xs,
  },
  fieldLabel: {
    ...type.label,
    color: colors.faintForeground,
  },
  fieldInput: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.border,
    paddingHorizontal: 0,
    paddingVertical: space.md,
    ...type.body,
    color: colors.body,
    minHeight: 46,
  },
  empty: {
    alignItems: 'flex-start',
    paddingVertical: space.xxl,
    gap: space.sm,
  },
  emptyRule: {
    width: 28,
    height: 2,
    backgroundColor: colors.accent,
    marginBottom: space.xs,
  },
  emptyTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  emptySubtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.lg,
    minHeight: 56,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  rowText: {
    flex: 1,
    gap: 3,
  },
  rowTitle: {
    ...type.body,
    fontWeight: '600',
    color: colors.foreground,
  },
  rowHint: {
    ...type.hint,
    color: colors.faintForeground,
  },
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.pill,
    borderWidth: hairline,
    paddingHorizontal: space.md,
    paddingVertical: 4,
  },
  badgeText: {
    ...type.caption,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  divider: {
    height: hairline,
    backgroundColor: colors.divider,
  },
});
