/**
 * 蜕皮记录：最上面一条提醒，下面是"什么时候开始、什么时候蜕完"的时间线。
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
import { colors, radius } from '@/lib/theme';
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
            icon="cloud-offline"
            title="App 还没连上电脑"
            subtitle="在「我的 → 高级设置」里填入电脑地址。"
          />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <PageHeader title="蜕皮记录" subtitle={pet ? `记录 ${pet.name} 的每一次蜕皮` : '每次蜕皮记一条'} />

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
          style={({ pressed }) => [styles.alertCard, pressed && styles.pressed]}
        >
          <View style={styles.alertIcon}>
            <Ionicons name="notifications" size={22} color={colors.primaryDark} />
          </View>
          <View style={styles.alertBody}>
            <Text style={styles.alertTitle}>{alertTitle(latestAlert.kind, pet?.name)}</Text>
            <Text style={styles.alertMeta}>
              {shortDate(latestAlert.local_date)} · 点开看看
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.mutedForeground} />
        </Pressable>
      ) : null}

      {petId === '' ? (
        <Card style={{ gap: 12 }}>
          <EmptyState icon="paw" title="还没有你的守宫" subtitle="先建个档案，再来记录蜕皮" />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      ) : (
        <>
          {formOpen ? (
            <Card style={{ gap: 14 }}>
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
              <EmptyState icon="hourglass" title="加载中…" />
            </Card>
          ) : records.length === 0 ? (
            <Card>
              <EmptyState
                icon="calendar"
                title="还没有记录"
                subtitle="守宫蜕皮时点上面那个按钮记一条，以后就能看出规律。"
              />
            </Card>
          ) : (
            <View style={styles.timeline}>
              {records.map((record) => (
                <View key={record.id} style={styles.recordRow}>
                  <View style={styles.timelineDot} />
                  <View style={styles.recordBody}>
                    <Text style={styles.recordDate}>{shortDate(record.started_on)}</Text>
                    <Text style={styles.recordState}>
                      {record.completed_on
                        ? `${recordLabel(record.completed_on)} · ${shortDate(record.completed_on)}`
                        : recordLabel(null)}
                    </Text>
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
    gap: 12,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 3,
    borderColor: colors.primary,
    padding: 14,
  },
  pressed: {
    opacity: 0.85,
  },
  alertIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  alertBody: {
    flex: 1,
    gap: 3,
  },
  alertTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.foreground,
  },
  alertMeta: {
    fontSize: 13,
    color: colors.mutedForeground,
  },
  formTitle: {
    fontSize: 17,
    fontWeight: '800',
    color: colors.foreground,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  switchLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.foreground,
  },
  switchHint: {
    fontSize: 12,
    color: colors.mutedForeground,
    marginTop: 2,
  },
  error: {
    fontSize: 14,
    color: colors.destructive,
  },
  timeline: {
    gap: 4,
  },
  recordRow: {
    flexDirection: 'row',
    gap: 12,
  },
  timelineDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.primary,
    marginTop: 6,
  },
  recordBody: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    padding: 14,
    gap: 4,
    marginBottom: 10,
  },
  recordDate: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.foreground,
  },
  recordState: {
    fontSize: 14,
    color: colors.mutedForeground,
  },
  recordNotes: {
    fontSize: 14,
    color: colors.foreground,
    lineHeight: 20,
  },
  recordActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 6,
  },
  smallButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  smallButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  smallButtonGhost: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
  },
  smallButtonGhostText: {
    color: colors.mutedForeground,
    fontSize: 13,
    fontWeight: '700',
  },
});
