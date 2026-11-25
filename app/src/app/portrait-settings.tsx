/**
 * 萌照设置：要不要每天拍、一天几张、几点到几点拍。
 * 纸感极简（P34）：开关与步进器都用 1px 纸线分隔，去掉卡片框。
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Divider,
  EmptyState,
  Eyebrow,
  Marker,
  PrimaryButton,
  Screen,
  Toggle,
} from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { usePortraitSettings, useUpdatePortraitSettings } from '@/hooks/usePortraits';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, hairline, radius, space, type } from '@/lib/theme';

function Stepper({
  label,
  value,
  display,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  display: string;
  min: number;
  max: number;
  onChange: (next: number) => void;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.stepper}>
        <Pressable
          onPress={() => onChange(Math.max(min, value - 1))}
          disabled={value <= min}
          accessibilityRole="button"
          accessibilityLabel={`${label}减一`}
          style={[styles.stepButton, value <= min && styles.stepDisabled]}
        >
          <Text style={styles.stepText}>−</Text>
        </Pressable>
        <Text style={styles.stepValue}>{display}</Text>
        <Pressable
          onPress={() => onChange(Math.min(max, value + 1))}
          disabled={value >= max}
          accessibilityRole="button"
          accessibilityLabel={`${label}加一`}
          style={[styles.stepButton, value >= max && styles.stepDisabled]}
        >
          <Text style={styles.stepText}>＋</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function PortraitSettingsScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const petId = petsQuery.data?.items[0]?.id ?? null;
  const settingsQuery = usePortraitSettings(petId);
  const update = useUpdatePortraitSettings(petId);

  const saved = settingsQuery.data ?? null;
  const [draft, setDraft] = useState<{
    enabled: boolean;
    per_day: number;
    start_hour: number;
    end_hour: number;
  } | null>(null);

  const current =
    draft ??
    (saved
      ? {
          enabled: saved.enabled,
          per_day: saved.per_day,
          start_hour: saved.start_hour,
          end_hour: saved.end_hour,
        }
      : null);

  if (serverUrl === '') {
    return (
      <Screen>
        <EmptyState title="还没连上服务端" subtitle="先回到「我的」，填好地址。" />
      </Screen>
    );
  }

  if (!petId) {
    return (
      <Screen>
        <EmptyState title="还没有你的守宫" subtitle="先建个档案再来设置" />
        <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
      </Screen>
    );
  }

  if (!current) {
    return (
      <Screen>
        <Text style={styles.hint}>正在读取…</Text>
      </Screen>
    );
  }

  function patch(next: Partial<NonNullable<typeof current>>) {
    if (!current) return;
    setDraft({ ...current, ...next });
  }

  const dirty =
    draft !== null &&
    saved !== null &&
    (draft.enabled !== saved.enabled ||
      draft.per_day !== saved.per_day ||
      draft.start_hour !== saved.start_hour ||
      draft.end_hour !== saved.end_hour);

  const span = current.end_hour - current.start_hour;
  const windowInvalid = span <= 0;

  return (
    <Screen>
      <Text style={styles.subtitle}>设备会在这段时间里挑一张最好看的留下来</Text>

      <Divider />

      <View style={styles.row}>
        <Text style={styles.rowLabel}>每天拍萌照</Text>
        <Toggle value={current.enabled} onValueChange={(next) => patch({ enabled: next })} />
      </View>

      <View style={styles.rowDivider}>
        <Stepper
          label="一天几张"
          value={current.per_day}
          display={`${current.per_day} 张`}
          min={0}
          max={6}
          onChange={(next) => patch({ per_day: next })}
        />
      </View>

      <Eyebrow>拍摄时间</Eyebrow>

      <View style={styles.rowDivider}>
        <Stepper
          label="开始"
          value={current.start_hour}
          display={`${current.start_hour}:00`}
          min={0}
          max={23}
          onChange={(next) => patch({ start_hour: next })}
        />
      </View>
      <Stepper
        label="结束"
        value={current.end_hour}
        display={`${current.end_hour}:00`}
        min={1}
        max={24}
        onChange={(next) => patch({ end_hour: next })}
      />

      {windowInvalid ? (
        <Text style={styles.errorText}>结束时间要晚于开始时间。</Text>
      ) : (
        <Text style={styles.hint}>
          这段时间一共 {span} 小时，设备会自己分配拍摄时刻，晚上不拍。
        </Text>
      )}

      <Divider />

      <PrimaryButton
        title={dirty ? '保存设置' : '已保存'}
        onPress={() => {
          if (!current) return;
          update.mutate(current, {
            onSuccess: () => setDraft(null),
          });
        }}
        disabled={!dirty || windowInvalid || update.isPending}
      />

      {update.isError ? (
        <Text style={styles.errorText}>没存上。检查一下网络，再点一次保存。</Text>
      ) : null}

      <View style={styles.note}>
        <Marker />
        <Text style={styles.noteText}>
          照片只存在你自己的电脑上，不会发给别人。想删掉旧照片，可以在后端打开「照片保留」设置。
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: { ...type.bodySm, color: colors.mutedForeground },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    minHeight: 48,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  rowLabel: { ...type.body, fontWeight: '600', color: colors.foreground },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  stepButton: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDisabled: { opacity: 0.35 },
  stepText: { fontSize: 20, fontWeight: '600', color: colors.foreground },
  stepValue: {
    minWidth: 64,
    textAlign: 'center',
    ...type.body,
    fontWeight: '700',
    color: colors.foreground,
  },
  hint: { ...type.caption, color: colors.mutedForeground },
  errorText: { ...type.bodySm, color: colors.destructive },
  note: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
  },
  noteText: { ...type.caption, flex: 1, color: colors.faintForeground },
});
