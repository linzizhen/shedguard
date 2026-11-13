/**
 * 萌照设置：要不要每天拍、一天几张、几点到几点拍。
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import { Card, EmptyState, PrimaryButton, Screen, SectionTitle } from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { usePortraitSettings, useUpdatePortraitSettings } from '@/hooks/usePortraits';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';

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
        <Card>
          <EmptyState icon="cloud-offline" title="App 还没连上电脑" subtitle="先回到「我的」，填好地址。" />
        </Card>
      </Screen>
    );
  }

  if (!petId) {
    return (
      <Screen>
        <Card style={{ gap: 12 }}>
          <EmptyState icon="paw" title="还没有你的守宫" subtitle="先建个档案再来设置" />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      </Screen>
    );
  }

  if (!current) {
    return (
      <Screen>
        <Card>
          <EmptyState icon="hourglass" title="正在读取…" />
        </Card>
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

      <Card style={{ gap: 12 }}>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>每天拍萌照</Text>
          <Switch
            value={current.enabled}
            onValueChange={(next) => patch({ enabled: next })}
            trackColor={{ true: colors.primary, false: colors.border }}
            thumbColor="#FFFFFF"
          />
        </View>

        <Stepper
          label="一天几张"
          value={current.per_day}
          display={`${current.per_day} 张`}
          min={0}
          max={6}
          onChange={(next) => patch({ per_day: next })}
        />
      </Card>

      <SectionTitle>拍摄时间</SectionTitle>
      <Card style={{ gap: 12 }}>
        <Stepper
          label="开始"
          value={current.start_hour}
          display={`${current.start_hour}:00`}
          min={0}
          max={23}
          onChange={(next) => patch({ start_hour: next })}
        />
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
      </Card>

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

      <Text style={styles.hint}>
        照片只存在你自己的电脑上，不会发给别人。想删掉旧照片，可以在后端打开「照片保留」设置。
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    fontSize: 14,
    color: colors.mutedForeground,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    minHeight: 44,
  },
  rowLabel: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.foreground,
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepButton: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDisabled: {
    opacity: 0.4,
  },
  stepText: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.primaryDark,
  },
  stepValue: {
    minWidth: 64,
    textAlign: 'center',
    fontSize: 16,
    fontWeight: '700',
    color: colors.foreground,
  },
  hint: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.mutedForeground,
  },
  errorText: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.destructive,
  },
});
