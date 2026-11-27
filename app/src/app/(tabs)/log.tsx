/**
 * 蜕皮记录：最上面一条提醒，下面是「什么时候开始、什么时候蜕完」的时间线。
 * 文案全部口语化，不出现内部状态名。纸感极简（P34）：时间线靠 1px 竖线与方形标记分层，不用卡片框。
 *
 * P37（2026-11-27）层级重排：一屏只有页大标题一个最强层级；分组名走 Eyebrow / Group 的标题位；
 * 时间线三层分别是 Hint（日期 12.5）/ Badge（状态 12）/ Note（备注 14）；
 * 组间用 Group 的 40，组内（时间线块之间）用 space.tight 的 12。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Badge,
  BrandBar,
  EmptyState,
  Eyebrow,
  Field,
  Group,
  Hint,
  IconButton,
  Marker,
  Note,
  PageHeader,
  PrimaryButton,
  Screen,
  TextLink,
  Toggle,
} from '@/components/ui';
import { useAlerts } from '@/hooks/useAlerts';
import { usePets } from '@/hooks/usePets';
import {
  useCreateShedRecord,
  useDeleteShedRecord,
  useShedRecords,
  useUpdateShedRecord,
} from '@/hooks/useShed';
import { todayIso } from '@/lib/dates';
import { useDeviceId } from '@/lib/deviceId';
import { alertTitle, recordLabel } from '@/lib/resultCopy';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, radius, space, type } from '@/lib/theme';
import type { ShedRecord } from '@/lib/types';

function shortDate(iso: string): string {
  const [, month, day] = iso.split('-');
  return `${Number(month)}月${Number(day)}日`;
}

export default function LogScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const deviceId = useDeviceId();
  const [formOpen, setFormOpen] = useState(false);
  const [startedOn, setStartedOn] = useState(todayIso());
  const [completed, setCompleted] = useState(false);
  const [notes, setNotes] = useState('');
  const [errorText, setErrorText] = useState<string | null>(null);

  const pets = petsQuery.data?.items ?? [];
  const pet = pets[0] ?? null;
  const petId = pet?.id ?? '';
  const recordsQuery = useShedRecords(petId === '' ? null : petId);
  const alertsQuery = useAlerts({ petId: petId === '' ? null : petId, deviceId: deviceId || null });
  const createRecord = useCreateShedRecord(petId);
  const updateRecord = useUpdateShedRecord(petId);
  const deleteRecord = useDeleteShedRecord(petId);

  const records: ShedRecord[] = recordsQuery.data?.items ?? [];
  const latestAlert = alertsQuery.data?.items?.[0] ?? null;

  async function save() {
    setErrorText(null);
    if (petId === '') return;
    try {
      await createRecord.mutateAsync({
        started_on: startedOn,
        completed_on: completed ? startedOn : undefined,
        notes: notes.trim() === '' ? undefined : notes.trim(),
      });
      setFormOpen(false);
      setNotes('');
      setCompleted(false);
      setStartedOn(todayIso());
    } catch (err) {
      setErrorText(err instanceof Error ? err.message : '没保存上，再试一次');
    }
  }

  async function markDone(record: ShedRecord) {
    try {
      await updateRecord.mutateAsync({
        recordId: record.id,
        input: {
          started_on: record.started_on,
          completed_on: todayIso(),
          notes: record.notes ?? undefined,
        },
      });
    } catch {
      Alert.alert('没改成', '网络好像不太顺，等一下再试。');
    }
  }

  function confirmDelete(record: ShedRecord) {
    Alert.alert('删掉这条记录？', '删了就找不回来了。', [
      { text: '不删', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => void deleteRecord.mutateAsync(record.id).catch(() => undefined),
      },
    ]);
  }

  if (serverUrl === '') {
    return (
      <Screen>
        <BrandBar />
        <PageHeader title="蜕皮记录" subtitle="每次蜕皮记一条，方便回看" />
        <EmptyState title="还没连上服务端" subtitle="在「我的 → 高级设置」里填入地址。" />
      </Screen>
    );
  }

  return (
    <Screen>
      <BrandBar />
      <PageHeader
        title="蜕皮记录"
        subtitle={pet ? `${pet.name}的每一次蜕皮` : '每次蜕皮记一条'}
      />

      {/* 组间节奏与 Screen 一致：24 的基础间距 + Group 的 16 = 40，避免叠成 64 */}
      <View style={styles.stack}>
        {latestAlert ? (
          <Pressable
            onPress={() =>
              router.push({
                pathname: '/alert/[id]',
                params: {
                  id: latestAlert.id,
                  kind: latestAlert.kind,
                  image_id: latestAlert.image_id ?? '',
                  state: latestAlert.state,
                  local_date: latestAlert.local_date,
                  confidence: latestAlert.confidence !== null ? String(latestAlert.confidence) : '',
                },
              })
            }
            accessibilityRole="button"
            style={({ pressed }) => [styles.alertRow, pressed && clayPress]}
          >
            <Marker />
            <View style={styles.alertBody}>
              <Text style={styles.alertTitle}>{alertTitle(latestAlert.kind, pet?.name)}</Text>
              <Hint>{shortDate(latestAlert.local_date)} · 点开看看</Hint>
            </View>
            <Ionicons name="chevron-forward" size={17} color={colors.ghostForeground} />
          </Pressable>
        ) : null}

        {petId === '' ? (
          <>
            <EmptyState title="还没有你的守宫" subtitle="先建个档案，再来记录蜕皮" />
            <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
          </>
        ) : (
          <>
            <Group title={formOpen ? '记一次蜕皮' : undefined}>
              {formOpen ? (
                <>
                  <Field
                    label="哪天开始蜕的"
                    placeholder="2026-11-12"
                    value={startedOn}
                    onChangeText={setStartedOn}
                    autoCapitalize="none"
                  />
                  <View style={styles.switchRow}>
                    <View style={styles.switchText}>
                      <Text style={styles.switchLabel}>已经蜕完了</Text>
                      <Hint>还没蜕完就关着，之后再点「标记蜕完」</Hint>
                    </View>
                    <Toggle value={completed} onValueChange={setCompleted} />
                  </View>
                  <Field
                    label="备注（可不填）"
                    placeholder="比如：这次蜕得很干净"
                    value={notes}
                    onChangeText={setNotes}
                    multiline
                  />
                  <PrimaryButton
                    title="保存"
                    onPress={() => void save()}
                    loading={createRecord.isPending}
                  />
                  <TextLink title="取消" onPress={() => setFormOpen(false)} />
                  {errorText ? <Text style={styles.error}>{errorText}</Text> : null}
                </>
              ) : (
                <PrimaryButton title="记一条新的" onPress={() => setFormOpen(true)} />
              )}
            </Group>

            <Group>
              <View style={styles.sectionHead}>
                <Eyebrow>以前的记录</Eyebrow>
                {records.length > 0 ? (
                  <Hint style={styles.count}>{records.length} 条</Hint>
                ) : null}
              </View>

              {recordsQuery.isLoading ? (
                <EmptyState title="加载中…" />
              ) : records.length === 0 ? (
                <EmptyState
                  title="还没有记录"
                  subtitle="守宫蜕皮时点上面那个按钮记一条，以后就能看出规律。"
                />
              ) : (
                <View style={styles.timeline}>
                  {records.map((record, index) => (
                    <View key={record.id} style={styles.recordRow}>
                      <View style={styles.rail}>
                        <View style={[styles.dot, !record.completed_on && styles.dotLive]} />
                        {index < records.length - 1 ? <View style={styles.railLine} /> : null}
                      </View>
                      <View style={styles.recordBody}>
                        <View style={styles.recordHead}>
                          <Hint>{shortDate(record.started_on)}</Hint>
                          <Badge
                            label={recordLabel(record.completed_on)}
                            tone={record.completed_on ? 'neutral' : 'accent'}
                          />
                        </View>
                        {record.completed_on ? (
                          <Hint>蜕完于 {shortDate(record.completed_on)}</Hint>
                        ) : null}
                        {record.notes ? <Note>{record.notes}</Note> : null}
                        <View style={styles.recordActions}>
                          {record.completed_on ? null : (
                            <Pressable
                              onPress={() => void markDone(record)}
                              accessibilityRole="button"
                              style={styles.smallButton}
                            >
                              <Text style={styles.smallButtonText}>标记蜕完</Text>
                            </Pressable>
                          )}
                          <Pressable
                            onPress={() => confirmDelete(record)}
                            accessibilityRole="button"
                            style={styles.smallButtonGhost}
                          >
                            <Text style={styles.smallButtonGhostText}>删除</Text>
                          </Pressable>
                        </View>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </Group>

            <Group>
              <View style={styles.extraRow}>
                <IconButton
                  icon="book-outline"
                  title="养之前先看看"
                  onPress={() => router.push('/knowledge')}
                />
                <IconButton icon="camera-outline" title="萌照相册" onPress={() => router.push('/portraits')} />
              </View>
            </Group>
          </>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: space.xxl,
  },
  alertRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  alertBody: {
    flex: 1,
    gap: space.xxs,
  },
  /** 提醒条是「一行可点的东西」，不是标题：比 heading 小一档，靠 600 字重站住 */
  alertTitle: {
    ...type.body,
    fontWeight: '600',
    color: colors.foreground,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  switchText: {
    flex: 1,
    gap: space.xxs,
  },
  switchLabel: {
    ...type.body,
    fontWeight: '600',
    color: colors.foreground,
  },
  error: {
    ...type.note,
    color: colors.destructive,
  },
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  count: {
    color: colors.ghostForeground,
  },
  timeline: {
    gap: space.tight,
  },
  recordRow: {
    flexDirection: 'row',
    gap: space.md,
  },
  rail: {
    width: 10,
    alignItems: 'center',
    // 圆点的中心对准日期那一行（Hint 18 高）的中心
    paddingTop: space.sm + 2,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: radius.xs,
    backgroundColor: colors.ghostForeground,
  },
  dotLive: {
    backgroundColor: colors.accent,
  },
  railLine: {
    flex: 1,
    width: hairline,
    backgroundColor: colors.divider,
    marginTop: space.sm,
  },
  recordBody: {
    flex: 1,
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
    gap: space.xs,
    paddingBottom: space.xs,
  },
  recordHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  recordActions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.sm,
  },
  smallButton: {
    paddingHorizontal: space.md,
    minHeight: 36,
    justifyContent: 'center',
    borderRadius: radius.pill,
    backgroundColor: colors.foreground,
  },
  smallButtonText: {
    ...type.caption,
    fontWeight: '700',
    color: colors.onPrimary,
  },
  smallButtonGhost: {
    paddingHorizontal: space.md,
    minHeight: 36,
    justifyContent: 'center',
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
  },
  smallButtonGhostText: {
    ...type.caption,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
  extraRow: {
    flexDirection: 'row',
    gap: space.sm,
  },
});
