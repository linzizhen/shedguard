/**
 * 通用 UI 组件。
 *
 * P32 视觉重做后统一为「细边 + 柔阴影 + 8pt 间距」：卡片不再用 3px 橙框，
 * 按钮固定 56px 高，分组标题用小字距标签，可点元素一律 Pressable + 按压反馈。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import type { ReactNode } from 'react';
import type { StyleProp, TextInputProps, ViewStyle } from 'react-native';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { clayPress, colors, hairline, radius, shadow, space, type } from '@/lib/theme';

/** 页面骨架：安全区 + 奶油底色 + 可滚动内容 */
export function Screen({ children }: { children: ReactNode }) {
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

/** 页面标题：大字 + 一行说明 */
export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <View style={styles.pageHeader}>
      <Text style={styles.pageTitle}>{title}</Text>
      {subtitle ? <Text style={styles.pageSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

/** 白底卡片：细边 + 柔阴影 */
export function Card({
  children,
  style,
  tone = 'default',
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  tone?: 'default' | 'soft';
}) {
  return <View style={[styles.card, tone === 'soft' && styles.cardSoft, style]}>{children}</View>;
}

/** 主按钮：橙底白字，56px 高 */
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
        <ActivityIndicator color="#FFFFFF" />
      ) : (
        <Text style={styles.buttonText}>{title}</Text>
      )}
    </Pressable>
  );
}

/** 次按钮：白底橙字，细边 */
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

/** 表单字段：标签 + 输入框 */
export function Field({ label, ...inputProps }: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        placeholderTextColor={colors.faintForeground}
        {...inputProps}
      />
    </View>
  );
}

/** 空态：浅色图标底座 + 主文案 + 副文案 */
export function EmptyState({
  icon,
  title,
  subtitle,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIconWrap}>
        <Ionicons name={icon} size={28} color={colors.primaryDark} />
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      {subtitle ? <Text style={styles.emptySubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

/** 分组小标题：小字 + 字距，代替原来的粗体小节标题 */
export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

/** 可点行：左图标 + 标题/说明 + 右箭头，用于「我的」等列表 */
export function ListRow({
  icon,
  title,
  hint,
  onPress,
  right,
  last = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  hint?: string;
  onPress?: () => void;
  right?: ReactNode;
  last?: boolean;
}) {
  const content = (
    <>
      <View style={styles.rowIconWrap}>
        <Ionicons name={icon} size={18} color={colors.primaryDark} />
      </View>
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{title}</Text>
        {hint ? <Text style={styles.rowHint}>{hint}</Text> : null}
      </View>
      {right ??
        (onPress ? <Ionicons name="chevron-forward" size={18} color={colors.faintForeground} /> : null)}
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

/** 小徽章：用于状态与分类 */
export function Badge({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'accent';
}) {
  return (
    <View style={[styles.badge, badgeTone[tone].bg]}>
      <Text style={[styles.badgeText, badgeTone[tone].text]}>{label}</Text>
    </View>
  );
}

/** 分隔线 */
export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.divider, style]} />;
}

const badgeTone = {
  neutral: { bg: { backgroundColor: colors.muted }, text: { color: colors.mutedForeground } },
  primary: { bg: { backgroundColor: colors.primarySoft }, text: { color: colors.primaryDark } },
  success: { bg: { backgroundColor: colors.successSoft }, text: { color: colors.success } },
  warning: { bg: { backgroundColor: colors.warningSoft }, text: { color: colors.warning } },
  danger: { bg: { backgroundColor: colors.destructiveSoft }, text: { color: colors.destructive } },
  accent: { bg: { backgroundColor: colors.accentSoft }, text: { color: colors.accent } },
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
    paddingHorizontal: space.xl,
    paddingTop: space.sm,
    paddingBottom: space.xxxl,
    gap: space.lg,
  },
  pageHeader: {
    marginTop: space.sm,
    gap: space.xs,
  },
  pageTitle: {
    ...type.display,
    color: colors.foreground,
  },
  pageSubtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: hairline,
    borderColor: colors.border,
    padding: space.lg + 2,
    gap: space.md,
    ...shadow.card,
  },
  cardSoft: {
    backgroundColor: colors.muted,
    shadowOpacity: 0,
    elevation: 0,
  },
  button: {
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
    minHeight: 56,
  },
  buttonPrimary: {
    backgroundColor: colors.primary,
    ...shadow.card,
  },
  buttonDanger: {
    backgroundColor: colors.destructive,
  },
  buttonDisabled: {
    opacity: 0.4,
  },
  buttonText: {
    ...type.button,
    color: '#FFFFFF',
  },
  buttonSecondary: {
    backgroundColor: colors.card,
    borderWidth: hairline,
    borderColor: colors.border,
    minHeight: 52,
  },
  buttonSecondaryText: {
    ...type.button,
    color: colors.primaryDark,
  },
  field: {
    gap: space.sm,
  },
  fieldLabel: {
    ...type.label,
    color: colors.mutedForeground,
  },
  fieldInput: {
    backgroundColor: colors.card,
    borderWidth: hairline,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    ...type.body,
    color: colors.body,
    minHeight: 52,
  },
  empty: {
    alignItems: 'center',
    paddingVertical: space.xxl,
    gap: space.sm,
  },
  emptyIconWrap: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.xs,
  },
  emptyTitle: {
    ...type.heading,
    color: colors.foreground,
    textAlign: 'center',
  },
  emptySubtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
    textAlign: 'center',
    paddingHorizontal: space.lg,
  },
  sectionTitle: {
    ...type.label,
    color: colors.mutedForeground,
    marginTop: space.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md + 2,
    minHeight: 56,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  rowIconWrap: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowText: {
    flex: 1,
    gap: 2,
  },
  rowTitle: {
    ...type.heading,
    fontSize: 16,
    color: colors.foreground,
  },
  rowHint: {
    ...type.caption,
    color: colors.mutedForeground,
  },
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 5,
  },
  badgeText: {
    ...type.caption,
    fontWeight: '700',
  },
  divider: {
    height: hairline,
    backgroundColor: colors.divider,
  },
});
