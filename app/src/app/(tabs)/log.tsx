/**
 * 蜕皮记录：最上面一条提醒，下面是「什么时候开始、什么时候蜕完」的时间线。
 * 文案全部口语化，不出现内部状态名。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import {
  Card,
  EmptyState,
  Field,
  PageHeader,
  PrimaryButton,
  Screen,
  SecondaryButton,
  SectionTitle,
} from '@/components/ui';
import { useAlerts } from '@/hooks/useAlerts';
import { usePets } from '@/hooks/usePets';
import {
  useCreateShedRecord,
  useDeleteShedRecord,
  useShedRecords,
  useUpdateShedRecord,
} from '@/hooks/useShed';
import { useDeviceId } from '@/lib/deviceId';
import { todayIso } from '@/lib/dates';
import { alertTitle, recordLabel } from '@/lib/resultCopy';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, radius, shadow, space, type } from '@/lib/theme';
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
        <PageHeader title="蜕皮记录" subtitle="每次蜕皮记一条，方便回看" />
        <Card>
          <EmptyState
            icon="cloud-offline-outline"
            title="App 还没连上电脑"
            subtitle="在「我的 → 高级设置」里填入电脑地址。"
          />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <PageHeader
        title="蜕皮记录"
        subtitle={pet ? `记录 ${pet.name} 的每一次蜕皮` : '每次蜕皮记一条'}
      />

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
                confidence:
                  latestAlert.confidence !== null ? String(latestAlert.confidence) : '',
              },
            })
          }
          accessibilityRole="button"
          style={({ pressed }) => [styles.alertCard, pressed && clayPress]}
        >
          <View style={styles.alertIcon}>
            <Ionicons name="notifications" size={20} color={colors.primaryDark} />
          </View>
          <View style={styles.alertBody}>
            <Text style={styles.alertTitle}>{alertTitle(latestAlert.kind, pet?.name)}</Text>
            <Text style={styles.alertMeta}>{shortDate(latestAlert.local_date)} · 点开看看</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.primaryDark} />
        </Pressable>
      ) : null}

      {petId === '' ? (
        <Card style={{ gap: space.md }}>
          <EmptyState
            icon="paw-outline"
            title="还没有你的守宫"
            subtitle="先建个档案，再来记录蜕皮"
          />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      ) : (
        <>
          {formOpen ? (
            <Card style={{ gap: space.lg }}>
              <Text style={styles.formTitle}>记一次蜕皮</Text>
              <Field
                label="哪天开始蜕的"
                placeholder="2026-11-12"
                value={startedOn}
                onChangeText={setStartedOn}
                autoCapitalize="none"
              />
              <View style={styles.switchRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.switchLabel}>已经蜕完了</Text>
                  <Text style={styles.switchHint}>还没蜕完就关着，之后再点「标记蜕完」</Text>
                </View>
                <Switch
                  value={completed}
                  onValueChange={setCompleted}
                  trackColor={{ true: colors.primary, false: colors.border }}
                  thumbColor="#FFFFFF"
                />
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
              <SecondaryButton title="取消" onPress={() => setFormOpen(false)} />
              {errorText ? <Text style={styles.error}>{errorText}</Text> : null}
            </Card>
          ) : (
            <PrimaryButton title="添加一条记录" onPress={() => setFormOpen(true)} />
          )}

          <SectionTitle>以前的记录</SectionTitle>

          {recordsQuery.isLoading ? (
            <Card>
              <EmptyState icon="hourglass-outline" title="加载中…" />
            </Card>
          ) : records.length === 0 ? (
            <Card>
              <EmptyState
                icon="calendar-outline"
                title="还没有记录"
                subtitle="守宫蜕皮时点上面那个按钮记一条，以后就能看出规律。"
              />
            </Card>
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
                      <Text style={styles.recordDate}>{shortDate(record.started_on)}</Text>
                      <View
                        style={[
                          styles.statePill,
                          record.completed_on ? styles.statePillDone : styles.statePillLive,
                        ]}
                      >
                        <Text
                          style={[
                            styles.statePillText,
                            record.completed_on
                              ? styles.statePillTextDone
                              : styles.statePillTextLive,
                          ]}
                        >
                          {recordLabel(record.completed_on)}
                        </Text>
                      </View>
                    </View>
                    {record.completed_on ? (
                      <Text style={styles.recordState}>
                        蜕完于 {shortDate(record.completed_on)}
                      </Text>
                    ) : null}
                    {record.notes ? <Text style={styles.recordNotes}>{record.notes}</Text> : null}
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
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  alertCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: colors.primarySoft,
    borderRadius: radius.lg,
    padding: space.md + 2,
  },
  alertIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  alertBody: {
    flex: 1,
    gap: 2,
  },
  alertTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  alertMeta: {
    ...type.caption,
    color: colors.primaryDark,
  },
  formTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  switchLabel: {
    ...type.body,
    fontWeight: '600',
    color: colors.foreground,
  },
  switchHint: {
    ...type.caption,
    color: colors.mutedForeground,
    marginTop: 2,
  },
  error: {
    ...type.caption,
    color: colors.destructive,
  },
  timeline: {
    gap: 0,
  },
  recordRow: {
    flexDirection: 'row',
    gap: space.md,
  },
  rail: {
    width: 12,
    alignItems: 'center',
    paddingTop: space.lg,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
  },
  dotLive: {
    backgroundColor: colors.primary,
  },
  railLine: {
    flex: 1,
    width: hairline,
    backgroundColor: colors.border,
    marginTop: space.xs,
  },
  recordBody: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: hairline,
    borderColor: colors.border,
    padding: space.lg,
    gap: space.xs,
    marginBottom: space.md,
    ...shadow.card,
  },
  recordHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  recordDate: {
    ...type.heading,
    color: colors.foreground,
  },
  statePill: {
    borderRadius: radius.pill,
    paddingHorizontal: space.sm + 2,
    paddingVertical: 3,
  },
  statePillDone: {
    backgroundColor: colors.muted,
  },
  statePillLive: {
    backgroundColor: colors.primarySoft,
  },
  statePillText: {
    ...type.caption,
    fontSize: 12,
    fontWeight: '700',
  },
  statePillTextDone: {
    color: colors.mutedForeground,
  },
  statePillTextLive: {
    color: colors.primaryDark,
  },
  recordState: {
    ...type.caption,
    color: colors.mutedForeground,
  },
  recordNotes: {
    ...type.bodySm,
    color: colors.body,
    marginTop: 2,
  },
  recordActions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.sm,
  },
  smallButton: {
    paddingHorizontal: space.md,
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  smallButtonText: {
    ...type.caption,
    fontWeight: '700',
    color: colors.primaryDark,
  },
  smallButtonGhost: {
    paddingHorizontal: space.md,
    minHeight: 40,
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
});
